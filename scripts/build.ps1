param(
    [switch]$OneFile = $false,
    [switch]$Clean = $false,
    [string]$Name = "wolf_app"
)

$ErrorActionPreference = 'Stop'

Write-Host "==> Building $Name (OneFile=$OneFile, Clean=$Clean)" -ForegroundColor Cyan

# Ensure we run from project root (this script resides in scripts/)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir
Set-Location $root

# Check python
try {
    $pyVersion = & python --version 2>$null
    if (-not $pyVersion) { throw "python not found" }
    Write-Host "Python: $pyVersion"
} catch {
    Write-Error "Python is not available on PATH. Please install Python 3.x and try again."
    exit 1
}

# Ensure PyInstaller
try {
    $pi = & python -m pip show pyinstaller 2>$null
    if (-not $pi) {
        Write-Host "Installing PyInstaller..." -ForegroundColor Yellow
        & python -m pip install pyinstaller | Out-Null
    }
} catch {
    Write-Error "Failed to install PyInstaller: $_"
    exit 1
}

# Common args
$commonArgs = @(
    "--name", $Name,
    "--windowed",
    "--hidden-import", "tkinter",
    "--hidden-import", "PIL.Image",
    "--hidden-import", "PIL.ImageTk",
    "--hidden-import", "pygame",
    "--hidden-import", "playsound"
)

# 仅在目录存在时才打包静态资源，避免路径不存在导致失败
if (Test-Path "images") {
    # 打包整个 images 目录（含 images/roles 与 background.*）
    $commonArgs += @("--add-data", "images;images")
}
if (Test-Path "sounds") {
    $commonArgs += @("--add-data", "sounds;sounds")
}

# 入口脚本放在参数末尾
$commonArgs += @("wolf\main.py")

if ($OneFile) { $commonArgs = @("--onefile") + $commonArgs }
if ($Clean) { $commonArgs = @("--clean") + $commonArgs }

# Ensure audio backends are available (pygame preferred, playsound fallback)
try {
    & python -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('pygame') else 1)" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing pygame..." -ForegroundColor Yellow
        & python -m pip install pygame | Out-Null
    }
} catch {
    Write-Warning "Unable to verify/install pygame. If audio is missing in the EXE, install pygame manually."
}
try {
    & python -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('playsound') else 1)" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing playsound (fallback)..." -ForegroundColor Yellow
        & python -m pip install playsound | Out-Null
    }
} catch {
    Write-Host "Skipping playsound installation." -ForegroundColor DarkYellow
}

# Run PyInstaller
Write-Host "Running: python -m PyInstaller $($commonArgs -join ' ')" -ForegroundColor Gray
& python -m PyInstaller @commonArgs
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

# Locate output
$distDir = Join-Path $root "dist"
$targetDir = if ($OneFile) { $distDir } else { Join-Path $distDir $Name }
$exePath = if ($OneFile) { Join-Path $distDir ("{0}.exe" -f $Name) } else { Join-Path $targetDir ("{0}.exe" -f $Name) }

if (Test-Path $exePath) {
    Write-Host "==> Build success: $exePath" -ForegroundColor Green
} else {
    Write-Warning "Build completed but could not find exe at: $exePath"
}
