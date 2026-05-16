@echo off
chcp 65001 >nul
echo ========================================
echo LOF份额自动抓取 - 定时任务配置
echo ========================================
echo.

REM 获取当前目录
set SCRIPT_DIR=%~dp0
set PYTHON_SCRIPT=%SCRIPT_DIR%auto_fetch_shares.py
set VENV_PYTHON=%SCRIPT_DIR%..\venv\Scripts\python.exe

echo 正在创建定时任务...
echo 任务名称: LOF Shares Auto Fetch
echo 执行时间: 每天 07:00
echo 执行脚本: %PYTHON_SCRIPT%
echo.

schtasks /create /tn "LOF Shares Auto Fetch" /tr "\"%VENV_PYTHON%\" \"%PYTHON_SCRIPT%\"" /sc daily /st 07:00 /ru SYSTEM

if %errorlevel% equ 0 (
    echo ✅ 定时任务创建成功！
    echo.
    echo 查看任务: schtasks /query /tn "LOF Shares Auto Fetch"
    echo 删除任务: schtasks /delete /tn "LOF Shares Auto Fetch"
) else (
    echo ❌ 定时任务创建失败，请以管理员身份运行此脚本
)

pause
