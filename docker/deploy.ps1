# ============================================
# LOF 基金监控系统 - Docker 生产环境部署脚本 (PowerShell)
# ============================================

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Green
Write-Host "LOF 基金监控系统 - Docker 部署脚本" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green

# 检查 Docker 是否安装
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "错误: Docker 未安装" -ForegroundColor Red
    exit 1
}

# 检查 Docker Compose 是否可用（Docker Desktop 已内置）
try {
    docker compose version | Out-Null
} catch {
    Write-Host "错误: Docker Compose 不可用" -ForegroundColor Red
    exit 1
}

# 切换到脚本所在目录
Set-Location $PSScriptRoot

# 检查环境变量文件
if (-not (Test-Path ".env")) {
    Write-Host "警告: .env 文件不存在" -ForegroundColor Yellow
    Write-Host "正在从模板创建..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "请编辑 .env 文件，修改数据库密码等配置！" -ForegroundColor Red
    exit 1
}

# 函数：显示菜单
function Show-Menu {
    Write-Host ""
    Write-Host "请选择操作："
    Write-Host "1) 拉取最新镜像并启动服务（推荐）"
    Write-Host "2) 仅启动服务（使用本地已有镜像）"
    Write-Host "3) 停止服务"
    Write-Host "4) 重启服务"
    Write-Host "5) 查看日志"
    Write-Host "6) 查看服务状态"
    Write-Host "7) 清理无用资源"
    Write-Host "8) 备份数据库"
    Write-Host "9) 恢复数据库"
    Write-Host "0) 退出"
    Write-Host ""
}

# 函数：拉取镜像并启动
function Build-And-Start {
    Write-Host "拉取最新 Docker 镜像..." -ForegroundColor Green
    docker compose --env-file .env pull
    
    Write-Host "启动服务..." -ForegroundColor Green
    docker compose --env-file .env up -d
    
    Write-Host "等待服务启动..." -ForegroundColor Green
    Start-Sleep -Seconds 10
    
    Write-Host "检查服务状态..." -ForegroundColor Green
    docker compose --env-file .env ps
    
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "部署完成！" -ForegroundColor Green
    Write-Host "访问地址: http://localhost" -ForegroundColor Green
    Write-Host "健康检查: http://localhost/health" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
}

# 函数：仅启动
function Start-Only {
    Write-Host "启动服务..." -ForegroundColor Green
    docker compose --env-file .env up -d
    
    Write-Host "服务已启动" -ForegroundColor Green
    docker compose --env-file .env ps
}

# 函数：停止服务
function Stop-Services {
    Write-Host "停止服务..." -ForegroundColor Yellow
    docker compose --env-file .env down
    
    Write-Host "服务已停止" -ForegroundColor Green
}

# 函数：重启服务
function Restart-Services {
    Write-Host "重启服务..." -ForegroundColor Yellow
    docker compose --env-file .env restart
    
    Write-Host "服务已重启" -ForegroundColor Green
}

# 函数：查看日志
function View-Logs {
    Write-Host "查看日志（按 Ctrl+C 退出）..." -ForegroundColor Green
    docker compose --env-file .env logs -f
}

# 函数：查看状态
function View-Status {
    Write-Host "服务状态：" -ForegroundColor Green
    docker compose --env-file .env ps
    Write-Host ""
    Write-Host "资源使用情况：" -ForegroundColor Green
    try {
        docker stats --no-stream lof-app lof-postgres lof-nginx
    } catch {
        Write-Host "服务未运行" -ForegroundColor Yellow
    }
}

# 函数：清理资源
function Cleanup {
    Write-Host "清理无用的 Docker 资源..." -ForegroundColor Yellow
    docker system prune -f
    docker volume prune -f
    Write-Host "清理完成" -ForegroundColor Green
}

# 函数：备份数据库
function Backup-DB {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupFile = "backup_$timestamp.sql"
    
    Write-Host "备份数据库到: $backupFile" -ForegroundColor Green
    
    # 从 .env 读取配置
    $envContent = Get-Content ".env" | Where-Object { $_ -match '^\s*[^#]' }
    $dbUser = ($envContent | Where-Object { $_ -match '^DB_USER=' }) -replace '^DB_USER=', ''
    $dbName = ($envContent | Where-Object { $_ -match '^DB_NAME=' }) -replace '^DB_NAME=', ''
    
    if (-not $dbUser) { $dbUser = "postgres" }
    if (-not $dbName) { $dbName = "lof_funds" }
    
    docker exec lof-postgres pg_dump -U $dbUser $dbName > $backupFile
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "备份成功: $backupFile" -ForegroundColor Green
    } else {
        Write-Host "备份失败" -ForegroundColor Red
        exit 1
    }
}

# 函数：恢复数据库
function Restore-DB {
    $backupFile = Read-Host "请输入备份文件路径"
    
    if (-not (Test-Path $backupFile)) {
        Write-Host "文件不存在: $backupFile" -ForegroundColor Red
        exit 1
    }
    
    $confirm = Read-Host "警告：此操作将覆盖现有数据！继续吗？(y/N)"
    
    if ($confirm -ne "y" -and $confirm -ne "Y") {
        Write-Host "操作已取消" -ForegroundColor Yellow
        return
    }
    
    Write-Host "恢复数据库..." -ForegroundColor Green
    
    # 从 .env 读取配置
    $envContent = Get-Content ".env" | Where-Object { $_ -match '^\s*[^#]' }
    $dbUser = ($envContent | Where-Object { $_ -match '^DB_USER=' }) -replace '^DB_USER=', ''
    $dbName = ($envContent | Where-Object { $_ -match '^DB_NAME=' }) -replace '^DB_NAME=', ''
    
    if (-not $dbUser) { $dbUser = "postgres" }
    if (-not $dbName) { $dbName = "lof_funds" }
    
    Get-Content $backupFile | docker exec -i lof-postgres psql -U $dbUser $dbName
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "恢复成功" -ForegroundColor Green
    } else {
        Write-Host "恢复失败" -ForegroundColor Red
        exit 1
    }
}

# 主循环
while ($true) {
    Show-Menu
    $choice = Read-Host "请输入选项 [0-9]"
    
    switch ($choice) {
        "1" { Build-And-Start }
        "2" { Start-Only }
        "3" { Stop-Services }
        "4" { Restart-Services }
        "5" { View-Logs }
        "6" { View-Status }
        "7" { Cleanup }
        "8" { Backup-DB }
        "9" { Restore-DB }
        "0" { Write-Host "再见！" -ForegroundColor Green; exit 0 }
        default { Write-Host "无效选项" -ForegroundColor Red }
    }
    
    Write-Host ""
    Read-Host "按回车键继续..."
}
