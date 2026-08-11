#!/bin/bash
# -*- coding: utf-8 -*-
"""
快速启动脚本 - 一键运行GAIA_Runner
"""

set -e

echo "========================================================="
echo "GAIA_Runner 快速启动脚本"
echo "========================================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查Python版本
echo "检查Python版本..."
python_version=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
if (( $(echo "$python_version < 3.9" | bc -l) )); then
    echo -e "${RED}错误: 需要Python 3.9+，当前版本: $python_version${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python版本: $python_version${NC}"

# 检查数据集
echo ""
echo "检查GAIA数据集..."
if [ ! -d "dataset/GAIA/2023/test" ]; then
    echo -e "${RED}错误: 找不到GAIA数据集 (dataset/GAIA/2023/test)${NC}"
    exit 1
fi

parquet_files=$(find dataset/GAIA -name "*.parquet" | wc -l)
echo -e "${GREEN}✓ 找到 $parquet_files 个parquet文件${NC}"

# 创建虚拟环境
echo ""
echo "设置虚拟环境..."
if [ ! -d "gaia_env" ]; then
    python3 -m venv gaia_env
    echo -e "${GREEN}✓ 虚拟环境已创建${NC}"
else
    echo -e "${GREEN}✓ 虚拟环境已存在${NC}"
fi

# 激活虚拟环境
source gaia_env/bin/activate

# 安装依赖
echo ""
echo "安装依赖..."
pip install -q -r GAIA_Runner/requirements.txt
echo -e "${GREEN}✓ 依赖安装完成${NC}"

# 检查QwenPaw连接
echo ""
echo "检查QwenPaw服务..."
if command -v curl &> /dev/null; then
    if curl -s -u admin:password http://127.0.0.1:8088/healthz > /dev/null 2>&1; then
        echo -e "${GREEN}✓ QwenPaw服务正在运行${NC}"
    else
        echo -e "${YELLOW}⚠ 无法连接到QwenPaw (http://127.0.0.1:8088)${NC}"
        echo "  请确保QwenPaw容器已启动:"
        echo "  docker compose --env-file .env up -d"
    fi
else
    echo -e "${YELLOW}⚠ 跳过QwenPaw连接检查 (curl未安装)${NC}"
fi

# 创建输出目录
mkdir -p outputs/traces outputs/reports

# 运行三个代表性case
echo ""
echo "========================================================="
echo "开始执行三个代表性case"
echo "========================================================="
echo ""

python GAIA_Runner/scripts/run_three_cases.py \
    --output-dir outputs/ \
    --dataset-root dataset/GAIA \
    --qwenpaw-url http://127.0.0.1:8088/api \
    --api-user admin \
    --api-pass password

# 检查执行结果
if [ -f "outputs/reports/analysis_report.json" ]; then
    echo ""
    echo -e "${GREEN}=========================================================${NC}"
    echo -e "${GREEN}执行成功！${NC}"
    echo -e "${GREEN}=========================================================${NC}"
    echo ""
    echo "输出文件位置:"
    echo "  轨迹数据: outputs/traces/"
    echo "  分析报告: outputs/reports/analysis_report.json"
    echo "  可视化报告: outputs/reports/analysis_report.html"
    echo "  执行日志: outputs/gaia_runner.log"
    echo ""
    echo "查看报告:"
    echo "  cat outputs/reports/analysis_report.json | python -m json.tool"
    echo "  open outputs/reports/analysis_report.html"
    exit 0
else
    echo ""
    echo -e "${RED}执行失败${NC}"
    echo "查看日志: tail -100 outputs/gaia_runner.log"
    exit 1
fi
