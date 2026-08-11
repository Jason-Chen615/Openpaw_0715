# GAIA_Runner OpenEuler 24.03 部署完整指南（独立 GAIA 容器版本）

本指南说明如何在OpenEuler 24.03服务器上部署 GAIA_Runner，使用**独立的 QwenPaw GAIA 容器**（与 LoCoMo 隔离）。

## 📋 快速导航

- [前置检查](#前置检查)
- [本地准备](#本地准备)
- [服务器部署](#服务器部署)
- [启动容器](#启动容器)
- [运行测试](#运行测试)
- [故障排除](#故障排除)

---

## ✅ 前置检查

### 环境要求
- ✅ OpenEuler 24.03
- ✅ Docker 已安装
- ✅ Docker Compose 已安装
- ✅ Python 3.9+
- ✅ 100GB+ 可用磁盘空间

### 数据准备
- ✅ GAIA 数据集在 `dataset/GAIA/`
- ✅ `.env` 文件已准备（API密钥）
- ✅ QwenPaw 源码目录

### 清理旧容器
```bash
docker rm qwenpaw 2>/dev/null || echo "No old container"
docker ps -a | grep qwenpaw
```

---

## 📦 本地准备

### 验证代码完整性
```bash
cd /path/to/QwenPaw
ls -la GAIA_Runner/
# 应该看到: docker-compose.yml, .env.example, DOCKER_COMPOSE_GUIDE.md 等
```

### 打包代码
```bash
cd /path/to/QwenPaw
tar -czf GAIA_Runner.tar.gz GAIA_Runner/
```

---

## 🚀 服务器部署

### 步骤 1: 上传代码
```bash
scp GAIA_Runner.tar.gz user@your-server:/home/user/
```

### 步骤 2: 连接和解压
```bash
ssh user@your-server
cd /path/to/QwenPaw
tar -xzf /home/user/GAIA_Runner.tar.gz
ls -la GAIA_Runner/
```

### 步骤 3: 验证 GAIA 数据集
```bash
ls -la dataset/GAIA/2023/test/metadata*.parquet
# 应该看到 metadata.parquet, metadata.level1.parquet 等
```

---

## 🐳 启动 GAIA 容器

### 步骤 1: 准备 .env 文件
```bash
cd GAIA_Runner
cp .env.example .env
nano .env
# 编辑以下内容：
# QWENPAW_AUTH_PASSWORD=your_secure_password
# DASHSCOPE_API_KEY=sk-your-actual-key
```

### 步骤 2: 启动容器
```bash
cd /path/to/QwenPaw
docker compose -f GAIA_Runner/docker-compose.yml \
  --env-file GAIA_Runner/.env up -d
```

### 步骤 3: 验证启动
```bash
sleep 60
curl -u admin:your_password http://127.0.0.1:8089/healthz
# 预期: {"status":"ok"}
```

### 步骤 4: 查看挂载信息
```bash
docker inspect qwenpaw_gaia | grep -A 5 "Mounts"
# 应该看到:
# - /path/to/dataset/GAIA → /data/gaia (ro)
# - /path/to/GAIA_Runner/outputs → /app/gaia_outputs (rw)
```

---

## ⚙️ 配置模型

### 浏览器配置
```
http://your-server:8089
用户名: admin
密码: your_secure_password

进入 设置 → 模型，启用所需的模型（如 Qwen-Max）
```

---

## 🧪 运行测试

### 步骤 1: 准备 Python 环境
```bash
cd /path/to/QwenPaw/GAIA_Runner
python3 -m venv gaia_env
source gaia_env/bin/activate
pip install -r requirements.txt
mkdir -p outputs/{traces,reports} logs cache
```

### 步骤 2: 设置环境变量
```bash
export QWENPAW_BASE_URL=http://127.0.0.1:8089/api
export QWENPAW_API_USER=admin
export QWENPAW_API_PASS=your_secure_password
```

### 步骤 3: 运行三个代表性 Case
```bash
source gaia_env/bin/activate
python scripts/run_three_cases.py \
  --output-dir outputs \
  --dataset-root ../dataset/GAIA \
  --qwenpaw-url http://127.0.0.1:8089/api \
  --api-user admin \
  --api-pass your_secure_password
```

### 步骤 4: 查看结果
```bash
# 查看日志
tail -100 outputs/gaia_runner.log

# 查看轨迹文件
ls -lah outputs/traces/

# 查看分析报告
cat outputs/reports/analysis_report.json | python3 -m json.tool
```

---

## 🐛 常见问题

### 问题 1: 容器无法启动
```bash
docker compose -f GAIA_Runner/docker-compose.yml logs qwenpaw_gaia
cat GAIA_Runner/.env  # 检查格式
docker compose -f GAIA_Runner/docker-compose.yml restart qwenpaw_gaia
```

### 问题 2: 无法连接
```bash
docker ps | grep qwenpaw_gaia
docker port qwenpaw_gaia
sleep 120  # 等待更长时间
curl -u admin:password http://127.0.0.1:8089/healthz
```

### 问题 3: API 调用失败
```bash
echo $QWENPAW_BASE_URL
curl -u admin:password http://127.0.0.1:8089/api/health
docker logs qwenpaw_gaia | tail -50
```

### 问题 4: 找不到数据集
```bash
ls -la ../dataset/GAIA/2023/test/metadata.parquet
chmod -R 755 ../dataset/GAIA
docker inspect qwenpaw_gaia | grep -A 3 "Source.*GAIA"
```

### 问题 5: 与 LoCoMo 冲突
```bash
docker ps -a
docker rm qwenpaw  # 删除旧容器
docker network inspect gaia_network
```

---

## 📊 监控

```bash
# 实时日志
docker compose -f GAIA_Runner/docker-compose.yml logs -f qwenpaw_gaia

# 资源使用
docker stats qwenpaw_gaia

# 进程信息
docker top qwenpaw_gaia
```

---

## 📝 关键配置

| 项目 | 值 |
|-----|-----|
| 容器名称 | qwenpaw_gaia |
| 端口 | 8089 |
| 网络 | gaia_network |
| 数据集路径 | /data/gaia (ro) |
| 输出路径 | /app/gaia_outputs |
| 与 LoCoMo 隔离 | ✅ 是 |

---

## ✨ 完整工作流

```bash
# 本地
tar -czf GAIA_Runner.tar.gz GAIA_Runner/

# 服务器
scp ... && tar -xzf ...
cd GAIA_Runner && cp .env.example .env && nano .env
cd ..
docker compose -f GAIA_Runner/docker-compose.yml --env-file GAIA_Runner/.env up -d
sleep 60

# 测试
cd GAIA_Runner
python3 -m venv gaia_env
source gaia_env/bin/activate
pip install -r requirements.txt
python scripts/run_three_cases.py --output-dir outputs --dataset-root ../dataset/GAIA
```

详见: `DOCKER_COMPOSE_GUIDE.md` 和 `QUICK_REFERENCE.md`
