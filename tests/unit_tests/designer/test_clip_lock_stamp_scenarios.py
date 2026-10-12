# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""≥50k spatial positioning stamp matrix (any stance — not seating-only).

One integer case_id keeps collection fast. Each case is a single clip so the
full 50k suite finishes in reasonable time; multi-clip / chain failures live in
test_clip_spatial_positioning.py.
"""

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
    spatial_positions_from_shot,
    stamp_shot_states_on_clip_cfg,
)

_PLACES = (
    "head of table",
    "foot of table",
    "left of table",
    "right of table",
    "near window",
    "by the door",
    "sofa left",
    "sofa right",
    "kitchen island",
    "bar counter",
    "bench near hearth",
    "desk",
    "picnic blanket",
    "stage left mark",
    "stage right mark",
    "counter corner",
    "armchair by lamp",
    "floor cushion",
    "hallway arch",
    "porch rail",
    "garden path",
    "altar steps",
    "platform edge",
    "fireplace",
    "balcony rail",
)
_POSTURES = (
    "standing",
    "seated",
    "leaning",
    "kneeling",
    "crouching",
    "reclining",
    "walking",
    "running",
    "perched",
    "half-standing",
)
_SOURCES = (
    "spatial_anchors",
    "seat_anchors_legacy",
    "blocking",
    "cast_actions",
    "start_state",
)
_CHAR_LAYOUTS = (
    ("char_a",),
    ("char_a", "char_b"),
    ("char_a", "char_b", "char_c"),
    ("char_host", "char_guest"),
)
_ACTION_VERB = {
    "standing": "stands",
    "seated": "sits",
    "leaning": "leans",
    "kneeling": "kneels",
    "crouching": "crouches",
    "reclining": "reclines",
    "walking": "walks",
    "running": "runs",
    "perched": "perches",
    "half-standing": "stands half-up",
}

# 25×10×5×4 = 5_000 unique combos; ×10 seeds → 50_000 cases.
_COMBO_SPACE = len(_PLACES) * len(_POSTURES) * len(_SOURCES) * len(_CHAR_LAYOUTS)
_SEED_COUNT = 10
_MATRIX_SIZE = _COMBO_SPACE * _SEED_COUNT
assert _MATRIX_SIZE >= 50_000


def _decode(case_id: int) -> tuple[str, str, str, tuple[str, ...], int]:
    seed = case_id // _COMBO_SPACE
    n = case_id % _COMBO_SPACE
    n, char_i = divmod(n, len(_CHAR_LAYOUTS))
    n, source_i = divmod(n, len(_SOURCES))
    n, posture_i = divmod(n, len(_POSTURES))
    place_i = n % len(_PLACES)
    return (
        _PLACES[place_i],
        _POSTURES[posture_i],
        _SOURCES[source_i],
        _CHAR_LAYOUTS[char_i],
        seed,
    )


def _has_place(anchor: dict) -> bool:
    return bool(
        str(anchor.get("place") or "").strip()
        or str(anchor.get("zone") or "").strip()
        or str(anchor.get("seat") or "").strip()
        or str(anchor.get("landmark") or "").strip()
    )


def _has_posture(anchor: dict) -> bool:
    return bool(
        str(anchor.get("posture") or "").strip()
        or str(anchor.get("pose") or "").strip()
    )


def _cfg_positions(cfg: dict) -> dict:
    return (
        cfg.get("spatial_anchors")
        if isinstance(cfg.get("spatial_anchors"), dict)
        else cfg.get("seat_anchors")
        if isinstance(cfg.get("seat_anchors"), dict)
        else {}
    )


def _shot_for(
    *,
    place: str,
    posture: str,
    source: str,
    chars: tuple[str, ...],
    seed: int,
) -> dict:
    facing = ("toward_camera", "toward_table", "profile_left", "profile_right")[seed % 4]
    zone = ("left", "mid", "right", "foreground")[seed % 4]
    verb = _ACTION_VERB.get(posture, "is")
    base: dict = {
        "clip_index": 1,
        "setting_id": "set_1",
        "action": f"Beat: {verb} at {place}",
        "camera": "medium / eye-level",
        "on_screen": list(chars),
        "character_ids": list(chars),
        "speech_line": f"Line from {chars[0]}",
        "cast_actions": {cid: f"{verb} at {place}" for cid in chars},
    }
    positions = {
        cid: {
            "place": f"{place} [{cid[-1]}]",
            "posture": posture,
            "facing": facing,
            "zone": zone,
        }
        for cid in chars
    }
    if source == "spatial_anchors":
        base["spatial_anchors"] = positions
    elif source == "seat_anchors_legacy":
        base["seat_anchors"] = positions
    elif source == "blocking":
        base["blocking"] = {
            "landmark": place,
            "positions": [
                {
                    "character_id": cid,
                    "zone": zone,
                    "place": positions[cid]["place"],
                    "pose": posture,
                    "facing": facing,
                    "near": place,
                }
                for cid in chars
            ],
        }
    elif source == "cast_actions":
        pass
    else:
        base["start_state"] = {
            "pose": f"Already {posture} at {place}",
            "seats": positions,
            "on_screen": list(chars),
        }
    return base


@pytest.mark.parametrize("case_id", range(_MATRIX_SIZE))
def test_spatial_positions_stamp_matrix(case_id: int) -> None:
    """Fail if any source drops place or posture for any stance."""
    place, posture, source, chars, seed = _decode(case_id)
    shot = _shot_for(
        place=place,
        posture=posture,
        source=source,
        chars=chars,
        seed=seed,
    )
    ensured = ensure_clip_start_end_states([shot])[0]
    positions = spatial_positions_from_shot(ensured)
    assert positions, f"missing spatial positions source={source} posture={posture}"
    for cid in chars:
        assert cid in positions
        detail = positions[cid]
        assert _has_place(detail) or _has_posture(detail), detail
    cfg = stamp_shot_states_on_clip_cfg({"role": "clip"}, shot=ensured)
    assert cfg.get("start_state")
    stamped = _cfg_positions(cfg)
    assert stamped
    assert cfg.get("spatial_anchors"), "canonical spatial_anchors required"
    for cid in chars:
        anchor = stamped.get(cid) or {}
        assert isinstance(anchor, dict)
        assert _has_place(anchor) or _has_posture(anchor), (cid, anchor, posture)
        if posture != "seated" and _has_posture(anchor):
            got = str(anchor.get("posture") or anchor.get("pose") or "").lower()
            assert "seated" not in got or posture == "seated", (
                f"non-seated posture collapsed to seated: {got} from {posture}"
            )
    assert cfg.get("previous_action") == ""
    assert cfg.get("previous_clip_handoff_ready") is False
