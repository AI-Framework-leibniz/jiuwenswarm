# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Spatial positioning stamping: any stance, any authored source, two characters."""

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

import pytest

from jiuwenswarm.server.runtime.designer.pipeline.storyboard_clip_state import (
    ensure_clip_start_end_states,
    spatial_positions_from_shot,
    stamp_shot_states_on_clip_cfg,
)

_SOURCES = ("spatial_anchors", "seat_anchors_legacy", "blocking", "end_state", "start_state")
_POSTURES = ("standing", "seated", "walking", "kneeling")
_PLACE_KEYS = ("place", "zone", "seat", "landmark")
_POSTURE_KEYS = ("posture", "pose")


def _text(anchor: dict, keys: tuple) -> str:
    return " ".join(str(anchor.get(key) or "").strip() for key in keys).strip()


def _shot(place: str, posture: str, source: str, chars: tuple = ("char_a", "char_b")) -> dict:
    anchors = {cid: {"place": f"{place} [{cid[-1]}]", "posture": posture} for cid in chars}
    shot = {
        "clip_index": 1,
        "setting_id": "set_1",
        "action": f"Beat: {posture} at {place}",
        "camera": "medium / eye-level",
        "on_screen": list(chars),
        "cast_actions": {cid: f"{posture} at {place}" for cid in chars},
    }
    if source == "spatial_anchors":
        shot["spatial_anchors"] = anchors
    elif source == "seat_anchors_legacy":
        shot["seat_anchors"] = anchors
    elif source == "blocking":
        shot["blocking"] = {
            "landmark": place,
            "positions": [
                {"character_id": cid, "place": anchors[cid]["place"], "pose": posture, "near": place}
                for cid in chars
            ],
        }
    elif source == "end_state":
        shot["end_state"] = {"pose": f"Ending {posture} at {place}", "seats": anchors}
    else:
        shot["start_state"] = {"pose": f"Already {posture} at {place}", "seats": anchors}
    return shot


@pytest.mark.parametrize("source", _SOURCES)
@pytest.mark.parametrize("posture", _POSTURES)
def test_every_source_stamps_place_and_posture(posture: str, source: str) -> None:
    """5 sources × 4 stances: canonical anchors keep place + posture for both chars."""
    ensured = ensure_clip_start_end_states([_shot("head of table", posture, source)])[0]
    positions = spatial_positions_from_shot(ensured)
    assert positions
    cfg = stamp_shot_states_on_clip_cfg({}, shot=ensured)
    stamped = cfg.get("spatial_anchors") or {}
    assert stamped and "seat_anchors" not in cfg, "legacy seat_anchors must not be written"
    for cid in ("char_a", "char_b"):
        assert cid in positions and cid in stamped
        assert _text(positions[cid], _PLACE_KEYS + _POSTURE_KEYS)
        anchor = stamped[cid]
        assert _text(anchor, _PLACE_KEYS + _POSTURE_KEYS)
        if posture != "seated":
            got = _text(anchor, _POSTURE_KEYS).lower()
            assert "seated" not in got, (source, posture, got)
    assert cfg.get("previous_action") == ""
    assert cfg.get("previous_clip_handoff_ready") is False


def test_cast_actions_prose_is_not_parsed_for_positions() -> None:
    """Director-authored metadata only: scenario prose never creates clip locks."""
    shot = {
        "clip_index": 1,
        "setting_id": "set_1",
        "action": "Beat: stands at head of table",
        "on_screen": ["char_a"],
        "cast_actions": {"char_a": "standing at the head of the table"},
    }
    ensured = ensure_clip_start_end_states([shot])[0]
    assert spatial_positions_from_shot(ensured) == {}
    cfg = stamp_shot_states_on_clip_cfg({}, shot=ensured)
    assert not (cfg.get("spatial_anchors") or {})


def test_restamp_row_overwrites_and_silent_row_keeps_cfg_edits() -> None:
    """Re-stamp policy: row-provided fields overwrite; silent row preserves cfg edits."""
    row = {
        "clip_index": 1,
        "setting_id": "set_1",
        "action": "Host stands near the window.",
        "on_screen": ["char_1"],
        "start_state": {"seats": {"char_1": {"place": "near window", "posture": "standing"}}},
    }
    cfg = stamp_shot_states_on_clip_cfg({}, shot=row)
    cfg["camera"] = "user camera sweep"
    row2 = {
        **row,
        "start_state": {"seats": {"char_1": {"place": "at the table", "posture": "seated"}}},
    }
    out = stamp_shot_states_on_clip_cfg(cfg, shot=row2)
    anchor = (out.get("spatial_anchors") or {}).get("char_1") or {}
    assert "table" in str(anchor.get("place") or "").lower()
    assert str(anchor.get("posture") or "") == "seated"
    # The row is silent on camera — the cfg-only edit survives the re-stamp.
    assert out["camera"] == "user camera sweep"


def test_reference_led_prepare_preserves_structured_spatial_positions() -> None:
    from jiuwenswarm.server.runtime.designer.pipeline.reference_led import _prepare_shots

    anchor = {"place": "head of table", "posture": "standing"}
    analysis = {
        "characters": [{"id": "char_a", "name": "Amen"}],
        "clips": [
            {"action": "Amen stands and raises a glass", "setting_id": "set_1",
             "on_screen": ["char_a"], "spatial_anchors": {"char_a": dict(anchor)},
             "cast_actions": {"char_a": "standing at head of table, raises glass"},
             "speech_line": "To us!"},
            {"action": "Amen nods", "setting_id": "set_1",
             "on_screen": ["char_a"], "spatial_anchors": {"char_a": dict(anchor)}},
        ],
    }
    shots = _prepare_shots(analysis, "dinner toast")
    cfg0 = stamp_shot_states_on_clip_cfg({}, shot=shots[0])
    cfg1 = stamp_shot_states_on_clip_cfg({}, shot=shots[1])
    assert cfg0["spatial_anchors"]["char_a"]["place"] == "head of table"
    assert cfg1["spatial_anchors"]["char_a"]["posture"] == "standing"
    assert "raises a glass" not in str((cfg1.get("start_state") or {}).get("pose") or "")
