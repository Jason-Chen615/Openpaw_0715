# LoCoMo × QwenPaw 服务器部署与评测文档

## 目录

- [1. 项目概览](#1-项目概览)
- [2. 文件说明](#2-文件说明)
- [3. 前置条件](#3-前置条件)
- [4. 服务器快速部署](#4-服务器快速部署)
- [5. Nginx 反向代理配置](#5-nginx-反向代理配置)
- [6. 配置模型 API Key](#6-配置模型-api-key)
- [7. 获取 agent 回答（消息拉取）](#7-获取-agent-回答消息拉取)
- [8. 运行评测脚本](#8-运行评测脚本)
- [9. 查看评测结果](#9-查看评测结果)
- [10. 评测指标说明](#10-评测指标说明)
- [11. 服务器资源建议](#11-服务器资源建议)
- [12. 安全注意事项](#12-安全注意事项)
- [13. 常见问题排查](#13-常见问题排查)

---

## 1. 项目概览

本方案将 **LoCoMo**（Long Conversation Memory）基准数据集与 **QwenPaw** 个人 AI 助理结合，
自动化测试 QwenPaw 的**跨会话长期记忆召回**、**时间推理**、**推断能力**和**对抗性问题识别**。

### 数据集结构

| 字段 | 说明 |
|------|------|
| 4 个 session，带真实时间戳 | 跨越约 2 个月的对话（2023-05-08 至 2023-06-27） |
| 部分 turn 含 `img_url` | 支持多模态模型，纯文本模型自动降级为 `blip_caption` |
| 52 条 QA，分 5 个 category | 详见第 10 节 |

### 架构图

```
服务器
├── Docker 容器：QwenPaw（端口 8088，仅本机可达）
├── Nginx 反代：HTTPS 443 → 127.0.0.1:8088
│
├── /app/eval/locomo_small.json   ← 挂载（只读）
├── /app/eval/eval_locomo.py      ← 挂载（只读）
└── /app/eval_results/            ← 挂载（可写，保存结果）

客户端（服务器本地 或 远程）
└── python eval_locomo.py → HTTP/HTTPS → QwenPaw API
```

---

## 2. 文件说明

```
locomo10_small_dataset/
├── locomo_small.json      # LoCoMo 数据集（1 个对话样本，52 条 QA）
├── eval_locomo.py         # 评测脚本
├── requirements.txt       # 评测脚本 Python 依赖
├── docker-compose.yml     # QwenPaw 服务器部署配置
└── DEPLOYMENT.md          # 本文档
```

---

## 3. 前置条件

### 服务器端

| 软件 | 版本要求 | 说明 |
|------|---------|------|
| Docker | ≥ 24.0 | 运行 QwenPaw 容器 |
| Docker Compose | ≥ 2.20 | 编排容器 |
| Nginx | ≥ 1.18 | 反向代理（可选但推荐） |
| curl | 任意 | 健康检查 |

### 客户端（运行评测脚本）

| 软件 | 版本要求 |
|------|---------|
| Python | ≥ 3.8 |
| pip | 任意 |

---

## 4. 服务器快速部署

### 4.1 上传文件到服务器

```bash
# 在本地机器上执行
scp locomo10_small_dataset/locomo_small.json  user@your-server:~/qwenpaw-eval/
scp locomo10_small_dataset/eval_locomo.py     user@your-server:~/qwenpaw-eval/
scp locomo10_small_dataset/docker-compose.yml user@your-server:~/qwenpaw-eval/
scp locomo10_small_dataset/requirements.txt   user@your-server:~/qwenpaw-eval/
```

### 4.2 创建 .env 文件（存放敏感信息）

在服务器上 `~/qwenpaw-eval/` 目录创建 `.env`，**不要提交到 git**：

```bash
# ~/qwenpaw-eval/.env
QWENPAW_AUTH_USERNAME=admin
QWENPAW_AUTH_PASSWORD=your_strong_password_here

# 填写你使用的模型 API Key（至少填一项）
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
# OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
# ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxx
# DEEPSEEK_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> ⚠️ 把 `your_strong_password_here` 替换为实际强密码（建议 16 位以上，含大小写+数字+符号）。

### 4.3 创建评测结果目录

```bash
mkdir -p ~/qwenpaw-eval/eval_results
```

### 4.4 启动 QwenPaw

```bash
cd ~/qwenpaw-eval
docker compose --env-file .env up -d
```

### 4.5 验证启动状态

```bash
# 查看容器状态（应为 healthy）
docker compose ps

# 查看启动日志
docker compose logs -f qwenpaw

# 测试 API 可达性（本机访问）
curl -u admin:your_strong_password_here http://127.0.0.1:8088/healthz
```

正常响应示例：
```json
{"status": "ok"}
```

---

## 5. Nginx 反向代理配置

如需从外部访问 QwenPaw 控制台（配置模型等），推荐配置 Nginx + HTTPS。

### 5.1 安装 Nginx 和 Certbot

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
```

### 5.2 创建 Nginx 站点配置

```bash
sudo nano /etc/nginx/sites-available/qwenpaw
```

写入以下内容（替换 `your.domain.com`）：

```nginx
server {
    listen 443 ssl;
    server_name your.domain.com;

    ssl_certificate     /etc/letsencrypt/live/your.domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your.domain.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    # 安全头
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";

    location / {
        proxy_pass         http://127.0.0.1:8088;
        proxy_http_version 1.1;

        # WebSocket 支持（QwenPaw 控制台用到）
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;

        # SSE / 流式响应：禁用缓冲
        proxy_buffering    off;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }
}

server {
    listen 80;
    server_name your.domain.com;
    return 301 https://$host$request_uri;
}
```

### 5.3 启用配置并申请证书

```bash
sudo ln -s /etc/nginx/sites-available/qwenpaw /etc/nginx/sites-enabled/
sudo certbot --nginx -d your.domain.com
sudo nginx -t && sudo systemctl reload nginx
```

---

## 6. 配置模型 API Key

QwenPaw 启动后，在浏览器访问控制台配置模型：

1. 打开 `https://your.domain.com`（或本机 `http://127.0.0.1:8088`）
2. 用 `.env` 中设置的用户名/密码登录
3. 进入 **设置 → 模型**
4. 选择提供商（如 DashScope），确认 API Key 已加载，启用模型

**推荐模型配置**：

| 优先级 | 提供商 | 模型 | 上下文 | 说明 |
|--------|--------|------|--------|------|
| 优先 | DashScope | qwen-plus / qwen-turbo | ≥ 32K | 均衡性价比 |
| 多模态 | DashScope | qwen-vl-max | ≥ 32K | 支持图片 turn |
| 本地 | QwenPaw Local | QwenPaw-Flash-9B Q8 | 32K | 无需 API Key |

---

## 7. 获取 agent 回答（消息拉取）

> **重要**：`eval_locomo.py` 中的 `ask_question()` 当前返回占位符
> `[PENDING — see DEPLOYMENT.md §6 for polling implementation]`。
> 这是因为 QwenPaw 的 `/messages/send` 是异步"发件箱"，
> 回答由 agent 异步产生后存入 session 消息流。

完整实现需要在发出问题后**轮询 session 消息接口**，取最新 assistant 消息：

```python
import time
import requests
from requests.auth import HTTPBasicAuth

def poll_latest_answer(
    base_url: str,
    agent_id: str,
    session_id: str,
    auth,
    timeout: float = 30.0,
    poll_interval: float = 1.0,
) -> str:
    """
    轮询 QwenPaw session 消息，返回最新的 assistant 回复。
    
    接口路径（以实际 Swagger 为准，访问 /docs 确认）：
        GET /api/chats/{agentId}/sessions/{sessionId}/messages
    """
    deadline = time.time() + timeout
    last_seen_id = None

    while time.time() < deadline:
        resp = requests.get(
            f"{base_url}/chats/{agent_id}/sessions/{session_id}/messages",
            auth=auth,
            timeout=10,
        )
        if resp.ok:
            messages = resp.json().get("messages", [])
            # 找最后一条 role == "assistant" 的消息
            for msg in reversed(messages):
                if msg.get("role") == "assistant":
                    msg_id = msg.get("id")
                    if msg_id != last_seen_id:
                        return msg.get("content", "")
                    break
        time.sleep(poll_interval)

    return "[TIMEOUT: no answer received]"
```

将此函数集成到 `ask_question()` 中替换 `time.sleep` + 占位返回即可。

> **提示**：实际接口路径请以 `http://127.0.0.1:8088/docs` 的 Swagger 文档为准。

---

## 8. 运行评测脚本

### 8.1 安装评测脚本依赖

```bash
# 在服务器上（或本地机器）
cd ~/qwenpaw-eval

# 推荐使用虚拟环境
python3 -m venv eval_env
source eval_env/bin/activate      # Windows: eval_env\Scripts\activate

pip install -r requirements.txt
```

### 8.2 设置环境变量

```bash
# 方式 A：从 .env 文件加载（推荐）
export $(grep -v '^#' .env | xargs)

# 方式 B：手动设置
export QWENPAW_BASE_URL=http://127.0.0.1:8088/api   # 服务器本地运行时
# export QWENPAW_BASE_URL=https://your.domain.com/api  # 远程调用时
export QWENPAW_API_USER=admin
export QWENPAW_API_PASS=your_strong_password_here
```

### 8.3 运行评测

```bash
# 基本用法（在 ~/qwenpaw-eval/ 目录下）
python eval_locomo.py \
  --data locomo_small.json \
  --agent-id locomo_eval \
  --output eval_results/eval_results.json

# 完整参数说明
python eval_locomo.py --help
```

**参数说明**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--data` | `locomo_small.json` | 数据集文件路径 |
| `--agent-id` | `locomo_eval` | QwenPaw agent ID（自动创建） |
| `--output` | `eval_results.json` | 结果输出路径 |
| `--base-url` | 读环境变量 | 覆盖 QWENPAW_BASE_URL |
| `--delete-after` | 不删除 | 评测完成后删除 eval agent |

### 8.4 预期输出

```
QwenPaw Endpoint : http://127.0.0.1:8088/api
Auth             : enabled
Data file        : locomo_small.json
Agent ID         : locomo_eval
Output           : eval_results/eval_results.json

Loaded 1 sample(s) from locomo_small.json

[✓] Agent 'locomo_eval' created.

================================================================
  Sample : conv-26
  Session: eval_conv_26_1720000000
  QA cnt : 52
================================================================
[1/2] Feeding conversation turns...
    [Session 1] 1:56 pm on 8 May, 2023 — 18 turns
    [Session 2] 1:14 pm on 25 May, 2023 — 17 turns
    [Session 3] 7:55 pm on 9 June, 2023 — 23 turns
    [Session 4] 10:37 am on 27 June, 2023 — 18 turns
    → 76 turns fed into session 'eval_conv_26_1720000000'
[2/2] Running QA evaluation...
  ...

================================================================
  EVALUATION METRICS
================================================================
  Cat1 Factual        [████████░░░░░░░░░░░░]  4/ 6 = 66.7%
  Cat2 Temporal       [███████░░░░░░░░░░░░░]  6/11 = 54.5%
  Cat3 Inferential    [████░░░░░░░░░░░░░░░░]  1/ 2 = 50.0%
  Cat4 General QA     [██████████████░░░░░░] 19/27 = 70.4%
  Cat5 Adversarial    [████░░░░░░░░░░░░░░░░]  2/ 6 = 33.3%
  ──────────────────────────────────────────────────────────
  Overall              32/52 = 61.5%
================================================================

[✓] Results saved to eval_results/eval_results.json
```

---

## 9. 查看评测结果

结果保存为 JSON，结构如下：

```json
{
  "config": {
    "base_url": "http://127.0.0.1:8088/api",
    "agent_id": "locomo_eval",
    "data_file": "locomo_small.json"
  },
  "metrics": {
    "category_1": {"correct": 4, "total": 6, "accuracy": 0.6667},
    "category_2": {"correct": 6, "total": 11, "accuracy": 0.5455},
    "category_3": {"correct": 1, "total": 2, "accuracy": 0.5000},
    "category_4": {"correct": 19, "total": 27, "accuracy": 0.7037},
    "category_5": {"correct": 2, "total": 6, "accuracy": 0.3333},
    "overall":    {"correct": 32, "total": 52, "accuracy": 0.6154}
  },
  "results": [
    {
      "sample_id": "conv-26",
      "category": 1,
      "question": "What did Caroline research?",
      "expected": "Adoption agencies",
      "got": "Caroline researched adoption agencies...",
      "correct": true,
      "evidence": ["D2:8"]
    }
  ]
}
```

---

## 10. 评测指标说明

| Category | 类型 | 测试能力 | 预期准确率参考 |
|----------|------|---------|--------------|
| 1 | Factual（事实性） | 从对话中直接提取事实 | 50–70% |
| 2 | Temporal（时间推理） | 推算日期、时长、顺序 | 40–60% |
| 3 | Inferential（推断性） | 跨轮推断、隐含逻辑 | 30–50% |
| 4 | General QA（综合问答） | 标准理解问答 | 60–75% |
| 5 | Adversarial（对抗性） | 识别并纠正错误归因 | 20–40% |

> 以上参考值基于长上下文模型（≥32K）推测，开启 ReMe 长期记忆后分值通常更高。

**Category 5 特别说明**：这类问题故意把 A 的行为归因给 B（例如把 Caroline 做的事归给 Melanie），正确行为是模型识别并纠正错误假设，而非直接回答。评测脚本对此类别有专门的判断逻辑（见 `judge_answer()` 中的 `_CORRECTION_SIGNALS`）。

---

## 11. 服务器资源建议

| 场景 | CPU | 内存 | 磁盘 | 说明 |
|------|-----|------|------|------|
| 云端 API 模型 | 2 核 | 4 GB | 20 GB | 只转发请求，无本地推理 |
| QwenPaw-Flash-4B Q4 | 8 核 | 16 GB | 30 GB | CPU 推理，速度较慢 |
| QwenPaw-Flash-9B Q8 | 16 核 / GPU | 32 GB | 50 GB | 强烈建议 GPU（≥16GB 显存） |

---

## 12. 安全注意事项

1. **不要将 8088 端口直接暴露到公网**：`docker-compose.yml` 已绑定 `127.0.0.1:8088`，通过 Nginx 反代
2. **API Key 和密码通过 `.env` 文件传入**，不要硬编码在脚本或 `docker-compose.yml` 中
3. **将 `.env` 加入 `.gitignore`**，防止意外提交
4. **服务器防火墙只开放 80/443**：
   ```bash
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   sudo ufw allow 22/tcp   # SSH
   sudo ufw enable
   ```
5. **定期更新镜像**：
   ```bash
   docker compose pull && docker compose up -d
   ```

---

## 13. 常见问题排查

### Q1：`Cannot connect to QwenPaw` 报错

```bash
# 检查容器是否运行
docker compose ps

# 检查端口监听
ss -tlnp | grep 8088

# 检查容器日志
docker compose logs qwenpaw | tail -50
```

### Q2：认证失败（401 Unauthorized）

确认 `.env` 文件中的 `QWENPAW_AUTH_USERNAME` 和 `QWENPAW_AUTH_PASSWORD` 与环境变量一致：
```bash
# 验证认证
curl -u admin:your_password http://127.0.0.1:8088/api/agents
```

### Q3：Agent 创建失败（400 错误）

agent ID 已存在时会返回 400，脚本会自动复用，无需处理。若需要全新评测：
```bash
python eval_locomo.py --agent-id locomo_eval_v2
```

### Q4：评测结果全是 `[PENDING...]`

这是正常的占位符，说明 `ask_question()` 尚未实现消息拉取。
参考第 7 节实现 `poll_latest_answer()` 并替换 `ask_question()` 中的返回值。

### Q5：容器启动很慢

QwenPaw 初始化包括加载模型配置和 Skills，首次启动可能需要 60–120 秒。
观察 `docker compose logs -f qwenpaw` 直到出现 `Application started` 即可。

### Q6：如何重置评测（清空 agent 记忆）

```bash
# 删除 eval agent（会清除其记忆和会话）
curl -u admin:your_password \
     -X DELETE http://127.0.0.1:8088/api/agents/locomo_eval

# 下次运行评测时会自动重新创建
python eval_locomo.py --agent-id locomo_eval
```

---

*文档版本：v1.0 | 对应数据集：locomo_small.json | QwenPaw 版本：v2.0+*