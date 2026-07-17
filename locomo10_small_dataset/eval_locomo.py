# -*- coding: utf-8 -*-
"""
LoCoMo × QwenPaw 评测脚本  (v4 — 自然语言记忆注入版)

用法：
    python eval_locomo.py --data locomo_small.json --agent-id locomo_eval
    python eval_locomo.py --data locomo_small.json --agent-id locomo_eval --output results.json

环境变量：
    QWENPAW_BASE_URL   QwenPaw API 地址，默认 http://127.0.0.1:8088/api
    QWENPAW_API_USER   认证用户名（Docker 部署开启 Auth 时填写）
    QWENPAW_API_PASS   认证密码

接口（已验证）：
    POST /api/console/chat   — SSE 流式，user→agent 发消息并获取回复
    认证：Bearer Token（通过 POST /api/auth/login 获取）
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from pathlib import Path

import requests

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# ─── 配置 ─────────────────────────────────────────────────────────────────────
BASE_URL: str = os.getenv("QWENPAW_BASE_URL", "http://127.0.0.1:8088/api")
API_USER: str = os.getenv("QWENPAW_API_USER", "")
API_PASS: str = os.getenv("QWENPAW_API_PASS", "")

USER_ID = "evaluator"

TURN_DELAY: float = 0.3       # session 之间的间隔（秒）
ANSWER_TIMEOUT: float = 120.0  # SSE 流等待超时（秒）
REQUEST_TIMEOUT: int = 130     # HTTP 请求超时（需大于 ANSWER_TIMEOUT）

_BEARER_TOKEN: str = ""
# ──────────────────────────────────────────────────────────────────────────────


# ─── 认证 ─────────────────────────────────────────────────────────────────────

def _login() -> bool:
    """登录获取 Bearer Token。无 API_USER 时跳过（pip 本地无认证部署）。"""
    global _BEARER_TOKEN
    if not API_USER:
        return True
    try:
        resp = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": API_USER, "password": API_PASS},
            timeout=30,
        )
    except requests.exceptions.ConnectionError:
        return False
    if not resp.ok:
        print(f"[!] 登录失败: {resp.status_code} {resp.text[:120]}")
        return False
    token = resp.json().get("token", "")
    if not token:
        print(f"[!] 登录响应中未找到 token: {resp.json()}")
        return False
    _BEARER_TOKEN = token
    print(f"[✓] 登录成功，Token 前 12 位：{token[:12]}...")
    return True


def _base_headers(extra: dict | None = None) -> dict:
    """构建带 Bearer Token 的请求头。"""
    h: dict = {"Content-Type": "application/json"}
    if _BEARER_TOKEN:
        h["Authorization"] = f"Bearer {_BEARER_TOKEN}"
    if extra:
        h.update(extra)
    return h


# ─── SSE 核心：POST /api/console/chat ──────────────────────────────────────────

def _sse_chat(
    agent_id: str,
    session_id: str,
    text: str,
    collect_reply: bool = True,
    timeout: float = ANSWER_TIMEOUT,
) -> str:
    """
    通过 POST /api/console/chat（SSE 流式）向 agent 发消息。

    Args:
        agent_id:      目标 agent 的 ID
        session_id:    会话 ID（同一 session 维持对话记忆）
        text:          发送的文本内容
        collect_reply: True 时收集并返回完整回复文本；False 时只等流结束
        timeout:       等待流结束的最大秒数

    Returns:
        agent 的文本回复（collect_reply=False 时返回空字符串）
    """
    payload = {
        "user_id": USER_ID,
        "session_id": session_id,
        "input": [
            {
                "role": "user",
                "content": [{"type": "text", "text": text}],
            }
        ],
    }

    headers = _base_headers({"X-Agent-Id": agent_id, "Accept": "text/event-stream"})

    try:
        with requests.post(
            f"{BASE_URL}/console/chat",
            json=payload,
            headers=headers,
            stream=True,
            timeout=timeout,
        ) as resp:
            if not resp.ok:
                print(f"  [!] /console/chat 请求失败: {resp.status_code} {resp.text[:120]}")
                return ""

            if not collect_reply:
                # 只消费流，不收集内容
                for _ in resp.iter_lines():
                    pass
                return ""

            # 收集 SSE 流中的文本片段
            reply_parts: list[str] = []
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                # iter_lines 返回 bytes 或 str
                line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if data_str in ("", "[DONE]"):
                    continue
                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                # 跳过 token 用量等元数据事件
                ev_type = event.get("type", "")
                if ev_type in ("turn_usage", "error", "ping"):
                    continue

                # 提取文本内容（兼容多种字段格式）
                content = event.get("content", "")
                if isinstance(content, str) and content:
                    reply_parts.append(content)
                elif isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            t = c.get("text", "")
                            if t:
                                reply_parts.append(t)

                # 兼容直接放在 text 字段的格式
                text_field = event.get("text", "")
                if isinstance(text_field, str) and text_field and not content:
                    reply_parts.append(text_field)

                # output 字段（部分版本）
                output = event.get("output", "")
                if isinstance(output, str) and output and not content and not text_field:
                    reply_parts.append(output)

            return "".join(reply_parts).strip()

    except requests.exceptions.Timeout:
        print(f"  [!] SSE 流等待超时（>{timeout}s）")
        return ""
    except requests.exceptions.RequestException as e:
        print(f"  [!] 请求异常: {e}")
        return ""


# ─── Agent 管理 ───────────────────────────────────────────────────────────────

def create_eval_agent(agent_id: str) -> str:
    resp = requests.post(
        f"{BASE_URL}/agents",
        json={
            "id": agent_id,
            "name": "LoCoMo Evaluator",
            "description": "Automated evaluation agent for LoCoMo benchmark.",
            "language": "en",
        },
        headers=_base_headers(),
        timeout=30,
    )
    if resp.status_code == 201:
        print(f"[✓] Agent '{agent_id}' 创建成功")
    elif resp.status_code in (400, 409):
        print(f"[~] Agent '{agent_id}' 已存在，直接复用")
    else:
        print(f"[!] 创建 agent 异常: {resp.status_code} {resp.text[:120]}")
    return agent_id


# ─── 对话喂入 ─────────────────────────────────────────────────────────────────

def feed_conversation(agent_id: str, sample_id: str, conversation: dict) -> str:
    """
    将每个 session 的所有对话整体打包成一条自然语言消息发给 agent，
    agent 会主动将其存入记忆系统。每个 session 使用独立的 context，
    注入完毕后自然 reset，避免上下文积压。

    Returns:
        最后一个有内容 session 的日期字符串（供 QA 阶段使用）
    """
    last_date_str = ""
    turns_fed = 0

    for s_idx in range(1, 5):
        key = f"session_{s_idx}"
        date_key = f"session_{s_idx}_date_time"
        if key not in conversation:
            continue

        turns = conversation[key]
        if not turns:
            continue

        date_str = conversation.get(date_key, f"Session {s_idx}")
        last_date_str = date_str

        print(f"    [Session {s_idx}] {date_str} — {len(turns)} 条对话")

        # 将整个 session 的所有 turn 拼成对话文本
        lines: list[str] = []
        for turn in turns:
            speaker = turn.get("speaker", "Unknown")
            text = turn.get("text", "")
            imgs = turn.get("img_url", [])
            img = imgs[0] if imgs else None
            caption = turn.get("blip_caption", "")

            if img:
                text = f"[Image URL: {img}] {text}".strip()
            elif caption:
                text = f"{text} [Image description: {caption}]".strip()

            lines.append(f"{speaker}: {text}")
            turns_fed += 1

        # 整体打包成一条自然语言消息，让 agent 主动存入记忆系统
        big_message = (
            f"Remember to your memory, [group chat conversation: {date_str}]\n\n"
            + "\n".join(lines)
        )

        # 每个 session 用独立的临时 session_id，注入后 context 自然隔离
        ingest_session_id = f"ingest_{sample_id}_s{s_idx}"
        _sse_chat(
            agent_id, ingest_session_id,
            big_message,
            collect_reply=True,
            timeout=ANSWER_TIMEOUT,
        )
        time.sleep(TURN_DELAY)

    print(f"    → 共喂入 {turns_fed} 条对话")
    return last_date_str


# ─── 评判 ─────────────────────────────────────────────────────────────────────

_CORRECTION_SIGNALS = [
    "actually", "correction", "incorrect", "wrong", "not ", "it was",
    "she did", "he did", "不是", "实际上", "并非", "错误", "纠正", "应该是",
]


def judge_answer(category: int, expected: str, got: str) -> bool:
    exp_lower = expected.lower().strip()
    got_lower = got.lower().strip()
    if exp_lower in got_lower:
        return True
    if len(got_lower) > 3 and got_lower in exp_lower:
        return True
    if category == 5:
        return any(sig in got_lower for sig in _CORRECTION_SIGNALS)
    return False


# ─── 单 sample 评测 ───────────────────────────────────────────────────────────

def evaluate_sample(agent_id: str, sample: dict) -> list[dict]:
    sample_id = sample["sample_id"]
    safe_id = sample_id.replace("-", "_")

    print(f"\n{'='*64}")
    print(f"  Sample : {sample_id}")
    print(f"  QA 数量: {len(sample.get('qa', []))}")
    print(f"{'='*64}")

    print("[1/2] 喂入对话...")
    last_date_str = feed_conversation(agent_id, safe_id, sample["conversation"])

    print("[2/2] 开始 QA 评测...")
    results: list[dict] = []
    qa_list = sample.get("qa", [])

    # QA 阶段使用独立的新 session，agent 从记忆系统中检索作答
    eval_session_id = f"eval_{safe_id}_{int(time.time())}"

    iter_qa = tqdm(qa_list, desc="  QA") if HAS_TQDM else qa_list
    for qa in iter_qa:
        question = qa["question"]
        expected = str(qa["answer"])
        category = qa.get("category", 0)
        evidence = qa.get("evidence", [])

        if last_date_str:
            prompt = f"Current date: {last_date_str}\nAnswer the question directly: {question}"
        else:
            prompt = f"Answer the question directly: {question}"

        got = _sse_chat(
            agent_id, eval_session_id,
            prompt,
            collect_reply=True,
            timeout=ANSWER_TIMEOUT,
        )
        if not got:
            got = "[TIMEOUT/NO_REPLY]"

        correct = judge_answer(category, expected, got)
        results.append({
            "sample_id": sample_id,
            "category": category,
            "question": question,
            "expected": expected,
            "got": got,
            "correct": correct,
            "evidence": evidence,
        })

        mark = "✓" if correct else "✗"
        print(
            f"  [{mark}] Cat{category} | {question[:55]}\n"
            f"       期望: {expected}\n"
            f"       回答: {got[:100]}"
        )

    return results


# ─── 指标统计 ─────────────────────────────────────────────────────────────────

def compute_metrics(results: list[dict]) -> dict:
    cat_correct: dict[int, int] = defaultdict(int)
    cat_total: dict[int, int] = defaultdict(int)
    for r in results:
        cat = r["category"]
        cat_total[cat] += 1
        if r.get("correct"):
            cat_correct[cat] += 1
    metrics: dict = {}
    for cat in sorted(cat_total.keys()):
        total = cat_total[cat]
        correct = cat_correct[cat]
        metrics[f"category_{cat}"] = {
            "correct": correct,
            "total": total,
            "accuracy": round(correct / total, 4) if total else 0.0,
        }
    total_all = len(results)
    correct_all = sum(r.get("correct", False) for r in results)
    metrics["overall"] = {
        "correct": correct_all,
        "total": total_all,
        "accuracy": round(correct_all / total_all, 4) if total_all else 0.0,
    }
    return metrics


def print_metrics(metrics: dict) -> None:
    cat_labels = {
        1: "Factual    ", 2: "Temporal   ", 3: "Inferential",
        4: "General QA ", 5: "Adversarial",
    }
    print(f"\n{'='*64}")
    print("  EVALUATION METRICS")
    print(f"{'='*64}")
    for key, v in metrics.items():
        if key.startswith("category_"):
            cat_num = int(key.split("_")[1])
            label = cat_labels.get(cat_num, f"Category {cat_num}")
            bar_fill = int(v["accuracy"] * 20)
            bar = "█" * bar_fill + "░" * (20 - bar_fill)
            print(
                f"  Cat{cat_num} {label} [{bar}] "
                f"{v['correct']:>2}/{v['total']:>2} = {v['accuracy']:.1%}"
            )
    v = metrics["overall"]
    print(f"  {'─'*58}")
    print(f"  Overall                    {v['correct']:>2}/{v['total']:>2} = {v['accuracy']:.1%}")
    print(f"{'='*64}\n")


# ─── 主函数 ───────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="在 QwenPaw 上评测 LoCoMo 长期记忆数据集")
    p.add_argument("--data", default="locomo_small.json")
    p.add_argument("--agent-id", default="locomo_eval")
    p.add_argument("--output", default="eval_results.json")
    p.add_argument("--base-url", default=None)
    p.add_argument("--answer-timeout", type=float, default=ANSWER_TIMEOUT)
    p.add_argument("--delete-after", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    global BASE_URL, ANSWER_TIMEOUT, REQUEST_TIMEOUT
    if args.base_url:
        BASE_URL = args.base_url
    ANSWER_TIMEOUT = args.answer_timeout
    REQUEST_TIMEOUT = int(ANSWER_TIMEOUT) + 10

    print("=" * 64)
    print("  LoCoMo × QwenPaw 评测  (v4 — 自然语言记忆注入版)")
    print("=" * 64)
    print(f"  API 地址 : {BASE_URL}")
    print(f"  认证     : {'Bearer Token' if API_USER else '无（pip 本地部署）'}")
    print(f"  数据文件 : {args.data}")
    print(f"  Agent ID : {args.agent_id}")
    print(f"  输出文件 : {args.output}")
    print(f"  SSE 超时 : {ANSWER_TIMEOUT}s")
    print("=" * 64)

    # 登录
    if API_USER:
        print(f"\n[Auth] 正在登录（用户：{API_USER}）...")
        if not _login():
            print("[ERROR] 登录失败，请检查 QWENPAW_API_USER / QWENPAW_API_PASS")
            raise SystemExit(1)

    # 连通性检查
    try:
        requests.get(f"{BASE_URL}/agents", headers=_base_headers(), timeout=10)
    except requests.exceptions.ConnectionError:
        print(f"\n[ERROR] 无法连接到 QwenPaw: {BASE_URL}")
        raise SystemExit(1)

    # 读取数据集
    data_path = Path(args.data)
    if not data_path.exists():
        print(f"[ERROR] 数据文件不存在: {data_path}")
        raise SystemExit(1)
    with open(data_path, encoding="utf-8") as f:
        dataset: list[dict] = json.load(f)
    print(f"\n已加载 {len(dataset)} 个样本\n")

    # 创建 agent
    agent_id = create_eval_agent(args.agent_id)

    # 评测
    all_results: list[dict] = []
    try:
        for sample in dataset:
            results = evaluate_sample(agent_id, sample)
            all_results.extend(results)
    finally:
        if all_results:
            metrics = compute_metrics(all_results)
            out_data = {
                "config": {
                    "base_url": BASE_URL,
                    "agent_id": agent_id,
                    "data_file": str(data_path),
                    "answer_timeout": ANSWER_TIMEOUT,
                },
                "metrics": metrics,
                "results": all_results,
            }
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(out_data, f, ensure_ascii=False, indent=2)
            print_metrics(metrics)
            print(f"[✓] 结果已保存到 {out_path}")

        if args.delete_after:
            requests.delete(
                f"{BASE_URL}/agents/{agent_id}",
                headers=_base_headers(),
                timeout=10,
            )


if __name__ == "__main__":
    main()