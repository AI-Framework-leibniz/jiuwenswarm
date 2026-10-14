# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Continuity locks for scene-spec and clip prompts — Director-authored metadata.

The Director LLM authors one ``continuity_lock`` per clip from the user prompt
(motion, facing, screen direction, prohibits) during storyboard authoring, and
the storyboard JSON carries it as structured data (metadata). This module only
normalizes those authored locks, chains carried state forward, and renders the
prompt clause; it never infers continuity from scenario text.
"""

from __future__ import annotations

from typing import Any

_MAX_KEY = 48
_MAX_VALUE = 280

# Carried forward between same-setting clips when this clip's lock is silent.
_CARRIED_KEYS = ("exited_ids", "speaker_placement", "screen_direction")


def normalize_continuity_lock(raw: Any) -> dict[str, str]:
    """Normalize a Director-authored continuity lock to trimmed str->str pairs."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        key_s = str(key or "").strip()
        if not key_s:
            continue
        if isinstance(value, (list, tuple)):
            value_s = ",".join(str(x).strip() for x in value if str(x).strip())
        else:
            value_s = str(value or "").strip()
        if not value_s:
            continue
        out[key_s[:_MAX_KEY]] = value_s[:_MAX_VALUE]
    return out


def continuity_prompt_clause(lock: dict[str, str] | None) -> str:
    if not lock:
        return ""
    parts = [f"{k}={v}" for k, v in lock.items() if v]
    if not parts:
        return ""
    return (
        " CONTINUITY LOCK ("
        + "; ".join(parts)
        + "). Obey lock; do not reverse motion/facing."
    )


def merge_lock_with_previous(
    lock: dict[str, str], prev: dict[str, str] | None
) -> dict[str, str]:
    """Carry forward authored state that must survive into this clip's lock."""
    prev = prev or {}
    out = dict(lock)
    for key in _CARRIED_KEYS:
        if prev.get(key) and not out.get(key):
            out[key] = prev[key]
    return out
