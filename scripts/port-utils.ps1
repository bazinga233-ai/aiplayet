function Get-BlockingPortConnections {
  param(
    [object[]]$Connections
  )

  @(
    $Connections |
      Where-Object {
        $_ -and
        $null -ne $_.OwningProcess -and
        [int]$_.OwningProcess -gt 0 -and
        $_.State -notin @("TimeWait", "DeleteTcb")
      }
  )
}

function Get-BlockingPortProcessIds {
  param(
    [int]$Port
  )

  @(
    Get-BlockingPortConnections -Connections @(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue) |
      Select-Object -ExpandProperty OwningProcess -Unique
  )
}

function Test-PortHasBlockingConnections {
  param(
    [int]$Port
  )

  @(Get-BlockingPortConnections -Connections @(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue)).Count -gt 0
}

function Get-PortUsageReport {
  param(
    [int]$Port
  )

  @(
    Get-BlockingPortConnections -Connections @(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue) |
      Select-Object LocalAddress, LocalPort, State, OwningProcess
  )
}
