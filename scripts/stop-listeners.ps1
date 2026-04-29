param(
  [int[]]$Ports
)

. (Join-Path $PSScriptRoot "port-utils.ps1")

function Get-PortProcessIds {
  param(
    [int]$Port
  )

  @(Get-BlockingPortProcessIds -Port $Port)
}

foreach ($port in $Ports) {
  $processIds = @(Get-PortProcessIds -Port $port)

  foreach ($processId in $processIds) {
    Write-Host "Stopping process $processId listening on port $port..."
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
  }

  for ($attempt = 0; $attempt -lt 20; $attempt++) {
    $remaining = @(Get-PortProcessIds -Port $port)
    if ($remaining.Count -eq 0) {
      break
    }

    foreach ($processId in $remaining) {
      Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 250
  }
}
