# LoCoMo × QwenPaw 评测使用指南（pip 方式）

## 前置条件

- 服务器已安装 Python 3.11 ~ 3.13
- 已有可用的 LLM API Key（DashScope / OpenAI / DeepSeek 任选一）

---

## 第一步：上传评测文件到服务器

在本地机器执行：

```bash
scp locomo10_small_dataset/* user@your-server:~/qwenpaw-eval/
```

---

## 第二步：安装 QwenPaw

在服务器上执行：

```bash
# 创建虚拟环境（推荐，避免污染系统 Python）
python3 -m venv ~/qwenpaw_env
source ~/qwenpaw_env/bin/activate

# 安装 QwenPaw（使用国内镜像加速）
pip install qwenpaw -i https://mirrors.aliyun.com/pypi/simple/

# 初始化配置
qwenpaw init --defaults
```

---

## 第三步：配置 API Key

在启动 QwenPaw 前，设置你的模型 API Key：

```bash
# DashScope（通义千问，国内直连，推荐）
export DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx

# 或 OpenAI
# export OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx

# 或 DeepSeek（国内直连，无需代理）
# export DEEPSEEK_API_KEY=xxxxxxxxxxxxxxxx
```

---

## 第四步：启动 QwenPaw

```bash
# 激活虚拟环境（如果还没激活）
source ~/qwenpaw_env/bin/activate

# 后台运行，日志写入 qwenpaw.log
nohup qwenpaw app > ~/qwenpaw.log 2>&1 &

# 等待约 30 秒，验证是否启动成功
curl http://127.0.0.1:8088/healthz
# 返回 {"status": "ok"} 即成功
```

---

## 第五步：在浏览器配置模型

打开浏览器，访问 `http://服务器IP:8088`

进入 **设置 → 模型**，选择对应提供商（DashScope / OpenAI / DeepSeek），
确认 API Key 已加载，点击启用模型。

> **无法直接访问的解决方法（SSH 端口转发）：**
> ```bash
> # 在本地机器执行
> ssh -L 8088:127.0.0.1:8088 user@your-server
> # 然后本地浏览器访问 http://127.0.0.1:8088
> ```

---

## 第六步：安装评测脚本依赖

```bash
cd ~/qwenpaw-eval

# 新建评测专用虚拟环境（与 QwenPaw 虚拟环境分开）
python3 -m venv eval_env
source eval_env/bin/activate

pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

---

## 第七步：运行评测

```bash
cd ~/qwenpaw-eval
mkdir -p eval_results

# QwenPaw pip 方式本地运行，无需认证
export QWENPAW_BASE_URL=http://127.0.0.1:8088/api

python eval_locomo.py \
  --data locomo_small.json \
  --agent-id locomo_eval \
  --output eval_results/results.json
```

评测会自动执行以下流程：

1. 创建名为 `locomo_eval` 的专用 agent
2. 将 4 个 session（共约 76 条）的对话按时间顺序喂给 agent
3. 对 52 个 QA 问题逐一提问，并自动拉取 agent 回答
4. 按 5 个 category 统计准确率，打印指标摘要

---

## 第八步：查看结果

评测结束后，控制台打印指标摘要：

```
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
```

完整结果查看：

```bash
cat eval_results/results.json
```

---

## 常用运维命令

```bash
# 查看 QwenPaw 实时日志
tail -f ~/qwenpaw.log

# 停止 QwenPaw
pkill -f "qwenpaw app"

# 重启 QwenPaw
source ~/qwenpaw_env/bin/activate
nohup qwenpaw app > ~/qwenpaw.log 2>&1 &

# 重置评测 agent（清空记忆，从头重新跑）
curl -X DELETE http://127.0.0.1:8088/api/agents/locomo_eval

# 使用不同 agent ID 运行新一轮评测（保留上次结果）
python eval_locomo.py --agent-id locomo_eval_v2 --output eval_results/results_v2.json
```

---

## Category 指标说明

| Category | 类型 | 测试能力 | 预期准确率 |
|----------|------|---------|----------|
| 1 | 事实性 | 从对话中直接提取事实 | 50–70% |
| 2 | 时间推理 | 推算日期、时长、事件顺序 | 40–60% |
| 3 | 推断性 | 跨轮推断、隐含逻辑 | 30–50% |
| 4 | 综合问答 | 标准理解问答 | 60–75% |
| 5 | 对抗性 | 识别并纠正错误归因 | 20–40% |

> **提升准确率的建议：**
> - 在控制台为 `locomo_eval` agent 开启 **ReMe 长期记忆**
> - 选择上下文窗口 ≥ 32K 的模型（qwen-plus、gpt-4o 等）