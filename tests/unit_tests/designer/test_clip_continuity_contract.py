# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Continuity contract: authored-state chains, holds, enforcement, user-origin guard."""

from __future__ import annotations

import sys
import types

try:
    import openjiuwen.core.kv_cache  # noqa: F401
except ImportError:  # pragma: no cover - shared designer test shim
    _pkg = types.ModuleType("openjiuwen")
    _core = types.ModuleType("openjiuwen.core")
    _kv = types.ModuleType("openjiuwen.core.kv_cache")
    _kv.KVCacheAffinityConfig = type("KVCacheAffinityConfig", (), {})
    _pkg.core, _core.kv_cache = _core, _kv
    sys.modules.setdefault("openjiuwen", _pkg)
    sys.modules.setdefault("openjiuwen.core", _core)
    sys.modules["openjiuwen.core.kv_cache"] = _kv

from jiuwenswarm.server.runtime.designer.pipeline.clip_continuity_contract import (
    apply_continuity_contracts,
    enforce_prompt_continuity,
    extract_prop_holds,
    extract_prop_removals,
    hold_lines_for_cfg,
    reconcile_shot_to_contract,
    stamp_contract_on_clip_cfg,
)
from jiuwenswarm.server.runtime.designer.pipeline.storyboard_clip_state import (
    ensure_clip_start_end_states,
    stamp_shot_states_on_clip_cfg,
)


def _p(idx: int, setting: str, action: str = "Beat.", on_screen: tuple = ("char_1",), **extra) -> dict:
    return {"clip_index": idx, "setting_id": setting, "action": action,
            "on_screen": list(on_screen), **extra}


def _pipe(shots: list[dict]) -> list[dict]:
    """ensure → stamp → enforce, the production clip path. Returns cfg per clip."""
    rows = []
    for shot in ensure_clip_start_end_states(shots):
        cfg = stamp_shot_states_on_clip_cfg({}, shot=shot)
        enforce_prompt_continuity(str(shot.get("action") or "Camera holds."), cfg)
        rows.append(cfg)
    return rows


def _props_of(cfg: dict) -> dict:
    for source, nested in ((cfg.get("clip_contract"), True), (cfg.get("scene_hold"), False)):
        if not isinstance(source, dict):
            continue
        holder = source.get("hold") if nested else source
        props = holder.get("props") if isinstance(holder, dict) else None
        if isinstance(props, dict) and props:
            return props
    return {}


def _blob(cfg: dict) -> str:
    return (str(_props_of(cfg)) + " " + str(cfg.get("pose_holds") or [])).lower()


def test_reconcile_uses_authored_positions_only() -> None:
    """Opening/ending positioning come from authored states — no text inference."""
    shot = _p(
        2, "set_1", "The child climbs onto the chair and sits upright.",
        start_state={"seats": {"char_a": {"place": "left side", "posture": "standing"}}},
        end_state={"seats": {"char_a": {"place": "left side", "posture": "seated"}}},
    )
    opening = reconcile_shot_to_contract(shot)["opening"]["char_a"]
    assert opening.get("posture") == "standing"
    assert shot["end_state"]["seats"]["char_a"].get("posture") == "seated"


def test_prose_is_never_parsed_and_nothing_is_guessed() -> None:
    """No authored state → empty contract, empty prop holds/removals."""
    shot = _p(2, "set_1", "Host sets down the blue ceramic teapot at the mantel and sits.")
    assert reconcile_shot_to_contract(shot)["opening"] == {}
    assert extract_prop_holds(shot) == {}
    assert extract_prop_removals(shot) == []


def test_prop_hold_carries_to_next_shot_and_prompt() -> None:
    """Authored prop survives the agent rewrite: hold lines + enforce reinjection."""
    shots = apply_continuity_contracts(
        [
            _p(
                1, "set_1", "A cook sets the steaming platter at the center of the table.",
                end_state={"props": {"steaming platter": "the center of the table"}},
            ),
            _p(2, "set_1", "Guests sit and fold their hands.", on_screen=("char_a", "char_b")),
        ]
    )
    cfg = stamp_contract_on_clip_cfg(
        stamp_shot_states_on_clip_cfg({}, shot=shots[1]), shot=shots[1]
    )
    assert any("platter" in line.lower() for line in hold_lines_for_cfg(cfg))
    fixed, notes = enforce_prompt_continuity("Guests sit and fold their hands.", cfg)
    assert "platter" in fixed.lower()
    assert notes


def test_setting_cut_and_return_isolates_holds() -> None:
    rows = _pipe(
        [
            _p(1, "set_a", "Places the gift box.", end_state={"props": {"gift box": "the mantel"}}),
            _p(2, "set_b", "Cut to the hallway.", on_screen=("char_2",)),
            _p(3, "set_a", "Back by the mantel."),
        ]
    )
    assert "gift" in _blob(rows[0])
    assert "gift" not in _blob(rows[1])
    assert "gift" in _blob(rows[2])


def test_cleared_prop_stops_being_held() -> None:
    rows = _pipe(
        [
            _p(1, "set_1", "Places the crate.", end_state={"props": {"wooden crate": "the floor"}}),
            _p(2, "set_1", "Removes the crate.", end_state={"cleared": ["wooden crate"]}),
            _p(3, "set_1", "Guest enters.", on_screen=("char_2",)),
        ]
    )
    assert "crate" in _blob(rows[0])
    assert "crate" not in _blob(rows[2])


def test_multiple_prop_holds_survive() -> None:
    rows = _pipe(
        [
            _p(1, "set_1", "Places the teapot and the ledger.",
               end_state={"props": {"blue teapot": "the mantel", "leather ledger": "the shelf"}}),
            _p(2, "set_1", "Quiet beat."),
        ]
    )
    blob = _blob(rows[1])
    assert "teapot" in blob and "ledger" in blob


def test_enforce_prompt_continuity_never_truncates() -> None:
    """Backend limits are advisory — enforcement must not cut text (was [:4000])."""
    long_prompt = "The camera creeps slowly across the room. " * 120
    assert len(long_prompt) > 4000
    out, _ = enforce_prompt_continuity(long_prompt, {})
    assert out == long_prompt.strip()


def test_user_origin_prompt_is_not_appended_with_holds() -> None:
    """Toolbar/user edits win over hold re-injection (no 'Continuity holds' block)."""
    from jiuwenswarm.server.runtime.designer.pipeline.video_prompt_practice import (
        director_approve_video_prompt,
    )

    shot = _p(1, "set_1", "Places the gift box.", end_state={"props": {"gift box": "the mantel"}})
    cfg = stamp_shot_states_on_clip_cfg({}, shot=ensure_clip_start_end_states([shot])[0])
    user_text = "Host walks out of frame; the mantel is left empty behind him."
    cfg["generate"] = {"prompt": user_text, "prompt_origin": "user"}
    approved, reasons = director_approve_video_prompt(
        user_text, cfg=cfg, graph={}, clip_index=1, action="", camera=""
    )
    assert "Continuity holds" not in approved
    assert "holds_skipped_user_origin" in reasons


def test_later_authored_end_position_updates_scene_hold() -> None:
    """Latest authored end position wins in the setting store (not first-seen)."""
    seats_v1 = {"char_1": {"place": "near window", "posture": "standing"}}
    seats_v2 = {"char_1": {"place": "at the table", "posture": "seated"}}
    shots = apply_continuity_contracts(
        [
            _p(1, "set_1", "Stands near the window.", end_state={"seats": seats_v1}),
            _p(2, "set_1", "Sits at the table.", end_state={"seats": seats_v2}),
            _p(3, "set_1", "Quiet beat."),
        ]
    )
    anchor = (shots[2].get("clip_contract") or {}).get("opening", {}).get("char_1") or {}
    assert "table" in str(anchor.get("place") or "").lower()
    assert str(anchor.get("posture") or "").lower() == "seated"


def test_brief_instruction_forbids_lock_sections() -> None:
    from jiuwenswarm.server.runtime.designer.handlers.text_nodes import _BRIEF_INSTRUCTION

    text = _BRIEF_INSTRUCTION.lower()
    assert "forbidden" in text
    assert "production lock bible" in text
    assert "copy locks, do not drop them" not in text
    assert "seating plans" not in text
