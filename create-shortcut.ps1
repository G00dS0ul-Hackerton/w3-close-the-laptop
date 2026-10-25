<#
.SYNOPSIS
Creates a Windows Desktop shortcut (.lnk) for SteadyDev.

.DESCRIPTION
Configures a Windows Shell shortcut targeting the verified SteadyDev entrypoint
with proper working directory, icon location, and Unicode/spaces/parentheses resilience.
Only creates shortcut when explicit user confirmation is given or when -Force is passed.

.PARAMETER Force
Skip the confirmation prompt and create the shortcut immediately.

.PARAMETER DestinationDir
Directory where the shortcut (.lnk) will be placed. Defaults to the user's Desktop.
#>

[CmdletBinding()]
param(
    [switch]$Force,
    [string]$DestinationDir = [Environment]::GetFolderPath('Desktop')
)

$ErrorActionPreference = 'Stop'

function Get-ShortPath {
    param([string]$Path)
    try {
        $fso = New-Object -ComObject Scripting.FileSystemObject
        if (Test-Path $Path -PathType Container) {
            return $fso.GetFolder($Path).ShortPath
        } elseif (Test-Path $Path -PathType Leaf) {
            return $fso.GetFile($Path).ShortPath
        } else {
            $parent = Split-Path $Path -Parent
            $leaf = Split-Path $Path -Leaf
            if ($parent -and (Test-Path $parent)) {
                return (Join-Path ($fso.GetFolder($parent).ShortPath) $leaf)
            }
        }
    } catch {
        # Fall back to original path if COM conversion fails
    }
    return $Path
}

# 1. Require explicit user consent unless -Force is specified
if (-not $Force) {
    $prompt = "Do you want to create a SteadyDev shortcut on your Desktop? (y/N): "
    $response = Read-Host -Prompt $prompt.TrimEnd(' ', ':')
    if ($response -notmatch '^(?i:y|yes)$') {
        Write-Host "Shortcut creation cancelled by user."
        exit 0
    }
}

# 2. Determine root directory
$root = $PSScriptRoot
if (-not $root) {
    $root = (Get-Location).Path
}

# 3. Resolve Target Entrypoint
$targetPath = $null
if (Test-Path (Join-Path $root "desktop\desktop.exe")) {
    $targetPath = (Join-Path $root "desktop\desktop.exe")
} elseif (Test-Path (Join-Path $root "desktop\build\windows\x64\runner\Release\desktop.exe")) {
    $targetPath = (Join-Path $root "desktop\build\windows\x64\runner\Release\desktop.exe")
} elseif (Test-Path (Join-Path $root "start-steadydev.bat")) {
    $targetPath = (Join-Path $root "start-steadydev.bat")
} else {
    Write-Error "Neither desktop.exe nor start-steadydev.bat found in $root."
    exit 1
}

# 4. Resolve Icon Location
$iconLocation = $null
if (Test-Path (Join-Path $root "steadydev.ico")) {
    $iconLocation = "$((Get-ShortPath (Join-Path $root 'steadydev.ico'))),0"
} elseif (Test-Path (Join-Path $root "desktop\assets\brand\steadydev.ico")) {
    $iconLocation = "$((Get-ShortPath (Join-Path $root 'desktop\assets\brand\steadydev.ico'))),0"
} elseif (Test-Path (Join-Path $root "..\docs\challenge\w3\SteadyDev-Brand-Kit\steadydev.ico")) {
    $iconLocation = "$((Get-ShortPath (Join-Path $root '..\docs\challenge\w3\SteadyDev-Brand-Kit\steadydev.ico'))),0"
} else {
    $iconLocation = "$((Get-ShortPath $targetPath)),0"
}

# 5. Resolve Destination Directory
if (-not (Test-Path $DestinationDir)) {
    New-Item -ItemType Directory -Path $DestinationDir -Force | Out-Null
}
$shortDest = Get-ShortPath $DestinationDir
$shortcutPath = Join-Path $shortDest "SteadyDev.lnk"

# 6. Create Shortcut via WScript.Shell COM Object
try {
    $wsh = New-Object -ComObject WScript.Shell
    $shortcut = $wsh.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = Get-ShortPath $targetPath
    $shortcut.WorkingDirectory = Get-ShortPath $root
    $shortcut.IconLocation = $iconLocation
    $shortcut.Description = "SteadyDev - Local-First Open-Weight Code Reviewer"
    $shortcut.Save()

    Write-Host "[OK] SteadyDev shortcut created successfully at: $shortcutPath"
    Write-Host "     Target: $targetPath"
    Write-Host "     Working Directory: $root"
    Write-Host "     Icon Location: $iconLocation"
} catch {
    Write-Error "Failed to create shortcut at ${shortcutPath}: $_"
    exit 1
}
