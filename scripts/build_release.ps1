<#
.SYNOPSIS
Builds the Windows release bundle for Nova Workbench.

.DESCRIPTION
FFmpeg binaries must come from a build-machine directory that contains both
ffmpeg.exe and ffprobe.exe. Provide that directory with -FfmpegDir <absolute-path>
or set the NOVALAI_FFMPEG_DIR environment variable before invoking the script.
Use -PythonExe <absolute-path> or NOVALAI_PYTHON_EXE to pin the interpreter that
runs PyInstaller on machines with multiple Python installations.
#>
[CmdletBinding()]
param(
    [string]$FfmpegDir,
    [string]$PythonExe
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Fail-Build {
    param([string]$Message)

    throw $Message
}

function Resolve-ExistingAbsoluteDirectory {
    param(
        [string]$PathValue,
        [string]$Label
    )

    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        return $null
    }

    if (-not [System.IO.Path]::IsPathRooted($PathValue)) {
        Fail-Build("$Label must be an absolute path. Received: $PathValue")
    }

    try {
        return (Resolve-Path -LiteralPath $PathValue -ErrorAction Stop).Path
    } catch {
        Fail-Build("$Label was not found: $PathValue")
    }
}

function Assert-FileExists {
    param(
        [string]$PathValue,
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $PathValue -PathType Leaf)) {
        Fail-Build("$Label was not found: $PathValue")
    }
}

function Assert-DirectoryExists {
    param(
        [string]$PathValue,
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $PathValue -PathType Container)) {
        Fail-Build("$Label was not found: $PathValue")
    }
}

function Resolve-PythonExecutable {
    param([string]$PathValue)

    if (-not [string]::IsNullOrWhiteSpace($PathValue)) {
        if ([System.IO.Path]::IsPathRooted($PathValue)) {
            try {
                return (Resolve-Path -LiteralPath $PathValue -ErrorAction Stop).Path
            } catch {
                Fail-Build("Python executable was not found: $PathValue")
            }
        }

        try {
            return (Get-Command $PathValue -CommandType Application -ErrorAction Stop).Source
        } catch {
            Fail-Build("Python executable command was not found: $PathValue")
        }
    }

    $pyLauncher = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue
    if ($null -ne $pyLauncher) {
        $resolvedPython = & $pyLauncher.Source -3 -c "import sys; print(sys.executable)"
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($resolvedPython)) {
            return $resolvedPython.Trim()
        }
    }

    try {
        return (Get-Command python.exe -CommandType Application -ErrorAction Stop).Source
    } catch {
        Fail-Build("Python executable was not found. Provide -PythonExe <absolute-path> or set NOVALAI_PYTHON_EXE.")
    }
}

function Remove-IfExists {
    param([string]$PathValue)

    if (Test-Path -LiteralPath $PathValue) {
        Remove-Item -LiteralPath $PathValue -Recurse -Force
    }
}

function Invoke-NativeStep {
    param(
        [scriptblock]$Command,
        [string]$StepName
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        Fail-Build("$StepName failed with exit code $LASTEXITCODE.")
    }
}

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$frontendDir = Join-Path $repoRoot "frontend"
$frontendDistDir = Join-Path $frontendDir "dist"
$packagingDir = Join-Path $repoRoot "packaging"
$ffmpegRuntimeHelper = Join-Path $repoRoot "release_ffmpeg.py"
$releaseDir = Join-Path $repoRoot "novalai-release"
$releaseBrowserProfileDir = Join-Path $releaseDir ".workbench-browser-profile"
$pyinstallerBuildRoot = Join-Path $repoRoot "build"
$pyinstallerDistRoot = Join-Path $repoRoot "dist"
$buildRunId = Get-Date -Format "yyyyMMddHHmmssfff"
$backendBuildDir = Join-Path $pyinstallerBuildRoot ("backend-" + $buildRunId)
$launcherBuildDir = Join-Path $pyinstallerBuildRoot ("launcher-" + $buildRunId)
$backendSpec = Join-Path $packagingDir "backend.spec"
$launcherSpec = Join-Path $packagingDir "launcher.spec"
$backendExe = Join-Path $pyinstallerDistRoot "Backend.exe"
$launcherExeName = [string]::Concat([char]0x542F, [char]0x52A8, ".exe")
$launcherExe = Join-Path $pyinstallerDistRoot $launcherExeName

if ([string]::IsNullOrWhiteSpace($FfmpegDir)) {
    $FfmpegDir = $env:NOVALAI_FFMPEG_DIR
}

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $PythonExe = $env:NOVALAI_PYTHON_EXE
}

if ([string]::IsNullOrWhiteSpace($FfmpegDir)) {
    Fail-Build(
        "FFmpeg binary source directory is required. Provide -FfmpegDir <absolute-path> " +
        "or set NOVALAI_FFMPEG_DIR."
    )
}

$resolvedPythonExe = Resolve-PythonExecutable -PathValue $PythonExe
$resolvedFfmpegDir = Resolve-ExistingAbsoluteDirectory -PathValue $FfmpegDir -Label "FFmpeg binary source directory"
$ffmpegSource = Join-Path $resolvedFfmpegDir "ffmpeg.exe"
$ffprobeSource = Join-Path $resolvedFfmpegDir "ffprobe.exe"

Assert-FileExists -PathValue $resolvedPythonExe -Label "Python executable"
Assert-FileExists -PathValue $ffmpegSource -Label "ffmpeg.exe"
Assert-FileExists -PathValue $ffprobeSource -Label "ffprobe.exe"
Assert-FileExists -PathValue $backendSpec -Label "Backend PyInstaller spec"
Assert-FileExists -PathValue $launcherSpec -Label "Launcher PyInstaller spec"
Assert-FileExists -PathValue $ffmpegRuntimeHelper -Label "FFmpeg runtime helper"

Write-Host "Cleaning prior release output..."
Remove-IfExists -PathValue $releaseDir
Remove-IfExists -PathValue $pyinstallerBuildRoot
Remove-IfExists -PathValue $backendExe
Remove-IfExists -PathValue $launcherExe
Remove-IfExists -PathValue $releaseBrowserProfileDir
Get-ChildItem -LiteralPath $pyinstallerDistRoot -Filter "RCX*.tmp" -ErrorAction SilentlyContinue |
    Remove-Item -Force

Write-Host "Running frontend production build..."
Push-Location $frontendDir
try {
    Invoke-NativeStep -StepName "Frontend production build" -Command { npm.cmd run build }
} finally {
    Pop-Location
}

Assert-FileExists -PathValue (Join-Path $frontendDistDir "index.html") -Label "frontend/dist/index.html"

Write-Host "Checking PyInstaller availability..."
Push-Location $repoRoot
try {
    Invoke-NativeStep -StepName "PyInstaller availability check" -Command { & $resolvedPythonExe -m PyInstaller --version }
} finally {
    Pop-Location
}

Write-Host "Building Backend.exe..."
Push-Location $repoRoot
try {
    Invoke-NativeStep -StepName "Backend.exe build" -Command {
        & $resolvedPythonExe -m PyInstaller --noconfirm --clean --distpath $pyinstallerDistRoot --workpath $backendBuildDir $backendSpec
    }

    Write-Host "Building launcher executable..."
    Invoke-NativeStep -StepName "Launcher executable build" -Command {
        & $resolvedPythonExe -m PyInstaller --noconfirm --clean --distpath $pyinstallerDistRoot --workpath $launcherBuildDir $launcherSpec
    }
} finally {
    Pop-Location
}

Assert-FileExists -PathValue $backendExe -Label "Backend.exe"
Assert-FileExists -PathValue $launcherExe -Label "Launcher executable"

Write-Host "Assembling novalai-release..."
$null = New-Item -ItemType Directory -Path $releaseDir -Force
$null = New-Item -ItemType Directory -Path (Join-Path $releaseDir "frontend_dist") -Force

Copy-Item -LiteralPath $backendExe -Destination (Join-Path $releaseDir "Backend.exe") -Force
Copy-Item -LiteralPath $launcherExe -Destination (Join-Path $releaseDir $launcherExeName) -Force
Invoke-NativeStep -StepName "FFmpeg runtime copy" -Command {
    & $resolvedPythonExe $ffmpegRuntimeHelper copy --source $resolvedFfmpegDir --destination $releaseDir
}

Get-ChildItem -LiteralPath $frontendDistDir -Force | Copy-Item -Destination (Join-Path $releaseDir "frontend_dist") -Recurse -Force

foreach ($directoryName in @("videos", "scripts", "output")) {
    $null = New-Item -ItemType Directory -Path (Join-Path $releaseDir $directoryName) -Force
}

Remove-IfExists -PathValue $releaseBrowserProfileDir
if (Test-Path -LiteralPath $releaseBrowserProfileDir) {
    Fail-Build("Release bundle must not contain transient browser profile data: $releaseBrowserProfileDir")
}

Assert-FileExists -PathValue (Join-Path $releaseDir "Backend.exe") -Label "Release Backend.exe"
Assert-FileExists -PathValue (Join-Path $releaseDir $launcherExeName) -Label "Release launcher executable"
Assert-FileExists -PathValue (Join-Path $releaseDir "ffmpeg.exe") -Label "Release ffmpeg.exe"
Assert-FileExists -PathValue (Join-Path $releaseDir "ffprobe.exe") -Label "Release ffprobe.exe"
Assert-FileExists -PathValue (Join-Path $releaseDir "frontend_dist\\index.html") -Label "Release frontend_dist/index.html"
Assert-DirectoryExists -PathValue (Join-Path $releaseDir "videos") -Label "Release videos directory"
Assert-DirectoryExists -PathValue (Join-Path $releaseDir "scripts") -Label "Release scripts directory"
Assert-DirectoryExists -PathValue (Join-Path $releaseDir "output") -Label "Release output directory"

Write-Host "Validating release FFmpeg runtime..."
Push-Location $releaseDir
try {
    Invoke-NativeStep -StepName "Release ffmpeg validation" -Command {
        & (Join-Path $releaseDir "ffmpeg.exe") -version | Out-Null
    }
    Invoke-NativeStep -StepName "Release ffprobe validation" -Command {
        & (Join-Path $releaseDir "ffprobe.exe") -version | Out-Null
    }
} finally {
    Pop-Location
}

Write-Host "Release package created at $releaseDir"
