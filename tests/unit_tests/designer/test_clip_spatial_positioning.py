# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Focused spatial positioning stamp regressions (any stance, not seating-only)."""

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

import pytest

from jiuwenswarm.server.runtime.designer.pipeline.storyboard_clip_state import (
    ensure_clip_start_end_states,
    stamp_shot_states_on_clip_cfg,
)


def _cfg_positions(cfg: dict) -> dict:
    return (
        cfg.get("spatial_anchors")
        if isinstance(cfg.get("spatial_anchors"), dict)
        else cfg.get("seat_anchors")
        if isinstance(cfg.get("seat_anchors"), dict)
        else {}
    )


@pytest.mark.parametrize(
    "failure_case",
    (
        "place_only_no_posture",
        "posture_only_standing",
        "posture_only_walking",
        "thin_zone_no_place",
        "legacy_seat_key_standing",
        "cast_action_standing_by_door",
        "cast_action_walking_along_path",
        "mixed_cast_sit_and_stand",
        "clip2_must_not_replay_clip1_motion",
        "offscreen_not_forced_on_screen",
    ),
)
def test_spatial_positioning_failure_cases(failure_case: str) -> None:
    """Targeted surfaces that seating-only logic would miss."""
    if failure_case == "place_only_no_posture":
        shot = {
            "clip_index": 1,
            "setting_id": "set_1",
            "action": "waits by the window",
            "on_screen": ["char_a"],
            "spatial_anchors": {"char_a": {"place": "near window"}},
        }
        cfg = stamp_shot_states_on_clip_cfg({}, shot=ensure_clip_start_end_states([shot])[0])
        assert _cfg_positions(cfg)["char_a"].get("place") == "near window"

    elif failure_case == "posture_only_standing":
        shot = {
            "clip_index": 1,
            "setting_id": "set_1",
            "action": "stands still",
            "on_screen": ["char_a"],
            "spatial_anchors": {"char_a": {"posture": "standing"}},
        }
        cfg = stamp_shot_states_on_clip_cfg({}, shot=ensure_clip_start_end_states([shot])[0])
        assert "stand" in str(_cfg_positions(cfg)["char_a"].get("posture") or "").lower()

    elif failure_case == "posture_only_walking":
        shot = {
            "clip_index": 1,
            "setting_id": "set_1",
            "action": "walks through the hall",
            "on_screen": ["char_a"],
            "cast_actions": {"char_a": "walking along hallway arch"},
        }
        cfg = stamp_shot_states_on_clip_cfg({}, shot=ensure_clip_start_end_states([shot])[0])
        pos = _cfg_positions(cfg)["char_a"]
        assert "walk" in str(pos.get("posture") or "").lower()
        assert "hallway" in str(pos.get("place") or "").lower()

    elif failure_case == "thin_zone_no_place":
        shot = {
            "clip_index": 1,
            "setting_id": "set_1",
            "action": "holds mid frame",
            "on_screen": ["char_a"],
            "spatial_anchors": {"char_a": {"zone": "mid", "posture": "standing"}},
        }
        cfg = stamp_shot_states_on_clip_cfg({}, shot=ensure_clip_start_end_states([shot])[0])
        pos = _cfg_positions(cfg)["char_a"]
        assert pos.get("place") == "mid" or pos.get("zone") == "mid"
        assert "stand" in str(pos.get("posture") or "").lower()

    elif failure_case == "legacy_seat_key_standing":
        shot = {
            "clip_index": 1,
            "setting_id": "set_1",
            "action": "stands at the rail",
            "on_screen": ["char_a"],
            "seat_anchors": {
                "char_a": {"place": "balcony rail", "posture": "standing"}
            },
        }
        cfg = stamp_shot_states_on_clip_cfg({}, shot=ensure_clip_start_end_states([shot])[0])
        assert cfg.get("spatial_anchors", {}).get("char_a", {}).get("posture") == "standing"
        assert cfg.get("seat_anchors", {}).get("char_a", {}).get("place") == "balcony rail"

    elif failure_case == "cast_action_standing_by_door":
        shot = {
            "clip_index": 1,
            "setting_id": "set_1",
            "action": "greets arrivals",
            "on_screen": ["char_a"],
            "cast_actions": {"char_a": "standing by the door"},
        }
        cfg = stamp_shot_states_on_clip_cfg({}, shot=ensure_clip_start_end_states([shot])[0])
        pos = _cfg_positions(cfg)["char_a"]
        assert pos.get("posture") == "standing"
        assert "door" in str(pos.get("place") or "").lower()

    elif failure_case == "cast_action_walking_along_path":
        shot = {
            "clip_index": 1,
            "setting_id": "set_1",
            "action": "crosses the garden",
            "on_screen": ["char_a"],
            "cast_actions": {"char_a": "walking along garden path"},
        }
        cfg = stamp_shot_states_on_clip_cfg({}, shot=ensure_clip_start_end_states([shot])[0])
        pos = _cfg_positions(cfg)["char_a"]
        assert pos.get("posture") == "walking"
        assert "garden" in str(pos.get("place") or "").lower()

    elif failure_case == "mixed_cast_sit_and_stand":
        shot = {
            "clip_index": 1,
            "setting_id": "set_1",
            "action": "host stands while guest sits",
            "on_screen": ["char_host", "char_guest"],
            "spatial_anchors": {
                "char_host": {"place": "head of table", "posture": "standing"},
                "char_guest": {"place": "foot of table", "posture": "seated"},
            },
        }
        cfg = stamp_shot_states_on_clip_cfg({}, shot=ensure_clip_start_end_states([shot])[0])
        pos = _cfg_positions(cfg)
        assert pos["char_host"]["posture"] == "standing"
        assert pos["char_guest"]["posture"] == "seated"
        assert pos["char_host"]["place"] != pos["char_guest"]["place"]

    elif failure_case == "clip2_must_not_replay_clip1_motion":
        shots = ensure_clip_start_end_states(
            [
                {
                    "clip_index": 1,
                    "setting_id": "set_1",
                    "action": "walks to the window",
                    "on_screen": ["char_a"],
                    "spatial_anchors": {
                        "char_a": {"place": "near window", "posture": "walking"}
                    },
                    "speech_line": "Look!",
                },
                {
                    "clip_index": 2,
                    "setting_id": "set_1",
                    "action": "stands at the window",
                    "on_screen": ["char_a"],
                    "spatial_anchors": {
                        "char_a": {"place": "near window", "posture": "standing"}
                    },
                },
            ]
        )
        cfg2 = stamp_shot_states_on_clip_cfg({}, shot=shots[1])
        pose = str((cfg2.get("start_state") or {}).get("pose") or "").lower()
        assert "walks to the window" not in pose
        assert _cfg_positions(cfg2)["char_a"].get("place")

    else:  # offscreen_not_forced_on_screen
        shot = {
            "clip_index": 1,
            "setting_id": "set_1",
            "action": "solo beat",
            "on_screen": ["char_a"],
            "offscreen": ["char_b"],
            "spatial_anchors": {
                "char_a": {"place": "desk", "posture": "standing"},
            },
        }
        cfg = stamp_shot_states_on_clip_cfg({}, shot=ensure_clip_start_end_states([shot])[0])
        pos = _cfg_positions(cfg)
        assert "char_a" in pos
        assert "char_b" not in (cfg.get("on_screen") or [])


def test_reference_led_prepare_preserves_structured_spatial_positions() -> None:
    from jiuwenswarm.server.runtime.designer.pipeline.reference_led import _prepare_shots

    analysis = {
        "characters": [{"id": "char_a", "name": "Amen"}],
        "clips": [
            {
                "action": "Amen stands and raises a glass",
                "setting_id": "set_1",
                "on_screen": ["char_a"],
                "spatial_anchors": {
                    "char_a": {
                        "place": "head of table",
                        "posture": "standing",
                        "facing": "toward guests",
                    }
                },
                "cast_actions": {"char_a": "standing at head of table, raises glass"},
                "speech_line": "To us!",
            },
            {
                "action": "Amen nods",
                "setting_id": "set_1",
                "on_screen": ["char_a"],
                "spatial_anchors": {
                    "char_a": {
                        "place": "head of table",
                        "posture": "standing",
                        "facing": "toward guests",
                    }
                },
            },
        ],
    }
    shots = _prepare_shots(analysis, "dinner toast")
    assert len(shots) == 2
    assert isinstance(shots[0].get("end_state"), dict)
    assert shots[0].get("spatial_anchors", {}).get("char_a", {}).get("place")
    cfg0 = stamp_shot_states_on_clip_cfg({}, shot=shots[0])
    cfg1 = stamp_shot_states_on_clip_cfg({}, shot=shots[1])
    assert cfg0["spatial_anchors"]["char_a"]["place"] == "head of table"
    assert cfg0["spatial_anchors"]["char_a"]["posture"] == "standing"
    assert cfg1["spatial_anchors"]["char_a"]["place"] == "head of table"
    assert "raises a glass" not in str(cfg1.get("start_state", {}).get("pose") or "")


def test_reference_led_graph_stamps_spatial_positions_on_clip_nodes() -> None:
    from jiuwenswarm.server.runtime.designer.pipeline.reference_led import (
        ROLE_CHARACTER,
        ROLE_SCENE,
        VIDEO_MULTI_REF,
        build_reference_led_video_graph,
    )

    analysis = {
        "characters": [{"id": "char_a", "name": "Amen", "description": "host"}],
        "scenes": [{"id": "set_1", "description": "dining room"}],
        "clips": [
            {
                "action": "Amen toasts while standing",
                "setting_id": "set_1",
                "on_screen": ["char_a"],
                "spatial_anchors": {
                    "char_a": {
                        "place": "head of table",
                        "posture": "standing",
                        "facing": "guests",
                    }
                },
                "cast_actions": {"char_a": "standing toast"},
                "speech_line": "Cheers",
                "duration_sec": 5,
            }
        ],
        "style_lock": {"medium": "live action", "look": "warm indoor"},
        "creative_intent": {
            "mode": "reference_led",
            "slots": [
                {
                    "slot": 1,
                    "node_id": "n_ref_char",
                    "roles": [ROLE_CHARACTER],
                    "bindings": {ROLE_CHARACTER: "verbatim"},
                    "character_id": "char_a",
                    "path": "/tmp/char.png",
                    "video_binding": VIDEO_MULTI_REF,
                },
                {
                    "slot": 2,
                    "node_id": "n_ref_scene",
                    "roles": [ROLE_SCENE],
                    "bindings": {ROLE_SCENE: "verbatim"},
                    "setting_id": "set_1",
                    "path": "/tmp/scene.png",
                    "video_binding": VIDEO_MULTI_REF,
                },
            ],
        },
    }
    graph = build_reference_led_video_graph(
        project_id="p_test",
        prompt="dinner toast",
        analysis=analysis,
        title="Spatial stamp",
    )
    clips = [
        n
        for n in graph["nodes"]
        if (n.get("config") or {}).get("role") == "clip"
        or str(n.get("id") or "").startswith("n_clip_")
    ]
    assert clips
    cfg = clips[0]["config"]
    assert cfg.get("start_state")
    assert cfg.get("spatial_anchors", {}).get("char_a", {}).get("place") == "head of table"
    assert cfg.get("spatial_anchors", {}).get("char_a", {}).get("posture") == "standing"
    assert cfg.get("seat_anchors", {}).get("char_a", {}).get("posture") == "standing"
    prompt = str((cfg.get("generate") or {}).get("prompt") or "")
    assert "head of table" in prompt.lower() or "begins" in prompt.lower()


def test_brief_instruction_spatial_not_seat_authority() -> None:
    from jiuwenswarm.server.runtime.designer.handlers.text_nodes import _BRIEF_INSTRUCTION

    text = _BRIEF_INSTRUCTION.lower()
    assert "spatial" in text
    assert "copy locks, do not drop them" not in text
    assert "seating plans" not in text
