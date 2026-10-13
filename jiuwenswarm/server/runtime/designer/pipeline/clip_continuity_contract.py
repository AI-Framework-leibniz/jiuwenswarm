# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Clip continuity contract — one authority per shot (domain-agnostic).

Layers (never peer-compete):
  change  — this window's motion + speech
  opening — Director-authored first-frame spatial positions / posture
  hold    — Director-authored carries still true (objects placed, occupied places)
  exit    — what stopped being true this window

All layers come from Director-authored structured shot fields: ``start_state`` /
``end_state`` / ``continuity_lock`` (scene locks and clip locks live in
metadata). This module merges those fields, chains setting-scoped carries from
metadata, and verifies the final prompt — it never parses scenario prose.
"""

from __future__ import annotations

import re
from typing import Any

from jiuwenswarm.server.runtime.designer.pipeline.storyboard_clip_state import (
    _short,
    merge_spatial_maps,
    normalize_shot_state,
    spatial_positions_from_shot,
)


def _id_list(raw: Any) -> list[str]:
    return [str(x).strip() for x in (raw or []) if str(x).strip()]


def extract_prop_holds(raw: Any) -> dict[str, dict[str, str]]:
    """Director-authored object state — carried into later same-setting shots.

    Reads ``props`` from a clip's ``end_state`` (metadata only; never parsed
    from scenario text). Accepts the end_state itself or the full shot.
    """
    source = raw
    if isinstance(raw, dict) and isinstance(raw.get("end_state"), (dict, str)):
        source = raw.get("end_state")
    state = normalize_shot_state(source if isinstance(source, dict) else {})
    props = state.get("props") if isinstance(state.get("props"), dict) else {}
    out: dict[str, dict[str, str]] = {}
    for label, place in props.items():
        label_s = re.sub(r"\s+", " ", str(label or "")).strip(" .")
        place_s = re.sub(r"\s+", " ", str(place or "")).strip(" .")
        if len(label_s) < 2:
            continue
        key = re.sub(r"[^a-z0-9]+", "_", label_s.lower()).strip("_")[:48]
        if not key:
            continue
        out[key] = {"label": label_s[:80], "place": place_s[:120]}
    return out


def extract_prop_removals(raw: Any) -> list[str]:
    """Director-authored labels cleared this window (end_state.cleared)."""
    source = raw
    if isinstance(raw, dict) and isinstance(raw.get("end_state"), (dict, str)):
        source = raw.get("end_state")
    state = normalize_shot_state(source if isinstance(source, dict) else {})
    return [str(x).strip()[:80] for x in (state.get("cleared") or []) if str(x).strip()]


def _drop_props_by_labels(
    props: dict[str, Any] | None,
    labels: list[str],
) -> dict[str, dict[str, str]]:
    """Remove hold props whose label/key overlaps a removed object name."""
    kept: dict[str, dict[str, str]] = {}
    needles = [re.sub(r"\s+", " ", str(x).lower()).strip() for x in labels if str(x).strip()]
    for key, item in (props or {}).items():
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or key).lower()
        key_l = str(key).lower().replace("_", " ")
        drop = False
        for needle in needles:
            if not needle:
                continue
            if needle in label or needle in key_l or any(
                tok and tok in label
                for tok in needle.split()
                if len(tok) >= 4
            ):
                drop = True
                break
        if drop:
            continue
        kept[str(key)] = {
            "label": str(item.get("label") or key)[:80],
            "place": str(item.get("place") or "")[:120],
        }
    return kept


def empty_scene_hold() -> dict[str, Any]:
    return {"props": {}, "cast": {}, "phrases": []}


def merge_scene_hold(base: dict[str, Any] | None, extra: dict[str, Any] | None) -> dict[str, Any]:
    out = empty_scene_hold()
    for src in (base, extra):
        if not isinstance(src, dict):
            continue
        props = src.get("props") if isinstance(src.get("props"), dict) else {}
        for key, item in props.items():
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or key).strip()
            place = str(item.get("place") or "").strip()
            if label or place:
                out["props"][str(key)] = {
                    "label": label[:80],
                    "place": place[:120],
                }
        cast = src.get("cast") if isinstance(src.get("cast"), dict) else {}
        merged = merge_spatial_maps(out.get("cast"), cast)
        if merged:
            out["cast"] = merged
        for phrase in src.get("phrases") or []:
            text = _short(str(phrase), limit=160)
            if text and text not in out["phrases"]:
                out["phrases"].append(text)
    out["phrases"] = out["phrases"][:8]
    return out


def update_scene_hold_from_shot(
    scene_hold: dict[str, Any] | None,
    shot: dict[str, Any] | None,
) -> dict[str, Any]:
    """Fold this shot's authored end state + object state into the setting hold."""
    shot = shot if isinstance(shot, dict) else {}
    hold = merge_scene_hold(scene_hold, None)
    action = str(shot.get("action") or shot.get("clip_action") or "")
    hold = merge_scene_hold(hold, {"props": extract_prop_holds(shot)})
    removed = extract_prop_removals(shot)
    if removed:
        hold["props"] = _drop_props_by_labels(hold.get("props"), removed)
    end = normalize_shot_state(shot.get("end_state"))
    seats = end.get("seats") if isinstance(end.get("seats"), dict) else {}
    if not seats:
        seats = spatial_positions_from_shot(shot)
    if seats:
        hold["cast"] = merge_spatial_maps(hold.get("cast"), seats)
    # Positive hold phrases from end pose when not just restating this action.
    pose = _short(str(end.get("pose") or ""), limit=160)
    if pose and pose.lower() not in action.lower():
        # Prefer compact "still true" phrasing without replaying motion verbs.
        if not re.search(
            r"\b(walks?|runs?|climbs?|carries?|sets?|puts?|says?|speaks?)\b",
            pose,
            flags=re.I,
        ):
            if pose not in hold["phrases"]:
                hold["phrases"].append(pose)
    irreversible = _short(str(shot.get("irreversible") or end.get("irreversible") or ""), limit=160)
    if irreversible and irreversible.lower() not in action.lower():
        if irreversible not in hold["phrases"]:
            hold["phrases"].append(irreversible)
    hold["phrases"] = hold["phrases"][:8]
    return hold


def reconcile_shot_to_contract(
    shot: dict[str, Any],
    *,
    scene_hold: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge Director-authored opening/ending state with the setting hold.

    Locks come from structured metadata (start_state / end_state / scene hold);
    nothing is re-derived from action text.
    """
    shot = shot if isinstance(shot, dict) else {}
    action = str(shot.get("action") or shot.get("clip_action") or "")
    cast_actions = (
        shot.get("cast_actions") if isinstance(shot.get("cast_actions"), dict) else {}
    )
    start = normalize_shot_state(shot.get("start_state"))
    end = normalize_shot_state(shot.get("end_state"))
    opening = merge_spatial_maps(
        start.get("seats"),
        shot.get("spatial_anchors"),
        shot.get("seat_anchors"),
        (scene_hold or {}).get("cast") if isinstance(scene_hold, dict) else None,
    )
    ending = merge_spatial_maps(end.get("seats"), opening)

    # Carry prior + this clip's authored object state; drop cleared objects.
    hold = merge_scene_hold(scene_hold, {"props": extract_prop_holds(shot)})
    removed = extract_prop_removals(shot)
    if removed:
        hold["props"] = _drop_props_by_labels(hold.get("props"), removed)
    # Drop cast from hold when we have authoritative opening for them.
    hold_cast = {
        cid: pos
        for cid, pos in (hold.get("cast") or {}).items()
        if cid not in opening
    }
    hold["cast"] = hold_cast

    if opening:
        start["seats"] = opening
    if ending:
        end["seats"] = ending
    shot["start_state"] = start
    shot["end_state"] = end
    if opening:
        from jiuwenswarm.server.runtime.designer.pipeline.storyboard_clip_state import (
            _stamp_spatial_anchors,
        )

        _stamp_spatial_anchors(shot, opening)

    contract = {
        "change": {
            "action": action[:500],
            "cast_actions": {
                str(k): str(v)[:200]
                for k, v in cast_actions.items()
                if str(k).strip() and str(v).strip()
            },
            "speech_line": str(shot.get("speech_line") or "")[:500],
        },
        "opening": opening,
        "hold": {
            "props": dict(hold.get("props") or {}),
            "phrases": list(hold.get("phrases") or [])[:8],
        },
        "exit": _id_list(end.get("exited") or shot.get("exiting_character_ids")),
    }
    shot["clip_contract"] = contract
    shot["scene_hold"] = {
        "props": dict(hold.get("props") or {}),
        "phrases": list(hold.get("phrases") or [])[:8],
        "cast": dict(opening),
    }
    return contract


def apply_continuity_contracts(
    shots: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Reconcile each shot and chain setting-scoped holds. Returns new list."""
    out: list[dict[str, Any]] = []
    hold_by_setting: dict[str, dict[str, Any]] = {}
    for raw in shots or []:
        if not isinstance(raw, dict):
            continue
        shot = dict(raw)
        sid = str(shot.get("setting_id") or "set_1").strip() or "set_1"
        prior = hold_by_setting.get(sid) or empty_scene_hold()
        reconcile_shot_to_contract(shot, scene_hold=prior)
        # After this shot, update store from end + new props.
        hold_by_setting[sid] = update_scene_hold_from_shot(prior, shot)
        # Expose next-open hold on the shot for stamping (post-update includes this row's props).
        shot["scene_hold_after"] = hold_by_setting[sid]
        out.append(shot)
    return out


def hold_lines_for_cfg(cfg: dict[str, Any] | None) -> list[str]:
    """Compact positive hold lines for prompts (not prior-clip plot)."""
    cfg = cfg if isinstance(cfg, dict) else {}
    lines: list[str] = []
    contract = cfg.get("clip_contract") if isinstance(cfg.get("clip_contract"), dict) else {}
    hold = contract.get("hold") if isinstance(contract.get("hold"), dict) else {}
    if not hold:
        hold = cfg.get("scene_hold") if isinstance(cfg.get("scene_hold"), dict) else {}
    props = hold.get("props") if isinstance(hold.get("props"), dict) else {}
    for item in list(props.values())[:6]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        place = str(item.get("place") or "").strip()
        if label and place:
            lines.append(f"{label} remains at {place}.")
        elif label:
            lines.append(f"{label} remains in frame.")
    for phrase in list(hold.get("phrases") or [])[:4]:
        text = _short(str(phrase), limit=140)
        if not text:
            continue
        if not text.lower().startswith("still"):
            text = f"Still true: {text.rstrip('.')}."
        else:
            text = text.rstrip(".") + "."
        if text not in lines:
            lines.append(text)
    # Opening pose as hold when it states established state.
    start = normalize_shot_state(cfg.get("start_state"))
    pose = _short(str(start.get("pose") or ""), limit=140)
    action = str(cfg.get("clip_action") or cfg.get("action") or "")
    if pose and pose.lower() not in action.lower():
        if not re.search(
            r"\b(walks?|runs?|climbs?|carries?|sets?|puts?)\b", pose, flags=re.I
        ):
            line = pose.rstrip(".") + "."
            if line not in lines:
                lines.append(line)
    return lines[:8]


def _tokens_for_hold(text: str) -> list[str]:
    raw = re.findall(r"[a-z0-9]{4,}", str(text or "").lower())
    stop = {
        "with",
        "from",
        "that",
        "this",
        "have",
        "been",
        "into",
        "onto",
        "their",
        "them",
        "then",
        "than",
        "still",
        "true",
        "remains",
        "frame",
        "already",
    }
    out: list[str] = []
    for tok in raw:
        if tok in stop or tok in out:
            continue
        out.append(tok)
        if len(out) >= 6:
            break
    return out


def hold_covered_in_prompt(prompt: str, hold_line: str) -> bool:
    """True when the prompt already expresses this hold (token overlap)."""
    body = str(prompt or "").lower()
    if not body or not str(hold_line or "").strip():
        return True
    tokens = _tokens_for_hold(hold_line)
    if not tokens:
        return True
    hits = sum(1 for tok in tokens if tok in body)
    need = 1 if len(tokens) == 1 else max(2, (len(tokens) + 1) // 2)
    return hits >= need


def enforce_prompt_continuity(
    prompt: str,
    cfg: dict[str, Any] | None,
) -> tuple[str, list[str]]:
    """Ensure opening/hold lines survive into the final video prompt."""
    cfg = cfg if isinstance(cfg, dict) else {}
    text = str(prompt or "").strip()
    notes: list[str] = []
    missing: list[str] = []
    for line in hold_lines_for_cfg(cfg):
        if hold_covered_in_prompt(text, line):
            continue
        missing.append(line)
    # Opening spatial one-liners for cast with place/posture.
    start = normalize_shot_state(cfg.get("start_state"))
    seats = start.get("seats") if isinstance(start.get("seats"), dict) else {}
    if not seats and isinstance(cfg.get("spatial_anchors"), dict):
        seats = cfg["spatial_anchors"]
    for cid, anchor in list(seats.items())[:6]:
        if not isinstance(anchor, dict):
            continue
        place = str(anchor.get("place") or anchor.get("zone") or "").strip()
        posture = str(anchor.get("posture") or anchor.get("pose") or "").strip()
        bits = [b for b in (posture, f"at {place}" if place else "") if b]
        if not bits:
            continue
        line = f"{cid} begins {' '.join(bits)}."
        if not hold_covered_in_prompt(text, line) and line not in missing:
            # Only force when place or posture tokens are absent.
            probe = place or posture
            if probe and probe.lower().split()[0] not in text.lower():
                missing.append(line)
    if missing:
        block = "Continuity holds: " + " ".join(missing)
        text = (text.rstrip() + " " + block).strip()
        notes.append(f"reinjected_holds:{len(missing)}")
    return text[:4000], notes


def stamp_contract_on_clip_cfg(
    cfg: dict[str, Any],
    *,
    shot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy clip_contract / scene_hold onto clip config."""
    out = dict(cfg or {})
    shot = shot if isinstance(shot, dict) else {}
    contract = shot.get("clip_contract") or out.get("clip_contract")
    if isinstance(contract, dict) and contract:
        out["clip_contract"] = contract
    hold = shot.get("scene_hold") or out.get("scene_hold")
    if isinstance(hold, dict) and hold:
        out["scene_hold"] = hold
    # Seed pose_holds with continuity hold lines.
    holds = [str(x) for x in (out.get("pose_holds") or []) if str(x).strip()]
    for line in hold_lines_for_cfg(out):
        if line not in holds:
            holds.append(line)
    if holds:
        out["pose_holds"] = holds[:10]
    return out
