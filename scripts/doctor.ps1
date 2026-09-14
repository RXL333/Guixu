$ErrorActionPreference = 'Continue'
$projectRoot = Split-Path -Parent $PSScriptRoot
Write-Output "Guixu developer environment"
python --version
node --version
npm --version
uv --version
if ($IsWindows) { Write-Output 'Windows: yes' } else { Write-Output 'Windows: no' }
Write-Output "64-bit OS: $([Environment]::Is64BitOperatingSystem)"
Write-Output "Inno Setup: $((Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source)"
$diagnosticRoot = Join-Path $projectRoot 'artifacts\test-workspaces\doctor'
New-Item -ItemType Directory -Force -Path $diagnosticRoot | Out-Null
$env:GUIXU_DIAGNOSTIC_DATA_DIR = $diagnosticRoot
try {
  uv --directory (Join-Path $projectRoot 'backend') run python -m guixu --diagnose
} finally {
  Remove-Item Env:GUIXU_DIAGNOSTIC_DATA_DIR -ErrorAction SilentlyContinue
}
