param(
    [int]$GatewayPort = 8000,
    [int]$DownstreamPort = 8001,
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python executable not found: $Python"
}

$previousDownstreamUrl = $env:TASK2_DOWNSTREAM_URL
$env:TASK2_DOWNSTREAM_URL = "http://127.0.0.1:$DownstreamPort"

$downstream = $null
$gateway = $null
try {
    $downstream = Start-Process -FilePath $Python -ArgumentList @(
        "-m", "uvicorn", "task2.downstream.mock_server:app",
        "--host", "127.0.0.1", "--port", $DownstreamPort
    ) -PassThru -WindowStyle Hidden
    $gateway = Start-Process -FilePath $Python -ArgumentList @(
        "-m", "uvicorn", "task2.gateway.app:app",
        "--host", "127.0.0.1", "--port", $GatewayPort
    ) -PassThru -WindowStyle Hidden

    Write-Host "Gateway: http://127.0.0.1:$GatewayPort"
    Write-Host "Downstream: http://127.0.0.1:$DownstreamPort"
    Write-Host "Press Ctrl+C to stop both services."

    while (-not $gateway.HasExited -and -not $downstream.HasExited) {
        Start-Sleep -Milliseconds 250
        $gateway.Refresh()
        $downstream.Refresh()
    }
} finally {
    foreach ($process in @($gateway, $downstream)) {
        if ($null -ne $process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force
            $process.WaitForExit()
        }
    }
    if ($null -eq $previousDownstreamUrl) {
        Remove-Item Env:TASK2_DOWNSTREAM_URL -ErrorAction SilentlyContinue
    } else {
        $env:TASK2_DOWNSTREAM_URL = $previousDownstreamUrl
    }
}
