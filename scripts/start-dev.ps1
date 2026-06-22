# TripTrace 开发环境一键启动脚本
# 使用方式：在 PowerShell 中运行 .\scripts\start-dev.ps1

$root = Split-Path $PSScriptRoot -Parent

Write-Host "🚀 启动 TripTrace 开发环境..." -ForegroundColor Cyan

# ── 停止旧进程 ──────────────────────────────────────────────

# 停止旧的 Python（后端）进程
Get-Process -Name python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

# 停止占用 5173 端口的进程（旧的 Vite/Node 进程）
$port5173 = netstat -ano 2>$null | Select-String "TCP.*:5173\s.*LISTENING" |
    ForEach-Object { ($_.ToString().Trim() -split '\s+')[-1] } |
    Select-Object -First 1
if ($port5173) {
    Stop-Process -Id ([int]$port5173) -Force -ErrorAction SilentlyContinue
    Write-Host "⚠️  已停止端口 5173 的旧进程 (PID: $port5173)" -ForegroundColor Yellow
}

Start-Sleep -Seconds 1

# ── 启动后端 ────────────────────────────────────────────────

Write-Host "⚙️  启动后端 (http://localhost:17890)..." -ForegroundColor Yellow
$py = "$root\backend\.venv\Scripts\python.exe"
Start-Process -FilePath $py -ArgumentList "uvicorn_config.py" -WorkingDirectory "$root\backend" -NoNewWindow

Start-Sleep -Seconds 3

# 验证后端
$health = try { (Invoke-WebRequest -Uri "http://localhost:17890/health" -TimeoutSec 3).StatusCode } catch { "未响应" }
if ($health -eq 200) {
    Write-Host "✅ 后端启动成功" -ForegroundColor Green
} else {
    Write-Host "❌ 后端启动失败，请检查虚拟环境" -ForegroundColor Red
}

# ── 启动前端 ────────────────────────────────────────────────

Write-Host "🌐 启动前端 (http://localhost:5173)..." -ForegroundColor Yellow
Write-Host "   测试控制台: http://localhost:5173/test" -ForegroundColor Cyan

# 在独立 PowerShell 窗口中启动前端（可见错误输出）
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npm run dev:renderer" -WindowStyle Normal

Start-Sleep -Seconds 5

# 验证前端是否启动
$frontendOk = try { (Invoke-WebRequest -Uri "http://localhost:5173" -TimeoutSec 3).StatusCode } catch { "未响应" }
if ($frontendOk -eq 200) {
    Write-Host "✅ 前端启动成功" -ForegroundColor Green
} else {
    Write-Host "⚠️  前端可能还在启动中，请稍等..." -ForegroundColor Yellow
    Write-Host "   如遇错误，请查看新打开的 PowerShell 窗口" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "✅ 开发环境启动完成！" -ForegroundColor Green
Write-Host "   📌 测试控制台: http://localhost:5173/test" -ForegroundColor White
Write-Host "   💡 提示：访问 /test 后，页面固定在测试控制台（Zustand 状态）" -ForegroundColor DarkGray
