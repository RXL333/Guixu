$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
uv --directory (Join-Path $projectRoot 'backend') run python -m guixu
