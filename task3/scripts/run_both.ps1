param(
    [int]$GatewayPort = 8100,
    [int]$ProviderPort = 8101,
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $Python)) { throw "Python executable not found: $Python" }

$previousProviderUrl = $env:TASK3_PROVIDER_URL
$env:TASK3_PROVIDER_URL = "http://127.0.0.1:$ProviderPort/v1/chat/completions"
$provider = $null
$gateway = $null
try {
    $provider = Start-Process -FilePath $Python -ArgumentList @(
        "-m", "uvicorn", "task3.provider.mock_provider:app",
        "--host", "127.0.0.1", "--port", $ProviderPort
    ) -PassThru -WindowStyle Hidden
    $gateway = Start-Process -FilePath $Python -ArgumentList @(
        "-m", "uvicorn", "task3.gateway.app:app",
        "--host", "127.0.0.1", "--port", $GatewayPort
    ) -PassThru -WindowStyle Hidden
    Write-Host "Gateway: http://127.0.0.1:$GatewayPort"
    Write-Host "Provider: http://127.0.0.1:$ProviderPort"
    Write-Host "Press Ctrl+C to stop both services."
    while (-not $gateway.HasExited -and -not $provider.HasExited) {
        Start-Sleep -Milliseconds 250
        $gateway.Refresh()
        $provider.Refresh()
    }
} finally {
    foreach ($process in @($gateway, $provider)) {
        if ($null -ne $process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force
            $process.WaitForExit()
        }
    }
    if ($null -eq $previousProviderUrl) {
        Remove-Item Env:TASK3_PROVIDER_URL -ErrorAction SilentlyContinue
    } else { $env:TASK3_PROVIDER_URL = $previousProviderUrl }
}
