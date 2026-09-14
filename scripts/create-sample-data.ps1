param([string]$Destination)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Destination) { $Destination = Join-Path $projectRoot 'artifacts/test-workspaces/phase-01-sample' }
$resolvedParent = [IO.Path]::GetFullPath((Split-Path -Parent $Destination))
$allowedRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot 'artifacts/test-workspaces'))
if (-not $resolvedParent.StartsWith($allowedRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Destination must be inside artifacts/test-workspaces' }
New-Item -ItemType Directory -Force -Path (Join-Path $Destination '学习/网络') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Destination '工作') | Out-Null
Set-Content -LiteralPath (Join-Path $Destination '根目录说明.txt') -Value 'Guixu只读扫描样本' -Encoding utf8
Set-Content -LiteralPath (Join-Path $Destination '学习/网络/课程笔记.md') -Value '# 网络课程' -Encoding utf8
[IO.File]::WriteAllBytes((Join-Path $Destination '工作/需求截图.png'), [byte[]](137,80,78,71,13,10,26,10))
Write-Output ([IO.Path]::GetFullPath($Destination))

