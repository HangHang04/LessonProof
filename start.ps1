param([switch]$NoBrowser, [string]$OllamaPath = '')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskWork = Join-Path $PSScriptRoot 'work'
New-Item -ItemType Directory -Path $taskWork -Force | Out-Null

function Test-LessonProof {
    try {
        $taskPage = Invoke-WebRequest -Uri 'http://127.0.0.1:8765' -TimeoutSec 2
        return $taskPage.Content.Contains('lessonproof-token')
    } catch { return $false }
}

try {
    $taskModels = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2
} catch {
    if (-not $OllamaPath) {
        $taskOllamaCommand = Get-Command 'ollama.exe' -ErrorAction SilentlyContinue
        if ($taskOllamaCommand) { $OllamaPath = $taskOllamaCommand.Source }
        else {
            foreach ($taskCandidate in @((Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'), 'E:\AI\ollama\ollama.exe')) {
                if (Test-Path -LiteralPath $taskCandidate) { $OllamaPath = $taskCandidate; break }
            }
        }
    }
    if (-not $OllamaPath) { throw '找不到 Ollama。请先启动 Ollama，或使用 -OllamaPath 指定程序路径。' }
    $taskPreviousEnv = @{}
    foreach ($taskName in @('OLLAMA_MODELS','OLLAMA_HOST','OLLAMA_NUM_PARALLEL','OLLAMA_CONTEXT_LENGTH')) {
        $taskPreviousEnv[$taskName] = [Environment]::GetEnvironmentVariable($taskName, 'Process')
    }
    try {
        $taskUserModels = [Environment]::GetEnvironmentVariable('OLLAMA_MODELS','User')
        if ($taskUserModels) { $env:OLLAMA_MODELS = $taskUserModels }
        $env:OLLAMA_HOST = '127.0.0.1:11434'
        $env:OLLAMA_NUM_PARALLEL = '1'
        $env:OLLAMA_CONTEXT_LENGTH = '8192'
        $taskModelProcess = Start-Process -FilePath $OllamaPath -ArgumentList @('serve') -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $taskWork 'ollama.stdout.log') -RedirectStandardError (Join-Path $taskWork 'ollama.stderr.log')
        Set-Content -LiteralPath (Join-Path $taskWork 'ollama.pid') -Value $taskModelProcess.Id
    } finally {
        foreach ($taskName in $taskPreviousEnv.Keys) {
            [Environment]::SetEnvironmentVariable($taskName, $taskPreviousEnv[$taskName], 'Process')
        }
    }
    for ($taskAttempt=0; $taskAttempt -lt 15; $taskAttempt++) {
        Start-Sleep -Seconds 1
        try { $taskModels = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2; break } catch {}
    }
}
if (-not $taskModels -or -not ($taskModels.models.name -contains 'qwen3:4b')) {
    throw 'Ollama 中还没有 qwen3:4b。请先准备这个本地模型，再启动工作台。'
}
if (-not (Test-LessonProof)) {
    $taskPython = (Get-Command 'python.exe' -ErrorAction Stop).Source
    $taskProcess = Start-Process -FilePath $taskPython -ArgumentList @('app.py') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $taskWork 'app.stdout.log') -RedirectStandardError (Join-Path $taskWork 'app.stderr.log')
    Set-Content -LiteralPath (Join-Path $taskWork 'app.pid') -Value $taskProcess.Id
    @{pid=$taskProcess.Id; started_at=$taskProcess.StartTime.ToUniversalTime().ToString('o'); executable=$taskPython; workspace=$PSScriptRoot} |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskWork 'app-process.json') -Encoding utf8
    for ($taskAttempt=0; $taskAttempt -lt 15; $taskAttempt++) {
        if (Test-LessonProof) { break }
        if ($taskProcess.HasExited) { throw '工作台启动失败，请查看 work/app.stderr.log。' }
        Start-Sleep -Seconds 1
    }
    if (-not (Test-LessonProof)) { throw '工作台尚未响应，请查看 work/app.stderr.log。' }
}
Write-Host 'LessonProof 已就绪：http://127.0.0.1:8765'
if (-not $NoBrowser) { Start-Process -FilePath 'http://127.0.0.1:8765' }
