# GAIA QwenPaw 容器快速启动指南

## 🎯 一句话总结
在服务器上用独立的 docker-compose 启动 GAIA 专用 QwenPaw 容器（端口8089），与 LoCoMo 容器（端口8088）完全隔离。

---

## ⚡ 最快 5 步启动

### 第 1 步：本地打包
```bash
cd /path/to/QwenPaw
tar -czf GAIA_Runner.tar.gz GAIA_Runner/
```

### 第 2 步：上传服务器
```bash
scp GAIA_Runner.tar.gz user@server:/home/user/
ssh user@server
cd /path/to/QwenPaw
tar -xzf /home/user/GAIA_Runner.tar.gz
```

### 第 3 步：准备配置
```bash
cd GAIA_Runner
cp .env.example .env
nano .env
# 编辑：QWENPAW_AUTH_PASSWORD 和 DASHSCOPE_API_KEY
```

### 第 4 步：启动容器
```bash
cd /path/to/QwenPaw
docker compose -f GAIA_Runner/docker-compose.yml \
  --env-file GAIA_Runner/.env up -d
sleep 60
```

### 第 5 步：验证
```bash
curl -u admin:your_password http://127.0.0.1:8089/healthz
# 预期: {"status":"ok"}
```

---

## 📂 关键文件位置

| 文件 | 位置 | 用途 |
|-----|------|-----|
| docker-compose.yml | `GAIA_Runner/` | 容器配置 |
| .env | `GAIA_Runner/` | 环境变量（你创建） |
| 数据集 | `dataset/GAIA/` | GAIA 数据 |
| 输出结果 | `GAIA_Runner/outputs/` | 测试结果 |

---

## 🔧 常用命令

```bash
# 启动
docker compose -f GAIA_Runner/docker-compose.yml \
  --env-file GAIA_Runner/.env up -d

# 停止
docker compose -f GAIA_Runner/docker-compose.yml stop

# 查看日志
docker compose -f GAIA_Runner/docker-compose.yml logs -f qwenpaw_gaia

# 重启
docker compose -f GAIA_Runner/docker-compose.yml restart qwenpaw_gaia

# 删除
docker compose -f GAIA_Runner/docker-compose.yml down

# 检查状态
docker ps | grep qwenpaw_gaia
```

---

## 📋 .env 文件内容

```bash
# 认证
QWENPAW_AUTH_ENABLED=true
QWENPAW_AUTH_USERNAME=admin
QWENPAW_AUTH_PASSWORD=your_secure_password_here

# API（必填）
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx
```

---

## 🔍 验证清单

✅ 容器名称: `qwenpaw_gaia`  
✅ 端口: `8089`（与 LoCoMo 的 8088 隔离）  
✅ 网络: `gaia_network`（独立网络）  
✅ 数据卷: `/data/gaia` (ro)  
✅ 输出卷: `/app/gaia_outputs` (rw)  

---

## 🚨 快速故障排除

| 问题 | 命令 |
|-----|------|
| 容器无法启动 | `docker compose -f GAIA_Runner/docker-compose.yml logs qwenpaw_gaia` |
| 查看挂载点 | `docker inspect qwenpaw_gaia \| grep -A 5 Mounts` |
| 查看端口映射 | `docker port qwenpaw_gaia` |
| 检查网络 | `docker network inspect gaia_network` |
| 手动测试 | `curl -u admin:password http://127.0.0.1:8089/healthz` |

---

## 📊 与 LoCoMo 的区别

| 项目 | LoCoMo | GAIA |
|-----|--------|------|
| 容器名称 | qwenpaw | qwenpaw_gaia |
| 端口 | 8088 | 8089 |
| 网络 | default | gaia_network |
| 数据集 | locomo_small.json | dataset/GAIA/ |
| compose 文件 | 根目录 | GAIA_Runner/ |
| 状态 | 已删除 | 新建 |

---

## 🎓 运行测试

```bash
cd /path/to/QwenPaw/GAIA_Runner

# 准备环境
python3 -m venv gaia_env
source gaia_env/bin/activate
pip install -r requirements.txt

# 设置环境变量
export QWENPAW_BASE_URL=http://127.0.0.1:8089/api
export QWENPAW_API_USER=admin
export QWENPAW_API_PASS=your_secure_password

# 运行
python scripts/run_three_cases.py \
  --output-dir outputs \
  --dataset-root ../dataset/GAIA
```

---

## 📝 .env 文件示例

```bash
# GAIA_Runner/.env

# 认证配置
QWENPAW_AUTH_ENABLED=true
QWENPAW_AUTH_USERNAME=admin
QWENPAW_AUTH_PASSWORD=secure_password_123

# API 密钥（从阿里云 DashScope 获取）
DASHSCOPE_API_KEY=sk-abcd1234efgh5678ijkl90mnopqrstu

# 可选：自定义目录
# QWENPAW_DATA_DIR=/data/gaia
# QWENPAW_LOG_DIR=/logs
# QWENPAW_CACHE_DIR=/cache
```

---

## ✨ 关键特性

✅ **完全隔离**: 独立容器、网络、端口  
✅ **配置灵活**: 环境变量驱动  
✅ **数据持久**: 输出挂载到宿主机  
✅ **易于管理**: docker-compose 原生支持  
✅ **零冲突**: 与 LoCoMo 完全分离  

---

## 🎯 下一步

1. **编辑 .env**: 填入你的 API 密钥和密码
2. **启动容器**: `docker compose up -d`
3. **验证**: `curl http://127.0.0.1:8089/healthz`
4. **配置模型**: 打开浏览器配置
5. **运行测试**: `python scripts/run_three_cases.py`

详见: 
- `DOCKER_COMPOSE_GUIDE.md` - Docker Compose 详细指南
- `OPENEULER_DEPLOYMENT_v2.md` - OpenEuler 完整部署指南
- `QUICK_REFERENCE.md` - 总体快速参考
