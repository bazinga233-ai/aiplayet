$root = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $root
. (Join-Path $repoRoot "scripts\port-utils.ps1")

powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts\stop-listeners.ps1") -Ports 5173

for ($attempt = 0; $attempt -lt 20; $attempt++) {
  if (-not (Test-PortHasBlockingConnections -Port 5173)) {
    break
  }
  Start-Sleep -Milliseconds 250
}

$stillInUse = @(Get-PortUsageReport -Port 5173)
if ($stillInUse.Count -gt 0) {
  Write-Host "Port 5173 is still in use after cleanup."
  $stillInUse | Select-Object LocalAddress, LocalPort, State, OwningProcess | Format-Table -AutoSize
  exit 1
}

$vitePath = Join-Path $root "node_modules\.bin\vite.cmd"
& $vitePath --host 127.0.0.1 --port 5173 --strictPort
exit $LASTEXITCODE
