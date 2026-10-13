#requires -version 5.1
<#
================================================================================
 pre-commit (PowerShell flavour)  --  module2-git lab
================================================================================

WHAT THIS IS
  The PowerShell twin of ./pre-commit. It contains **no policy logic**: it
  locates the Python checker, runs it, and forwards its exit code. That
  forwarding is the entire mechanism by which a hook can stop a commit.

HOW TO WIRE IT UP (pick one -- approach A is the one used by this lab)

  A) bash forwarder  (works in git-bash / Git for Windows / WSL / Linux)
     Put this file next to a file named exactly `pre-commit` in the hooks dir,
     and let that `pre-commit` be a 3-line bash script:

         #!/usr/bin/env bash
         exec powershell -NoProfile -ExecutionPolicy Bypass \
              -File "$(dirname "$0")/pre-commit.ps1" "$@"

     Because it uses `dirname "$0"` it works both in `.git/hooks/` and in a
     versioned `hooks/` directory selected with `core.hooksPath`.

  B) core.hooksPath  (keeps hooks in the repo, so they are versioned)
         git config core.hooksPath hooks
     ... plus the same bash forwarder as (A). This is the answer to
     "hooks live in .git/, so a fresh clone has none".

  NOT VIABLE HERE: a hook file whose shebang is `#!/usr/bin/env pwsh`.
     1. `pwsh` (PowerShell 7) is not installed on this machine -- only
        `powershell.exe` (Windows PowerShell 5.1).
     2. git for Windows executes a hook via its shebang; that requires
        /usr/bin/env to run, and in this sandbox every msys binary dies with
        0xC0000142. Bash forwarders + `powershell -File` are the reliable route.

  Also note: git ignores the *.ps1 extension. It runs the file named exactly
  `pre-commit`; a bare `pre-commit` file containing PowerShell source is not a
  thing git can execute (no shebang semantics for CreateProcess). Hence (A).

EXIT CODE CONTRACT (inherited from the checker, see scripts/check_tests_touched.py)
  0 = allow the commit
  1 = policy violation -> git ABORTS the commit
  2 = usage error      -> treated as a failure, so the commit is blocked too
  Any unexpected error in this file also exits 1: hooks fail CLOSED.

STREAM DISCIPLINE
  stdout carries payload only, stderr carries human errors only. This script
  does not merge them: the child inherits this process' stdout/stderr handles,
  so `git commit` shows the ERROR text on stderr and CI can still parse stdout.

BY THE WAY
  `git commit --no-verify` skips every client-side hook. That is by design and
  is demonstrated on purpose by demo_hook.ps1 (scenario 3).

NOTE ON ENCODING
  Windows PowerShell 5.1 decodes a BOM-less .ps1 as ANSI (GBK on this console),
  so this file is deliberately ASCII-only. The Chinese explanation lives in
  ../README.md; the checker keeps its own output ASCII-labeled for the same
  reason.
================================================================================
#>

# Do NOT set $ErrorActionPreference = 'Stop' here: in Windows PowerShell 5.1 a
# native command that writes to stderr turns into a terminating
# NativeCommandError when the error stream is redirected, which would destroy
# the checker's carefully separated output. Check $LASTEXITCODE explicitly.
$ErrorActionPreference = 'Continue'

# ---------------------------------------------------------------------------
# 1. Where are we? A hook must behave the same no matter which subdirectory the
#    developer typed `git commit` in. git sets the cwd to the work tree root for
#    pre-commit, but we do not rely on that.
# ---------------------------------------------------------------------------
$repoRoot = $null
$top = & git.exe rev-parse --show-toplevel 2>$null
if ($LASTEXITCODE -eq 0 -and $top) {
    $repoRoot = ([string]($top | Select-Object -First 1)).Trim()
}
if (-not $repoRoot) {
    [Console]::Error.WriteLine('ERROR: pre-commit: not inside a git work tree (git rev-parse --show-toplevel failed)')
    exit 1
}
try { Set-Location -LiteralPath $repoRoot } catch {
    [Console]::Error.WriteLine("ERROR: pre-commit: cannot cd into repo root: $repoRoot")
    exit 1
}

# ---------------------------------------------------------------------------
# 2. Find the checker.
#    Order: $env:TESTS_TOUCHED_CHECKER (escape hatch for tests), then the hooks
#    directory that git itself reports (works even when .git is a *file*, as in
#    linked worktrees and submodules), then the two layouts used by this lab.
# ---------------------------------------------------------------------------
$checker = $null
$candidates = New-Object System.Collections.Generic.List[string]
if ($env:TESTS_TOUCHED_CHECKER) { $candidates.Add($env:TESTS_TOUCHED_CHECKER) }

$hooksDir = $null
$gitPath = & git.exe rev-parse --git-path hooks 2>$null
if ($LASTEXITCODE -eq 0 -and $gitPath) {
    $hooksDir = ([string]($gitPath | Select-Object -First 1)).Trim()
    if (-not [System.IO.Path]::IsPathRooted($hooksDir)) {
        $hooksDir = Join-Path $repoRoot $hooksDir
    }
    $candidates.Add((Join-Path $hooksDir 'check_tests_touched.py'))
}
$candidates.Add((Join-Path $repoRoot 'scripts\check_tests_touched.py'))
$candidates.Add((Join-Path $repoRoot 'lab\module2-git\scripts\check_tests_touched.py'))

foreach ($c in $candidates) {
    if ($c -and (Test-Path -LiteralPath $c -PathType Leaf)) { $checker = $c; break }
}
if (-not $checker) {
    [Console]::Error.WriteLine('ERROR: pre-commit: cannot find check_tests_touched.py')
    foreach ($c in $candidates) { [Console]::Error.WriteLine("ERROR:   looked at: $c") }
    [Console]::Error.WriteLine('ERROR: fix: set $env:TESTS_TOUCHED_CHECKER to its full path')
    exit 1   # fail closed: a broken hook must not silently allow commits
}

# ---------------------------------------------------------------------------
# 3. Find a real Python 3.
#    `python3` on Windows is usually the Microsoft Store alias stub: `Get-Command`
#    finds it, but running it opens the Store instead of executing Python. It is
#    rejected by path before it is ever executed.
# ---------------------------------------------------------------------------
$python = $null
$probeCode = 'import sys; raise SystemExit(0 if sys.version_info[0] >= 3 else 1)'

$attempts = New-Object System.Collections.Generic.List[object]
if ($env:TESTS_TOUCHED_PYTHON) {
    $attempts.Add([pscustomobject]@{ Exe = $env:TESTS_TOUCHED_PYTHON; Pre = @() })
}
foreach ($name in @('python3', 'python', 'py')) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $cmd) { continue }
    if ($cmd.Source -like '*Microsoft\WindowsApps*') { continue }   # Store stub
    if ($name -eq 'py') {
        $attempts.Add([pscustomobject]@{ Exe = $cmd.Source; Pre = @('-3') })
    } else {
        $attempts.Add([pscustomobject]@{ Exe = $cmd.Source; Pre = @() })
    }
}
foreach ($a in $attempts) {
    $probeArgs = @($a.Pre) + @('-c', $probeCode)
    & $a.Exe @probeArgs 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $python = [pscustomobject]@{ Exe = $a.Exe; Pre = [string[]]$a.Pre }
        break
    }
}
if (-not $python) {
    [Console]::Error.WriteLine('ERROR: pre-commit: no Python 3 interpreter found')
    [Console]::Error.WriteLine('ERROR:   tried: $env:TESTS_TOUCHED_PYTHON, python3, python, py -3')
    [Console]::Error.WriteLine('ERROR: fix: install Python 3 or set $env:TESTS_TOUCHED_PYTHON')
    exit 1   # fail closed
}

# ---------------------------------------------------------------------------
# 4. Run the checker and FORWARD ITS EXIT CODE.
#    No redirection: the child inherits our stdout/stderr, so the checker's
#    stream discipline survives untouched (stdout = payload, stderr = ERROR).
#    `$args` is whatever the caller passed; git passes nothing to pre-commit,
#    but keeping it makes the hook usable by hand:
#        powershell -NoProfile -File .git/hooks/pre-commit.ps1 --all --json
# ---------------------------------------------------------------------------
$checkerArgs = @($python.Pre) + @($checker) + @($args)
& $python.Exe @checkerArgs
$status = $LASTEXITCODE
if ($null -eq $status) { $status = 1 }   # could not even start -> fail closed

if ($status -eq 0) {
    # On success the checker prints NOTHING (that is the discipline). One short
    # line on stderr, only if it was not silenced, is nice feedback for humans.
    if ($env:TESTS_TOUCHED_QUIET -ne '1') {
        [Console]::Error.WriteLine('pre-commit[check-tests-touched]: ok')
    }
}

# Non-zero here == git aborts the commit, and every staged/unstaged change is
# preserved in the work tree. The developer stays in control: `git commit
# --no-verify` skips this hook entirely (the documented escape hatch).
exit $status
