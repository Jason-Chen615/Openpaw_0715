# GAIA_Runner OpenEuler 24.03 部署完整指南

本指南说明如何在OpenEuler 24.03服务器上从零开始部署和运行GAIA_Runner框架。

## 目录

1. [前置检查](#前置检查)
2. [本地准备](#本地准备)
3. [服务器部署](#服务器部署)
4. [运行验证](#运行验证)
5. [故障排除](#故障排除)

---

## 前置检查

在开始前，确保你有以下条件：

- ✅ 本地开发机：Windows/macOS/Linux
- ✅ OpenEuler 24.03服务器SSH访问权限
- ✅ Docker/Docker Compose已安装在服务器
- ✅ 至少100GB可用磁盘空间
- ✅ Python 3.9+
- ✅ GAIA数据集在服务器 `dataset/GAIA/` 目录

---

## 本地准备

### 第一步：验证代码完整性

```bash
# Windows PowerShell
cd d:\Huawei_Code\QwenPaw
dir GAIA_Runner

# macOS/Linux
cd /path/to/QwenPaw
ls -la GAIA_Runner/
```

应该看到完整的目录结构：
```
GAIA_Runner/
├── core/ (models.py, case_loader.py, trace_collector.py)
├── runner/ (agent_runner.py, execution_env.py, trace_hooks.py)
├── analysis/ (analyzer.py, metrics.py, report_gen.py)
├── config/ (default_config.py)
├── scripts/ (run_three_cases.py, run_single_case.py, generate_report.py, quick_start.sh, quick_start.bat)
├── README.md
├── IMPLEMENTATION_PLAN.md
├── DEPLOYMENT_GUIDE.md
└── requirements.txt
```

### 第二步：打包代码

```bash
# Windows PowerShell
cd d:\Huawei_Code\QwenPaw
tar -czf GAIA_Runner.tar.gz GAIA_Runner/

# macOS/Linux
cd /path/to/QwenPaw
tar -czf GAIA_Runner.tar.gz GAIA_Runner/
```

---

## 服务器部署

### 第一步：上传代码

```bash
# 从本地上传到服务器
scp GAIA_Runner.tar.gz user@openeuler-server:/home/user/

# 或使用WinSCP（Windows用户）
```

### 第二步：解压并验证

```bash
# SSH连接到服务器
ssh user@openeuler-server

# 进入QwenPaw目录
cd /path/to/QwenPaw

# 解压代码
tar -xzf /home/user/GAIA_Runner.tar.gz

# 验证
ls -la GAIA_Runner/
```

### 第三步：启动QwenPaw容器

```bash
# 进入QwenPaw根目录
cd /path/to/QwenPaw

# 创建.env文件
cat > .env << 'EOF'
QWENPAW_AUTH_ENABLED=true
QWENPAW_AUTH_USERNAME=admin
QWENPAW_AUTH_PASSWORD=your_secure_password_here
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxx
EOF

# 启动容器
docker compose --env-file .env up -d

# 等待60秒
sleep 60

# 验证服务
curl -u admin:your_secure_password_here http://127.0.0.1:8088/healthz
# 预期: {"status":"ok"}
```

### 第四步：配置GAIA_Runner环境

```bash
# 验证GAIA数据集
ls -la dataset/GAIA/2023/test/metadata*.parquet

# 创建虚拟环境
python3 -m venv gaia_env
source gaia_env/bin/activate

# 安装依赖
pip install -r GAIA_Runner/requirements.txt

# 创建输出目录
mkdir -p GAIA_Runner/outputs/traces
mkdir -p GAIA_Runner/outputs/reports
```

### 第五步：设置环境变量

```bash
# 创建.env文件
cat > GAIA_Runner/.env << 'EOF'
QWENPAW_BASE_URL=http://127.0.0.1:8088/api
QWENPAW_API_USER=admin
QWENPAW_API_PASS=your_secure_password_here
GAIA_DATASET_ROOT=dataset/GAIA
OUTPUT_DIR=GAIA_Runner/outputs
LOG_LEVEL=INFO
EOF

# 或导出环境变量
export QWENPAW_BASE_URL=http://127.0.0.1:8088/api
export QWENPAW_API_USER=admin
export QWENPAW_API_PASS=your_secure_password_here
export GAIA_DATASET_ROOT=dataset/GAIA
```

---

## 运行验证

### 执行三个代表性Case

```bash
# 激活虚拟环境
source gaia_env/bin/activate

# 运行
python GAIA_Runner/scripts/run_three_cases.py \
  --output-dir GAIA_Runner/outputs \
  --dataset-root dataset/GAIA \
  --qwenpaw-url http://127.0.0.1:8088/api \
  --api-user admin \
  --api-pass your_secure_password_here
```

### 预期输出

```
========================================================
启动GAIA Runner - 三个代表性case
========================================================

找到 3 个代表性案例
  Level 1: xxxxxxxx-1
  Level 2: xxxxxxxx-2
  Level 3: xxxxxxxx-3

开始执行 Level 1 案例: xxxxxxxx-1
执行完成: 成功=True 耗时=1.23s 事件数=45

...

分析完成:
  总案例: 3
  成功: 3
  成功率: 100.0%

JSON报告: GAIA_Runner/outputs/reports/analysis_report.json
HTML报告: GAIA_Runner/outputs/reports/analysis_report.html

========================================================
执行完成！
========================================================
```

### 查看结果

```bash
# 查看轨迹文件
ls -la GAIA_Runner/outputs/traces/

# 查看JSON报告
cat GAIA_Runner/outputs/reports/analysis_report.json | python3 -m json.tool

# 查看日志
tail -100 GAIA_Runner/outputs/gaia_runner.log
```

---

## 故障排除

### 问题1：连接到QwenPaw失败

```bash
# 检查容器状态
docker ps | grep qwenpaw

# 检查服务健康
curl http://127.0.0.1:8088/healthz

# 查看容器日志
docker logs qwenpaw

# 重启容器
docker compose restart
```

### 问题2：找不到GAIA数据集

```bash
# 验证数据集位置
ls -la dataset/GAIA/2023/test/

# 找到parquet文件
find dataset/GAIA -name "*.parquet"

# 检查权限
chmod 644 dataset/GAIA/2023/test/*.parquet
```

### 问题3：内存不足

```bash
# 增加容器内存
docker update --memory=16g qwenpaw

# 运行单个case
python GAIA_Runner/scripts/run_single_case.py --level 1

# 检查系统内存
free -h
```

### 问题4：权限问题

```bash
# 赋予写入权限
chmod -R 755 GAIA_Runner/outputs/

# 检查所有权
chown -R user:user GAIA_Runner/
```

### 问题5：Python依赖冲突

```bash
# 重建虚拟环境
rm -rf gaia_env
python3 -m venv gaia_env
source gaia_env/bin/activate

# 重装依赖
pip install --upgrade pip
pip install -r GAIA_Runner/requirements.txt

# 验证
python3 -c "import pandas; import pyarrow; print('OK')"
```

---

## 常用命令

```bash
# SSH连接
ssh user@openeuler-server

# 激活环境
source gaia_env/bin/activate

# 运行三个case
python GAIA_Runner/scripts/run_three_cases.py \
  --output-dir GAIA_Runner/outputs \
  --dataset-root dataset/GAIA

# 查看实时日志
tail -f GAIA_Runner/outputs/gaia_runner.log

# 查看报告
cat GAIA_Runner/outputs/reports/analysis_report.json | python3 -m json.tool

# 清理输出
rm -rf GAIA_Runner/outputs/*
```

---

## 后续操作

### 运行其他case

```bash
python GAIA_Runner/scripts/run_single_case.py --level 2 --case-id <case-id>
```

### 扩展到450+个case

修改脚本中的加载逻辑，核心执行逻辑保持不变。

### 生成聚合报告

```bash
python GAIA_Runner/scripts/generate_report.py \
  --traces-dir GAIA_Runner/outputs/traces/ \
  --output-dir GAIA_Runner/outputs/reports/
```

---

## 性能参考

- 单个case: 5-30秒
- 三个case总时间: 15-90秒
- 轨迹文件: 100-500KB/case
- 报告生成: <2秒
- 推荐配置: 8GB+ RAM, 4核+ CPU

详见 DEPLOYMENT_GUIDE.md 获取更多信息。
