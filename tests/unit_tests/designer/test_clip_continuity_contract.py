# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""General continuity contract: reconcile, hold chain, prompt verify."""

from __future__ import annotations

import sys
import types

try:
    import openjiuwen.core.kv_cache  # noqa: F401
except ImportError:
    _package = types.ModuleType("openjiuwen")
    _core = types.ModuleType("openjiuwen.core")
    _kv = types.ModuleType("openjiuwen.core.kv_cache")

    class KVCacheAffinityConfig:
        pass

    _kv.KVCacheAffinityConfig = KVCacheAffinityConfig
    _package.core = _core
    _core.kv_cache = _kv
    sys.modules.setdefault("openjiuwen", _package)
    sys.modules.setdefault("openjiuwen.core", _core)
    sys.modules["openjiuwen.core.kv_cache"] = _kv


def test_reconcile_fixes_opening_already_at_result_posture() -> None:
    from jiuwenswarm.server.runtime.designer.pipeline.clip_continuity_contract import (
        reconcile_shot_to_contract,
    )

    shot = {
        "clip_index": 2,
        "setting_id": "set_1",
        "action": "The child climbs onto the chair and sits upright.",
        "on_screen": ["char_a"],
        "cast_actions": {"char_a": "climbing into the chair and sitting upright"},
        "spatial_anchors": {
            "char_a": {"place": "the left side", "posture": "seated"},
        },
        "start_state": {
            "seats": {"char_a": {"place": "the left side", "posture": "seated"}},
        },
    }
    contract = reconcile_shot_to_contract(shot)
    opening = contract["opening"]["char_a"]
    ending = shot["end_state"]["seats"]["char_a"]
    assert opening.get("posture") == "standing"
    assert ending.get("posture") == "seated"


def test_sets_down_and_rests_and_remove_use_backend_verbs() -> None:
    from jiuwenswarm.server.runtime.designer.pipeline.clip_continuity_contract import (
        extract_prop_holds,
        extract_prop_removals,
    )
    from jiuwenswarm.server.runtime.designer.pipeline.storyboard_clip_state import (
        ensure_clip_start_end_states,
        stamp_shot_states_on_clip_cfg,
    )
    from jiuwenswarm.server.runtime.designer.pipeline.clip_continuity_contract import (
        enforce_prompt_continuity,
    )

    down = extract_prop_holds("Host sets down the blue ceramic teapot at the mantel.")
    assert down
    label = " ".join(str(v.get("label") or "") for v in down.values()).lower()
    assert "teapot" in label
    assert not label.startswith("down")

    rests = extract_prop_holds("Host rests the brass desk lamp at the shelf.")
    assert any("lamp" in str(v.get("label") or "").lower() for v in rests.values())

    assert extract_prop_removals("Host removes the brass desk lamp from the shelf.")

    shots = ensure_clip_start_end_states(
        [
            {
                "clip_index": 1,
                "setting_id": "set_1",
                "action": "Host places the gift box on the mantel.",
                "on_screen": ["char_1"],
            },
            {
                "clip_index": 2,
                "setting_id": "set_1",
                "action": "Host removes the gift box from the mantel.",
                "on_screen": ["char_1"],
            },
            {
                "clip_index": 3,
                "setting_id": "set_1",
                "action": "Guest looks at the empty mantel.",
                "on_screen": ["char_2"],
            },
        ]
    )
    cfg3 = stamp_shot_states_on_clip_cfg({}, shot=shots[2])
    fixed, _ = enforce_prompt_continuity("Guest looks around.", cfg3)
    assert "gift" not in fixed.lower() and "box" not in fixed.lower()


def test_prop_hold_resolves_pronoun_past_path_preposition() -> None:
    """'carries X from the doorway and sets it at Y' must hold X, not doorway."""
    from jiuwenswarm.server.runtime.designer.pipeline.clip_continuity_contract import (
        apply_continuity_contracts,
        enforce_prompt_continuity,
        extract_prop_holds,
    )
    from jiuwenswarm.server.runtime.designer.pipeline.storyboard_clip_state import (
        stamp_shot_states_on_clip_cfg,
    )

    holds = extract_prop_holds(
        "Mom carries a steaming casserole dish from the kitchen doorway "
        "and sets it at the center of the wooden dining table."
    )
    assert holds
    labels = " ".join(str(v.get("label") or "") for v in holds.values()).lower()
    assert "casserole" in labels or "dish" in labels
    assert "doorway" not in labels
    assert "kitchen" not in labels

    shots = apply_continuity_contracts(
        [
            {
                "clip_index": 1,
                "setting_id": "set_1",
                "action": (
                    "Mom carries a steaming casserole dish from the kitchen doorway "
                    "and sets it at the center of the wooden dining table."
                ),
                "on_screen": ["char_2"],
                "cast_actions": {"char_2": "sets the dish"},
                "end_state": {"pose": "the meal is on the table"},
            },
            {
                "clip_index": 2,
                "setting_id": "set_1",
                "action": "Mom sits. Kids climb into chairs.",
                "on_screen": ["char_2", "char_3"],
                "cast_actions": {
                    "char_2": "seating herself at the right side",
                    "char_3": "climbing into her chair and sitting upright",
                },
            },
        ]
    )
    cfg = stamp_shot_states_on_clip_cfg({}, shot=shots[1])
    fixed, _ = enforce_prompt_continuity("Mom sits. Kids climb into chairs.", cfg)
    assert "casserole" in fixed.lower() or "dish" in fixed.lower()
    assert "meal" in fixed.lower()
    assert "doorway" not in fixed.lower()


def test_prop_hold_carries_to_next_shot_and_prompt() -> None:
    from jiuwenswarm.server.runtime.designer.pipeline.clip_continuity_contract import (
        apply_continuity_contracts,
        enforce_prompt_continuity,
        hold_lines_for_cfg,
        stamp_contract_on_clip_cfg,
    )
    from jiuwenswarm.server.runtime.designer.pipeline.storyboard_clip_state import (
        stamp_shot_states_on_clip_cfg,
    )

    shots = apply_continuity_contracts(
        [
            {
                "clip_index": 1,
                "setting_id": "set_1",
                "action": (
                    "A cook sets the steaming platter at the center of the table. "
                    "Guests walk in."
                ),
                "on_screen": ["char_a"],
                "cast_actions": {"char_a": "setting the platter down"},
                "end_state": {
                    "pose": "the meal is on the table",
                    "seats": {"char_a": {"place": "near table", "posture": "standing"}},
                },
            },
            {
                "clip_index": 2,
                "setting_id": "set_1",
                "action": "Guests sit and fold their hands.",
                "on_screen": ["char_a", "char_b"],
                "cast_actions": {
                    "char_a": "standing at the head of the table",
                    "char_b": "sitting at the right side",
                },
            },
        ]
    )
    assert "platter" in str(shots[0].get("scene_hold_after") or {}).lower() or (
        "platter" in str(shots[1].get("clip_contract") or {}).lower()
    )
    hold = (shots[1].get("clip_contract") or {}).get("hold") or {}
    props = hold.get("props") or {}
    assert props, "shot 2 must inherit prop holds from shot 1"
    assert any("platter" in str(v.get("label") or "").lower() for v in props.values())

    cfg = stamp_shot_states_on_clip_cfg({}, shot=shots[1])
    cfg = stamp_contract_on_clip_cfg(cfg, shot=shots[1])
    lines = hold_lines_for_cfg(cfg)
    assert any("platter" in ln.lower() for ln in lines)
    # Agent dropped the prop — enforce reinjects.
    fixed, notes = enforce_prompt_continuity(
        "Guests sit and fold their hands. Camera holds medium.",
        cfg,
    )
    assert "platter" in fixed.lower()
    assert notes


def test_cast_action_place_wins_over_conflicting_lock_place() -> None:
    from jiuwenswarm.server.runtime.designer.pipeline.clip_continuity_contract import (
        reconcile_shot_to_contract,
    )

    shot = {
        "clip_index": 2,
        "setting_id": "set_1",
        "action": "Mom sits at the right side of the table.",
        "on_screen": ["char_mom"],
        "cast_actions": {"char_mom": "seating herself at the right side of the table"},
        "spatial_anchors": {
            # Wrong: prop place used as person place.
            "char_mom": {"place": "table center", "posture": "seated"},
        },
    }
    contract = reconcile_shot_to_contract(shot)
    end_place = (shot.get("end_state") or {}).get("seats", {}).get("char_mom", {}).get(
        "place", ""
    )
    assert "right" in end_place.lower()
    assert contract["opening"]["char_mom"].get("posture") == "standing"


def test_brief_instruction_forbids_lock_sections() -> None:
    from jiuwenswarm.server.runtime.designer.handlers.text_nodes import _BRIEF_INSTRUCTION

    text = _BRIEF_INSTRUCTION.lower()
    assert "forbidden" in text
    assert "production lock bible" in text
    assert "copy locks, do not drop them" not in text


def test_ensure_chains_contracts() -> None:
    from jiuwenswarm.server.runtime.designer.pipeline.storyboard_clip_state import (
        ensure_clip_start_end_states,
        stamp_shot_states_on_clip_cfg,
    )

    shots = ensure_clip_start_end_states(
        [
            {
                "clip_index": 1,
                "setting_id": "set_a",
                "action": "Host places the gift box on the mantel.",
                "on_screen": ["char_1"],
                "cast_actions": {"char_1": "places the gift box on the mantel"},
            },
            {
                "clip_index": 2,
                "setting_id": "set_a",
                "action": "Host turns and smiles.",
                "on_screen": ["char_1"],
                "cast_actions": {"char_1": "standing by the mantel, smiling"},
            },
        ]
    )
    assert shots[1].get("clip_contract")
    cfg2 = stamp_shot_states_on_clip_cfg({}, shot=shots[1])
    assert cfg2.get("scene_hold") or cfg2.get("clip_contract")
    prompt = "Host turns and smiles at camera."
    from jiuwenswarm.server.runtime.designer.pipeline.clip_continuity_contract import (
        enforce_prompt_continuity,
    )

    fixed, _ = enforce_prompt_continuity(prompt, cfg2)
    assert "gift" in fixed.lower() or "box" in fixed.lower() or "mantel" in fixed.lower()
