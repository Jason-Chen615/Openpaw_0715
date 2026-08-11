@echo off
REM 快速启动脚本 - Windows版本

setlocal enabledelayedexpansion

echo =========================================================
echo GAIA_Runner 快速启动脚本 (Windows)
echo =========================================================

REM 检查Python版本
echo 检查Python版本...
python --version > nul 2>&1
if errorlevel 1 (
    echo 错误: 找不到Python，请确保已安装Python 3.9+
    pause
    exit /b 1
)

REM 检查数据集
echo 检查GAIA数据集...
if not exist "dataset\GAIA\2023\test" (
    echo 错误: 找不到GAIA数据集 (dataset\GAIA\2023\test)
    pause
    exit /b 1
)

REM 创建虚拟环境
echo 设置虚拟环境...
if not exist "gaia_env" (
    python -m venv gaia_env
    echo 虚拟环境已创建
) else (
    echo 虚拟环境已存在
)

REM 激活虚拟环境
call gaia_env\Scripts\activate.bat

REM 安装依赖
echo 安装依赖...
pip install -q -r GAIA_Runner\requirements.txt

REM 创建输出目录
if not exist "outputs\traces" mkdir outputs\traces
if not exist "outputs\reports" mkdir outputs\reports

REM 运行三个代表性case
echo.
echo =========================================================
echo 开始执行三个代表性case
echo =========================================================
echo.

python GAIA_Runner\scripts\run_three_cases.py ^
    --output-dir outputs\ ^
    --dataset-root dataset\GAIA ^
    --qwenpaw-url http://127.0.0.1:8088/api ^
    --api-user admin ^
    --api-pass password

REM 检查执行结果
if exist "outputs\reports\analysis_report.json" (
    echo.
    echo =========================================================
    echo 执行成功！
    echo =========================================================
    echo.
    echo 输出文件位置:
    echo   轨迹数据: outputs\traces\
    echo   分析报告: outputs\reports\analysis_report.json
    echo   可视化报告: outputs\reports\analysis_report.html
    echo   执行日志: outputs\gaia_runner.log
    echo.
    echo 查看报告:
    echo   type outputs\reports\analysis_report.json
    echo   start outputs\reports\analysis_report.html
    pause
    exit /b 0
) else (
    echo.
    echo 执行失败
    echo 查看日志: type outputs\gaia_runner.log
    pause
    exit /b 1
)
