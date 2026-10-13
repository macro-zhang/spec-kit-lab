<#
.SYNOPSIS
    Compile tools/hookprobe/HookProbe.cs into hookprobe.exe.

.DESCRIPTION
    The probe is a real PE executable because that is the only kind of file git
    for Windows will run as a hook in this environment: .bat and .ps1 hook files
    are ignored outright, and sh-script hooks need an MSYS shell that cannot
    start here.

    The result is a build artefact. It is not committed; run this script first
    (scripts/probe_win_hook_dispatch.py does it automatically when needed).

.NOTES
    Uses Add-Type, i.e. the C# compiler that ships with PowerShell. No SDK, no
    network, no package manager: the point is that the experiment is
    reproducible on a bare Windows box.
#>
[CmdletBinding()]
param(
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $here 'HookProbe.cs'
if (-not $OutputPath) { $OutputPath = Join-Path $here 'hookprobe.exe' }

if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "probe source not found: $source"
}

if (Test-Path -LiteralPath $OutputPath -PathType Leaf) {
    Remove-Item -LiteralPath $OutputPath -Force
}

Add-Type -TypeDefinition (Get-Content -Raw -LiteralPath $source) `
         -OutputAssembly $OutputPath `
         -OutputType ConsoleApplication

Write-Output "built $OutputPath"
