param([int]$IntervalSeconds = 10)

$ErrorActionPreference = 'SilentlyContinue'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$keywords = 'download|install|setup|uv|pip|pnpm|npm|git|curl|wget|Maa|MXU|Framework'
$previous = @{}
$previousNetwork = $null
$previousTime = Get-Date
$totals = @{}

while ($true) {
    Clear-Host
    Write-Host "GPT下载监视器" -ForegroundColor Cyan
    Write-Host "刷新间隔: ${IntervalSeconds}s    $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    Write-Host "按 Ctrl+C 退出`n"

    $now = Get-Date
    $elapsed = ($now - $previousTime).TotalSeconds
    $procs = Get-CimInstance Win32_Process |
        Where-Object { $_.CommandLine -match $keywords -or $_.Name -match $keywords } |
        Select-Object ProcessId, Name, CommandLine
    Write-Host "下载任务:" -ForegroundColor Yellow
    if ($procs) {
        $procs | Format-Table ProcessId, Name, @{N='命令'; E={
            $line = $_.CommandLine
            if ($line.Length -gt 110) { $line.Substring(0, 107) + '...' } else { $line }
        }} -AutoSize
    } else { Write-Host '未发现匹配的下载/安装进程。' -ForegroundColor DarkGray }

    $network = Get-NetAdapterStatistics | Measure-Object ReceivedBytes, SentBytes -Sum
    if ($previousNetwork -and $elapsed -gt 0) {
        $rx = (($network[0].Sum - $previousNetwork[0]) / 1KB) / $elapsed
        $tx = (($network[1].Sum - $previousNetwork[1]) / 1KB) / $elapsed
        Write-Host ("网速: ↓ {0:N1} KB/s   ↑ {1:N1} KB/s" -f $rx, $tx) -ForegroundColor Green
    } else { Write-Host '网速: 正在采样...' -ForegroundColor DarkGray }
    $previousNetwork = @($network[0].Sum, $network[1].Sum)

    $connections = Get-NetTCPConnection -State Established |
        Where-Object { $_.RemoteAddress -notin @('127.0.0.1','::1') } |
        Group-Object OwningProcess |
        ForEach-Object {
            $p = Get-Process -Id $_.Name -ErrorAction SilentlyContinue
            [pscustomobject]@{ PID=$_.Name; Process=if ($p) {$p.ProcessName} else {'已退出'}; Connections=$_.Count }
        }
    Write-Host "`n活动网络连接:" -ForegroundColor Yellow
    if ($connections) { $connections | Sort-Object Connections -Descending | Format-Table -AutoSize }
    else { Write-Host '没有活动的外部 TCP 连接。' -ForegroundColor Red }

    $files = Get-ChildItem -LiteralPath (Join-Path $root '.cache') -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in @('.zip', '.xz', '.part', '.tmp', '.nupkg') } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 12
    Write-Host "文件进度（总大小未知时显示已下载量与速度）:" -ForegroundColor Yellow
    if ($files) {
        $rows = foreach ($file in $files) {
            $key=$file.FullName; $speed=$null; $eta='--'; $progress='总大小未知'
            try {
                $stream=[IO.File]::Open($key, 'Open', 'Read', 'ReadWrite')
                try { $length=$stream.Length } finally { $stream.Dispose() }
            } catch { continue }
            if ($previous.ContainsKey($key) -and $elapsed -gt 0) { $speed=[math]::Max(0, ($length-$previous[$key])/$elapsed) }
            $previous[$key]=$length
            if (-not $totals.ContainsKey($key)) {
                $totals[$key]=0
                if ($file.Name -match '^(MAA|MXU)-.*-(v[0-9.]+)\.zip$') {
                    $repo=if ($Matches[1] -eq 'MAA') {'MaaXYZ/MaaFramework'} else {'MistEO/MXU'}
                    try {
                        $release=Invoke-RestMethod "https://api.github.com/repos/$repo/releases/tags/$($Matches[2])" -TimeoutSec 10 -ErrorAction Stop
                        $asset=$release.assets | Where-Object name -eq $file.Name | Select-Object -First 1
                        if ($asset) { $totals[$key]=[long]$asset.size }
                    } catch { }
                }
            }
            $total=$totals[$key]
            if ($total -gt 0) {
                $progress=('{0:N1}%' -f (100*$length/$total))
                if ($length -ge $total) { $eta='已下载' }
                elseif ($speed -gt 0) { $eta=[TimeSpan]::FromSeconds(($total-$length)/$speed).ToString('hh\:mm\:ss') }
                elseif ($null -ne $speed) { $eta='等待数据' }
            }
            $speedText=if ($null -eq $speed) {'采样中'} else {('{0:N1} KB/s' -f ($speed/1KB))}
            [pscustomobject]@{ 文件=$file.Name; 已下载=('{0:N2} MB' -f ($length/1MB)); 总大小=if ($total) {('{0:N2} MB' -f ($total/1MB))} else {'未知'}; 速度=$speedText; 进度=$progress; 预计剩余=$eta }
        }
        $rows | Format-Table -AutoSize
    } else { Write-Host '暂无最近变化的下载文件。' -ForegroundColor DarkGray }
    $previousTime=$now
    Start-Sleep -Seconds $IntervalSeconds
}
