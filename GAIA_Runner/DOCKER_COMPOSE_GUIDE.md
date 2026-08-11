# GAIA_Runner Docker Compose 部署指南

## 📋 快速启动（3步）

### 第一步：准备 .env 文件

在服务器上的 `GAIA_Runner/` 目录下创建 `.env` 文件：

```bash
cd /path/to/QwenPaw/GAIA_Runner

# 复制示例文件
cp .env.example .env

# 编辑 .env 文件，填入实际的密钥和密码
nano .env
```

**关键参数说明**:
- `QWENPAW_AUTH_USERNAME`: 管理员用户名（默认: admin）
- `QWENPAW_AUTH_PASSWORD`: 管理员密码（必填，建议使用强密码）
- `DASHSCOPE_API_KEY`: 阿里云 DashScope API 密钥（必填）

### 第二步：启动容器

```bash
# 进入 GAIA_Runner 目录
cd /path/to/QwenPaw/GAIA_Runner

# 启动容器（使用你准备的 .env 文件）
docker compose --env-file .env up -d

# 查看启动日志
docker compose logs -f qwenpaw_gaia
```

### 第三步：验证启动

```bash
# 等待 60 秒让容器完全启动
sleep 60

# 检查容器状态
docker ps | grep qwenpaw_gaia

# 验证健康状态
curl -u admin:your_password http://127.0.0.1:8089/healthz

# 预期输出
{"status": "ok"}
```

---

## 🔑 关键要点

### 容器隔离

✅ **与 LoCoMo 隔离**:
- 容器名称: `qwenpaw_gaia`（不是 `qwenpaw`）
- 端口: `8089`（LoCoMo 使用 `8088`）
- 网络: `gaia_network`（独立的 Docker 网络）
- 数据卷: 独立的挂载点

### 数据挂载

| 本地路径 | 容器路径 | 权限 | 说明 |
|--------|--------|------|-----|
| `dataset/GAIA` | `/data/gaia` | ro | GAIA数据集（只读） |
| `GAIA_Runner/outputs` | `/app/gaia_outputs` | rw | 测试结果输出 |
| `GAIA_Runner/logs` | `/logs` | rw | 日志文件 |
| `GAIA_Runner/cache` | `/cache` | rw | 缓存文件 |

### 环境变量

所有参数都可以在 `.env` 文件中配置，支持以下变量：

```bash
# 认证
QWENPAW_AUTH_ENABLED=true
QWENPAW_AUTH_USERNAME=admin
QWENPAW_AUTH_PASSWORD=secure_password

# API
DASHSCOPE_API_KEY=sk-xxxxx

# 目录
QWENPAW_DATA_DIR=/data/gaia
QWENPAW_LOG_DIR=/logs
QWENPAW_CACHE_DIR=/cache
```

---

## 🐛 常见问题

### Q1: 容器无法启动

**症状**: `docker compose up -d` 后容器立即退出

**解决方案**:
```bash
# 查看详细错误日志
docker compose logs qwenpaw_gaia

# 检查 .env 文件格式
cat .env

# 重新启动
docker compose restart qwenpaw_gaia
```

### Q2: 无法连接容器

**症状**: `curl: (7) Failed to connect to 127.0.0.1:8089`

**解决方案**:
```bash
# 检查容器是否运行
docker ps | grep qwenpaw_gaia

# 检查端口绑定
docker port qwenpaw_gaia

# 查看网络配置
docker network inspect gaia_network

# 重新启动容器
docker compose restart qwenpaw_gaia
```

### Q3: 健康检查失败

**症状**: `healthcheck failed: exit code 1`

**解决方案**:
```bash
# 增加启动时间
docker compose up -d
sleep 120  # 等待120秒

# 手动检查健康状态
docker exec qwenpaw_gaia curl http://localhost:8088/healthz

# 查看容器日志
docker compose logs qwenpaw_gaia | tail -50
```

### Q4: API 密钥配置错误

**症状**: 容器启动后无法调用大模型

**解决方案**:
```bash
# 检查环境变量是否正确设置
docker exec qwenpaw_gaia printenv | grep DASHSCOPE

# 如果没有看到密钥，编辑 .env 并重启
nano .env
docker compose restart qwenpaw_gaia
```

### Q5: 与 LoCoMo 容器冲突

**症状**: 端口被占用或网络冲突

**解决方案**:
```bash
# 检查现有容器
docker ps -a

# 如果还有旧的 qwenpaw 容器，删除它
docker rm qwenpaw

# 检查网络
docker network ls | grep gaia

# 创建新的网络（如果需要）
docker network create gaia_network

# 重新启动
docker compose up -d
```

---

## 📊 容器信息

### 容器详情

```bash
# 查看容器详细信息
docker inspect qwenpaw_gaia

# 查看挂载点
docker inspect qwenpaw_gaia | grep -A 20 "Mounts"

# 查看网络配置
docker inspect qwenpaw_gaia | grep -A 10 "NetworkSettings"
```

### 容器日志

```bash
# 实时查看日志
docker compose logs -f qwenpaw_gaia

# 查看最后100行
docker compose logs --tail 100 qwenpaw_gaia

# 查看特定时间的日志
docker compose logs --since 10m qwenpaw_gaia
```

### 性能监控

```bash
# 查看容器资源使用情况
docker stats qwenpaw_gaia

# 查看容器进程
docker top qwenpaw_gaia
```

---

## 🔧 高级配置

### 修改端口

如果需要使用不同的端口（例如使用 8090 而不是 8089）：

```yaml
# docker-compose.yml
ports:
  - "8090:8088"  # 修改这里
```

然后重启：
```bash
docker compose down
docker compose up -d
```

### 增加资源限制

如果容器需要更多资源：

```yaml
# docker-compose.yml 中添加
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 8G
    reservations:
      cpus: '1'
      memory: 4G
```

### 持久化存储

如果想使用 Docker 卷而不是 bind mount：

```yaml
# docker-compose.yml 中修改
volumes:
  - gaia_data:/data/gaia:ro
  - gaia_outputs:/app/gaia_outputs
  - gaia_logs:/logs

volumes:
  gaia_data:
  gaia_outputs:
  gaia_logs:
```

---

## 🚀 完整工作流

### 场景1：第一次启动

```bash
# 1. 进入目录
cd /path/to/QwenPaw/GAIA_Runner

# 2. 准备环境文件
cp .env.example .env
nano .env  # 编辑密钥和密码

# 3. 启动容器
docker compose up -d

# 4. 验证
sleep 60
curl -u admin:your_password http://127.0.0.1:8089/healthz

# 5. 配置模型（在浏览器中）
# 打开 http://your-server:8089
# 进入 设置 → 模型，启用对应模型
```

### 场景2：重启容器

```bash
# 重启
docker compose restart qwenpaw_gaia

# 验证
sleep 30
curl -u admin:your_password http://127.0.0.1:8089/healthz
```

### 场景3：停止容器

```bash
# 停止（保留数据）
docker compose stop qwenpaw_gaia

# 或者删除容器（保留数据卷）
docker compose down

# 完全清理（包括数据）
docker compose down -v
```

---

## 📝 环境变量速查表

| 变量名 | 默认值 | 说明 | 必填 |
|------|------|------|-----|
| QWENPAW_AUTH_ENABLED | true | 启用身份验证 | 否 |
| QWENPAW_AUTH_USERNAME | admin | 用户名 | 否 |
| QWENPAW_AUTH_PASSWORD | - | 密码 | 是 |
| DASHSCOPE_API_KEY | - | API密钥 | 是 |
| QWENPAW_DATA_DIR | /data/gaia | 数据目录 | 否 |
| QWENPAW_LOG_DIR | /logs | 日志目录 | 否 |
| QWENPAW_CACHE_DIR | /cache | 缓存目录 | 否 |

---

## 🎯 下一步

容器启动后，按以下步骤继续：

1. **配置模型**: 打开 `http://your-server:8089`，配置所需的模型
2. **运行脚本**: 执行 `python GAIA_Runner/scripts/run_three_cases.py`
3. **查看结果**: 检查 `GAIA_Runner/outputs/` 目录

详见: `OPENEULER_DEPLOYMENT.md`

---

## 📞 获取帮助

- 容器启动问题: 查看 `docker compose logs`
- 连接问题: 检查 `docker network inspect gaia_network`
- API 问题: 验证 `.env` 中的 `DASHSCOPE_API_KEY`
- 其他问题: 参考 `DEPLOYMENT_GUIDE.md`
