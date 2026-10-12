# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Storyboard start/end state — sole continuity authority (domain-agnostic).

Each shot is a closed window:
  start_state → action/camera/speech → end_state
Same-setting chain: shot N start_state must match shot N-1 end_state.
No prior-clip Wan text required.
"""

from __future__ import annotations

import re
from typing import Any


def _short(text: str, *, limit: int = 200) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())[:limit]


def _as_state(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        return {"pose": raw.strip()[:280]}
    return {}


# Spatial positioning detail (sit, stand, lean, walk, any place — not seat-only).
_SPATIAL_DETAIL_KEYS = (
    "place",
    "zone",
    "seat",
    "posture",
    "pose",
    "facing",
    "screen",
    "landmark",
    "near",
    "beside",
)

_POSTURE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(sit|sits|sitting|seated)\b", "seated"),
    (r"\b(stand|stands|standing)\b", "standing"),
    (r"\b(lean|leans|leaning)\b", "leaning"),
    (r"\b(kneel|kneels|kneeling)\b", "kneeling"),
    (r"\b(crouch|crouches|crouching)\b", "crouching"),
    (r"\b(reclin\w*|lie|lies|lying|laid)\b", "reclining"),
    (r"\b(walk|walks|walking|pace|paces|pacing)\b", "walking"),
    (r"\b(run|runs|running)\b", "running"),
    (r"\b(perch|perches|perched)\b", "perched"),
)


def detailed_spatial_anchor(anchor: Any) -> dict[str, str]:
    """Normalize one spatial position lock: place/zone/posture/facing (any stance)."""
    if isinstance(anchor, dict):
        out: dict[str, str] = {}
        for key in _SPATIAL_DETAIL_KEYS:
            val = str(anchor.get(key) or "").strip()
            if val:
                out[key] = val[:120]
        # Accept alternate keys from storyboard / blocking.
        for src, dst in (
            ("position", "place"),
            ("at", "place"),
            ("location", "place"),
            ("chair", "seat"),
            ("stance", "posture"),
            ("gaze", "facing"),
        ):
            if dst not in out:
                val = str(anchor.get(src) or "").strip()
                if val:
                    out[dst] = val[:120]
        if not out.get("place"):
            place = out.get("seat") or out.get("zone") or out.get("landmark") or ""
            if place:
                out["place"] = place
        return out
    text = str(anchor or "").strip()
    if not text:
        return {}
    return {"place": text[:120]}


# Back-compat alias (wire/docs historically said "seat").
detailed_seat_anchor = detailed_spatial_anchor


def merge_spatial_maps(*maps: Any) -> dict[str, dict[str, str]]:
    """Merge spatial position maps; later maps fill missing detail keys only."""
    out: dict[str, dict[str, str]] = {}
    for raw in maps:
        if not isinstance(raw, dict):
            continue
        for cid, anchor in list(raw.items())[:12]:
            key = str(cid or "").strip()
            if not key:
                continue
            detail = detailed_spatial_anchor(anchor)
            if not detail:
                continue
            cur = dict(out.get(key) or {})
            for k, v in detail.items():
                if v and not cur.get(k):
                    cur[k] = v
            out[key] = cur
    return out


merge_seat_maps = merge_spatial_maps


def _posture_from_text(text: str) -> str:
    low = str(text or "").strip().lower()
    if not low:
        return ""
    for pattern, label in _POSTURE_PATTERNS:
        if re.search(pattern, low):
            return label
    return ""


def spatial_positions_from_shot(shot: dict[str, Any] | None) -> dict[str, dict[str, str]]:
    """Build detailed spatial positioning plan (place + posture for any stance).

    Not seating-only: standing, walking, leaning, kneeling, etc. are first-class.
    Reads spatial_anchors (preferred) and seat_anchors (legacy wire key).
    """
    shot = shot if isinstance(shot, dict) else {}
    start = shot.get("start_state") if isinstance(shot.get("start_state"), dict) else {}
    end = shot.get("end_state") if isinstance(shot.get("end_state"), dict) else {}
    blocking = shot.get("blocking") if isinstance(shot.get("blocking"), dict) else {}
    landmark = str(blocking.get("landmark") or "").strip()
    from_positions: dict[str, dict[str, str]] = {}
    for pos in blocking.get("positions") or []:
        if not isinstance(pos, dict):
            continue
        cid = str(pos.get("character_id") or pos.get("id") or "").strip()
        if not cid:
            continue
        from_positions[cid] = detailed_spatial_anchor(
            {
                "place": pos.get("place") or pos.get("zone") or pos.get("seat"),
                "zone": pos.get("zone"),
                "seat": pos.get("seat"),
                "posture": pos.get("posture") or pos.get("pose"),
                "pose": pos.get("pose"),
                "facing": pos.get("facing"),
                "screen": pos.get("screen"),
                "landmark": pos.get("near") or pos.get("beside") or landmark,
                "near": pos.get("near"),
                "beside": pos.get("beside"),
            }
        )
    # cast_actions may encode posture + place ("standing by the door", "seated at table").
    from_actions: dict[str, dict[str, str]] = {}
    cast_actions = shot.get("cast_actions") if isinstance(shot.get("cast_actions"), dict) else {}
    for cid, action in cast_actions.items():
        key = str(cid or "").strip()
        text = str(action or "").strip()
        if not key or not text:
            continue
        detail: dict[str, str] = {}
        posture = _posture_from_text(text)
        if posture:
            detail["posture"] = posture
        m = re.search(
            r"\b(?:at|on|by|beside|near|in|along)\s+([^,.;]{2,80})",
            text,
            flags=re.IGNORECASE,
        )
        if m:
            detail["place"] = m.group(1).strip()[:120]
        if detail:
            from_actions[key] = detail
    return merge_spatial_maps(
        shot.get("spatial_anchors"),
        shot.get("seat_anchors"),
        start.get("seats") if isinstance(start.get("seats"), dict) else None,
        start.get("spatial_anchors") if isinstance(start.get("spatial_anchors"), dict) else None,
        start.get("seat_anchors") if isinstance(start.get("seat_anchors"), dict) else None,
        end.get("seats") if isinstance(end.get("seats"), dict) else None,
        end.get("spatial_anchors") if isinstance(end.get("spatial_anchors"), dict) else None,
        from_positions,
        from_actions,
    )


# Back-compat alias.
seats_from_shot = spatial_positions_from_shot


def _stamp_spatial_anchors(target: dict[str, Any], positions: dict[str, dict[str, str]]) -> None:
    """Write spatial positioning under both canonical and legacy keys."""
    if not positions:
        return
    payload = dict(positions)
    target["spatial_anchors"] = payload
    target["seat_anchors"] = payload  # legacy consumers / prompt practice


def normalize_shot_state(raw: Any) -> dict[str, Any]:
    """Normalize start_state / end_state to a compact structured dict."""
    st = _as_state(raw)
    out: dict[str, Any] = {}
    pose = _short(str(st.get("pose") or st.get("blocking") or st.get("holds") or ""), limit=280)
    if pose:
        out["pose"] = pose
    seats = st.get("seats") if isinstance(st.get("seats"), dict) else {}
    if not seats and isinstance(st.get("spatial_anchors"), dict):
        seats = st["spatial_anchors"]
    if not seats and isinstance(st.get("seat_anchors"), dict):
        seats = st["seat_anchors"]
    cleaned = merge_spatial_maps(seats)
    if cleaned:
        out["seats"] = cleaned
    facing = _short(str(st.get("facing") or st.get("gaze") or ""), limit=160)
    if facing:
        out["facing"] = facing
    camera = _short(str(st.get("camera") or ""), limit=120)
    if camera:
        out["camera"] = camera
    exited = [
        str(x).strip()
        for x in (st.get("exited") or st.get("exited_ids") or [])
        if str(x).strip()
    ]
    if exited:
        out["exited"] = exited[:12]
    speech_done = _short(str(st.get("speech_done") or st.get("speech") or ""), limit=160)
    if speech_done:
        out["speech_done"] = speech_done
    on_screen = [str(x).strip() for x in (st.get("on_screen") or []) if str(x).strip()]
    if on_screen:
        out["on_screen"] = on_screen[:12]
    offscreen = [str(x).strip() for x in (st.get("offscreen") or []) if str(x).strip()]
    if offscreen:
        out["offscreen"] = offscreen[:12]
    return out


def _infer_start_from_shot(shot: dict[str, Any]) -> dict[str, Any]:
    staging = shot.get("staging") if isinstance(shot.get("staging"), dict) else {}
    pose = _short(
        str(
            shot.get("start_pose")
            or staging.get("positioning_lock")
            or shot.get("positioning_lock")
            or ""
        ),
        limit=280,
    )
    positions = spatial_positions_from_shot(shot)
    out: dict[str, Any] = {}
    if pose:
        out["pose"] = pose
    if positions:
        out["seats"] = positions
    camera = _short(str(shot.get("camera") or ""), limit=120)
    if camera:
        out["camera"] = camera
    on_screen = [str(x) for x in (shot.get("on_screen") or []) if str(x)]
    if on_screen:
        out["on_screen"] = on_screen
    offscreen = [str(x) for x in (shot.get("offscreen") or []) if str(x)]
    if offscreen:
        out["offscreen"] = offscreen
    return out


def _norm_phrase(text: str) -> str:
    body = re.sub(r"\s+", " ", str(text or "").strip().lower()).rstrip(".")
    return re.sub(
        r"^(after this shot|by the last frame|the earlier event is already finished)\s*:\s*",
        "",
        body,
    )


def _is_action_restatement(text: str, *actions: str) -> bool:
    """True when text is the previous shot's motion, not an image result."""
    raw = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if "after this shot" in raw or "already past:" in raw:
        return True
    body = _norm_phrase(text)
    if not body:
        return False
    for action in actions:
        act = _norm_phrase(action)
        if act and (body == act or act in body):
            return True
    return False


def _hold_state(state: dict[str, Any], *actions: str) -> dict[str, Any]:
    """Drop a pose that would make the next clip replay the previous motion."""
    out = dict(state)
    if _is_action_restatement(str(out.get("pose") or ""), *actions):
        out.pop("pose", None)
    if _is_action_restatement(str(out.get("irreversible") or ""), *actions):
        out.pop("irreversible", None)
    return {key: value for key, value in out.items() if value not in ("", [], {})}


def _infer_end_from_shot(shot: dict[str, Any]) -> dict[str, Any]:
    action = _short(str(shot.get("action") or shot.get("clip_prompt") or ""), limit=220)
    result = _short(str(shot.get("irreversible") or ""), limit=160)
    speech = _short(str(shot.get("speech_line") or ""), limit=160)
    exiting = [
        str(x)
        for x in (shot.get("exiting_character_ids") or shot.get("exiting") or [])
        if str(x)
    ]
    out: dict[str, Any] = {}
    if result and not _is_action_restatement(result, action):
        out["pose"] = result
        out["irreversible"] = result
    if speech:
        out["speech_done"] = speech
    if exiting:
        out["exited"] = exiting
    # Remaining on_screen after exits.
    on_screen = [str(x) for x in (shot.get("on_screen") or []) if str(x)]
    remain = [c for c in on_screen if c not in set(exiting)]
    if remain:
        out["on_screen"] = remain
    offscreen = [str(x) for x in (shot.get("offscreen") or []) if str(x)]
    if offscreen or exiting:
        out["offscreen"] = list(dict.fromkeys(offscreen + exiting))
    camera = _short(str(shot.get("camera") or ""), limit=120)
    if camera:
        out["camera"] = camera
    positions = spatial_positions_from_shot(shot)
    if positions:
        # Drop exited cast from spatial plan.
        out["seats"] = {
            k: v for k, v in positions.items() if str(k) not in set(exiting)
        }
    return out


_EMOTIONS = {
    "setup": "setup",
    "hook": "setup",
    "opening": "setup",
    "rise": "rise",
    "rising": "rise",
    "development": "rise",
    "turn": "rise",
    "problem": "rise",
    "desire": "rise",
    "proof": "rise",
    "demonstration": "rise",
    "climax": "climax",
    "peak": "climax",
    "release": "release",
    "payoff": "release",
    "cta": "release",
    "ending": "release",
}


def emotion_label(raw: Any) -> str:
    text = str(raw or "").strip().lower().replace("-", " ").replace("_", " ")
    return _EMOTIONS.get(text, "")


def _id_list(raw: Any) -> list[str]:
    return [str(x).strip() for x in (raw or []) if str(x).strip()]


def _normalize_cast_states(shot: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Per-shot wardrobe / emotion / presence. Face identity stays on the character sheet."""
    on_screen = set(_id_list(shot.get("on_screen")))
    offscreen = set(_id_list(shot.get("offscreen")))
    exited = set(
        _id_list(shot.get("exiting_character_ids") or shot.get("exiting"))
    )
    raw = shot.get("cast_states") if isinstance(shot.get("cast_states"), dict) else {}
    out: dict[str, dict[str, str]] = {}
    for cid, state in raw.items():
        key = str(cid or "").strip()
        if not key:
            continue
        item = state if isinstance(state, dict) else {"emotion": state}
        entry: dict[str, str] = {}
        wardrobe = _short(str(item.get("wardrobe") or item.get("costume") or ""), limit=160)
        feeling = _short(str(item.get("emotion") or ""), limit=80)
        presence = str(item.get("presence") or "").strip().lower()
        if wardrobe:
            entry["wardrobe"] = wardrobe
        if feeling:
            entry["emotion"] = feeling
        if presence in {"on_screen", "offscreen", "exited", "absent"}:
            entry["presence"] = presence
        if entry:
            out[key] = entry
    ids = list(dict.fromkeys([*_id_list(shot.get("character_ids")), *on_screen, *offscreen, *exited]))
    for cid in ids:
        entry = dict(out.get(cid) or {})
        if cid in exited:
            entry["presence"] = "exited"
        elif cid in offscreen:
            entry["presence"] = "offscreen"
        elif cid in on_screen:
            entry["presence"] = "on_screen"
        elif "presence" not in entry:
            entry["presence"] = "absent"
        if entry:
            out[cid] = entry
    return out


def apply_story_curve(shots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One climax, an irreversible end, and a carried character state.

    The next shot starts from the previous end. Face identity is not stored here.
    """
    rows = [shot for shot in shots if isinstance(shot, dict)]
    count = len(rows)
    if not count:
        return shots
    for shot in rows:
        shot["emotion"] = emotion_label(shot.get("emotion") or shot.get("beat"))
    climaxes = [i for i, shot in enumerate(rows) if shot.get("emotion") == "climax"]
    if len(climaxes) > 1:
        keep = climaxes[-1]
        for index in climaxes:
            if index != keep:
                rows[index]["emotion"] = "rise"
        climaxes = [keep]
    if not climaxes and count >= 2:
        index = count - 2 if count >= 3 else count - 1
        rows[index]["emotion"] = "climax"
    climax_index = next(
        (i for i, shot in enumerate(rows) if shot.get("emotion") == "climax"),
        None,
    )
    for index, shot in enumerate(rows):
        if shot.get("emotion"):
            continue
        if index == 0:
            shot["emotion"] = "setup"
        elif climax_index is not None and index > climax_index:
            shot["emotion"] = "release"
        else:
            shot["emotion"] = "rise"
    # Re-find after fills. A lone climax must survive the fill above.
    climaxes = [i for i, shot in enumerate(rows) if shot.get("emotion") == "climax"]
    if len(climaxes) > 1:
        keep = climaxes[-1]
        for index in climaxes:
            if index != keep:
                rows[index]["emotion"] = "rise"
    carried_by_setting: dict[str, dict[str, dict[str, str]]] = {}
    prior_event = ""
    for shot in rows:
        sid = str(shot.get("setting_id") or "set_1").strip() or "set_1"
        states = _normalize_cast_states(shot)
        carried = carried_by_setting.get(sid) or {}
        changes: list[str] = []
        for cid, entry in list(states.items()):
            previous = carried.get(cid) or {}
            if not entry.get("wardrobe") and previous.get("wardrobe"):
                entry["wardrobe"] = previous["wardrobe"]
            if not entry.get("emotion") and previous.get("emotion"):
                entry["emotion"] = previous["emotion"]
            wardrobe = str(entry.get("wardrobe") or "").strip()
            previous_wardrobe = str(previous.get("wardrobe") or "").strip()
            if wardrobe and previous_wardrobe and wardrobe != previous_wardrobe:
                changes.append(f"{cid} now wears {wardrobe}")
            states[cid] = entry
        shot["cast_states"] = states
        shot["wardrobe_changes"] = changes[:6]
        carried_by_setting[sid] = {
            cid: dict(entry) for cid, entry in states.items()
        }
        end = normalize_shot_state(shot.get("end_state"))
        action = str(shot.get("action") or "")
        irreversible = _short(
            str(shot.get("irreversible") or end.get("irreversible") or ""),
            limit=160,
        )
        if _is_action_restatement(irreversible, action):
            irreversible = ""
        if irreversible:
            shot["irreversible"] = irreversible
            end["irreversible"] = irreversible
            shot["end_state"] = end
        authored = [
            _short(str(item), limit=160)
            for item in (shot.get("do_not_replay") or [])
            if str(item).strip()
        ]
        replay: list[str] = []
        for item in ([prior_event] if prior_event else []) + authored:
            if item and item not in replay and not _is_action_restatement(item, action):
                replay.append(item)
        shot["do_not_replay"] = replay[:6]
        prior_event = irreversible or prior_event
    return shots


def ensure_clip_start_end_states(
    shots: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Fill start_state/end_state and chain same-setting start from prior end."""
    out: list[dict[str, Any]] = []
    last_end_by_setting: dict[str, dict[str, Any]] = {}
    last_action_by_setting: dict[str, str] = {}
    for raw in shots or []:
        if not isinstance(raw, dict):
            continue
        shot = dict(raw)
        # Enrich positioning/action/relationship before state fill.
        try:
            from jiuwenswarm.server.runtime.designer.pipeline.clip_staging_lock import (
                enrich_clip_staging,
            )

            enrich_clip_staging(shot, None)
        except Exception:  # noqa: BLE001
            pass
        sid = str(shot.get("setting_id") or "set_1").strip() or "set_1"
        action = str(shot.get("action") or shot.get("clip_prompt") or "")
        plan_positions = spatial_positions_from_shot(shot)
        start = normalize_shot_state(shot.get("start_state"))
        end = normalize_shot_state(shot.get("end_state"))
        if not start:
            prior_end = last_end_by_setting.get(sid) or {}
            if prior_end:
                # Keep where everyone is. Drop the previous motion so this clip
                # does not play the last shot's tail again.
                start = _hold_state(prior_end, last_action_by_setting.get(sid) or "")
            else:
                start = _infer_start_from_shot(shot)
        elif _is_action_restatement(str(start.get("pose") or ""), last_action_by_setting.get(sid) or ""):
            start = _hold_state(start, last_action_by_setting.get(sid) or "")
        # Fill thin start positions from this-row spatial plan / blocking.
        start_positions = merge_spatial_maps(start.get("seats"), plan_positions)
        if start_positions:
            start["seats"] = start_positions
        if not end:
            end = _infer_end_from_shot(shot)
        elif _is_action_restatement(str(end.get("pose") or ""), action):
            end = _hold_state(end, action)
        # Carry spatial positions from start into end when end omitted them.
        if start.get("seats") and not end.get("seats"):
            exited = set(end.get("exited") or [])
            end["seats"] = {
                k: v for k, v in (start.get("seats") or {}).items() if k not in exited
            }
        else:
            end_positions = merge_spatial_maps(
                end.get("seats"), start.get("seats"), plan_positions
            )
            if end_positions:
                exited = set(end.get("exited") or [])
                end["seats"] = {
                    k: v for k, v in end_positions.items() if k not in exited
                }
        shot["start_state"] = start
        shot["end_state"] = end
        # Spatial anchors for this clip open = start positions (detailed).
        if isinstance(start.get("seats"), dict) and start["seats"]:
            _stamp_spatial_anchors(shot, dict(start["seats"]))
        elif plan_positions:
            _stamp_spatial_anchors(shot, dict(plan_positions))
        last_end_by_setting[sid] = end
        last_action_by_setting[sid] = action
        out.append(shot)
    curved = apply_story_curve(out)
    # Reconcile change vs opening/hold and chain setting-scoped carries.
    try:
        from jiuwenswarm.server.runtime.designer.pipeline.clip_continuity_contract import (
            apply_continuity_contracts,
        )

        return apply_continuity_contracts(curved)
    except Exception:  # noqa: BLE001
        return curved


def validate_storyboard_state_chain(
    shots: list[dict[str, Any]] | None,
) -> list[str]:
    """Return domain-agnostic validation notes (empty = ok)."""
    notes: list[str] = []
    last_end_by_setting: dict[str, dict[str, Any]] = {}
    for shot in shots or []:
        if not isinstance(shot, dict):
            continue
        idx = int(shot.get("clip_index") or 0) or "?"
        sid = str(shot.get("setting_id") or "").strip() or "set_1"
        start = normalize_shot_state(shot.get("start_state"))
        end = normalize_shot_state(shot.get("end_state"))
        if not start:
            notes.append(f"shot{idx}:missing_start_state")
        if not end:
            notes.append(f"shot{idx}:missing_end_state")
        prior = last_end_by_setting.get(sid)
        if prior and start:
            # Soft structural check: prior exited should not be on_screen at start
            # unless storyboard returned them.
            prior_exited = {str(x) for x in (prior.get("exited") or []) if str(x)}
            start_on = {str(x) for x in (start.get("on_screen") or shot.get("on_screen") or []) if str(x)}
            leaked = sorted(prior_exited & start_on)
            # Return is allowed — only flag if start explicitly lists them in exited too.
            start_exited = {str(x) for x in (start.get("exited") or []) if str(x)}
            bad = sorted(prior_exited & start_exited & start_on)
            if bad:
                notes.append(f"shot{idx}:exited_cast_marked_on_screen:{','.join(bad)}")
        last_end_by_setting[sid] = end or prior or {}
    return notes


def stamp_shot_states_on_clip_cfg(
    cfg: dict[str, Any],
    *,
    shot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy this storyboard row's start/end + detailed locks onto clip config.

    Used by text-led (smart_graph) and reference-led builders so every mode
    gets hard spatial_anchors (place/posture for any stance), positioning,
    occupancy, speech, and cast_actions.
    """
    out = dict(cfg or {})
    shot = shot if isinstance(shot, dict) else {}
    start = normalize_shot_state(shot.get("start_state") or out.get("start_state"))
    end = normalize_shot_state(shot.get("end_state") or out.get("end_state"))
    plan_positions = spatial_positions_from_shot(shot) or merge_spatial_maps(
        out.get("spatial_anchors"),
        out.get("seat_anchors"),
        start.get("seats") if isinstance(start, dict) else None,
    )
    if start:
        if plan_positions:
            start["seats"] = merge_spatial_maps(start.get("seats"), plan_positions)
        out["start_state"] = start
        if isinstance(start.get("seats"), dict) and start["seats"]:
            _stamp_spatial_anchors(out, dict(start["seats"]))
        elif plan_positions:
            _stamp_spatial_anchors(out, dict(plan_positions))
        holds = [str(x) for x in (out.get("pose_holds") or []) if str(x).strip()]
        pose = str(start.get("pose") or "").strip()
        if pose:
            hold = pose if pose.lower().startswith("already") else f"Opening hold: {pose}"
            if hold not in holds:
                holds.insert(0, hold[:200])
            out["pose_holds"] = holds[:8]
        facing = str(start.get("facing") or "").strip()
        if facing:
            hold = f"Opening facing: {facing}"
            if hold not in (out.get("pose_holds") or []):
                out.setdefault("pose_holds", [])
                out["pose_holds"] = [hold, *list(out.get("pose_holds") or [])][:8]
        # Per-character spatial holds: posture (sit/stand/walk/…) + place.
        for cid, anchor in list((out.get("spatial_anchors") or out.get("seat_anchors") or {}).items())[:8]:
            if not isinstance(anchor, dict):
                continue
            place = anchor.get("place") or anchor.get("zone") or anchor.get("seat") or ""
            posture = anchor.get("posture") or anchor.get("pose") or ""
            bits = [b for b in (posture, f"at {place}" if place else "") if b]
            if not bits:
                continue
            hold = f"{cid} opening: {' '.join(bits)}"
            holds = [str(x) for x in (out.get("pose_holds") or []) if str(x).strip()]
            if hold not in holds:
                holds.insert(0, hold[:200])
                out["pose_holds"] = holds[:8]
    elif plan_positions:
        _stamp_spatial_anchors(out, dict(plan_positions))
    if end:
        if plan_positions and not end.get("seats"):
            exited = set(end.get("exited") or [])
            end["seats"] = {k: v for k, v in plan_positions.items() if k not in exited}
        out["end_state"] = end
        # Exited after this shot — for next storyboard row, not prior-clip handoff.
        exited = [str(x) for x in (end.get("exited") or []) if str(x)]
        if exited:
            out["exiting_character_ids"] = exited
    emotion = emotion_label(shot.get("emotion") or out.get("emotion"))
    if emotion:
        out["emotion"] = emotion
    irreversible = _short(str(shot.get("irreversible") or out.get("irreversible") or ""), limit=160)
    if irreversible:
        out["irreversible"] = irreversible
    replay = [
        _short(str(item), limit=160)
        for item in (shot.get("do_not_replay") or out.get("do_not_replay") or [])
        if str(item).strip()
    ]
    if replay:
        out["do_not_replay"] = replay[:6]
    if isinstance(shot.get("cast_states"), dict) and shot.get("cast_states"):
        out["cast_states"] = shot["cast_states"]
    changes = [
        _short(str(item), limit=160)
        for item in (shot.get("wardrobe_changes") or [])
        if str(item).strip()
    ]
    if changes:
        out["wardrobe_changes"] = changes[:6]

    # Clip-local lock fields (reference-led and text-led share this stamp).
    if shot.get("action") and not out.get("clip_action"):
        out["clip_action"] = str(shot["action"])[:500]
    if shot.get("camera") and not out.get("camera"):
        out["camera"] = str(shot["camera"])[:120]
    if shot.get("timeline") and not out.get("timeline"):
        out["timeline"] = str(shot["timeline"])[:40]
    if isinstance(shot.get("character_ids"), list) and not out.get("character_ids"):
        out["character_ids"] = [str(x) for x in shot["character_ids"] if str(x)]
    if isinstance(shot.get("on_screen"), list):
        out["on_screen"] = [str(x) for x in shot["on_screen"] if str(x)][:12]
    if isinstance(shot.get("offscreen"), list):
        out["offscreen"] = [str(x) for x in shot["offscreen"] if str(x)][:12]
    if isinstance(shot.get("cast_actions"), dict) and shot["cast_actions"]:
        out["cast_actions"] = {
            str(k): str(v)[:200]
            for k, v in shot["cast_actions"].items()
            if str(k).strip() and str(v).strip()
        }
    if isinstance(shot.get("occupancy"), dict) and shot["occupancy"]:
        out["occupancy"] = shot["occupancy"]
    if isinstance(shot.get("blocking"), dict) and shot["blocking"]:
        out["blocking"] = shot["blocking"]
    if isinstance(shot.get("continuity_lock"), dict) and shot["continuity_lock"]:
        out["continuity_lock"] = shot["continuity_lock"]
    if isinstance(shot.get("crowd_lock"), dict) and shot["crowd_lock"]:
        out["crowd_lock"] = shot["crowd_lock"]
    if isinstance(shot.get("spatial_lock"), dict) and shot["spatial_lock"]:
        out["spatial_lock"] = shot["spatial_lock"]
    staging = shot.get("staging") if isinstance(shot.get("staging"), dict) else {}
    for key in ("positioning_lock", "action_lock", "relationship_lock"):
        val = str(shot.get(key) or staging.get(key) or out.get(key) or "").strip()
        if val:
            out[key] = val[:720]
    costume = shot.get("costume_lock") or out.get("costume_lock")
    if isinstance(costume, dict) and costume:
        out["costume_lock"] = costume
    wardrobe = str(shot.get("wardrobe_lock") or out.get("wardrobe_lock") or "").strip()
    if wardrobe:
        out["wardrobe_lock"] = wardrobe[:400]
    if shot.get("speech_line") and not out.get("speech_line"):
        out["speech_line"] = str(shot.get("speech_line"))[:500]
    if isinstance(shot.get("speech_by_character"), dict) and shot["speech_by_character"]:
        out["speech_by_character"] = shot["speech_by_character"]
    if shot.get("language_lock") and not out.get("language_lock"):
        out["language_lock"] = str(shot.get("language_lock"))[:16]
    if shot.get("setting_id") and not out.get("setting_id"):
        out["setting_id"] = str(shot.get("setting_id"))[:40]
    if shot.get("lighting") and not out.get("lighting"):
        out["lighting"] = str(shot.get("lighting"))[:200]
    if shot.get("crowd") and not out.get("crowd"):
        out["crowd"] = str(shot.get("crowd"))[:200]
    motion = str(shot.get("motion_detail") or out.get("motion_detail") or "").strip()
    if motion:
        out["motion_detail"] = motion[:400]
    framing = str(shot.get("camera_framing_rule") or out.get("camera_framing_rule") or "").strip()
    if framing:
        out["camera_framing_rule"] = framing[:220]
    screen = shot.get("screen_axis") or shot.get("screen_positions") or out.get("screen_axis")
    if isinstance(screen, dict) and screen:
        out["screen_axis"] = screen

    try:
        from jiuwenswarm.server.runtime.designer.pipeline.clip_continuity_contract import (
            stamp_contract_on_clip_cfg,
        )

        out = stamp_contract_on_clip_cfg(out, shot=shot)
    except Exception:  # noqa: BLE001
        pass
    # Storyboard row is authority — do not require prior clip wiring.
    out.pop("continuity_clip_node_id", None)
    out["previous_clip_handoff_ready"] = False
    out["previous_action"] = ""
    out["previous_end_state"] = ""
    return out


def start_end_story_lines(cfg: dict[str, Any] | None) -> list[str]:
    """Opening placement from start_state. Finished action poses stay off the video body."""
    cfg = cfg if isinstance(cfg, dict) else {}
    lines: list[str] = []
    action = str(cfg.get("clip_action") or cfg.get("action") or "")
    prior_action = ""
    start = normalize_shot_state(cfg.get("start_state"))
    end = normalize_shot_state(cfg.get("end_state"))
    if start.get("pose") and not _is_action_restatement(
        str(start["pose"]), action, prior_action
    ):
        lines.append(str(start["pose"]).rstrip(".") + ".")
    elif start.get("facing"):
        lines.append(f"Opening: facing {start['facing']}.")
    positions = start.get("seats") if isinstance(start.get("seats"), dict) else {}
    if not positions and isinstance(cfg.get("spatial_anchors"), dict):
        positions = cfg["spatial_anchors"]
    if not positions and isinstance(cfg.get("seat_anchors"), dict):
        positions = cfg["seat_anchors"]
    for cid, anchor in list(positions.items())[:6]:
        if isinstance(anchor, dict):
            place = anchor.get("place") or anchor.get("zone") or anchor.get("seat") or ""
            posture = str(anchor.get("posture") or anchor.get("pose") or "").strip()
            facing = str(anchor.get("facing") or "").strip()
            bits = []
            if posture:
                bits.append(posture)
            if place:
                bits.append(f"at {place}")
            if facing:
                bits.append(f"facing {facing}")
            if bits:
                lines.append(f"{cid} begins {' '.join(bits)}.")
            elif place:
                lines.append(f"{cid} begins at {place}.")
        elif str(anchor).strip():
            lines.append(f"{cid} begins at {anchor}.")
    positioning = _short(str(cfg.get("positioning_lock") or ""), limit=220)
    if positioning and not any("begins" in ln for ln in lines):
        lines.append(f"Opening placement: {positioning.rstrip('.')}.")
    irreversible = _short(str(cfg.get("irreversible") or end.get("irreversible") or ""), limit=160)
    if irreversible and not _is_action_restatement(irreversible, action):
        lines.append(f"By the last frame, {irreversible.rstrip('.')}.")
    if emotion_label(cfg.get("emotion")) == "climax":
        lines.append("This shot is the film's single climax.")
    for change in list(cfg.get("wardrobe_changes") or [])[:3]:
        text = _short(str(change), limit=160)
        if text:
            lines.append(text.rstrip(".") + ".")
    try:
        from jiuwenswarm.server.runtime.designer.pipeline.clip_continuity_contract import (
            hold_lines_for_cfg,
        )

        for hold in hold_lines_for_cfg(cfg):
            if hold and hold not in lines:
                lines.append(hold)
    except Exception:  # noqa: BLE001
        pass
    return lines[:10]
