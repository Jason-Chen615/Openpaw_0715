# -*- coding: utf-8 -*-
"""默认配置"""

import os
from pathlib import Path

# QwenPaw配置
QWENPAW_BASE_URL = os.getenv('QWENPAW_BASE_URL', 'http://127.0.0.1:8088/api')
QWENPAW_API_USER = os.getenv('QWENPAW_API_USER', 'admin')
QWENPAW_API_PASS = os.getenv('QWENPAW_API_PASS', 'password')

# 数据集配置
GAIA_DATASET_ROOT = os.getenv('GAIA_DATASET_ROOT', 'dataset/GAIA')
GAIA_SPLIT = 'test'  # 或 'validation'

# 输出配置
OUTPUT_DIR = os.getenv('OUTPUT_DIR', 'outputs')
TRACES_DIR = os.path.join(OUTPUT_DIR, 'traces')
REPORTS_DIR = os.path.join(OUTPUT_DIR, 'reports')

# 创建输出目录
Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
Path(TRACES_DIR).mkdir(parents=True, exist_ok=True)
Path(REPORTS_DIR).mkdir(parents=True, exist_ok=True)

# 日志配置
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = os.path.join(OUTPUT_DIR, 'gaia_runner.log')

# 执行配置
MAX_ITERATIONS = 20
TIMEOUT_PER_CASE = 300  # 秒

# 三个代表性案例配置
REPRESENTATIVE_CASES_CONFIG = {
    1: {
        'level': 1,
        'description': '纯文本推理，无附件',
        'max_iterations': 3,
        'expected_tools': '0-2',
    },
    2: {
        'level': 2,
        'description': '文档处理，PDF/XLSX',
        'max_iterations': 8,
        'expected_tools': '5-15',
    },
    3: {
        'level': 3,
        'description': '多工具组合，长推理',
        'max_iterations': 15,
        'expected_tools': '15-30',
    },
}
