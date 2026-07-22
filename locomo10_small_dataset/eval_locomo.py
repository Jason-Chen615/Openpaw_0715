# -*- coding: utf-8 -*-
"""
LoCoMo x QwenPaw  (v6 -- pure QA eval, memory pre-loaded by prepare_memory.py)

Usage:
    python eval_locomo.py --data locomo_small.json --agent-id locomo_eval
    python eval_locomo.py --data locomo_small.json --agent-id locomo_eval --results-dir results

Env vars:
    QWENPAW_BASE_URL   default http://127.0.0.1:8088/api
    QWENPAW_API_USER   auth username (Docker deployments)
    QWENPAW_API_PASS   auth password

v6 vs v5:
    v5: feed_conversation (ingest 4 sessions) -> QA
    v6: skip ingest; memory/*.md already written by prepare_memory.py
        - each QA uses an independent session (create -> chat -> delete)
        - prompt forces memory_search tool call before answering
        - outputs results/eval_results.json and results/metrics.json
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

# ---------------------------------------------------------------------------
BASE_URL: str = os.getenv("QWENPAW_BASE_URL", "http://127.0.0.1:8088/api")
API_USER: str = os.getenv("QWENPAW_API_USER", "")
API_PASS: str = os.getenv("QWENPAW_API_PASS", "")

USER_ID = "evaluator"

TURN_DELAY: float = 0.3
ANSWER_TIMEOUT: float = 120.0
REQUEST_TIMEOUT: int = 130

_BEARER_TOKEN: str = ""
# ---------------------------------------------------------------------------


# --- auth ------------------------------------------------------------------

def _login() -> bool:
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
        print(f"[!] Login failed: {resp.status_code} {resp.text[:120]}")
        return False
    token = resp.json().get("token", "")
    if not token:
        print(f"[!] No token in login response: {resp.json()}")
        return False
    _BEARER_TOKEN = token
    print(f"[+] Logged in, token prefix: {token[:12]}...")
    return True


def _headers(extra: dict | None = None) -> dict:
    h: dict = {"Content-Type": "application/json"}
    if _BEARER_TOKEN:
        h["Authorization"] = f"Bearer {_BEARER_TOKEN}"
    if extra:
        h.update(extra)
    return h


# --- session management ----------------------------------------------------

def delete_session(agent_id: str, session_id: str) -> None:
    """Delete a session after each QA to free context."""
    try:
        resp = requests.delete(
            f"{BASE_URL}/sessions/{session_id}",
            headers=_headers({"X-Agent-Id": agent_id}),
            timeout=15,
        )
        if not resp.ok and resp.status_code != 404:
            print(f"  [session] delete failed: {resp.status_code}")
    except requests.exceptions.RequestException:
        pass  # non-critical


# --- SSE chat --------------------------------------------------------------

def _sse_chat(
    agent_id: str,
    session_id: str,
    text: str,
    timeout: float = ANSWER_TIMEOUT,
) -> str:
    """POST /api/console/chat (SSE stream) -> full reply text."""
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
    req_headers = _headers({"X-Agent-Id": agent_id, "Accept": "text/event-stream"})

    try:
        with requests.post(
            f"{BASE_URL}/console/chat",
            json=payload,
            headers=req_headers,
            stream=True,
            timeout=timeout,
        ) as resp:
            if not resp.ok:
                print(f"  [!] chat failed: {resp.status_code} {resp.text[:120]}")
                return ""

            parts: list[str] = []
            for raw in resp.iter_lines():
                if not raw:
                    continue
                line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if data_str in ("", "[DONE]"):
                    continue
                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                ev_type = event.get("type", "")
                if ev_type in ("turn_usage", "error", "ping"):
                    continue

                content = event.get("content", "")
                if isinstance(content, str) and content:
                    parts.append(content)
                elif isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            t = c.get("text", "")
                            if t:
                                parts.append(t)

                text_field = event.get("text", "")
                if isinstance(text_field, str) and text_field and not content:
                    parts.append(text_field)

                output = event.get("output", "")
                if isinstance(output, str) and output and not content and not text_field:
                    parts.append(output)

            return "".join(parts).strip()

    except requests.exceptions.Timeout:
        print(f"  [!] SSE timeout (>{timeout}s)")
        return ""
    except requests.exceptions.RequestException as exc:
        print(f"  [!] request error: {exc}")
        return ""


# --- agent management ------------------------------------------------------

def ensure_agent(agent_id: str) -> str:
    resp = requests.post(
        f"{BASE_URL}/agents",
        json={
            "id": agent_id,
            "name": "LoCoMo Evaluator",
            "description": "Automated evaluation agent for LoCoMo benchmark.",
            "language": "en",
        },
        headers=_headers(),
        timeout=30,
    )
    if resp.status_code == 201:
        print(f"[+] Agent '{agent_id}' created")
    elif resp.status_code in (400, 409):
        print(f"[~] Agent '{agent_id}' already exists, reusing")
    else:
        print(f"[!] Agent create: {resp.status_code} {resp.text[:120]}")
    return agent_id


# --- QA prompt building ----------------------------------------------------

# Prompt that forces the agent to call memory_search before answering.
_QA_PROMPT_TMPL = """\
You MUST call the memory_search tool first to retrieve relevant memories before answering.

Question: {question}

Instructions:
1. Call memory_search with keywords from the question.
2. Read the retrieved memories carefully.
3. Answer the question concisely based on the memories.
Do NOT answer from general knowledge alone."""

_QA_PROMPT_WITH_DATE_TMPL = """\
Current date context: {date}

You MUST call the memory_search tool first to retrieve relevant memories before answering.

Question: {question}

Instructions:
1. Call memory_search with keywords from the question.
2. Read the retrieved memories carefully.
3. Answer the question concisely based on the memories.
Do NOT answer from general knowledge alone."""


def build_qa_prompt(question: str, date_ctx: str = "") -> str:
    if date_ctx:
        return _QA_PROMPT_WITH_DATE_TMPL.format(date=date_ctx, question=question)
    return _QA_PROMPT_TMPL.format(question=question)


# --- judge -----------------------------------------------------------------

_CORRECTION_SIGNALS = [
    "actually", "correction", "incorrect", "wrong", "not ", "it was",
    "she did", "he did", "不是", "实际上", "并非", "错误", "纠正", "应该是",
]


def judge_answer(category: int, expected: str, got: str) -> bool:
    exp = expected.lower().strip()
    ans = got.lower().strip()
    if exp in ans:
        return True
    if len(ans) > 3 and ans in exp:
        return True
    if category == 5:
        return any(sig in ans for sig in _CORRECTION_SIGNALS)
    return False


# --- per-sample evaluation -------------------------------------------------

def _get_date_ctx(sample: dict) -> str:
    """Return the date string of the last non-empty session."""
    last = ""
    for s_idx in range(1, 5):
        turns = sample.get("conversation", {}).get(f"session_{s_idx}", [])
        date = sample.get("conversation", {}).get(f"session_{s_idx}_date_time", "")
        if turns and date:
            last = date
    return last


def evaluate_sample(agent_id: str, sample: dict) -> list[dict]:
    sample_id: str = sample["sample_id"]
    safe_id = sample_id.replace("-", "_")
    qa_list: list[dict] = sample.get("qa", [])
    date_ctx = _get_date_ctx(sample)

    print(f"\n{'='*64}")
    print(f"  Sample : {sample_id}")
    print(f"  QAs    : {len(qa_list)}")
    if date_ctx:
        print(f"  Date   : {date_ctx}")
    print(f"{'='*64}")

    results: list[dict] = []
    iter_qa = tqdm(qa_list, desc=f"  {sample_id}") if HAS_TQDM else qa_list

    for q_idx, qa in enumerate(iter_qa):
        question: str = qa["question"]
        expected: str = str(qa["answer"])
        category: int = qa.get("category", 0)
        evidence: list = qa.get("evidence", [])

        # Each QA gets its own fresh session
        session_id = f"qa_{safe_id}_{q_idx}_{int(time.time())}"
        prompt = build_qa_prompt(question, date_ctx)

        got = _sse_chat(agent_id, session_id, prompt, timeout=ANSWER_TIMEOUT)
        if not got:
            got = "[TIMEOUT/NO_REPLY]"

        correct = judge_answer(category, expected, got)
        results.append({
            "sample_id": sample_id,
            "q_idx": q_idx,
            "category": category,
            "question": question,
            "expected": expected,
            "got": got,
            "correct": correct,
            "evidence": evidence,
        })

        mark = "V" if correct else "X"
        print(
            f"  [{mark}] Cat{category} | {question[:55]}\n"
            f"       expected: {expected}\n"
            f"       got     : {got[:100]}"
        )

        # Clean up the session immediately after each QA
        delete_session(agent_id, session_id)
        time.sleep(TURN_DELAY)

    return results


# --- metrics ---------------------------------------------------------------

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
    correct_all = sum(1 for r in results if r.get("correct"))
    metrics["overall"] = {
        "correct": correct_all,
        "total": total_all,
        "accuracy": round(correct_all / total_all, 4) if total_all else 0.0,
    }
    return metrics


def print_metrics(metrics: dict) -> None:
    cat_labels = {
        1: "Factual    ",
        2: "Temporal   ",
        3: "Inferential",
        4: "General QA ",
        5: "Adversarial",
    }
    print(f"\n{'='*64}")
    print("  EVALUATION METRICS  (v6)")
    print(f"{'='*64}")
    for key, v in metrics.items():
        if key.startswith("category_"):
            cat_num = int(key.split("_")[1])
            label = cat_labels.get(cat_num, f"Cat {cat_num}    ")
            bar_fill = int(v["accuracy"] * 20)
            bar = "#" * bar_fill + "." * (20 - bar_fill)
            print(
                f"  Cat{cat_num} {label} [{bar}] "
                f"{v['correct']:>2}/{v['total']:>2} = {v['accuracy']:.1%}"
            )
    v = metrics["overall"]
    print(f"  {'-'*58}")
    print(f"  Overall              {v['correct']:>2}/{v['total']:>2} = {v['accuracy']:.1%}")
    print(f"{'='*64}\n")


# --- save results ----------------------------------------------------------

def save_results(
    results: list[dict],
    metrics: dict,
    results_dir: Path,
    config: dict,
) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)

    eval_path = results_dir / "eval_results.json"
    with open(eval_path, "w", encoding="utf-8") as f:
        json.dump(
            {"config": config, "metrics": metrics, "results": results},
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"[+] Saved eval results -> {eval_path}")

    metrics_path = results_dir / "metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump({"config": config, "metrics": metrics}, f, ensure_ascii=False, indent=2)
    print(f"[+] Saved metrics      -> {metrics_path}")


# --- CLI -------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Evaluate LoCoMo benchmark on QwenPaw (v6 - pure QA)"
    )
    p.add_argument("--data", default="locomo_small.json",
                   help="Path to LoCoMo JSON dataset")
    p.add_argument("--agent-id", default="locomo_eval",
                   help="QwenPaw agent ID to use")
    p.add_argument("--results-dir", default="results",
                   help="Directory for output JSON files")
    p.add_argument("--base-url", default=None,
                   help="Override QWENPAW_BASE_URL")
    p.add_argument("--answer-timeout", type=float, default=ANSWER_TIMEOUT,
                   help="SSE stream timeout in seconds")
    p.add_argument("--delete-after", action="store_true",
                   help="Delete the agent after evaluation")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    global BASE_URL, ANSWER_TIMEOUT, REQUEST_TIMEOUT
    if args.base_url:
        BASE_URL = args.base_url
    ANSWER_TIMEOUT = args.answer_timeout
    REQUEST_TIMEOUT = int(ANSWER_TIMEOUT) + 10

    print("=" * 64)
    print("  LoCoMo x QwenPaw Evaluation  (v6 -- pure QA)")
    print("=" * 64)
    print(f"  API URL     : {BASE_URL}")
    print(f"  Auth        : {'Bearer Token' if API_USER else 'none (local pip deploy)'}")
    print(f"  Data file   : {args.data}")
    print(f"  Agent ID    : {args.agent_id}")
    print(f"  Results dir : {args.results_dir}")
    print(f"  SSE timeout : {ANSWER_TIMEOUT}s")
    print("=" * 64)

    # auth
    if API_USER:
        print(f"\n[Auth] Logging in as {API_USER} ...")
        if not _login():
            print("[ERROR] Login failed. Check QWENPAW_API_USER / QWENPAW_API_PASS.")
            raise SystemExit(1)

    # connectivity check
    try:
        requests.get(f"{BASE_URL}/agents", headers=_headers(), timeout=10)
    except requests.exceptions.ConnectionError:
        print(f"\n[ERROR] Cannot reach QwenPaw at {BASE_URL}")
        raise SystemExit(1)

    # load dataset
    data_path = Path(args.data)
    if not data_path.exists():
        print(f"[ERROR] Data file not found: {data_path}")
        raise SystemExit(1)
    with open(data_path, encoding="utf-8") as f:
        dataset: list[dict] = json.load(f)
    print(f"\nLoaded {len(dataset)} samples\n")

    # ensure agent exists
    agent_id = ensure_agent(args.agent_id)

    # run evaluation
    all_results: list[dict] = []
    try:
        for sample in dataset:
            sample_results = evaluate_sample(agent_id, sample)
            all_results.extend(sample_results)
    finally:
        if all_results:
            metrics = compute_metrics(all_results)
            config = {
                "version": "v6",
                "base_url": BASE_URL,
                "agent_id": agent_id,
                "data_file": str(data_path),
                "answer_timeout": ANSWER_TIMEOUT,
            }
            save_results(all_results, metrics, Path(args.results_dir), config)
            print_metrics(metrics)

        if args.delete_after:
            try:
                requests.delete(
                    f"{BASE_URL}/agents/{agent_id}",
                    headers=_headers(),
                    timeout=10,
                )
                print(f"[+] Agent '{agent_id}' deleted")
            except requests.exceptions.RequestException:
                pass


if __name__ == "__main__":
    main()