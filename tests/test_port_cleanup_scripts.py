import subprocess
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
PORT_UTILS_PATH = ROOT_DIR / "scripts" / "port-utils.ps1"


class PortCleanupScriptTests(unittest.TestCase):
    def run_powershell(self, script: str) -> str:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT_DIR,
        )
        return completed.stdout.strip()

    def test_blocking_port_connections_ignore_timewait_with_pid_zero(self):
        script = f"""
$path = '{PORT_UTILS_PATH}'
if (-not (Test-Path $path)) {{
  Write-Output 'MISSING'
  exit 0
}}
. $path
$connections = @(
  [pscustomobject]@{{ LocalAddress = '127.0.0.1'; LocalPort = 5173; State = 'TimeWait'; OwningProcess = 0 }},
  [pscustomobject]@{{ LocalAddress = '127.0.0.1'; LocalPort = 5173; State = 'TimeWait'; OwningProcess = 0 }}
)
$result = @(Get-BlockingPortConnections -Connections $connections)
Write-Output $result.Count
"""

        output = self.run_powershell(script)

        self.assertEqual(output, "0")

    def test_blocking_port_connections_keep_real_listener_process(self):
        script = f"""
$path = '{PORT_UTILS_PATH}'
if (-not (Test-Path $path)) {{
  Write-Output 'MISSING'
  exit 0
}}
. $path
$connections = @(
  [pscustomobject]@{{ LocalAddress = '127.0.0.1'; LocalPort = 5173; State = 'Listen'; OwningProcess = 39208 }},
  [pscustomobject]@{{ LocalAddress = '127.0.0.1'; LocalPort = 5173; State = 'Established'; OwningProcess = 39208 }}
)
$result = @(Get-BlockingPortConnections -Connections $connections)
Write-Output $result[0].OwningProcess
"""

        output = self.run_powershell(script)

        self.assertEqual(output, "39208")


if __name__ == "__main__":
    unittest.main()
