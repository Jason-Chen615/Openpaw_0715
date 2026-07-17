# LoCoMo × QwenPaw 评测脚本实现说明

## 1. 评测目标

在 QwenPaw agent 平台上运行 **LoCoMo 长期对话记忆基准（Long-term Conversation Memory）**，衡量 agent 在经历跨越多个时间段的长对话后，能否准确回答与记忆相关的问题。

---

## 2. 数据集结构

数据文件：`locomo_small.json`（1 个样本 `conv-26`）

```
sample
├── sample_id          "conv-26"
├── conversation
│   ├── speaker_a      "Caroline"
│   ├── speaker_b      "Melanie"
│   ├── session_1_date_time
│   ├── session_1      [ {speaker, text, img_url?, blip_caption?}, ... ]
│   ├── session_2_date_time
│   ├── session_2      [ ... ]
│   ├── session_3_date_time
│   ├── session_3      [ ... ]
│   ├── session_4_date_time
│   └── session_4      [ ... ]
└── qa
    └── [ {question, answer, category, evidence}, ... ]
```

每个 sample 包含 **4 个 session**（Caroline 与 Melanie 的对话，时间跨度约 2 个月），共约 76 条对话，52 道 QA 问题。

---

## 3. 系统架构

```
eval_locomo.py
      │
      │  POST /api/auth/login          ← 获取 Bearer Token
      │  POST /api/agents              ← 创建评测专用 agent
      │
      │  [对话喂入阶段 — 每个 session 独立 context]
      │  POST /api/console/chat (SSE)  ← 整条 session 打包成自然语言消息发送
      │                                   agent 主动将其存入记忆系统
      │
      │  [QA 评测阶段 — 全新 context]
      │  POST /api/console/chat (SSE)  ← 发送问题，agent 从记忆系统检索作答
      │
      └─→ 结果写入 eval_results.json
```

**核心接口：`POST /api/console/chat`（SSE 流式）**

这是 QwenPaw 的用户→agent 消息接口，返回 Server-Sent Events 流。脚本通过 `requests` 的 `stream=True` 消费事件流，从 `data: {...}` 事件中提取文本内容。

> **注意**：`/api/messages/send` 是 agent→用户 的推送接口（方向相反），不可用于评测。

---

## 4. 认证机制

QwenPaw 使用 **Bearer Token** 认证（非 Basic Auth）。

```
POST /api/auth/login
Body: {"username": "admin", "password": "xxx"}
Response: {"token": "eyJ..."}
```

获取 Token 后，所有请求头携带：
```
Authorization: Bearer <token>
```

脚本启动时自动调用 `_login()` 获取 Token，全局存储在 `_BEARER_TOKEN` 变量中，并通过 `_base_headers()` 注入所有后续请求。

---

## 5. 核心实现流程

### 5.1 对话喂入（feed_conversation）

每个 LoCoMo session 被**整体打包成一条自然语言大消息**，通过 `"Remember to your memory, ..."` 的指令让 agent 主动将其存入长期记忆系统。每个 session 使用独立的临时 `session_id`，注入完毕后 context 自然隔离（reset），避免上下文积压。

```
for session in [1, 2, 3, 4]:
    将该 session 的所有 turn 拼成对话文本：
        "Speaker: text"（若有图片/描述则拼入）
    
    构建整体消息：
        "Remember to your memory, [group chat conversation: {date}]\n\n
         Alice: ...\n
         Bob: ...\n
         ..."
    
    POST /api/console/chat（ingest_session_id, collect_reply=True）
    ← 等待 agent 确认已记忆
    sleep(TURN_DELAY)

返回最后一个有内容 session 的日期字符串（供 QA 使用）
```

**关键设计：**
- 每个 session 用 `ingest_{sample_id}_s{N}` 作为独立 session_id，4 个 session 互相隔离
- `collect_reply=True`：等待 agent 完整回复（确认已记忆）后再处理下一个 session
- 图片信息优先使用 `img_url`，其次 `blip_caption`

### 5.2 QA 提问（evaluate_sample）

QA 阶段使用全新的 `eval_{sample_id}` session，agent 从记忆系统中检索信息作答，不依赖任何对话上下文。

```
eval_session_id = f"eval_{safe_id}_{timestamp}"

for qa in sample["qa"]:
    构建 prompt：
        若有日期：
            "Current date: {last_date_str}\nAnswer the question directly: {question}"
        否则：
            "Answer the question directly: {question}"
    
    POST /api/console/chat（eval_session_id, collect_reply=True）
    judge_answer(category, expected, got)
```

**prompt 设计说明：**
- `Current date: {date}`：帮助 agent 正确理解问题中的相对时间表达（如"最近""上次"），取自最后一个有内容 session 的日期
- `Answer the question directly:`：要求直接给出答案，便于 judge 模块提取关键词，不引导 agent 去查记忆

### 5.3 SSE 事件解析

```python
for raw_line in resp.iter_lines():
    line = raw_line.decode("utf-8")
    if not line.startswith("data:"):
        continue
    event = json.loads(line[5:].strip())
    
    # 兼容多种字段格式
    content = event.get("content", "")   # 主要字段
    text    = event.get("text", "")      # 备选字段
    output  = event.get("output", "")    # 部分版本
```

---

## 6. 评测指标（5 个 Category）

| Category | 类型 | 描述 |
|----------|------|------|
| 1 | Factual | 直接从对话提取事实（如"Caroline 的身份"） |
| 2 | Temporal | 时间推理（如"Caroline 何时演讲"） |
| 3 | Inferential | 跨轮隐含逻辑推断 |
| 4 | General QA | 综合理解问答 |
| 5 | Adversarial | 识别错误归因（把 A 的事问成 B 的） |

### 判题逻辑（judge_answer）

```python
# Category 1~4：关键词包含匹配
if expected.lower() in got.lower():
    return True

# Category 5：额外接受"纠正错误"的回答
correction_signals = ["actually", "incorrect", "wrong", "not ", ...]
if any(sig in got.lower() for sig in correction_signals):
    return True
```

---

## 7. 运行方式

### 环境变量

```bash
export QWENPAW_BASE_URL=http://127.0.0.1:8088/api
export QWENPAW_API_USER=admin
export QWENPAW_API_PASS=88888888
```

### 运行命令

```bash
python eval_locomo.py \
  --data locomo_small.json \
  --agent-id locomo_eval \
  --output eval_results/results.json \
  --answer-timeout 120
```

### 输出示例（控制台）

```
================================================================
  LoCoMo × QwenPaw 评测  (v4 — 自然语言记忆注入版)
================================================================
  [Session 1] 1:56 pm on 8 May, 2023 — 18 条对话
  [Session 2] 1:14 pm on 25 May, 2023 — 17 条对话
  ...
  → 共喂入 76 条对话
  [✓] Cat1 | What did Caroline research?
       期望: Adoption agencies
       回答: Caroline researched adoption agencies.
  [✗] Cat2 | When did Melanie run a charity race?
       期望: The sunday before 25 May 2023
       回答: Last Saturday.
================================================================
  EVALUATION METRICS
================================================================
  Cat1 Factual     [████████████░░░░░░░░]  5/ 6 = 83.3%
  Cat2 Temporal    [████████░░░░░░░░░░░░]  5/11 = 45.5%
  Cat3 Inferential [████████████████████]  2/ 2 = 100.0%
  Cat4 General QA  [████████████████░░░░] 22/27 = 81.5%
  Cat5 Adversarial [████████████░░░░░░░░]  4/ 6 = 66.7%
  ──────────────────────────────────────────────────────────
  Overall                    38/52 = 73.1%
================================================================
```

---

## 8. 输出文件结构（eval_results.json）

```json
{
  "config": {
    "base_url": "http://127.0.0.1:8088/api",
    "agent_id": "locomo_eval",
    "data_file": "locomo_small.json",
    "answer_timeout": 120.0
  },
  "metrics": {
    "category_1": {"correct": 5, "total": 6, "accuracy": 0.8333},
    "overall":    {"correct": 38, "total": 52, "accuracy": 0.7308}
  },
  "results": [
    {
      "sample_id": "conv-26",
      "category": 1,
      "question": "What did Caroline research?",
      "expected": "Adoption agencies",
      "got": "Caroline researched adoption agencies.",
      "correct": true,
      "evidence": ["D2:8"]
    },
    ...
  ]
}
```

---

## 9. 性能与限制

| 项目 | 说明 |
|------|------|
| 喂入速度 | 4 个 session × 约 10~60s/session = 约 1~5 分钟（每 session 一次请求） |
| 提问速度 | 52 题 × 5~30s/题 = 约 5~25 分钟 |
| 判题方式 | 关键词匹配，无语义理解，可能有误判 |
| 样本数量 | 当前仅 1 个 sample，结果仅供参考 |
| Token 有效期 | Bearer Token 默认 7 天，过期需重新运行脚本登录 |

---

## 10. 已排查的问题记录

| 错误 | 原因 | 解决方法 |
|------|------|---------|
| 401 Not authenticated | `/api/messages/send` 使用 Basic Auth 而非 Bearer Token | 改为先 `POST /auth/login` 获取 Token |
| Chat 列表为空 | `/api/messages/send` 是 agent→user 推送，方向相反 | 改用 `POST /api/console/chat` |
| 405 Method Not Allowed | Docker 镜像版本过旧，不支持 `/console/chat/task` | 改用旧版支持的 `/console/chat`（SSE） |
| 404 | `/api/console/chat` 需要升级镜像或确认路由 | 升级镜像后接口可用 |
| 轮询超时 | 旧代码用 `/api/chats/{chat_id}` 轮询，但 chat 从未创建 | 直接消费 SSE 流获取回复 |

---

## 9. 性能与限制

| 项目 | 说明 |
|------|------|
| 喂入速度 | 4 个 session × 约 10~60s/session = 约 1~5 分钟（每 session 一次请求） |
| 提问速度 | 52 题 × 5~30s/题 = 约 5~25 分钟 |
| 判题方式 | 关键词匹配，无语义理解，可能有误判 |
| 样本数量 | 当前仅 1 个 sample，结果仅供参考 |
| Token 有效期 | Bearer Token 默认 7 天，过期需重新运行脚本登录 |

---

## 10. 已排查的问题记录

| 错误 | 原因 | 解决方法 |
|------|------|---------|
| 401 Not authenticated | `/api/messages/send` 使用 Basic Auth 而非 Bearer Token | 改为先 `POST /auth/login` 获取 Token |
| Chat 列表为空 | `/api/messages/send` 是 agent→user 推送，方向相反 | 改用 `POST /api/console/chat` |
| 405 Method Not Allowed | Docker 镜像版本过旧，不支持 `/console/chat/task` | 改用旧版支持的 `/console/chat`（SSE） |
| 404 | `/api/console/chat` 需要升级镜像或确认路由 | 升级镜像后接口可用 |
| 轮询超时 | 旧代码用 `/api/chats/{chat_id}` 轮询，但 chat 从未创建 | 直接消费 SSE 流获取回复 |
