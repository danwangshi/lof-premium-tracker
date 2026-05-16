# Docker 构建和导出脚本 (PowerShell)
# 用法: .\build.ps1 [版本号]

param(
    [string]$Version = "latest"
)

# 配置
$ImageName = "lof-fund-app"
$ImageTag = $Version
$FullImageName = "${ImageName}:${ImageTag}"
$ExportDir = "docker/images"
$ExportFile = "${ExportDir}/${ImageName}-${ImageTag}.tar"

Write-Host "========================================" -ForegroundColor Green
Write-Host "  Docker 构建和导出脚本" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# 检查是否在正确的目录
if (-not (Test-Path "build/Dockerfile")) {
    Write-Host "错误: 请在项目根目录运行此脚本" -ForegroundColor Red
    exit 1
}

# 创建导出目录
Write-Host "[1/4] 创建导出目录..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $ExportDir | Out-Null

# 构建镜像
Write-Host "[2/4] 构建 Docker 镜像..." -ForegroundColor Yellow
Write-Host "镜像名称: $FullImageName"

try {
    # 尝试使用 docker compose 构建
    docker compose -f build/docker-compose.build.yml build
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose build failed"
    }
} catch {
    Write-Host "Docker Compose 构建失败，尝试直接使用 Dockerfile..." -ForegroundColor Yellow
    docker build -f build/Dockerfile -t $FullImageName .
    if ($LASTEXITCODE -ne 0) {
        Write-Host "错误: 镜像构建失败" -ForegroundColor Red
        exit 1
    }
}

Write-Host "✓ 镜像构建成功" -ForegroundColor Green
Write-Host ""

# 导出镜像
Write-Host "[3/4] 导出镜像到 $ExportFile..." -ForegroundColor Yellow
docker save $FullImageName -o $ExportFile

if ($LASTEXITCODE -ne 0) {
    Write-Host "错误: 镜像导出失败" -ForegroundColor Red
    exit 1
}

# 压缩文件
Write-Host "[4/4] 压缩镜像文件..." -ForegroundColor Yellow
$CompressedFile = "${ExportFile}.gz"

# 使用 7-Zip 或 GZip 压缩
if (Get-Command "7z" -ErrorAction SilentlyContinue) {
    # 使用 7-Zip
    7z a -tgzip $CompressedFile $ExportFile
    Remove-Item $ExportFile
} else {
    # 使用 PowerShell 内置压缩（较慢）
    Write-Host "警告: 未找到 7-Zip，使用 PowerShell 内置压缩（较慢）" -ForegroundColor Yellow
    $inputStream = [System.IO.File]::OpenRead($ExportFile)
    $outputStream = [System.IO.File]::Create($CompressedFile)
    $gzipStream = New-Object System.IO.Compression.GZipStream($outputStream, [System.IO.Compression.CompressionMode]::Compress)
    $inputStream.CopyTo($gzipStream)
    $gzipStream.Close()
    $inputStream.Close()
    $outputStream.Close()
    Remove-Item $ExportFile
}

if (-not (Test-Path $CompressedFile)) {
    Write-Host "错误: 文件压缩失败" -ForegroundColor Red
    exit 1
}

Write-Host "✓ 镜像导出成功" -ForegroundColor Green
Write-Host ""

# 显示结果
$FileSize = (Get-Item $CompressedFile).Length
$FileSizeMB = [math]::Round($FileSize / 1MB, 2)

Write-Host "========================================" -ForegroundColor Green
Write-Host "  构建完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "镜像名称: $FullImageName"
Write-Host "导出文件: $CompressedFile"
Write-Host "文件大小: ${FileSizeMB} MB"
Write-Host ""
Write-Host "使用以下命令加载镜像:" -ForegroundColor Yellow
Write-Host "  docker load -i $CompressedFile"
Write-Host ""
Write-Host "使用以下命令运行容器:" -ForegroundColor Yellow
Write-Host "  docker compose -f docker/docker-compose.yml up -d"
Write-Host ""
