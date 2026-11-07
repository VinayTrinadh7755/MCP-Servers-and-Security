param(
    [int]$GatewayPort = 8200,
    [int]$ProviderPort = 8201,
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $Python)) { throw "Python executable not found: $Python" }

$oldPrimary = $env:TASK4_PRIMARY_URL
$oldSecondary = $env:TASK4_SECONDARY_URL
$env:TASK4_PRIMARY_URL = "http://127.0.0.1:$ProviderPort/primary/v1/completions"
$env:TASK4_SECONDARY_URL = "http://127.0.0.1:$ProviderPort/secondary/v1/completions"
$provider = $null
$gateway = $null
try {
    $provider = Start-Process -FilePath $Python -ArgumentList @(
        "-m", "uvicorn", "task4.providers.mock_provider:app",
        "--host", "127.0.0.1", "--port", $ProviderPort
    ) -PassThru -WindowStyle Hidden
    $gateway = Start-Process -FilePath $Python -ArgumentList @(
        "-m", "uvicorn", "task4.app:app",
        "--host", "127.0.0.1", "--port", $GatewayPort
    ) -PassThru -WindowStyle Hidden
    Write-Host "Gateway: http://127.0.0.1:$GatewayPort"
    Write-Host "Providers: http://127.0.0.1:$ProviderPort"
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
    if ($null -eq $oldPrimary) { Remove-Item Env:TASK4_PRIMARY_URL -ErrorAction SilentlyContinue } else { $env:TASK4_PRIMARY_URL = $oldPrimary }
    if ($null -eq $oldSecondary) { Remove-Item Env:TASK4_SECONDARY_URL -ErrorAction SilentlyContinue } else { $env:TASK4_SECONDARY_URL = $oldSecondary }
}
