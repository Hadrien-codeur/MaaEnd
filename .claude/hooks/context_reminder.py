#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MaaEnd 项目：上下文用量提醒 hook（UserPromptSubmit 事件）

作用：每次博士提交消息时，读取本会话 transcript 文件，估算已用上下文（token），
当估算值 >= 阈值（默认 500k）时，向博士输出一次提醒（systemMessage）。
为避免刷屏，同一会话只在首次越过每个阈值档位时提醒一次（用标记文件去重）。

实现说明：
- Claude Code 的 hook 输入里没有精确 token 字段，这里用 transcript（JSONL，含全部消息）
  的文本字符数 / 估算系数 来近似 token。中英混排 + JSON 开销，系数取经验值。
- 任何异常都静默放过（绝不阻断会话）。
"""
import sys
import json
import os

# 估算阈值（token）。到达即提醒。可按需加档。
THRESHOLDS = [500_000, 700_000, 900_000]
# 字符 → token 估算系数：中英混排约 3 字符/token（粗略，仅用于"接近"提醒，不求精确）
CHARS_PER_TOKEN = 3.0


def estimate_tokens(transcript_path: str) -> int:
    """读 transcript（JSONL）累加文本字符数，估算 token。失败返回 0。"""
    try:
        total_chars = 0
        with open(transcript_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                # 直接按整行字符数累加（含 JSON 结构开销，作为单调上升的代理信号足够）
                total_chars += len(line)
        return int(total_chars / CHARS_PER_TOKEN)
    except Exception:
        return 0


def already_warned(session_id: str, level: int) -> bool:
    """检查/标记某会话是否已在该档位提醒过。"""
    try:
        cache_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), ".cache"
        )
        os.makedirs(cache_dir, exist_ok=True)
        flag = os.path.join(cache_dir, f"ctxwarn_{session_id}_{level}.flag")
        if os.path.exists(flag):
            return True
        with open(flag, "w") as fp:
            fp.write("1")
        return False
    except Exception:
        # 标记失败时宁可不提醒（避免每条消息重复刷），返回 True
        return True


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    transcript_path = data.get("transcript_path") or ""
    session_id = data.get("session_id") or "unknown"
    if not transcript_path:
        return

    tokens = estimate_tokens(transcript_path)
    if tokens <= 0:
        return

    # 找出已越过的最高档位
    crossed = [t for t in THRESHOLDS if tokens >= t]
    if not crossed:
        return
    level = max(crossed)
    if already_warned(session_id, level):
        return

    k = level // 1000
    est_k = tokens // 1000
    msg = (
        f"⚠️ 博士，当前会话上下文估算已约 {est_k}k tokens（越过 {k}k 档）。"
        f"建议尽快：① 让我把进度回写 CLAUDE.md ② 用 /compact 压缩或开新会话接力，"
        f"避免上下文溢出丢失关键信息。（此为估算值，仅作提醒）"
    )
    print(json.dumps({"systemMessage": msg}))


if __name__ == "__main__":
    main()
