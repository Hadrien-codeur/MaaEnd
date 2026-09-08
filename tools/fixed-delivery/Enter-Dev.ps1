# Dot-source this file in each development terminal.
$fixedDeliveryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$fixedDeliveryCache = Join-Path $fixedDeliveryRoot '.cache'
$env:UV_CACHE_DIR = Join-Path $fixedDeliveryCache 'uv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $fixedDeliveryCache 'python'
$env:GOCACHE = Join-Path $fixedDeliveryCache 'go-build'
$env:GOMODCACHE = Join-Path $fixedDeliveryCache 'go-mod'
$env:GOPATH = Join-Path $fixedDeliveryCache 'go'
$env:npm_config_cache = Join-Path $fixedDeliveryCache 'npm'
$env:TEMP = Join-Path $fixedDeliveryCache 'tmp'
$env:TMP = $env:TEMP
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null

$fixedDeliveryToolPaths = @(
    (Join-Path $fixedDeliveryCache 'tools\uv'),
    (Join-Path $fixedDeliveryCache 'BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin'),
    (Join-Path $fixedDeliveryCache 'BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja')
)
foreach ($fixedDeliveryToolPath in $fixedDeliveryToolPaths) {
    if ((Test-Path -LiteralPath $fixedDeliveryToolPath) -and ($env:PATH -split ';' -notcontains $fixedDeliveryToolPath)) {
        $env:PATH = $fixedDeliveryToolPath + ';' + $env:PATH
    }
}
Write-Host "Development root: $fixedDeliveryRoot"
