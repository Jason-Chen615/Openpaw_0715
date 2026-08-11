# GAIA_Runner 完整使用指南

一个完整的实验框架，用于在QwenPaw上测试和分析GAIA数据集中的Agent行为。

## 目录

1. [环境准备](#环境准备)
2. [部署流程](#部署流程)
3. [运行步骤](#运行步骤)
4. [输出文件](#输出文件)
5. [常见问题](#常见问题)

## 环境准备

### 前置条件

- Python 3.9+
- Docker和Docker Compose
- 访问QwenPaw服务器或本地部署

### 软件依赖

```bash
# 安装Python依赖
pip install -r GAIA_Runner/requirements.txt
```

必要的库：
- `pandas`: 数据处理
- `pyarrow`: Parquet文件支持
- `requests`: HTTP请求

### GAIA数据集

确保数据集位置正确：
```
/path/to/qwenpaw/dataset/GAIA/
├── 2023/
│   ├── test/
│   │   ├── metadata.parquet
│   │   ├── metadata.level1.parquet
│   │   ├── metadata.level2.parquet
│   │   ├── metadata.level3.parquet
│   │   └── [case files]
│   └── validation/
└── README.md
```

## 部署流程

### 第一步：启动QwenPaw容器

在OpenEuler 24.03服务器上执行：

```bash
# 进入QwenPaw项目目录
cd /path/to/QwenPaw

# 创建.env文件
cat > .env << EOF
QWENPAW_AUTH_ENABLED=true
QWENPAW_AUTH_USERNAME=admin
QWENPAW_AUTH_PASSWORD=your_secure_password
DASHSCOPE_API_KEY=sk-xxxxxxxx
EOF

# 启动容器
docker compose --env-file .env up -d

# 等待服务启动
sleep 60

# 验证服务
curl -u admin:your_secure_password http://127.0.0.1:8088/healthz
# 预期: {"status": "ok"}
```

### 第二步：配置API认证

```bash
# 在GAIA_Runner所在目录创建.env文件
cat > .env << EOF
QWENPAW_BASE_URL=http://127.0.0.1:8088/api
QWENPAW_API_USER=admin
QWENPAW_API_PASS=your_secure_password
GAIA_DATASET_ROOT=dataset/GAIA
OUTPUT_DIR=outputs
LOG_LEVEL=INFO
EOF
```

### 第三步：安装GAIA_Runner

```bash
# 创建虚拟环境
python3 -m venv gaia_env
source gaia_env/bin/activate

# 安装依赖
pip install -r GAIA_Runner/requirements.txt
```

## 运行步骤

### 运行三个代表性Case（推荐）

```bash
# 激活虚拟环境
source gaia_env/bin/activate

# 运行三个代表性case
python GAIA_Runner/scripts/run_three_cases.py \
  --output-dir outputs/ \
  --dataset-root dataset/GAIA \
  --qwenpaw-url http://127.0.0.1:8088/api \
  --api-user admin \
  --api-pass your_secure_password
```

预期输出：
```
========================================================
启动GAIA Runner - 三个代表性case
========================================================
找到 3 个代表性案例
  Level 1: xxxxx-1
  Level 2: xxxxx-2
  Level 3: xxxxx-3

开始执行 Level 1 案例...
执行完成: 成功=True 耗时=1.23s 事件数=45

生成报告...
JSON报告: outputs/reports/analysis_report.json
HTML报告: outputs/reports/analysis_report.html

========================================================
执行完成！
========================================================
```

### 运行单个Case

```bash
# 运行Level 2的代表性case
python GAIA_Runner/scripts/run_single_case.py \
  --level 2 \
  --output-dir outputs/
```

### 生成分析报告

```bash
python GAIA_Runner/scripts/generate_report.py \
  --traces-dir outputs/traces/ \
  --output-dir outputs/reports/
```

## 输出文件

### 目录结构

```
outputs/
├── traces/
│   ├── {case_id}_level{L}.jsonl
│   ├── {case_id}_level{L}_meta.json
│   └── ...
├── reports/
│   ├── analysis_report.json
│   └── analysis_report.html
└── gaia_runner.log
```

### 轨迹文件格式 (JSONL)

```json
{"timestamp": 1691234567.89, "event_type": "turn_start", "iteration": 1, "case_id": "xxx", "level": 1, "data": {"question": "...", "context_size": 1024}}
{"timestamp": 1691234568.01, "event_type": "tool_call", "iteration": 1, "case_id": "xxx", "level": 1, "data": {"tool_name": "web_search", "args": {...}, "duration": 0.12}}
```

事件类型：
- `turn_start`: Turn开始
- `turn_end`: Turn结束
- `tool_call`: 工具调用
- `tool_result`: 工具结果
- `context_change`: 上下文压缩
- `gate_check`: Gate检查

### 分析报告 (JSON)

```json
{
  "timestamp": "2024-08-11T15:30:00",
  "summary": {
    "total_cases": 3,
    "successful_cases": 3,
    "success_rate": 1.0
  },
  "analysis_results": [...]
}
```

## 常见问题

### Q1: 连接到QwenPaw失败

```bash
# 1. 检查QwenPaw状态
docker ps | grep qwenpaw

# 2. 检查健康状态
curl -u admin:password http://127.0.0.1:8088/healthz

# 3. 重启容器
docker compose restart
```

### Q2: 找不到GAIA数据集

```bash
# 检查数据集路径
ls -la dataset/GAIA/2023/test/

# 找到parquet文件
find dataset/GAIA -name "*.parquet" | head -5
```

### Q3: 轨迹文件过大

```bash
# 压缩轨迹文件
gzip outputs/traces/*.jsonl

# 存档旧数据
tar -czf outputs/traces_backup_$(date +%Y%m%d).tar.gz outputs/traces/
```

## 三个代表性Case

| Level | 特征 | 迭代数 | 工具数 | 难度评分 |
|------|------|------|------|--------|
| 1 | 纯文本推理 | 1-3 | 0-2 | 0.2-0.4 |
| 2 | 文档处理 | 4-8 | 5-15 | 0.4-0.6 |
| 3 | 多工具组合 | 8-15 | 15-30 | 0.6-1.0 |

## 架构概览

```
GAIA Dataset → Case Loader → Agent Runner → Trace Collector
                                               ↓
                                           Analyzer
                                               ↓
                                         Report Generator
```

四层事件采集：
- **Turn层**: Agent回复前后 (~50事件)
- **Tool层**: 工具调用和结果 (~100-200事件)
- **Context层**: 上下文压缩 (~5-20事件)
- **Gate层**: 迭代终止条件 (~5-10事件)

**总计**: 每个case 300+细粒度事件

## 查看日志

```bash
# 实时查看日志
tail -f outputs/gaia_runner.log

# 查看最后100行
tail -100 outputs/gaia_runner.log
```

详见README.md和IMPLEMENTATION_PLAN.md获取更多信息。
