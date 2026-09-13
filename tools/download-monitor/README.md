# GPT下载监视器

在仓库根目录 PowerShell 中运行：

```powershell
.\tools\download-monitor\DownloadMonitor.ps1
```

可用 `-IntervalSeconds 5` 调整刷新间隔。监视器显示匹配的下载/安装进程、外部 TCP 连接，以及 `.cache` 中最近变化的文件；按 `Ctrl+C` 退出。
