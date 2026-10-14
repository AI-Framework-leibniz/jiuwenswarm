# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Prior-shot consistency as storyboard notes — never paste full Wan prompts.

Format injected into leaves:
  PREVIOUS CLIP HAD … (context only — do not film again)
  YOUR ASSIGNMENT (storyboard shot N — film ONLY this)
"""

from __future__ import annotations

import re
from typing import Any


def _clip_nodes(graph: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = []
    for n in graph.get("nodes") or []:
        if not isinstance(n, dict):
            continue
        cfg = n.get("config") if isinstance(n.get("config"), dict) else {}
        if str(cfg.get("role") or "") == "clip":
            nodes.append(n)
    return sorted(
        nodes,
        key=lambda n: int((n.get("config") or {}).get("clip_index") or 0) or 99,
    )


def wan_prompt_from_clip_node(node: dict[str, Any] | None) -> str:
    if not isinstance(node, dict):
        return ""
    cfg = node.get("config") if isinstance(node.get("config"), dict) else {}
    for key in ("last_wan_prompt", "clip_prompt_preview", "agent_authored_prompt_text"):
        text = str(cfg.get(key) or "").strip()
        if text and key != "agent_authored_prompt_text":
            return text
    gen = cfg.get("generate") if isinstance(cfg.get("generate"), dict) else {}
    return str(gen.get("prompt") or cfg.get("prompt") or "").strip()


def _short_action(text: str) -> str:
    raw = re.sub(r"\s+", " ", (text or "").strip())
    for marker in (
        "PRIOR CLIP",
        "PRIOR CLIP",
        "YOUR ASSIGNMENT",
        "PREVIOUS CLIP HAD",
        "LANGUAGE LOCK",
        "STYLE LOCK",
        "SCENE SPECS",
        "CHARACTER CONSISTENCY",
        "MASTER SCENE",
    ):
        if marker in raw.upper():
            raw = raw.split(marker, 1)[0].strip()
    for pat in (
        r"Primary action for shot \d+:\s*(.+?)(?:\.|$)",
        r"YOUR ASSIGNMENT[\s\S]*?Action:\s*(.+?)(?:\n|$)",
        r"Character action:\s*(.+?)(?:\n|$)",
        r"Action:\s*(.+?)(?:\n|$)",
    ):
        m = re.search(pat, raw, flags=re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            break
    return raw


def _action_from_clip_node(node: dict[str, Any] | None) -> str:
    if not isinstance(node, dict):
        return ""
    cfg = node.get("config") if isinstance(node.get("config"), dict) else {}
    for key in ("clip_action", "character_action", "action", "previous_clip_action"):
        text = str(cfg.get(key) or "").strip()
        if text and key != "previous_clip_action":
            return _short_action(text)
    return _short_action(wan_prompt_from_clip_node(node))


def collect_prior_clip_prompts(
    graph: dict[str, Any],
    *,
    clip_index: int,
    max_clips: int = 6,
) -> list[dict[str, Any]]:
    """Earlier clips as storyboard shots (oldest → newest)."""
    out: list[dict[str, Any]] = []
    for node in _clip_nodes(graph):
        cfg = node.get("config") if isinstance(node.get("config"), dict) else {}
        idx = int(cfg.get("clip_index") or 0) or 0
        if idx <= 0 or idx >= int(clip_index or 0):
            continue
        action = _action_from_clip_node(node)
        prompt = wan_prompt_from_clip_node(node)
        if not action and not prompt:
            continue
        out.append(
            {
                "node_id": str(node.get("id") or ""),
                "clip_index": idx,
                "wan_prompt": prompt or "",
                "clip_action": action or "",
                "speech_line": str(cfg.get("speech_line") or ""),
                "camera": str(cfg.get("camera") or ""),
            }
        )
    return out[-max(1, int(max_clips)) :]


def stamp_wan_prompt_handoff(
    graph: dict[str, Any],
    *,
    clip_index: int,
    prompt: str,
    node_id: str = "",
    clip_action: str = "",
    speech_line: str = "",
) -> list[str]:
    """Save Wan prompt on this clip only (debug/regenerate).

    Continuity is storyboard start/end — do NOT stamp prior Wan onto later clips.
    """
    notes: list[str] = []
    text = (prompt or "").strip()
    if not text and not clip_action:
        return notes
    meta = dict(graph.get("metadata") or {})
    log = dict(meta.get("clip_wan_prompt_log") or {})
    key = str(node_id or f"n_clip_{clip_index}")
    src = next((n for n in _clip_nodes(graph) if str(n.get("id") or "") == key), None)
    src_cfg = src.get("config") if isinstance(src, dict) else {}
    action = _short_action(clip_action or _action_from_clip_node(src) or text)
    speech = (speech_line or str((src_cfg or {}).get("speech_line") or "")).strip()
    log[key] = {
        "clip_index": int(clip_index or 0),
        "prompt": text,
        "clip_action": action,
        "speech_line": speech,
    }
    meta["clip_wan_prompt_log"] = log
    graph["metadata"] = meta

    for node in _clip_nodes(graph):
        cfg = dict(node.get("config") or {})
        idx = int(cfg.get("clip_index") or 0) or 0
        nid = str(node.get("id") or "")
        if idx == int(clip_index or 0) or nid == key:
            if text:
                cfg["last_wan_prompt"] = text
                cfg["clip_prompt_preview"] = text
            if action:
                cfg["clip_action"] = cfg.get("clip_action") or action
            cfg["handoff_artifact_ready"] = True
            # Drop legacy prior-clip schedule wiring if present on older graphs.
            cfg.pop("continuity_clip_node_id", None)
            node["config"] = cfg
            notes.append(f"{nid}: saved last_wan_prompt (no next-clip Wan stamp)")
    return notes


def same_scene_prompt_gate_clause(
    *,
    clip_index: int = 0,
    this_action: str = "",
    this_camera: str = "",
    this_speech: str = "",
    already_done: list[str] | None = None,
    has_prior: bool = False,
) -> str:
    """LLM instruction: write from this storyboard row and its locks only."""
    del already_done, has_prior
    lines = [
        "STORYBOARD ROW GATE (write the video prompt to this contract):",
        f"1) THIS storyboard shot {int(clip_index or 0) or 'N'} is the sole plot authority "
        f"— action: {_short_action(this_action) or '(this row)'}"
        + (f"; camera: {str(this_camera).strip()}" if str(this_camera or "").strip() else "")
        + (f"; speech: {str(this_speech).strip()}" if str(this_speech or "").strip() else "")
        + ".",
        "2) The prompt MUST match that row exactly: action, posture "
        "(stand/sit/walk/…), spatial places, who is on screen, camera, and spoken words. "
        "Do not invent a different posture or dialogue. Do not film another shot's beat.",
        "3) Obey the locks on THIS storyboard row only. Do not use text, speech, "
        "frames, or locks from any previous clip.",
        "4) Write in the configured video model's best-practice story form "
        "(positive narrative; Image/@Image labels in attach order).",
        "Keep clothing, language, occupancy, and spatial positioning locks. "
        "Identity/place from attached media.",
    ]
    return "\n".join(lines)


_EVENT_FAMILIES: tuple[frozenset[str], ...] = (
    frozenset({"walk", "walks", "walked", "walking", "away"}),
    frozenset({"leave", "leaves", "leaving", "left", "exit", "exits", "exited", "exiting", "depart", "gone"}),
    frozenset({"sit", "sits", "sat", "sitting", "seated", "reseated", "reseat"}),
    frozenset({"start", "starts", "started", "starting", "begin", "begins", "began", "onset"}),
    frozenset({"turn", "turns", "turned", "turning", "look", "looks", "looked", "looking", "gaze", "gazes", "glance"}),
    frozenset({"reach", "reaches", "reached", "check", "checks", "checked", "grab", "grabs", "pick", "open", "opens"}),
    frozenset({"crowd", "colleagues", "coworker", "coworkers", "extras", "bystanders", "staff"}),
)


def _stem_token(token: str) -> str:
    t = str(token or "").strip().lower()
    if len(t) <= 3:
        return t
    for suf in ("ing", "ied", "ies", "ed", "es", "s"):
        if t.endswith(suf) and len(t) - len(suf) >= 3:
            stem = t[: -len(suf)]
            if stem.endswith("k") or len(stem) >= 3:
                return stem
    return t


def _content_stems(text: str) -> set[str]:
    try:
        from jiuwenswarm.server.runtime.designer.pipeline.clip_scope import (
            content_tokens,
        )
    except Exception:  # noqa: BLE001
        return { _stem_token(x) for x in re.findall(r"[A-Za-z]{2,}", str(text or "").lower()) }
    return { _stem_token(t) for t in content_tokens(text) }


def _families_in(text: str) -> set[int]:
    tokens = set(re.findall(r"[A-Za-z]{2,}", str(text or "").lower()))
    stems = { _stem_token(t) for t in tokens }
    bag = tokens | stems
    hit: set[int] = set()
    for i, fam in enumerate(_EVENT_FAMILIES):
        fam_stems = { _stem_token(x) for x in fam } | set(fam)
        if bag & fam_stems:
            hit.add(i)
    return hit


def agent_replays_finished_events(
    text: str,
    *,
    already_done: list[str] | None = None,
    this_action: str = "",
) -> bool:
    """True when the agent restages a finished event this shot did not ask to repeat."""
    body = str(text or "").strip()
    if not body:
        return False
    try:
        from jiuwenswarm.server.runtime.designer.pipeline.clip_scope import (
            overlap_ratio,
        )
    except Exception:  # noqa: BLE001
        overlap_ratio = None  # type: ignore[assignment]
    asked = _families_in(this_action)
    for note in already_done or []:
        note_s = str(note or "").strip()
        if len(note_s) < 12:
            continue
        if overlap_ratio is not None and overlap_ratio(note_s, this_action) >= 0.45:
            continue
        if overlap_ratio is not None and overlap_ratio(note_s, body) >= 0.45:
            # This row asked to repeat that finished beat — allow it.
            if overlap_ratio(note_s, this_action) >= 0.35:
                continue
            return True
        this_stems = _content_stems(this_action)
        note_stems = _content_stems(note_s) - this_stems
        body_stems = _content_stems(body) - this_stems
        shared = note_stems & body_stems
        denom = float(max(1, min(len(note_stems), len(body_stems))))
        if len(shared) >= 2 and (len(shared) / denom) >= 0.4:
            return True
        note_fams = _families_in(note_s) - asked
        if note_fams and note_fams & _families_in(body):
            return True
    return False


def _same_setting(src: dict[str, Any] | None, dst: dict[str, Any] | None) -> bool:
    """True only when both sides name the same setting_id.

    Missing IDs do not count as a match — that would leak continuity across rooms.
    """
    a = str((src or {}).get("setting_id") or "").strip()
    b = str((dst or {}).get("setting_id") or "").strip()
    if not a or not b:
        return False
    return a == b


def this_shot_assignment_clause(
    *,
    clip_index: int,
    action: str = "",
    camera: str = "",
    speech_line: str = "",
    already_done: list[str] | None = None,
) -> str:
    del already_done
    lines = [
        f"YOUR ASSIGNMENT (storyboard shot {int(clip_index or 0)} — film ONLY this part):",
        f"- Action: {_short_action(action) or '(follow this shot clip spec + storyboard shot)'}",
    ]
    if str(camera or "").strip():
        lines.append(f"- Camera: {str(camera).strip()}")
    if str(speech_line or "").strip():
        lines.append(f"- Speech this shot: {str(speech_line).strip()}")
    lines.append(
        "Use the storyboard shot assigned to you above. Do not invent another shot's action."
    )
    return "\n".join(lines)


def previous_clip_had_clause(prior: list[dict[str, Any]] | None) -> str:
    """Earlier clips are not described to the next clip."""
    del prior
    return ""


def handoff_clause_for_prompt(
    prior: list[dict[str, Any]] | None,
    *,
    this_clip_index: int = 0,
    this_action: str = "",
    this_camera: str = "",
    this_speech: str = "",
    already_done: list[str] | None = None,
) -> str:
    """This storyboard row only. Earlier clips are not summarized."""
    del prior
    parts: list[str] = []
    if int(this_clip_index or 0) > 0 or str(this_action or "").strip():
        parts.append(
            this_shot_assignment_clause(
                clip_index=int(this_clip_index or 0),
                action=this_action,
                camera=this_camera,
                speech_line=this_speech,
                already_done=already_done,
            )
        )
    if str(this_action or "").strip():
        parts.append(
            same_scene_prompt_gate_clause(
                clip_index=int(this_clip_index or 0),
                this_action=this_action,
                this_camera=this_camera,
                this_speech=this_speech,
                already_done=already_done,
                has_prior=False,
            )
        )
    return "\n\n".join(parts)


def clip_continuity_note(
    *,
    clip_index: int,
    this_action: str = "",
    this_camera: str = "",
    prior_action: str = "",
    prior_clip_index: int | None = None,
) -> str:
    """This storyboard row only. The previous clip's action is not included."""
    del prior_action, prior_clip_index
    parts: list[str] = []
    parts.append(
        this_shot_assignment_clause(
            clip_index=clip_index,
            action=this_action,
            camera=this_camera,
        ).replace("film ONLY", "draw ONLY").replace("Film ONLY", "Draw ONLY")
    )
    return "\n\n".join(parts)
