# -*- coding: utf-8 -*-
"""
LoCoMo × QwenPaw 评测脚本

用法：
    python eval_locomo.py --data locomo_small.json --agent-id locomo_eval
    python eval_locomo.py --data locomo_small.json --agent-id locomo_eval --output results.json

环境变量：
    QWENPAW_BASE_URL   QwenPaw API 地址，默认 http://127.0.0.1:8088/api
    QWENPAW_API_USER   认证用户名（Docker 部署开启 Auth 时填写，pip 方式无需）
    QWENPAW_API_PASS   认证密码（Docker 部署开启 Auth 时填写，pip 方式无需）

接口说明（已从源码确认）：
    - 用户→agent 发消息：POST /api/console/chat/task（后台任务）
    - 轮询任务结果：    GET  /api/console/chat/task/{task_id}
    - /api/messages/send 是 agent→用户 推送，不适合评测
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

TURN_DELAY: float = 0.5          # 喂对话 turn 之间的间隔（秒）
ANSWER_TIMEOUT: float = 120.0    # 等待 agent 回答的最大时间（秒）
POLL_INTERVAL: float = 2.0       # 轮询任务状态的间隔（秒）
REQUEST_TIMEOUT: int = 60        # HTTP 请求超时（秒）

_BEARER_TOKEN: str = ""
# ──────────────────────────────────────────────────────────────────────────────


# ─── 认证 ─────────────────────────────────────────────────────────────────────

def _login() -> bool:
    global _BEARER_TOKEN
    if not API_USER:
        return True
    try:
        resp = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": API_USER, "password": API_PASS},
            timeout=REQUEST_TIMEOUT,
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


def _auth_headers(extra: dict | None = None) -> dict:
    h: dict = {}
    if _BEARER_TOKEN:
        h["Authorization"] = f"Bearer {_BEARER_TOKEN}"
    if extra:
        h.update(extra)
    return h


def _request(method: str, path: str, **kwargs) -> requests.Response:
    url = f"{BASE_URL}{path}"
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    caller_headers = kwargs.pop("headers", {})
    kwargs["headers"] = _auth_headers(caller_headers)
    return requests.request(method, url, **kwargs)


# ─── Agent 管理 ───────────────────────────────────────────────────────────────

def create_eval_agent(agent_id: str) -> str:
    resp = _request(
        "POST", "/agents",
        json={
            "id": agent_id,
            "name": "LoCoMo Evaluator",
            "description": "Automated evaluation agent for LoCoMo benchmark.",
            "language": "en",
        },
    )
    if resp.status_code == 201:
        print(f"[✓] Agent '{agent_id}' 创建成功")
    elif resp.status_code in (400, 409):
        print(f"[~] Agent '{agent_id}' 已存在，直接复用")
    else:
        print(f"[!] 创建 agent 异常: {resp.status_code} {resp.text[:120]}")
    return agent_id


def delete_eval_agent(agent_id: str) -> None:
    if agent_id == "default":
        return
    resp = _request("DELETE", f"/agents/{agent_id}")
    if resp.ok:
        print(f"[✓] Agent '{agent_id}' 已删除")


# ─── 核心：通过 /console/chat/task 发消息并等待回复 ──────────────────────────

def _chat_task(
    agent_id: str,
    session_id: str,
    text: str,
    timeout: float = ANSWER_TIMEOUT,
) -> str | None:
    """
    发送消息给 agent 并等待回复。

    使用 POST /api/console/chat/task 提交后台任务，然后轮询
    GET /api/console/chat/task/{task_id} 直到任务完成或超时。

    返回 agent 的文字回复，超时或失败返回 None。
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
        "timeout": timeout,
    }

    # 提交后台任务
    resp = _request(
        "POST", "/console/chat/task",
        headers={"X-Agent-Id": agent_id},
        json=payload,
    )
    if not resp.ok:
        print(f"  [!] 提交任务失败: {resp.status_code} {resp.text[:120]}")
        return None

    task_id = resp.json().get("task_id")
    if not task_id:
        print(f"  [!] 响应中无 task_id: {resp.json()}")
        return None

    # 轮询任务结果
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        poll_resp = _request(
            "GET", f"/console/chat/task/{task_id}",
            headers={"X-Agent-Id": agent_id},
        )
        if not poll_resp.ok:
            continue

        data = poll_resp.json()
        status = data.get("status")

        if status == "finished":
            result = data.get("result", {})
            if result.get("status") == "failed":
                err = result.get("error", {}).get("message", "unknown error")
                print(f"  [!] 任务失败: {err}")
                return None

            # 从 output 字段提取文本回复
            output = result.get("output", [])
            if isinstance(output, list):
                texts = []
                for item in output:
                    if isinstance(item, dict):
                        content = item.get("content", "")
                        if isinstance(content, str) and content.strip():
                            texts.append(content.strip())
                        elif isinstance(content, list):
                            for c in content:
                                if isinstance(c, dict) and c.get("type") == "text":
                                    t = c.get("text", "").strip()
                                    if t:
                                        texts.append(t)
                if texts:
                    return " ".join(texts)

            # 尝试直接从 result.text 取
            if isinstance(result.get("text"), str):
                return result["text"].strip()

            return str(result)

    return None  # 超时


# ─── 对话喂入 ─────────────────────────────────────────────────────────────────

def feed_turn(agent_id: str, session_id: str, text: str) -> None:
    """
    向 agent 喂入单条对话 turn（不等回复，用于构建上下文）。
    使用后台任务接口，但不等待完成。
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
        "timeout": 60,
    }
    resp = _request(
        "POST", "/console/chat/task",
        headers={"X-Agent-Id": agent_id},
        json=payload,
    )
    if not resp.ok:
        print(f"  [!] 喂入 turn 失败: {resp.status_code} {resp.text[:80]}")
        return

    # 短暂等待，让 agent 处理完这条 turn 再发下一条
    task_id = resp.json().get("task_id")
    if task_id:
        deadline = time.time() + 60
        while time.time() < deadline:
            time.sleep(POLL_INTERVAL)
            pr = _request(
                "GET", f"/console/chat/task/{task_id}",
                headers={"X-Agent-Id": agent_id},
            )
            if pr.ok and pr.json().get("status") == "finished":
                break


def feed_conversation(agent_id: str, session_id: str, conversation: dict) -> None:
    """按时序将 4 个 session 的对话喂入 agent。"""
    turns_fed = 0
    for s_idx in range(1, 5):
        key = f"session_{s_idx}"
        date_key = f"session_{s_idx}_date_time"
        if key not in conversation:
            continue

        date_str = conversation.get(date_key, f"Session {s_idx}")
        turns = conversation[key]
        print(f"    [Session {s_idx}] {date_str} — {len(turns)} 条对话")

        # 注入时间背景（system 提示）
        feed_turn(
            agent_id, session_id,
            f"[System Context] The following conversation took place on: {date_str}. "
            "Please remember all details for future questions.",
        )
        time.sleep(TURN_DELAY)

        iter_turns = tqdm(turns, desc=f"  S{s_idx}", leave=False) if HAS_TQDM else turns
        for turn in iter_turns:
            speaker = turn.get("speaker", "Unknown")
            text = turn.get("text", "")
            imgs = turn.get("img_url", [])
            img = imgs[0] if imgs else None
            caption = turn.get("blip_caption", "")

            if caption and not img:
                text = f"{text} [Image description: {caption}]"
            elif img:
                text = f"[Image URL: {img}]\n{text}"

            feed_turn(agent_id, session_id, f"{speaker}: {text}")
            turns_fed += 1
            time.sleep(TURN_DELAY)

    print(f"    → 共喂入 {turns_fed} 条对话")


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
    session_id = f"eval_{sample_id.replace('-', '_')}_{int(time.time())}"

    print(f"\n{'='*64}")
    print(f"  Sample : {sample_id}")
    print(f"  Session: {session_id}")
    print(f"  QA 数量: {len(sample.get('qa', []))}")
    print(f"{'='*64}")

    print("[1/2] 喂入对话...")
    feed_conversation(agent_id, session_id, sample["conversation"])

    print("[2/2] 开始 QA 评测...")
    results: list[dict] = []
    qa_list = sample.get("qa", [])

    iter_qa = tqdm(qa_list, desc="  QA") if HAS_TQDM else qa_list
    for qa in iter_qa:
        question = qa["question"]
        expected = str(qa["answer"])
        category = qa.get("category", 0)
        evidence = qa.get("evidence", [])

        got_raw = _chat_task(
            agent_id, session_id,
            f"Based on our conversation history, please answer this question concisely: {question}",
            timeout=ANSWER_TIMEOUT,
        )
        got = got_raw if got_raw else "[TIMEOUT/ERROR]"
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

        status = "✓" if correct else "✗"
        print(
            f"  [{status}] Cat{category} | {question[:55]}\n"
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
    global BASE_URL, ANSWER_TIMEOUT
    if args.base_url:
        BASE_URL = args.base_url
    ANSWER_TIMEOUT = args.answer_timeout

    print("=" * 64)
    print("  LoCoMo × QwenPaw 评测")
    print("=" * 64)
    print(f"  API 地址 : {BASE_URL}")
    print(f"  认证     : {'Bearer Token' if API_USER else '无（pip 本地部署）'}")
    print(f"  数据文件 : {args.data}")
    print(f"  Agent ID : {args.agent_id}")
    print(f"  输出文件 : {args.output}")
    print(f"  等待超时 : {ANSWER_TIMEOUT}s")
    print("=" * 64)

    # 登录
    if API_USER:
        print(f"\n[Auth] 正在登录 QwenPaw（用户：{API_USER}）...")
        if not _login():
            print("[ERROR] 登录失败，请检查 QWENPAW_API_USER / QWENPAW_API_PASS")
            raise SystemExit(1)

    # 检查连通性
    try:
        _request("GET", "/agents")
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
            output = {
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
                json.dump(output, f, ensure_ascii=False, indent=2)
            print_metrics(metrics)
            print(f"[✓] 结果已保存到 {out_path}")

        if args.delete_after:
            _request("DELETE", f"/agents/{agent_id}")


if __name__ == "__main__":
    main()