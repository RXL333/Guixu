param(
    [switch]$SkipTests,
    [switch]$SkipInstaller
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$releaseRoot = Join-Path $projectRoot 'artifacts\release'
$workRoot = Join-Path $projectRoot 'artifacts\build\pyinstaller'
$backendRoot = Join-Path $projectRoot 'backend'
$frontendRoot = Join-Path $projectRoot 'frontend'

foreach ($target in @($releaseRoot, $workRoot)) {
    $absolute = [IO.Path]::GetFullPath($target)
    if (-not $absolute.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe packaging target: $absolute"
    }
}

if (-not $IsWindows -or -not [Environment]::Is64BitOperatingSystem) {
    throw 'Guixu Windows x64 packages must be built on Windows x64.'
}

New-Item -ItemType Directory -Force -Path $releaseRoot, $workRoot | Out-Null

Push-Location $frontendRoot
try {
    npm.cmd ci
    npm.cmd run build
} finally {
    Pop-Location
}

if (-not $SkipTests) {
    python (Join-Path $projectRoot 'scripts\verify.py') all
}

Push-Location $backendRoot
try {
    uv run pyinstaller --clean --noconfirm `
        --distpath $releaseRoot `
        --workpath $workRoot `
        (Join-Path $projectRoot 'packaging\Guixu.spec')
} finally {
    Pop-Location
}

$appRoot = Join-Path $releaseRoot 'Guixu-0.1.0'
$appExe = Join-Path $appRoot 'Guixu.exe'
if (-not (Test-Path -LiteralPath $appExe -PathType Leaf)) {
    throw "PyInstaller did not produce $appExe"
}

$diagnosticRoot = Join-Path $projectRoot 'artifacts\test-workspaces\phase-09-frozen-diagnostic'
New-Item -ItemType Directory -Force -Path $diagnosticRoot | Out-Null
$env:GUIXU_DIAGNOSTIC_DATA_DIR = $diagnosticRoot
try {
    $diagnosticProcess = Start-Process -FilePath $appExe -ArgumentList @('--diagnose') -Wait -PassThru -WindowStyle Hidden
    if ($diagnosticProcess.ExitCode -ne 0) { throw "Frozen diagnostic failed with exit code $($diagnosticProcess.ExitCode)" }
} finally {
    Remove-Item Env:GUIXU_DIAGNOSTIC_DATA_DIR -ErrorAction SilentlyContinue
}

$workerRoot = Join-Path $projectRoot 'artifacts\test-workspaces\phase-09-frozen-worker'
New-Item -ItemType Directory -Force -Path $workerRoot | Out-Null
$workerRunId = [Guid]::NewGuid().ToString('N')
$workerSource = Join-Path $workerRoot "中文-冻结-worker-$workerRunId.txt"
$workerJob = Join-Path $workerRoot "job-$workerRunId.json"
$workerOutput = Join-Path $workerRoot "result-$workerRunId.json"
[IO.File]::WriteAllText($workerSource, '归序冻结 worker 入口验证', [Text.UTF8Encoding]::new($false))
$job = @{ path=$workerSource; file_id='phase-09-worker'; preset='fast'; artifact_dir=(Join-Path $workerRoot 'cache') } | ConvertTo-Json -Compress
[IO.File]::WriteAllText($workerJob, $job, [Text.UTF8Encoding]::new($false))
$workerProcess = Start-Process -FilePath $appExe -ArgumentList @('--worker', '--job', $workerJob, '--output', $workerOutput) -Wait -PassThru -WindowStyle Hidden
if ($workerProcess.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $workerOutput -PathType Leaf)) {
    throw 'Frozen worker entry failed.'
}

$portable = Join-Path $releaseRoot 'Guixu-portable-x64-0.1.0.zip'
Compress-Archive -Path $appRoot -DestinationPath $portable -CompressionLevel Optimal -Force

if (-not $SkipInstaller) {
    $iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if (-not $iscc) {
        $known = @(
            (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
        ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }
        if ($known) { $iscc = Get-Item $known[0] }
    }
    if ($iscc) {
        & $iscc.FullName (Join-Path $projectRoot 'packaging\Guixu.iss')
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed with exit code $LASTEXITCODE" }
    } else {
        Write-Warning 'Inno Setup 6 not found. The verified onedir and portable zip were built; installer is BLOCKED_EXTERNAL.'
    }
}

Push-Location $backendRoot
try {
    uv run python (Join-Path $projectRoot 'scripts\generate_release_metadata.py')
} finally {
    Pop-Location
}

Write-Output "Verified onedir: $appRoot"
Write-Output "Portable archive: $portable"
