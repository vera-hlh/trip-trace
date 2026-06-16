# TripTrace 开发环境一键启动脚本
# 使用方式：在 PowerShell 中运行 .\scripts\start-dev.ps1

$root = Split-Path $PSScriptRoot -Parent

Write-Host "🚀 启动 TripTrace 开发环境..." -ForegroundColor Cyan

# 停止旧进程
Get-Process -Name python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

# 启动后端
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

# 启动前端
Write-Host "🌐 启动前端 (http://localhost:5173)..." -ForegroundColor Yellow
Write-Host "   测试控制台: http://localhost:5173/test" -ForegroundColor Cyan
Start-Process cmd -ArgumentList "/c", "cd `"$root\frontend`" && npm run dev:renderer" -NoNewWindow

Write-Host ""
Write-Host "✅ 开发环境已启动！" -ForegroundColor Green
Write-Host "   📌 测试控制台: http://localhost:5173/test" -ForegroundColor White
