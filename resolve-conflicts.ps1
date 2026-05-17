# ========================================
# LOF 基金监控系统 - 自动冲突解决脚本
# ========================================
# 策略：保留 dev 分支的定制功能，同时记录冲突文件供后续审查

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Git 冲突自动解决脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 定义冲突解决策略
# "dev" = 保留 dev 分支（你的定制版本）
# "manual" = 需要手动审查
# "merge" = 合并两者（取交集）

$files_strategy = @{
    # 🔴 核心定制文件 - 保留 dev 分支
    "backend/app.py"                  = "dev"
    "js/app.js"                       = "dev"
    "js/config.js"                    = "dev"
    "index.html"                      = "dev"
    "css/style.css"                   = "dev"
    
    # 🟡 配置文件 - 保留 dev 分支
    "backend/config.py"               = "dev"
    "backend/data_fetcher.py"         = "dev"
    "backend/fee_fetcher.py"          = "dev"
    "backend/history_db.py"           = "dev"
    "backend/history_fetcher.py"      = "dev"
    "backend/datasource/__init__.py"  = "dev"
    "requirements.txt"                = "dev"
    ".gitignore"                      = "dev"
    
    # 🟢 文档和页面 - 保留 dev 分支
    "README.md"                       = "dev"
    "CHANGELOG.md"                    = "dev"
    "CHANGELOG_USER.md"               = "dev"
    "pages/agreement.html"            = "dev"
    "pages/privacy.html"              = "dev"
    "js/api.js"                       = "dev"
}

# 统计信息
$resolved_count = 0
$manual_count = 0
$error_count = 0
$manual_files = @()

# 获取所有冲突文件
$conflict_files = git diff --name-only --diff-filter=U
$conflict_files += git diff --name-only --diff-filter=A | Where-Object { $_ }

Write-Host "📋 发现冲突文件：" -ForegroundColor Yellow
$conflict_files | ForEach-Object { Write-Host "   - $_" -ForegroundColor Gray }
Write-Host ""

# 处理每个冲突文件
foreach ($file in $conflict_files) {
    Write-Host "🔄 处理: $file" -ForegroundColor Cyan
    
    $strategy = $files_strategy[$file]
    
    if (-not $strategy) {
        Write-Host "   ⚠️  未定义策略，需要手动处理" -ForegroundColor Yellow
        $manual_files += $file
        $manual_count++
        continue
    }
    
    try {
        switch ($strategy) {
            "dev" {
                # 保留 dev 分支（ours）
                Write-Host "   ✓ 保留 dev 分支版本" -ForegroundColor Green
                git checkout --ours $file
                git add $file
                $resolved_count++
            }
            "manual" {
                Write-Host "   ⚠️  需要手动审查" -ForegroundColor Yellow
                $manual_files += $file
                $manual_count++
            }
            "merge" {
                Write-Host "   ⚠️  需要手动合并" -ForegroundColor Yellow
                $manual_files += $file
                $manual_count++
            }
        }
    }
    catch {
        Write-Host "   ✗ 处理失败: $_" -ForegroundColor Red
        $error_count++
        $manual_files += $file
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "✅ 冲突解决完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host " 统计信息：" -ForegroundColor Yellow
Write-Host "   ✓ 自动解决: $resolved_count 个文件" -ForegroundColor Green
Write-Host "   ⚠️  需要手动处理: $manual_count 个文件" -ForegroundColor Yellow
Write-Host "   ✗ 处理失败: $error_count 个文件" -ForegroundColor Red

if ($manual_files.Count -gt 0) {
    Write-Host ""
    Write-Host "⚠️  以下文件需要手动审查：" -ForegroundColor Yellow
    $manual_files | ForEach-Object { Write-Host "   - $_" -ForegroundColor Yellow }
    Write-Host ""
    Write-Host " 使用以下命令查看冲突：" -ForegroundColor Cyan
    Write-Host "   git status" -ForegroundColor Gray
}

Write-Host ""
Write-Host "🎯 下一步：" -ForegroundColor Cyan
Write-Host "   1. 检查上述需要手动处理的文件" -ForegroundColor Gray
Write-Host "   2. 提交合并: git commit -m 'merge: 合并 dev 分支到 latest-dev'" -ForegroundColor Gray
Write-Host ""
