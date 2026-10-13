$ErrorActionPreference = 'Continue'
$py      = 'python'
$checker = 'lab/module2-git\scripts\check_tests_touched.py'
$bashHook= 'lab/module2-git\hooks\pre-commit'
$base    = 'lab/_tmp_matrix'
if (Test-Path $base) { Remove-Item -Recurse -Force $base }

function New-Case([string]$name) {
  $d = Join-Path $base $name
  New-Item -ItemType Directory -Force -Path $d | Out-Null
  Push-Location $d
  git init -q 2>&1 | Out-Null
  git config user.name t
  git config user.email t@t
  New-Item -ItemType Directory -Force -Path src | Out-Null
  Set-Content -Path src\app.py -Value 'print(1)' -Encoding utf8
  git add src\app.py
  return $d
}

function Run-Case([string]$name) {
  $d = New-Case $name
  $log = Join-Path $base ($name + '.log')
  cmd /c "git commit -m case > `"$log`" 2>&1"
  $code = $LASTEXITCODE
  git rev-parse --verify --quiet HEAD > $null 2>&1
  $hasHead = ($LASTEXITCODE -eq 0)
  Pop-Location
  Write-Output ('[{0}] commit_exit={1}  commit_created={2}' -f $name, $code, $hasHead)
  Get-Content $log | ForEach-Object { '     | ' + $_.TrimEnd() }
  Write-Output ''
}

# --- a: no hook at all -------------------------------------------------
$null = New-Case 'a-no-hook'
Pop-Location
Run-Case 'a-no-hook'

# --- b: the real bash hook + real checker ------------------------------
$a = New-Case 'b-bash-real'
Copy-Item $bashHook (Join-Path $a '.git\hooks\pre-commit') -Force
Copy-Item $checker  (Join-Path $a '.git\hooks\check_tests_touched.py') -Force
Pop-Location
Run-Case 'b-bash-real'

# --- c: minimal sh hook, exit 1 ---------------------------------------
$c = New-Case 'c-bash-tiny'
Set-Content -Path (Join-Path $c '.git\hooks\pre-commit') -Value "#!/bin/sh`necho TINY_HOOK_1 >&2`nexit 1" -Encoding ascii
Pop-Location
Run-Case 'c-bash-tiny'

# --- d: minimal .bat hook, exit 1 --------------------------------------
$d2 = New-Case 'd-bat-tiny'
Set-Content -Path (Join-Path $d2 '.git\hooks\pre-commit.bat') -Value "@echo off`r`necho BAT_HOOK_1 1>&2`r`nexit /b 1" -Encoding ascii
Pop-Location
Run-Case 'd-bat-tiny'

# --- e: minimal .ps1 hook, exit 1 --------------------------------------
$e = New-Case 'e-ps1-tiny'
Set-Content -Path (Join-Path $e '.git\hooks\pre-commit.ps1') -Value "Write-Error 'PS1_HOOK_1'; exit 1" -Encoding ascii
Pop-Location
Run-Case 'e-ps1-tiny'

# --- f: minimal sh hook, exit 0 ---------------------------------------
$f = New-Case 'f-bash-exit0'
Set-Content -Path (Join-Path $f '.git\hooks\pre-commit') -Value "#!/bin/sh`necho TINY_HOOK_0 >&2`nexit 0" -Encoding ascii
Pop-Location
Run-Case 'f-bash-exit0'
