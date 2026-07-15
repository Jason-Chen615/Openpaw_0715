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
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# ─── 配置（可通过环境变量覆盖）─────────────────────────────────────────────────
BASE_URL: str = os.getenv("QWENPAW_BASE_URL", "http://127.0.0.1:8088/api")
API_USER: str = os.getenv("QWENPAW_API_USER", "")
API_PASS: str = os.getenv("QWENPAW_API_PASS", "")

CHANNEL = "console"
USER_ID = "evaluator"

# 发送 turn 之间的间隔（秒）
TURN_DELAY: float = 0.5
# 提问后拉取回答的最大等待时间（秒）
ANSWER_TIMEOUT: float = 30.0
# 拉取回答的轮询间隔（秒）
POLL_INTERVAL: float = 1.0
# HTTP 请求超时（秒）
REQUEST_TIMEOUT: int = 30
# ──────────────────────────────────────────────────────────────────────────────


def _auth() -> HTTPBasicAuth | None:
    """返回 Basic Auth 对象，若未配置用户名则返回 None（pip 本地方式无需认证）。"""
    if API_USER:
        return HTTPBasicAuth(API_USER, API_PASS)
    return None


def _request(method: str, path: str, **kwargs) -> requests.Response:
    """统一请求封装，附带认证与超时。"""
    url = f"{BASE_URL}{path}"
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    auth = _auth()
    if auth:
        kwargs["auth"] = auth
    resp = requests.request(method, url, **kwargs)
    return resp


# ─── Agent 管理 ───────────────────────────────────────────────────────────────

def create_eval_agent(agent_id: str) -> str:
    """
    创建专用评测 agent。
    若 agent 已存在（400/409），则直接复用。
    """
    resp = _request(
        "POST",
        "/agents",
        json={
            "id": agent_id,
            "name": "LoCoMo Evaluator",
            "description": "Automated evaluation agent for LoCoMo long-context memory benchmark.",
            "language": "en",
        },
    )
    if resp.status_code == 201:
        print(f"[✓] Agent '{agent_id}' 创建成功")
    elif resp.status_code in (400, 409):
        print(f"[~] Agent '{agent_id}' 已存在，直接复用")
    else:
        print(f"[!] 创建 agent 返回异常状态: {resp.status_code} — {resp.text[:120]}")
    return agent_id


def delete_eval_agent(agent_id: str) -> None:
    """删除评测 agent（清理用，默认 agent 无法删除）。"""
    if agent_id == "default":
        return
    resp = _request("DELETE", f"/agents/{agent_id}")
    if resp.ok:
        print(f"[✓] Agent '{agent_id}' 已删除")
    else:
        print(f"[~] 无法删除 agent '{agent_id}': {resp.status_code}")


# ─── 消息发送 ─────────────────────────────────────────────────────────────────

def send_turn(
    agent_id: str,
    session_id: str,
    text: str,
    img_url: str | None = None,
) -> bool:
    """
    向 agent 喂入单条对话 turn。
    若提供 img_url，则拼入消息前缀（多模态模型直接处理；纯文本模型作为参考跳过）。
    """
    content = text
    if img_url:
        content = f"[Image URL: {img_url}]\n{text}"

    resp = _request(
        "POST",
        "/messages/send",
        headers={"X-Agent-Id": agent_id},
        json={
            "channel": CHANNEL,
            "target_user": USER_ID,
            "target_session": session_id,
            "text": content,
        },
    )
    if not resp.ok:
        print(f"  [!] send_turn 失败: {resp.status_code} {resp.text[:100]}")
        return False
    return True


# ─── 消息拉取（核心实现）─────────────────────────────────────────────────────

def _find_chat_id(agent_id: str, session_id: str) -> str | None:
    """
    通过 GET /api/chats?user_id=evaluator&channel=console 找到对应的 chat_id。
    QwenPaw 的 chat 由 (session_id, user_id, channel) 三元组唯一标识。
    """
    resp = _request(
        "GET",
        "/chats",
        headers={"X-Agent-Id": agent_id},
        params={"user_id": USER_ID, "channel": CHANNEL},
    )
    if not resp.ok:
        return None
    chats = resp.json()
    # 找到 session_id 匹配的 chat
    for chat in chats:
        if chat.get("session_id") == session_id:
            return chat.get("id")
    return None


def _get_last_assistant_message(agent_id: str, chat_id: str) -> str | None:
    """
    通过 GET /api/chats/{chat_id} 取最后一条 role=="assistant" 的消息内容。
    """
    resp = _request(
        "GET",
        f"/chats/{chat_id}",
        headers={"X-Agent-Id": agent_id},
    )
    if not resp.ok:
        return None
    data = resp.json()
    messages = data.get("messages", [])
    # 从后往前找第一条 assistant 消息
    for msg in reversed(messages):
        role = msg.get("role", "")
        if role in ("assistant", "agent"):
            # content 可能是字符串或列表
            content = msg.get("content", "")
            if isinstance(content, list):
                # 多模态消息：取文本部分
                parts = [c.get("text", "") for c in content if isinstance(c, dict) and "text" in c]
                return " ".join(parts).strip() or None
            return str(content).strip() or None
    return None


def poll_answer(
    agent_id: str,
    session_id: str,
    timeout: float = ANSWER_TIMEOUT,
    poll_interval: float = POLL_INTERVAL,
) -> str:
    """
    发完问题后轮询，返回 agent 的实际回答。

    流程：
      1. 先找到 session 对应的 chat_id
      2. 轮询 GET /api/chats/{chat_id}，取最新 assistant 消息
      3. 超时则返回 [TIMEOUT]
    """
    deadline = time.time() + timeout
    chat_id: str | None = None
    last_content: str | None = None

    # 先等一下让 agent 有时间产生回复
    time.sleep(poll_interval)

    while time.time() < deadline:
        # 延迟查找 chat_id（发消息后可能需要片刻才创建 chat 记录）
        if not chat_id:
            chat_id = _find_chat_id(agent_id, session_id)

        if chat_id:
            content = _get_last_assistant_message(agent_id, chat_id)
            if content and content != last_content:
                # 等待一个额外的轮询间隔，确保消息已完全写入（流式输出）
                time.sleep(poll_interval)
                final = _get_last_assistant_message(agent_id, chat_id)
                return final if final else content
            last_content = content

        time.sleep(poll_interval)

    return "[TIMEOUT: 未在规定时间内收到回答，请适当增大 ANSWER_TIMEOUT]"


# ─── 提问并获取回答 ───────────────────────────────────────────────────────────

def ask_question(agent_id: str, session_id: str, question: str) -> str:
    """
    向 agent 提问，等待并返回真实回答。
    """
    ok = send_turn(agent_id, session_id, f"[EVAL QUESTION] {question}")
    if not ok:
        return "[ERROR: 发送问题失败]"
    return poll_answer(agent_id, session_id)


# ─── 对话喂入 ─────────────────────────────────────────────────────────────────

def feed_conversation(agent_id: str, session_id: str, conversation: dict) -> None:
    """
    按时序将 4 个 session 的对话 turns 喂入 agent。
    每个 session 前先注入时间背景，帮助 agent 建立时间感知记忆。
    """
    turns_fed = 0
    for s_idx in range(1, 5):
        key = f"session_{s_idx}"
        date_key = f"session_{s_idx}_date_time"
        if key not in conversation:
            continue

        date_str = conversation.get(date_key, f"Session {s_idx}")
        turns = conversation[key]
        print(f"    [Session {s_idx}] {date_str} — {len(turns)} 条对话")

        # 注入时间背景
        send_turn(
            agent_id,
            session_id,
            f"[Context] The following conversation took place on: {date_str}",
        )
        time.sleep(TURN_DELAY)

        # 按顺序喂入每条 turn
        iter_turns = tqdm(turns, desc=f"  S{s_idx}", leave=False) if HAS_TQDM else turns
        for turn in iter_turns:
            speaker = turn.get("speaker", "Unknown")
            text = turn.get("text", "")
            imgs = turn.get("img_url", [])
            img = imgs[0] if imgs else None
            caption = turn.get("blip_caption", "")

            # 纯文本降级：若无多模态模型，用 blip_caption 代替图片描述
            if caption and not img:
                text = f"{text} [Image description: {caption}]"

            msg = f"{speaker}: {text}"
            send_turn(agent_id, session_id, msg, img_url=img)
            turns_fed += 1
            time.sleep(TURN_DELAY)

    print(f"    → 共喂入 {turns_fed} 条对话到 session '{session_id}'")


# ─── Category 5 对抗性评判 ────────────────────────────────────────────────────

# 模型正确纠正错误归因时通常会出现的词
_CORRECTION_SIGNALS = [
    "actually", "correction", "incorrect", "wrong",
    "not ", "it was", "she did", "he did",
    "不是", "实际上", "并非", "错误", "纠正", "应该是",
]


def judge_answer(category: int, expected: str, got: str) -> bool:
    """
    判断回答是否正确。

    Category 1~4：expected 关键词包含在回答中即视为正确。
    Category 5（对抗性）：接受两种正确形式：
        a) 回答包含 expected（给出了正确答案）
        b) 回答明确纠正了错误归因
    """
    exp_lower = expected.lower().strip()
    got_lower = got.lower().strip()

    # 基础匹配
    if exp_lower in got_lower:
        return True
    # 宽松方向匹配（got 的核心词在 expected 中）
    if len(got_lower) > 3 and got_lower in exp_lower:
        return True

    # Category 5 额外容忍：纠正信号
    if category == 5:
        return any(sig in got_lower for sig in _CORRECTION_SIGNALS)

    return False


# ─── 单 sample 评测 ───────────────────────────────────────────────────────────

def evaluate_sample(agent_id: str, sample: dict) -> list[dict]:
    """
    对单个 sample 完整评测：喂对话 → 逐条提问 → 收集结果。
    """
    sample_id = sample["sample_id"]
    # 用 sample_id + 时间戳派生 session_id，确保每次运行互不干扰
    session_id = f"eval_{sample_id.replace('-', '_')}_{int(time.time())}"

    print(f"\n{'='*64}")
    print(f"  Sample : {sample_id}")
    print(f"  Session: {session_id}")
    print(f"  QA 数量: {len(sample.get('qa', []))}")
    print(f"{'='*64}")

    # Step 1: 喂入对话
    print("[1/2] 喂入对话...")
    feed_conversation(agent_id, session_id, sample["conversation"])

    # Step 2: 逐条提问
    print("[2/2] 开始 QA 评测...")
    results: list[dict] = []
    qa_list = sample.get("qa", [])

    iter_qa = tqdm(qa_list, desc="  QA") if HAS_TQDM else qa_list
    for qa in iter_qa:
        question = qa["question"]
        expected = str(qa["answer"])
        category = qa.get("category", 0)
        evidence = qa.get("evidence", [])

        got = ask_question(agent_id, session_id, question)
        correct = judge_answer(category, expected, got)

        results.append(
            {
                "sample_id": sample_id,
                "category": category,
                "question": question,
                "expected": expected,
                "got": got,
                "correct": correct,
                "evidence": evidence,
            }
        )

        status = "✓" if correct else "✗"
        print(
            f"  [{status}] Cat{category} | {question[:55]}\n"
            f"       期望: {expected}\n"
            f"       回答: {got[:80]}"
        )

    return results


# ─── 指标统计 ─────────────────────────────────────────────────────────────────

def compute_metrics(results: list[dict]) -> dict:
    """按 category 统计准确率，返回指标摘要。"""
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
    """打印指标摘要到控制台。"""
    cat_labels = {
        1: "Factual    ",
        2: "Temporal   ",
        3: "Inferential",
        4: "General QA ",
        5: "Adversarial",
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
    p = argparse.ArgumentParser(
        description="在 QwenPaw 上评测 LoCoMo 长期记忆数据集"
    )
    p.add_argument(
        "--data",
        default="locomo_small.json",
        help="数据集文件路径（默认：locomo_small.json）",
    )
    p.add_argument(
        "--agent-id",
        default="locomo_eval",
        help="QwenPaw agent ID，不存在时自动创建（默认：locomo_eval）",
    )
    p.add_argument(
        "--output",
        default="eval_results.json",
        help="结果输出路径（默认：eval_results.json）",
    )
    p.add_argument(
        "--base-url",
        default=None,
        help="覆盖 QWENPAW_BASE_URL 环境变量",
    )
    p.add_argument(
        "--answer-timeout",
        type=float,
        default=ANSWER_TIMEOUT,
        help=f"等待 agent 回答的最大秒数（默认：{ANSWER_TIMEOUT}）",
    )
    p.add_argument(
        "--delete-after",
        action="store_true",
        help="评测完成后删除 eval agent",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # 命令行参数可覆盖全局变量
    global BASE_URL, ANSWER_TIMEOUT
    if args.base_url:
        BASE_URL = args.base_url
    ANSWER_TIMEOUT = args.answer_timeout

    print("=" * 64)
    print("  LoCoMo × QwenPaw 评测")
    print("=" * 64)
    print(f"  API 地址 : {BASE_URL}")
    print(f"  认证     : {'已开启' if API_USER else '未开启（pip 本地部署）'}")
    print(f"  数据文件 : {args.data}")
    print(f"  Agent ID : {args.agent_id}")
    print(f"  输出文件 : {args.output}")
    print(f"  等待超时 : {ANSWER_TIMEOUT}s")
    print("=" * 64)

    # 检查 QwenPaw 是否可达
    try:
        _request("GET", "/agents")
    except requests.exceptions.ConnectionError:
        print(
            f"\n[ERROR] 无法连接到 QwenPaw: {BASE_URL}\n"
            "        请确认 QwenPaw 已启动（qwenpaw app）且地址正确\n"
            "        参考 how_to_do_with_pip.md 第四步"
        )
        raise SystemExit(1)

    # 读取数据集
    data_path = Path(args.data)
    if not data_path.exists():
        print(f"[ERROR] 数据文件不存在: {data_path}")
        raise SystemExit(1)

    with open(data_path, encoding="utf-8") as f:
        dataset: list[dict] = json.load(f)

    print(f"\n已加载 {len(dataset)} 个样本，来自 {data_path}\n")

    # 创建评测 agent
    agent_id = create_eval_agent(args.agent_id)

    # 逐 sample 评测
    all_results: list[dict] = []
    try:
        for sample in dataset:
            results = evaluate_sample(agent_id, sample)
            all_results.extend(results)
    finally:
        # 无论是否出错，都保存已有结果
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
            delete_eval_agent(agent_id)


if __name__ == "__main__":
    main()