<#
================================================================================
 demo_hook.ps1  --  module2-git lab, end-to-end hook demonstration (Windows)
================================================================================

WHAT IT DOES
  Builds a throwaway git repo in %TEMP%, installs the lab's hooks into its
  .git/hooks/, and then runs three scenarios that are asserted, not narrated:

    S1  only src/ is staged             -> the commit MUST FAIL (exit != 0)
    S2  src/ + tests/ are staged        -> the commit MUST SUCCEED (exit == 0)
                                           and prepare-commit-msg must have
                                           rewritten the message (branch trailer)
    S3  git commit --no-verify          -> MUST SUCCEED (the honest demonstration
                                           of the bypass), plus a re-proof that
                                           the very same staged state is blocked
                                           again without the flag
    X   non-ASCII path                  -> proves why the checker uses
                                           `git diff --cached --name-only -z`

  A PASS/FAIL table is printed at the end and the script exits 1 if any
  assertion failed, 0 only if all of them held.

HOW TO RUN
  powershell -NoProfile -ExecutionPolicy Bypass -File demo_hook.ps1
  powershell -NoProfile -ExecutionPolicy Bypass -File demo_hook.ps1 -Shebang bash
  powershell -NoProfile -ExecutionPolicy Bypass -File demo_hook.ps1 -Keep
  powershell -NoProfile -ExecutionPolicy Bypass -File demo_hook.ps1 -PythonPath C:\path\to\python.exe

  -ExecutionPolicy Bypass is needed on this machine: its CurrentUser policy is
  RemoteSigned, and a freshly written .ps1 has no signature, so a plain
  `& demo_hook.ps1` fails with "is not digitally signed".

EXIT CODES (this script)
  0  every assertion held
  1  at least one assertion FAILED -- the demonstration did not prove its point
  2  precondition not met (a lab file is missing, no git, no Python 3, or the
     requested hook flavour cannot be executed on this machine; see below)

WHY -Shebang HAS A MODE AT ALL (a sandbox fact, and a real Windows fact)
  git for Windows runs a hook by parsing the hook file's shebang line and
  spawning the interpreter it names. On a normal machine `#!/usr/bin/env bash`
  works. In THIS sandbox every msys/cygwin binary dies instantly with
  0xC0000142 ("fatal error - couldn't create signal pipe, Win32 error 5"), so
  git cannot spawn a bash hook here at all. Therefore:
      -Shebang python (default)  writes tiny shims whose shebang is the absolute
                                 python.exe path and which run the real checker
                                 through runpy. No logic lives in the shim.
      -Shebang bash              copies hooks/pre-commit and
                                 hooks/prepare-commit-msg verbatim (the real
                                 deliverables), and is what you use on a normal
                                 Windows/macOS/Linux machine.
  Both modes assert exactly the same three behaviours.

HARD-WON NOTES BAKED INTO THIS FILE
  * A PowerShell function named `Git` SHADOWS git.exe (functions win over PATH
    executables), so a helper that calls `& git` inside itself recurses forever
    and looks like a hang. The helper here is named Invoke-Git and always calls
    `git.exe`.
  * `Start-Process -PassThru` + WaitForExit() returns an empty ExitCode for a
    native command in this environment; `& cmd` + $LASTEXITCODE is reliable.
  * `2> file` on a native command does not capture raw stderr in PS 5.1 (it
    stores a decorated ErrorRecord); `& cmd 2>&1 | Out-String` renders clean
    per-record text, which is what the Output fields below rely on.
  * Windows PowerShell 5.1 decodes a BOM-less .ps1 as ANSI (GBK here), so this
    file is deliberately ASCII-only; the Chinese walk-through is ../README.md.
================================================================================
#>

param(
    [ValidateSet('python', 'bash')]
    [string]$Shebang = 'python',
    [string]$PythonPath = '',
    [switch]$Keep
)

$ErrorActionPreference = 'Continue'

$script:Pass = 0
$script:Fail = 0
$script:Rows = New-Object System.Collections.Generic.List[object]
$script:Repo = $null

# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
function Write-Head([string]$Title) {
    Write-Host ''
    Write-Host ('=' * 78) -ForegroundColor DarkGray
    Write-Host $Title -ForegroundColor Cyan
    Write-Host ('=' * 78) -ForegroundColor DarkGray
}

function Write-Note([string]$Text) {
    Write-Host ('  [i] ' + $Text) -ForegroundColor DarkGray
}

function BoolStr($Value) {
    if ($Value) { return 'true' }
    return 'false'
}

function Short([string]$Text, [int]$Max) {
    if ($null -eq $Text) { return '' }
    if ($Text.Length -le $Max) { return $Text }
    if ($Max -le 3) { return $Text.Substring(0, $Max) }
    return $Text.Substring(0, $Max - 3) + '...'
}

function Flatten([string]$Text) {
    if ($null -eq $Text) { return '' }
    return ($Text -replace "`r", ' ' -replace "`n", ' / ').Trim()
}

# NEVER name this function `Git`: see the header comment.
#
# Capturing a native command's two streams in PowerShell 5.1 is full of traps:
#   `& cmd 2>&1 | Out-String`  -> the first stderr line is wrapped in a
#                                 NativeCommandError record and Out-String
#                                 renders the whole "At line:.. CategoryInfo"
#                                 decoration into the text. Garbage.
#   `& cmd 2> file`            -> PS writes a UTF-16LE decorated ErrorRecord
#                                 to the file, not the raw bytes.
#   `& cmd 2>&1 | ForEach-Object { if ($_ -is [ErrorRecord]) { $_.Exception.Message } }`
#                              -> CLEAN raw stderr text (this is what we use).
# So: stderr arrives as ErrorRecord objects and stdout as strings, which lets
# this helper hand out both a merged view (for display) and a stdout-only view
# (for assertions, where merged text would be poison).
function Invoke-Git {
    param([string]$Repo, [string[]]$GitArgs)
    $stdoutLines = New-Object System.Collections.Generic.List[string]
    $mergedLines = New-Object System.Collections.Generic.List[string]
    & git.exe -C $Repo @GitArgs 2>&1 | ForEach-Object {
        if ($_ -is [System.Management.Automation.ErrorRecord]) {
            foreach ($l in ([string]$_.Exception.Message -split "`n")) {
                $mergedLines.Add($l.TrimEnd())
            }
        } else {
            $s = [string]$_
            $stdoutLines.Add($s.TrimEnd())
            $mergedLines.Add($s.TrimEnd())
        }
    }
    return [pscustomobject]@{
        ExitCode = $LASTEXITCODE
        Output   = (Remove-EnvNoise ($mergedLines -join "`n"))
        Stdout   = (($stdoutLines -join "`n").Trim())
    }
}

# This machine only: git tries to read C:\Users\<user>/.config/git/ignore and
# the sandbox denies it, so nearly every command emits
#   warning: unable to access 'C:\Users\.../.config/git/ignore': Permission denied
# That is environment noise with nothing to do with hooks, so the *display*
# drops it. Assertions never read this merged text -- they read exit codes and
# the stdout-only view, which is clean by construction.
function Remove-EnvNoise([string]$Text) {
    if (-not $Text) { return '' }
    $keep = New-Object System.Collections.Generic.List[string]
    foreach ($line in ($Text -split "`n")) {
        if ($line -like '*unable to access*config/git/ignore*') { continue }
        if ($line -like '*config/git/ignore*Permission denied*') { continue }
        $keep.Add($line.TrimEnd())
    }
    return (($keep -join "`n").Trim())
}

function Show-Git {
    param([string]$Label, $Result)
    Write-Host ("  > " + $Label) -ForegroundColor Yellow
    Write-Host ("    exit code: " + $Result.ExitCode) -ForegroundColor DarkYellow
    if ($Result.Output) {
        foreach ($line in ($Result.Output -split "`n")) {
            Write-Host ('    | ' + $line.TrimEnd())
        }
    } else {
        Write-Host '    | <no output>'
    }
}

function Assert-Equal {
    param([string]$Scenario, [string]$Name, [string]$Expected, [string]$Actual)
    $ok = ($Expected -eq $Actual)
    if ($ok) { $script:Pass++ } else { $script:Fail++ }
    $verdict = 'PASS'
    if (-not $ok) { $verdict = 'FAIL' }
    $colour = 'Green'
    if (-not $ok) { $colour = 'Red' }
    Write-Host ("  [{0}] {1}" -f $verdict, $Name) -ForegroundColor $colour
    Write-Host ("        expected: {0}" -f (Flatten $Expected)) -ForegroundColor DarkGray
    Write-Host ("        actual  : {0}" -f (Flatten $Actual)) -ForegroundColor DarkGray
    $script:Rows.Add([pscustomobject]@{
        Scenario = $Scenario
        Assertion = $Name
        Expected = $Expected
        Actual = (Flatten $Actual)
        Verdict = $verdict
    })
}

function Write-Text {
    param([string]$Path, [string]$Text)
    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    [System.IO.File]::WriteAllText($Path, $Text)
}

function Discover-Python {
    param([string]$Explicit)
    $cands = New-Object System.Collections.Generic.List[object]
    if ($Explicit) {
        $cands.Add([pscustomobject]@{ Exe = $Explicit; Pre = @() })
    } else {
        foreach ($name in @('python', 'python3', 'py')) {
            $cmd = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
            if (-not $cmd) { continue }
            # `python3` on Windows is normally the Microsoft Store alias stub:
            # Get-Command finds it, but running it opens the Store.
            if ($cmd.Source -like '*Microsoft\WindowsApps*') { continue }
            if ($name -eq 'py') {
                $cands.Add([pscustomobject]@{ Exe = $cmd.Source; Pre = @('-3') })
            } else {
                $cands.Add([pscustomobject]@{ Exe = $cmd.Source; Pre = @() })
            }
        }
    }
    foreach ($c in $cands) {
        $probeArgs = @($c.Pre) + @('-c', 'import sys; raise SystemExit(0 if sys.version_info[0] >= 3 else 1)')
        & $c.Exe @probeArgs 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { return $c }
    }
    return $null
}

# ===========================================================================
# 0. preconditions
# ===========================================================================
$LabDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Checker = Join-Path $LabDir 'scripts\check_tests_touched.py'
$BashPreCommit = Join-Path $LabDir 'hooks\pre-commit'
$BashPcm = Join-Path $LabDir 'hooks\prepare-commit-msg'

Write-Head 'module2-git / demo_hook.ps1 -- native git hooks, no third-party tools'
Write-Note ("lab directory : " + $LabDir)
Write-Note ("hook flavour  : " + $Shebang)
Write-Note ("PowerShell    : " + $PSVersionTable.PSVersion.ToString())

$missing = @()
foreach ($f in @($Checker, $BashPreCommit, $BashPcm)) {
    if (-not (Test-Path -LiteralPath $f -PathType Leaf)) { $missing += $f }
}
if ($missing.Count -gt 0) {
    foreach ($m in $missing) { Write-Host ("ERROR: missing file: " + $m) -ForegroundColor Red }
    exit 2
}

$gitVersion = (& git.exe --version 2>&1 | Out-String).Trim()
Write-Note ("git           : " + $gitVersion)
if ($LASTEXITCODE -ne 0) {
    Write-Host 'ERROR: git is not available on PATH' -ForegroundColor Red
    exit 2
}

# On this machine every git command also emits a harmless
# `warning: unable to access '.../.config/git/ignore': Permission denied`.
# It is environment noise, not part of the lesson, and it is dropped from the
# displayed output by Remove-EnvNoise (assertions read exit codes and stdout).
$probeWarning = (& git.exe -C $LabDir rev-parse --show-toplevel 2>&1 | Out-String)
if ($probeWarning -like '*config/git/ignore*') {
    Write-Note 'note: this machine also emits a harmless "unable to access .../git/ignore" warning;'
    Write-Note '      it is unrelated to hooks and is filtered out of the quoted output below.'
}

$python = Discover-Python -Explicit $PythonPath
if (-not $python) {
    Write-Host 'ERROR: no Python 3 interpreter found (tried the -PythonPath argument, python, python3, py -3)' -ForegroundColor Red
    exit 2
}
$pyVersion = (& $python.Exe @($python.Pre) @('-c', 'import sys; print(sys.version.split()[0])') 2>&1 | Out-String).Trim()
Write-Note ("python        : " + $python.Exe + ' ' + ($python.Pre -join ' ') + '   (' + $pyVersion + ')')

# Preflight for the bash flavour. git for Windows runs a bash hook by handing the
# shebang to msys: <gitroot>\usr\bin\env.exe -> bash.exe. If this machine cannot
# start env.exe at all (restricted token, EDR policy, sandbox), *every* commit
# fails -- including `--no-verify`, because prepare-commit-msg still runs -- and
# the demo would print a wall of FAILs that looks like a broken lab. Detect it
# and say what is actually wrong.
if ($Shebang -eq 'bash') {
    $msysExe = $null
    $gitCmd = Get-Command git.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($gitCmd) {
        $gitRoot = Split-Path -Parent (Split-Path -Parent $gitCmd.Source)
        foreach ($rel in @('usr\bin\env.exe', 'usr\bin\bash.exe', 'bin\bash.exe')) {
            $candidate = Join-Path $gitRoot $rel
            if (Test-Path -LiteralPath $candidate) { $msysExe = $candidate; break }
        }
    }
    if (-not $msysExe) {
        Write-Host 'ERROR: -Shebang bash needs git''s msys shell, but no env.exe/bash.exe was found next to git.exe.' -ForegroundColor Red
        Write-Host '       Use the default -Shebang python, or run demo_hook.sh from Git Bash.' -ForegroundColor Red
        exit 2
    }
    Write-Note ("msys preflight: " + $msysExe)
    $msysOut = ((& $msysExe --version 2>&1 | ForEach-Object { if ($_ -is [System.Management.Automation.ErrorRecord]) { [string]$_.Exception.Message } else { [string]$_ } }) -join "`n").Trim()
    $msysCode = $LASTEXITCODE
    if ($msysCode -ne 0) {
        Write-Host ''
        Write-Host 'ERROR: this machine cannot run a bash hook, so the bash flavour cannot be demonstrated here.' -ForegroundColor Red
        Write-Host ("       " + $msysExe + " exited " + $msysCode + ":") -ForegroundColor Red
        foreach ($line in ($msysOut -split "`n")) { Write-Host ('       | ' + $line.TrimEnd()) -ForegroundColor Red }
        Write-Host '       Every git commit would then fail for the wrong reason (git cannot spawn the hook),' -ForegroundColor Yellow
        Write-Host '       including `git commit --no-verify`, because prepare-commit-msg still runs.' -ForegroundColor Yellow
        Write-Host '       Re-run with the default -Shebang python, or run demo_hook.sh inside a working Git Bash.' -ForegroundColor Yellow
        exit 2
    }
    Write-Note ("msys ok       : " + $msysOut)
}

# ===========================================================================
# 1. throwaway repository
# ===========================================================================
$Repo = Join-Path $env:TEMP ('module2-git-demo-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
$script:Repo = $Repo

try {
    New-Item -ItemType Directory -Path $Repo -Force | Out-Null
    Write-Note ("temp repo     : " + $Repo)

    # `-b` needs git >= 2.28; fall back to symbolic-ref on anything older.
    $r = Invoke-Git $Repo @('init', '-q', '-b', 'feature/hooked')
    if ($r.ExitCode -ne 0) {
        $null = Invoke-Git $Repo @('init', '-q')
        $null = Invoke-Git $Repo @('symbolic-ref', 'HEAD', 'refs/heads/feature/hooked')
    }

    # Deterministic config: an identity (otherwise commit refuses), no signing,
    # no line-ending rewriting, and an explicit hooks path so a global
    # core.hooksPath setting cannot silently redirect which hooks run.
    $null = Invoke-Git $Repo @('config', 'user.email', 'lab@example.com')
    $null = Invoke-Git $Repo @('config', 'user.name', 'Module2 Lab')
    $null = Invoke-Git $Repo @('config', 'commit.gpgsign', 'false')
    $null = Invoke-Git $Repo @('config', 'core.autocrlf', 'false')
    $null = Invoke-Git $Repo @('config', 'core.hooksPath', (Join-Path $Repo '.git\hooks'))
    Write-Note ("branch        : " + (Invoke-Git $Repo @('symbolic-ref', '--short', 'HEAD')).Stdout)

    Write-Text (Join-Path $Repo 'src\app.py') "def add(a, b):`n    return a + b`n"
    Write-Text (Join-Path $Repo 'tests\test_app.py') "from src.app import add`n`n`ndef test_add():`n    assert add(1, 2) == 3`n"
    Write-Text (Join-Path $Repo '.gitignore') "__pycache__/`n*.pyc`n"
    Write-Note 'fixture       : src/app.py, tests/test_app.py, .gitignore'

    # -----------------------------------------------------------------------
    # 2. install the hooks
    # -----------------------------------------------------------------------
    $hooksDir = Join-Path $Repo '.git\hooks'
    if ($Shebang -eq 'bash') {
        Copy-Item -LiteralPath $BashPreCommit -Destination (Join-Path $hooksDir 'pre-commit') -Force
        Copy-Item -LiteralPath $BashPcm -Destination (Join-Path $hooksDir 'prepare-commit-msg') -Force
        Write-Note 'hooks         : hooks/pre-commit + hooks/prepare-commit-msg copied verbatim (bash)'
        # The bash hook locates the checker relative to the repository
        # (.git/hooks/, scripts/, lab/module2-git/scripts/), and this throwaway
        # repo has none of those paths, so point it at the lab copy through the
        # environment variable the hook honours. git passes its own environment
        # through to hooks, so nothing else is needed.
        $script:SavedCheckerEnv = $env:TESTS_TOUCHED_CHECKER
        $env:TESTS_TOUCHED_CHECKER = $Checker
        Write-Note ('checker env   : TESTS_TOUCHED_CHECKER=' + $Checker)
    } else {
        if ($python.Exe -like '* *') {
            Write-Host ("  [!] the python path contains a space; a git shebang line cannot quote it: " + $python.Exe) -ForegroundColor Yellow
        }
        $pyPosix = $python.Exe.Replace('\', '/')
        # The shim holds no logic: it exists only to give git an executable
        # shebang. Bash cannot be spawned by git in this sandbox (0xC0000142),
        # but a native .exe shebang runs fine -- verified.
        $preCommitShim = @"
#!$pyPosix
# Auto-generated by demo_hook.ps1 -- DO NOT EDIT.
# git for Windows runs a hook through its shebang line. All this file does is
# run the real checker (scripts/check_tests_touched.py) in-process and let its
# exit code propagate, because that exit code is what stops the commit.
import runpy
import sys

CHECKER = r"$Checker"
sys.argv = [CHECKER] + sys.argv[1:]
runpy.run_path(CHECKER, run_name="__main__")
"@
        $pcmShim = @"
#!$pyPosix
# Auto-generated by demo_hook.ps1 -- DO NOT EDIT.
# Python twin of hooks/prepare-commit-msg, used here because git cannot spawn a
# bash hook in this sandbox. Same behaviour: append a branch trailer once.
import subprocess
import sys

msg_path = sys.argv[1]
branch = subprocess.run(
    ['git', 'symbolic-ref', '--short', '-q', 'HEAD'],
    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True,
).stdout.strip()
if not branch:
    branch = 'detached'
with open(msg_path, encoding='utf-8', errors='replace') as fh:
    text = fh.read()
if '[branch ' not in text:
    with open(msg_path, 'a', encoding='utf-8') as fh:
        fh.write('\n[branch %s]\n' % branch)
"@
        Write-Text (Join-Path $hooksDir 'pre-commit') $preCommitShim
        Write-Text (Join-Path $hooksDir 'prepare-commit-msg') $pcmShim
        Write-Note ("hooks         : python shebang shims -> " + $Checker)
    }

    # chmod: NTFS has no POSIX execute bit. git for Windows decides whether a
    # hook is runnable from its shebang / content, not from a mode bit, so this
    # is deliberately informational and NOT an assertion. `git update-index
    # --chmod=+x` is the closest native equivalent and cannot work here: it only
    # touches files tracked by the index, and a .git/hooks file never is.
    $chmod = Invoke-Git $Repo @('update-index', '--chmod=+x', '.git/hooks/pre-commit')
    Write-Host '  [i] chmod/+x on Windows: no POSIX exec bit exists, git for Windows keys off' -ForegroundColor DarkGray
    Write-Host ('  [i]   the shebang. `git update-index --chmod=+x .git/hooks/pre-commit` -> exit ' + $chmod.ExitCode + ': ' + (Flatten $chmod.Output)) -ForegroundColor DarkGray
    Write-Note ("installed hooks: " + ((Get-ChildItem -LiteralPath $hooksDir -File | Where-Object { $_.Name -notlike '*.sample' } | ForEach-Object { $_.Name }) -join ', '))

    # =======================================================================
    # SCENARIO 1 -- src/ staged, no test staged -> commit must be blocked
    # =======================================================================
    Write-Head 'SCENARIO 1 / stage src/ only -> the commit MUST be blocked'

    $null = Invoke-Git $Repo @('reset', '-q')
    Write-Text (Join-Path $Repo 'src\app.py') "def add(a, b):`n    return a + b`n`n`ndef sub(a, b):`n    return a - b`n"
    Show-Git 'git add src/app.py' (Invoke-Git $Repo @('add', 'src/app.py'))

    $r1 = Invoke-Git $Repo @('commit', '-m', 'feat: change src only')
    Show-Git 'git commit -m "feat: change src only"' $r1

    Assert-Equal 'S1' 'the commit is blocked (non-zero exit)' 'true' (BoolStr ($r1.ExitCode -ne 0))
    Assert-Equal 'S1' 'git really refused it (HEAD still unborn)' 'true' (BoolStr ((Invoke-Git $Repo @('rev-parse', '--verify', '-q', 'HEAD')).ExitCode -ne 0))
    Assert-Equal 'S1' 'the staged change survived the abort' 'src/app.py' ((Invoke-Git $Repo @('diff', '--cached', '--name-only')).Stdout)

    # =======================================================================
    # SCENARIO 2 -- src/ + tests/ staged -> commit must succeed
    # =======================================================================
    Write-Head 'SCENARIO 2 / also stage a test -> the commit MUST succeed'

    Show-Git 'git add tests/test_app.py' (Invoke-Git $Repo @('add', 'tests/test_app.py'))
    $r2 = Invoke-Git $Repo @('commit', '-m', 'feat: add app and test')
    Show-Git 'git commit -m "feat: add app and test"' $r2

    Assert-Equal 'S2' 'the commit succeeded (exit 0)' '0' ([string]$r2.ExitCode)
    Assert-Equal 'S2' 'HEAD exists now' 'true' (BoolStr ((Invoke-Git $Repo @('rev-parse', '--verify', '-q', 'HEAD')).ExitCode -eq 0))
    Assert-Equal 'S2' 'exactly one commit landed' '1' ((Invoke-Git $Repo @('rev-list', '--count', 'HEAD')).Stdout)
    $msg2 = (Invoke-Git $Repo @('log', '-1', '--pretty=format:%B')).Stdout
    Assert-Equal 'S2' 'subject is untouched' 'feat: add app and test' ((Invoke-Git $Repo @('log', '-1', '--pretty=format:%s')).Stdout)
    # .Contains, not -like: in a PowerShell wildcard pattern "[...]" is a
    # character SET, so `-like '*[branch feature/hooked]*'` would match almost
    # anything and the assertion would be worthless.
    Assert-Equal 'S2' 'prepare-commit-msg injected the branch' 'true' (BoolStr ($msg2.Contains('[branch feature/hooked]')))

    # =======================================================================
    # SCENARIO 3 -- --no-verify bypasses the gate (honest limitation)
    # =======================================================================
    Write-Head 'SCENARIO 3 / git commit --no-verify -> the gate CAN be skipped'

    $null = Invoke-Git $Repo @('reset', '-q')
    Write-Text (Join-Path $Repo 'src\app.py') "def add(a, b):`n    return a + b`n`n`ndef sub(a, b):`n    return a - b`n`n`ndef mul(a, b):`n    return a * b`n"
    Show-Git 'git add src/app.py' (Invoke-Git $Repo @('add', 'src/app.py'))

    $r3 = Invoke-Git $Repo @('commit', '--no-verify', '-m', 'chore: bypass the hook')
    Show-Git 'git commit --no-verify -m "chore: bypass the hook"' $r3

    Assert-Equal 'S3' 'the bypassed commit succeeded' '0' ([string]$r3.ExitCode)
    Assert-Equal 'S3' 'two commits now exist' '2' ((Invoke-Git $Repo @('rev-list', '--count', 'HEAD')).Stdout)
    Assert-Equal 'S3' 'it landed with no test change at all' 'src/app.py' ((Invoke-Git $Repo @('show', '--name-only', '--pretty=format:', 'HEAD')).Stdout)
    $msg3 = (Invoke-Git $Repo @('log', '-1', '--pretty=format:%B')).Stdout
    Assert-Equal 'S3' '--no-verify does NOT skip prepare-commit-msg' 'true' (BoolStr ($msg3.Contains('[branch ')))

    # Re-proof: the identical staged state is blocked the moment the flag is gone.
    Write-Note 're-proof: undo that commit (keep the index) and commit again without the flag'
    Show-Git 'git reset --soft HEAD~1' (Invoke-Git $Repo @('reset', '--soft', 'HEAD~1'))
    $r3b = Invoke-Git $Repo @('commit', '-m', 'chore: same state, no bypass')
    Show-Git 'git commit -m "chore: same state, no bypass"' $r3b
    Assert-Equal 'S3' 'same state WITHOUT the flag is blocked' 'true' (BoolStr ($r3b.ExitCode -ne 0))
    Assert-Equal 'S3' 'still only one commit (nothing slid through)' '1' ((Invoke-Git $Repo @('rev-list', '--count', 'HEAD')).Stdout)
    Show-Git 'git commit --no-verify (again)' (Invoke-Git $Repo @('commit', '--no-verify', '-m', 'chore: bypass again'))

    # =======================================================================
    # EXTRA -- why -z: git C-quotes non-ASCII paths unless you ask for -z
    # =======================================================================
    Write-Head 'EXTRA / why the checker uses `git diff --cached --name-only -z`'

    # Built from code points on purpose: this .ps1 is ASCII-only, because
    # Windows PowerShell 5.1 decodes a BOM-less .ps1 as ANSI (GBK).
    $cn = ([string][char]0x4E2D) + ([string][char]0x6587)
    $cnRel = 'src/' + $cn + '.py'
    Write-Text (Join-Path $Repo ('src\' + $cn + '.py')) "# non-ASCII filename`n"
    Show-Git ('git add ' + $cnRel) (Invoke-Git $Repo @('add', $cnRel))

    $plain = (Invoke-Git $Repo @('diff', '--cached', '--name-only')).Stdout
    Write-Host '  > git diff --cached --name-only  (default: C-quoted, unreadable)' -ForegroundColor Yellow
    foreach ($line in ($plain -split "`n")) { Write-Host ('    | ' + $line.TrimEnd()) }

    Push-Location $Repo
    $jsonArgs = @($python.Pre) + @($Checker, '--json')
    $jsonOut = (& $python.Exe @jsonArgs 2>$null | Out-String).Trim()
    $jsonCode = $LASTEXITCODE
    Pop-Location
    Write-Host '  > check_tests_touched.py --json  (with -z: raw UTF-8, escaped for the payload)' -ForegroundColor Yellow
    Write-Host ('    | ' + $jsonOut)

    Assert-Equal 'X' 'plain git output is C-quoted (the trap)' 'true' (BoolStr ($plain.Contains('\344')))
    Assert-Equal 'X' 'the checker sees the real path, not the C-quoted one' 'true' (BoolStr ($jsonOut.Contains('src/\u4e2d\u6587.py')))
    Assert-Equal 'X' 'and it still blocks: src staged, no test' '1' ([string]$jsonCode)

    # =======================================================================
    # summary
    # =======================================================================
    Write-Head 'SUMMARY'
    $header = '{0,-4} {1,-40} {2,-14} {3,-30} {4,-7}' -f 'SC', 'ASSERTION', 'EXPECTED', 'ACTUAL', 'RESULT'
    Write-Host $header -ForegroundColor White
    Write-Host ('-' * $header.Length) -ForegroundColor DarkGray
    foreach ($row in $script:Rows) {
        $line = '{0,-4} {1,-40} {2,-14} {3,-30} {4,-7}' -f (Short $row.Scenario 4), (Short $row.Assertion 40), (Short $row.Expected 14), (Short $row.Actual 30), $row.Verdict
        if ($row.Verdict -eq 'PASS') {
            Write-Host $line
        } else {
            Write-Host $line -ForegroundColor Red
        }
    }
    Write-Host ''
    Write-Host ('RESULT: {0} passed, {1} failed  (flavour: {2})' -f $script:Pass, $script:Fail, $Shebang) -ForegroundColor White
    if ($script:Fail -eq 0) {
        Write-Host 'ALL ASSERTIONS PASSED' -ForegroundColor Green
    } else {
        Write-Host 'SOME ASSERTIONS FAILED' -ForegroundColor Red
    }
} finally {
    # Restore the environment exactly as we found it (the bash flavour sets
    # TESTS_TOUCHED_CHECKER for the child hooks; a demo must not leak state).
    if ($Shebang -eq 'bash') { $env:TESTS_TOUCHED_CHECKER = $script:SavedCheckerEnv }
    if ($script:Repo) {
        if ($Keep) {
            Write-Host ('[i] -Keep given, temp repo left in place: ' + $script:Repo) -ForegroundColor DarkGray
        } elseif ($script:Repo -like (Join-Path $env:TEMP 'module2-git-demo-*')) {
            # Guarded delete: only ever remove the throwaway directory we made.
            Set-Location -LiteralPath $env:TEMP
            Remove-Item -Recurse -Force -LiteralPath $script:Repo -ErrorAction SilentlyContinue
            Write-Host ('[i] removed temp repo: ' + $script:Repo) -ForegroundColor DarkGray
        }
    }
}

if ($script:Fail -gt 0) { exit 1 }
exit 0
