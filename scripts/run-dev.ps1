$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:GUIXU_DEV_SESSION = 'guixu-dev-session'
$env:GUIXU_DEV_GRANTS = '1'
$env:VITE_GUIXU_SESSION = 'guixu-dev-session'
$backend = Start-Process -FilePath 'uv' -ArgumentList @('run','python','-m','guixu.web') -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden -PassThru
try {
  npm --prefix (Join-Path $projectRoot 'frontend') run dev
} finally {
  Stop-Process -Id $backend.Id -ErrorAction SilentlyContinue
}

