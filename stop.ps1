# CareerPilot one-command stop: kills whatever listens on the app's ports.
$stopped = 0
foreach ($port in 8000, 3000) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
            $p = Get-Process -Id $_ -ErrorAction SilentlyContinue
            if ($p) {
                Write-Host "stopping $($p.ProcessName) (pid $($p.Id)) on port $port"
                Stop-Process -Id $p.Id -Force
                $script:stopped++
            }
        }
}
# the runner has no port — find it by command line
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "runner\.py" } | ForEach-Object {
        Write-Host "stopping runner (pid $($_.ProcessId))"
        Stop-Process -Id $_.ProcessId -Force
        $script:stopped++
    }

if ($stopped -eq 0) { Write-Host "nothing was running." }
else { Write-Host "done - $stopped process(es) stopped." }
