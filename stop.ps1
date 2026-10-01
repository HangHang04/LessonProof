$ErrorActionPreference = 'Stop'
$taskRecordPath = Join-Path $PSScriptRoot 'work/app-process.json'
if (-not (Test-Path -LiteralPath $taskRecordPath)) { throw '没有找到本项目的启动记录。请在启动工作台的终端中使用 Ctrl+C 结束。' }
$taskRecord = Get-Content -LiteralPath $taskRecordPath -Raw | ConvertFrom-Json
if ($taskRecord.workspace -ne $PSScriptRoot) { throw '启动记录不属于这个工作区。' }
$taskProcess = Get-Process -Id $taskRecord.pid -ErrorAction SilentlyContinue
if (-not $taskProcess) { Write-Host '工作台已经停止。'; exit 0 }
if ($taskProcess.Path -ne $taskRecord.executable -or $taskProcess.StartTime.ToUniversalTime().Ticks -ne ([datetime]$taskRecord.started_at).ToUniversalTime().Ticks) {
    throw '启动记录与当前进程不一致，未执行停止操作。'
}
Stop-Process -Id $taskProcess.Id
Write-Host '本项目工作台已停止。课程副本、运行证据和交付文件均已保留。'
