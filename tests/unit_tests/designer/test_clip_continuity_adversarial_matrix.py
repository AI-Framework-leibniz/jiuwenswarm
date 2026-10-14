# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""10k adversarial continuity cases through the exact designer backend path.

Pipeline under test (same as production leaf/orchestration/reference-led):
  ensure_clip_start_end_states  →  stamp_shot_states_on_clip_cfg  →  enforce_prompt_continuity

Do not call apply_continuity_contracts / extract_prop_holds directly here — those are
internals of ensure/stamp. Cases are multi-shot chains built to break holds, openings,
setting isolation, pronoun→noun prop resolution, and post-rewrite reinjection.
"""

from __future__ import annotations

import re
import sys
import types
from collections import Counter, defaultdict
from typing import Any

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

from jiuwenswarm.server.runtime.designer.pipeline.clip_continuity_contract import (
    enforce_prompt_continuity,
)
from jiuwenswarm.server.runtime.designer.pipeline.storyboard_clip_state import (
    ensure_clip_start_end_states,
    stamp_shot_states_on_clip_cfg,
)

# ---------------------------------------------------------------------------
# Diversity axes — product == 10_000
# 20 settings × 20 families × 5 props × 5 places = 10_000
# ---------------------------------------------------------------------------

_SETTINGS: tuple[tuple[str, str], ...] = (
    ("set_dining", "wooden dining room with long table"),
    ("set_kitchen", "narrow galley kitchen with island"),
    ("set_living", "sunlit living room with low sofa"),
    ("set_office", "open-plan office with glass desks"),
    ("set_cafe", "crowded cafe counter and window seats"),
    ("set_library", "quiet library aisle between tall stacks"),
    ("set_clinic", "clinic waiting bay with plastic chairs"),
    ("set_classroom", "classroom with front desk and rows"),
    ("set_workshop", "dusty workshop with steel benches"),
    ("set_studio", "photo studio with seamless backdrop"),
    ("set_porch", "front porch with rocking chairs"),
    ("set_garden", "garden path beside raised beds"),
    ("set_balcony", "narrow balcony overlooking the street"),
    ("set_bar", "dim bar with brass rail and stools"),
    ("set_lobby", "hotel lobby with marble counter"),
    ("set_garage", "garage workbench under fluorescent light"),
    ("set_attic", "attic room with slanted beams"),
    ("set_boat", "boat cabin with bolted table"),
    ("set_train", "train compartment with facing seats"),
    ("set_temple", "temple anteroom with low benches"),
)

_FAMILIES: tuple[str, ...] = (
    "prop_carry_plain",
    "prop_pronoun_from_path",
    "prop_puts_onto",
    "sit_from_standing",
    "climb_then_sit",
    "kneel_transition",
    "conflict_place_lock",
    "already_seated_open_lock",
    "setting_cut_no_leak",
    "multi_cast_mixed_posture",
    "agent_drops_prop",
    "agent_empty_prompt",
    "path_preposition_noise",
    # Harder breakers — verb / chain / clear edges:
    "sets_down_verb_split",
    "puts_down_on_place",
    "setting_return_must_keep_prop",
    "two_props_both_held",
    "rests_prop_at_place",
    "drops_prop_onto",
    "remove_prop_clears_hold",
)

_PROPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("steaming casserole dish", ("casserole", "dish")),
    ("blue ceramic teapot", ("teapot", "ceramic")),
    ("leather-bound ledger", ("ledger", "leather")),
    ("glass vase of lilies", ("vase", "lilies")),
    ("brass desk lamp", ("lamp", "brass")),
)

_PLACES: tuple[str, ...] = (
    "the center of the table",
    "the left edge of the counter",
    "the mantel beside the clock",
    "the middle of the workbench",
    "the shelf under the window",
)

_PATHS: tuple[str, ...] = (
    "the kitchen doorway",
    "the hallway arch",
    "the side corridor",
    "the service door",
    "the garden gate",
)

_CHAR_A = "char_host"
_CHAR_B = "char_guest"
_CHAR_C = "char_child"

_SETTING_N = len(_SETTINGS)
_FAMILY_N = len(_FAMILIES)
_PROP_N = len(_PROPS)
_PLACE_N = len(_PLACES)
_MATRIX_SIZE = _SETTING_N * _FAMILY_N * _PROP_N * _PLACE_N
assert _MATRIX_SIZE == 10_000, _MATRIX_SIZE

# Path / location nouns that must not win over the carried object.
_PATH_CONTAMINATION = (
    "doorway",
    "hallway",
    "corridor",
    "gate",
    "arch",
    "service door",
)


def _decode(case_id: int) -> tuple[tuple[str, str], str, tuple[str, tuple[str, ...]], str, int]:
    n = case_id % _MATRIX_SIZE
    n, place_i = divmod(n, _PLACE_N)
    n, prop_i = divmod(n, _PROP_N)
    n, family_i = divmod(n, _FAMILY_N)
    setting_i = n % _SETTING_N
    return (
        _SETTINGS[setting_i],
        _FAMILIES[family_i],
        _PROPS[prop_i],
        _PLACES[place_i],
        case_id,
    )


def _path_for(case_id: int) -> str:
    return _PATHS[case_id % len(_PATHS)]


def _alt_setting(setting_id: str) -> tuple[str, str]:
    for sid, label in _SETTINGS:
        if sid != setting_id:
            return sid, label
    return ("set_other", "other room")


# ---------------------------------------------------------------------------
# Exact backend path (no shortcuts)
# ---------------------------------------------------------------------------


def run_backend_pipeline(
    shots: list[dict[str, Any]],
    *,
    agent_prompts: dict[int, str] | None = None,
) -> list[dict[str, Any]]:
    """Mirror production: ensure → stamp → enforce (per clip)."""
    ensured = ensure_clip_start_end_states(shots)
    agent_prompts = agent_prompts or {}
    out: list[dict[str, Any]] = []
    for shot in ensured:
        idx = int(shot.get("clip_index") or 0)
        cfg = stamp_shot_states_on_clip_cfg({"role": "clip"}, shot=shot)
        raw_prompt = agent_prompts.get(
            idx,
            str(shot.get("action") or shot.get("clip_action") or "Camera holds."),
        )
        fixed, notes = enforce_prompt_continuity(raw_prompt, cfg)
        out.append(
            {
                "shot": shot,
                "cfg": cfg,
                "prompt_in": raw_prompt,
                "prompt_out": fixed,
                "notes": notes,
            }
        )
    return out


def _hold_props(cfg: dict[str, Any]) -> dict[str, Any]:
    contract = cfg.get("clip_contract") if isinstance(cfg.get("clip_contract"), dict) else {}
    hold = contract.get("hold") if isinstance(contract.get("hold"), dict) else {}
    props = hold.get("props") if isinstance(hold.get("props"), dict) else {}
    if props:
        return props
    scene = cfg.get("scene_hold") if isinstance(cfg.get("scene_hold"), dict) else {}
    return scene.get("props") if isinstance(scene.get("props"), dict) else {}


def _hold_blob(cfg: dict[str, Any]) -> str:
    return str(_hold_props(cfg)).lower() + " " + str(cfg.get("pose_holds") or []).lower()


def _opening_posture(shot: dict[str, Any], cid: str) -> str:
    contract = shot.get("clip_contract") if isinstance(shot.get("clip_contract"), dict) else {}
    opening = contract.get("opening") if isinstance(contract.get("opening"), dict) else {}
    anchor = opening.get(cid) if isinstance(opening.get(cid), dict) else {}
    if not anchor:
        start = shot.get("start_state") if isinstance(shot.get("start_state"), dict) else {}
        seats = start.get("seats") if isinstance(start.get("seats"), dict) else {}
        anchor = seats.get(cid) if isinstance(seats.get(cid), dict) else {}
    return str(anchor.get("posture") or anchor.get("pose") or "").lower()


def _end_place(shot: dict[str, Any], cid: str) -> str:
    end = shot.get("end_state") if isinstance(shot.get("end_state"), dict) else {}
    seats = end.get("seats") if isinstance(end.get("seats"), dict) else {}
    anchor = seats.get(cid) if isinstance(seats.get(cid), dict) else {}
    return str(
        anchor.get("place") or anchor.get("zone") or anchor.get("seat") or ""
    ).lower()


def _any_token(text: str, tokens: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(tok.lower() in low for tok in tokens)


# ---------------------------------------------------------------------------
# Scenario builders
# ---------------------------------------------------------------------------


def _base_shot(
    *,
    clip_index: int,
    setting_id: str,
    action: str,
    on_screen: list[str],
    cast_actions: dict[str, str] | None = None,
    spatial_anchors: dict[str, dict[str, str]] | None = None,
    start_state: dict[str, Any] | None = None,
    end_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    shot: dict[str, Any] = {
        "clip_index": clip_index,
        "setting_id": setting_id,
        "action": action,
        "camera": "medium / eye-level",
        "on_screen": list(on_screen),
        "character_ids": list(on_screen),
        "cast_actions": cast_actions or {cid: action[:120] for cid in on_screen},
    }
    if spatial_anchors:
        shot["spatial_anchors"] = spatial_anchors
    if start_state:
        shot["start_state"] = start_state
    if end_state:
        shot["end_state"] = end_state
    return shot


def build_case(
    case_id: int,
) -> tuple[str, list[dict[str, Any]], dict[int, str], dict[str, Any]]:
    """Return family, shots, agent_prompts, expectations."""
    (setting_id, setting_label), family, (prop_label, prop_tokens), place, _ = _decode(
        case_id
    )
    path = _path_for(case_id)
    expect: dict[str, Any] = {
        "family": family,
        "setting_id": setting_id,
        "prop_tokens": prop_tokens,
        "prop_label": prop_label,
        "place": place,
        "path": path,
        "check_prop_on": [],  # clip indices that must retain prop
        "forbid_prop_on": [],  # clip indices that must NOT get prior prop
        "sit_open_standing": [],  # (clip_index, cid)
        "place_must_contain": [],  # (clip_index, cid, needle)
        "path_must_not_contaminate": False,
        "require_contract": True,
    }
    shots: list[dict[str, Any]] = []
    prompts: dict[int, str] = {}

    def follow_up(action: str, cast: dict[str, str] | None = None) -> dict[str, Any]:
        return _base_shot(
            clip_index=2,
            setting_id=setting_id,
            action=action,
            on_screen=[_CHAR_A, _CHAR_B],
            cast_actions=cast
            or {
                _CHAR_A: "stands near the table smiling",
                _CHAR_B: "sits at the right side",
            },
        )

    if family == "prop_carry_plain":
        shots = [
            _base_shot(
                clip_index=1,
                setting_id=setting_id,
                action=(
                    f"In the {setting_label}, {_CHAR_A} places the {prop_label} "
                    f"at {place}."
                ),
                on_screen=[_CHAR_A],
                cast_actions={_CHAR_A: f"places the {prop_label} at {place}"},
                end_state={
                    "pose": f"the {prop_tokens[0]} is ready",
                    "props": {prop_label: place},
                },
            ),
            follow_up(f"In the {setting_label}, guests settle in."),
        ]
        expect["check_prop_on"] = [2]
        prompts[2] = "Guests settle in. Camera holds medium."

    elif family == "prop_pronoun_from_path":
        shots = [
            _base_shot(
                clip_index=1,
                setting_id=setting_id,
                action=(
                    f"{_CHAR_A} carries a {prop_label} from {path} and sets it "
                    f"at {place}."
                ),
                on_screen=[_CHAR_A],
                cast_actions={_CHAR_A: f"sets it at {place}"},
                end_state={
                    "pose": f"the {prop_tokens[0]} rests in place",
                    "props": {prop_label: place},
                },
            ),
            follow_up(f"{_CHAR_B} sits. {_CHAR_A} stands at the right side."),
        ]
        expect["check_prop_on"] = [2]
        expect["path_must_not_contaminate"] = True
        prompts[2] = f"{_CHAR_B} sits. {_CHAR_A} stands."

    elif family == "prop_puts_onto":
        shots = [
            _base_shot(
                clip_index=1,
                setting_id=setting_id,
                action=f"{_CHAR_A} puts the {prop_label} onto {place}.",
                on_screen=[_CHAR_A],
                end_state={"props": {prop_label: place}},
            ),
            follow_up("Conversation continues around the room."),
        ]
        expect["check_prop_on"] = [2]
        prompts[2] = "Conversation continues. Soft ambient light."

    elif family == "sit_from_standing":
        shots = [
            _base_shot(
                clip_index=1,
                setting_id=setting_id,
                action=f"{_CHAR_A} walks in and sits at the right side of the table.",
                on_screen=[_CHAR_A],
                cast_actions={_CHAR_A: "sitting at the right side of the table"},
                start_state={
                    "seats": {
                        _CHAR_A: {
                            "place": "the right side of the table",
                            "posture": "standing",
                        }
                    }
                },
                end_state={
                    "seats": {
                        _CHAR_A: {
                            "place": "the right side of the table",
                            "posture": "seated",
                        }
                    }
                },
            )
        ]
        expect["sit_open_standing"] = [(1, _CHAR_A)]
        expect["place_must_contain"] = [(1, _CHAR_A, "right")]

    elif family == "climb_then_sit":
        shots = [
            _base_shot(
                clip_index=1,
                setting_id=setting_id,
                action=f"{_CHAR_C} climbs onto the chair and sits upright.",
                on_screen=[_CHAR_C],
                cast_actions={_CHAR_C: "climbing into the chair and sitting upright"},
                start_state={
                    "seats": {
                        _CHAR_C: {"place": "the left side", "posture": "standing"}
                    }
                },
                end_state={
                    "seats": {
                        _CHAR_C: {"place": "the left side", "posture": "seated"}
                    }
                },
            )
        ]
        expect["sit_open_standing"] = [(1, _CHAR_C)]

    elif family == "kneel_transition":
        shots = [
            _base_shot(
                clip_index=1,
                setting_id=setting_id,
                action=f"{_CHAR_A} kneels beside {place}.",
                on_screen=[_CHAR_A],
                cast_actions={_CHAR_A: f"kneeling beside {place}"},
                start_state={
                    "seats": {_CHAR_A: {"place": place, "posture": "standing"}}
                },
                end_state={
                    "seats": {_CHAR_A: {"place": place, "posture": "kneeling"}}
                },
            )
        ]
        expect["sit_open_standing"] = [(1, _CHAR_A)]  # authored pre-kneel standing

    elif family == "conflict_place_lock":
        shots = [
            _base_shot(
                clip_index=1,
                setting_id=setting_id,
                action=f"{_CHAR_A} sits at the right side of the table.",
                on_screen=[_CHAR_A],
                cast_actions={_CHAR_A: "seating herself at the right side of the table"},
                start_state={
                    "seats": {_CHAR_A: {"place": "table center", "posture": "standing"}}
                },
                end_state={
                    "seats": {
                        _CHAR_A: {
                            "place": "the right side of the table",
                            "posture": "seated",
                        }
                    }
                },
            )
        ]
        expect["sit_open_standing"] = [(1, _CHAR_A)]
        expect["place_must_contain"] = [(1, _CHAR_A, "right")]

    elif family == "already_seated_open_lock":
        shots = [
            _base_shot(
                clip_index=1,
                setting_id=setting_id,
                action=f"{_CHAR_B} sits down at the foot of the table.",
                on_screen=[_CHAR_B],
                cast_actions={_CHAR_B: "sits down at the foot of the table"},
                start_state={
                    "seats": {
                        _CHAR_B: {"place": "the foot of the table", "posture": "standing"}
                    }
                },
                end_state={
                    "seats": {
                        _CHAR_B: {"place": "the foot of the table", "posture": "seated"}
                    }
                },
            )
        ]
        expect["sit_open_standing"] = [(1, _CHAR_B)]
        expect["place_must_contain"] = [(1, _CHAR_B, "foot")]

    elif family == "setting_cut_no_leak":
        other_id, other_label = _alt_setting(setting_id)
        shots = [
            _base_shot(
                clip_index=1,
                setting_id=setting_id,
                action=f"{_CHAR_A} places the {prop_label} at {place}.",
                on_screen=[_CHAR_A],
                end_state={"props": {prop_label: place}},
            ),
            _base_shot(
                clip_index=2,
                setting_id=other_id,
                action=f"Cut to {other_label}. {_CHAR_B} waves hello.",
                on_screen=[_CHAR_B],
                cast_actions={_CHAR_B: "waves hello"},
            ),
        ]
        expect["forbid_prop_on"] = [2]
        expect["check_prop_on"] = []
        prompts[2] = f"Cut to {other_label}. {_CHAR_B} waves hello."

    elif family == "multi_cast_mixed_posture":
        shots = [
            _base_shot(
                clip_index=1,
                setting_id=setting_id,
                action=(
                    f"{_CHAR_A} remains standing at the head of the table. "
                    f"{_CHAR_B} sits at the right side. "
                    f"{_CHAR_C} climbs into a chair at the left side."
                ),
                on_screen=[_CHAR_A, _CHAR_B, _CHAR_C],
                cast_actions={
                    _CHAR_A: "standing at the head of the table",
                    _CHAR_B: "sitting at the right side",
                    _CHAR_C: "climbing into a chair and sitting upright",
                },
                start_state={
                    "seats": {
                        _CHAR_A: {"place": "the head of the table", "posture": "standing"},
                        _CHAR_B: {"place": "the right side", "posture": "standing"},
                        _CHAR_C: {"place": "the left side", "posture": "standing"},
                    }
                },
                end_state={
                    "seats": {
                        _CHAR_A: {"place": "the head of the table", "posture": "standing"},
                        _CHAR_B: {"place": "the right side", "posture": "seated"},
                        _CHAR_C: {"place": "the left side", "posture": "seated"},
                    }
                },
            )
        ]
        expect["sit_open_standing"] = [(1, _CHAR_B), (1, _CHAR_C)]
        expect["place_must_contain"] = [
            (1, _CHAR_B, "right"),
            (1, _CHAR_C, "left"),
        ]

    elif family == "agent_drops_prop":
        shots = [
            _base_shot(
                clip_index=1,
                setting_id=setting_id,
                action=f"{_CHAR_A} sets the {prop_label} at {place}.",
                on_screen=[_CHAR_A],
                end_state={
                    "pose": f"the {prop_tokens[0]} stays put",
                    "props": {prop_label: place},
                },
            ),
            follow_up("Everyone looks toward camera."),
        ]
        expect["check_prop_on"] = [2]
        prompts[2] = "Everyone looks toward camera. No objects mentioned."

    elif family == "agent_empty_prompt":
        shots = [
            _base_shot(
                clip_index=1,
                setting_id=setting_id,
                action=f"{_CHAR_A} places the {prop_label} at {place}.",
                on_screen=[_CHAR_A],
                end_state={"props": {prop_label: place}},
            ),
            follow_up("Beat continues."),
        ]
        expect["check_prop_on"] = [2]
        prompts[2] = "Camera holds."

    elif family == "path_preposition_noise":
        shots = [
            _base_shot(
                clip_index=1,
                setting_id=setting_id,
                action=(
                    f"{_CHAR_A} walks from {path} through the side corridor toward "
                    f"the room, carrying a {prop_label}, and sets it at {place}."
                ),
                on_screen=[_CHAR_A],
                cast_actions={_CHAR_A: f"sets it at {place}"},
                end_state={"props": {prop_label: place}},
            ),
            follow_up("Quiet settles over the room."),
        ]
        expect["check_prop_on"] = [2]
        expect["path_must_not_contaminate"] = True
        prompts[2] = "Quiet settles. Soft breath."

    elif family == "sets_down_verb_split":
        # "sets down the X at Y" — label must stay the authored object name.
        shots = [
            _base_shot(
                clip_index=1,
                setting_id=setting_id,
                action=f"{_CHAR_A} sets down the {prop_label} at {place}.",
                on_screen=[_CHAR_A],
                cast_actions={_CHAR_A: f"sets down the {prop_label} at {place}"},
                end_state={"props": {prop_label: place}},
            ),
            follow_up("The room stays still for a beat."),
        ]
        expect["check_prop_on"] = [2]
        expect["path_must_not_contaminate"] = True
        prompts[2] = "The room stays still."

    elif family == "puts_down_on_place":
        shots = [
            _base_shot(
                clip_index=1,
                setting_id=setting_id,
                action=f"{_CHAR_A} puts the {prop_label} down on {place}.",
                on_screen=[_CHAR_A],
                end_state={"props": {prop_label: place}},
            ),
            follow_up("No one touches the object."),
        ]
        expect["check_prop_on"] = [2]
        prompts[2] = "No one touches anything. Camera holds."

    elif family == "setting_return_must_keep_prop":
        # Place prop in A → cut to B → return to A; hold store must still have prop.
        other_id, other_label = _alt_setting(setting_id)
        shots = [
            _base_shot(
                clip_index=1,
                setting_id=setting_id,
                action=f"{_CHAR_A} places the {prop_label} at {place}.",
                on_screen=[_CHAR_A],
                end_state={"props": {prop_label: place}},
            ),
            _base_shot(
                clip_index=2,
                setting_id=other_id,
                action=f"Cut to {other_label}. {_CHAR_B} waves.",
                on_screen=[_CHAR_B],
                cast_actions={_CHAR_B: "waves"},
            ),
            _base_shot(
                clip_index=3,
                setting_id=setting_id,
                action=f"Back in the {setting_label}. {_CHAR_A} stands near {place}.",
                on_screen=[_CHAR_A],
                cast_actions={_CHAR_A: f"standing near {place}"},
            ),
        ]
        expect["check_prop_on"] = [3]
        expect["forbid_prop_on"] = [2]
        prompts[2] = f"Cut to {other_label}. {_CHAR_B} waves."
        prompts[3] = f"Back in room. {_CHAR_A} stands."

    elif family == "two_props_both_held":
        other_prop, other_tokens = _PROPS[(case_id + 1) % _PROP_N]
        other_place = _PLACES[(case_id + 2) % _PLACE_N]
        shots = [
            _base_shot(
                clip_index=1,
                setting_id=setting_id,
                action=(
                    f"{_CHAR_A} places the {prop_label} at {place}. "
                    f"Then {_CHAR_B} puts the {other_prop} on {other_place}."
                ),
                on_screen=[_CHAR_A, _CHAR_B],
                cast_actions={
                    _CHAR_A: f"places the {prop_label} at {place}",
                    _CHAR_B: f"puts the {other_prop} on {other_place}",
                },
                end_state={"props": {prop_label: place, other_prop: other_place}},
            ),
            follow_up("Both objects remain untouched."),
        ]
        expect["check_prop_on"] = [2]
        expect["extra_prop_tokens"] = other_tokens
        prompts[2] = "Both objects remain untouched. Wide shot."

    elif family == "rests_prop_at_place":
        shots = [
            _base_shot(
                clip_index=1,
                setting_id=setting_id,
                action=f"{_CHAR_A} rests the {prop_label} at {place}.",
                on_screen=[_CHAR_A],
                end_state={"props": {prop_label: place}},
            ),
            follow_up("Quiet holds."),
        ]
        expect["check_prop_on"] = [2]
        prompts[2] = "Quiet holds. No props named."

    elif family == "drops_prop_onto":
        shots = [
            _base_shot(
                clip_index=1,
                setting_id=setting_id,
                action=f"{_CHAR_A} drops the {prop_label} onto {place}.",
                on_screen=[_CHAR_A],
                end_state={"props": {prop_label: place}},
            ),
            follow_up("Nobody picks it up."),
        ]
        expect["check_prop_on"] = [2]
        prompts[2] = "Nobody picks it up."

    else:  # remove_prop_clears_hold
        shots = [
            _base_shot(
                clip_index=1,
                setting_id=setting_id,
                action=f"{_CHAR_A} places the {prop_label} at {place}.",
                on_screen=[_CHAR_A],
                end_state={"props": {prop_label: place}},
            ),
            _base_shot(
                clip_index=2,
                setting_id=setting_id,
                action=f"{_CHAR_A} removes the {prop_label} from {place} and exits.",
                on_screen=[_CHAR_A],
                cast_actions={_CHAR_A: f"removes the {prop_label} from {place}"},
                end_state={
                    "exited": [_CHAR_A],
                    "pose": "the surface is clear",
                    "cleared": [prop_label],
                },
            ),
            _base_shot(
                clip_index=3,
                setting_id=setting_id,
                action=f"{_CHAR_B} enters and looks at {place}.",
                on_screen=[_CHAR_B],
                cast_actions={_CHAR_B: f"standing near {place}"},
            ),
        ]
        # After explicit remove, prop must not still be held as present.
        expect["forbid_prop_on"] = [3]
        expect["check_prop_on"] = []
        prompts[3] = f"{_CHAR_B} enters and looks around."

    return family, shots, prompts, expect


# ---------------------------------------------------------------------------
# Evaluators (surface flaws as codes)
# ---------------------------------------------------------------------------


def evaluate_continuity_case(case_id: int) -> list[str]:
    family, shots, prompts, expect = build_case(case_id)
    results = run_backend_pipeline(shots, agent_prompts=prompts)
    by_idx = {int(r["shot"].get("clip_index") or 0): r for r in results}
    flaws: list[str] = []

    if expect.get("require_contract"):
        for r in results:
            cfg = r["cfg"]
            if not isinstance(cfg.get("clip_contract"), dict) or not cfg.get(
                "clip_contract"
            ):
                flaws.append(
                    f"missing_clip_contract:clip{r['shot'].get('clip_index')}"
                )

    prop_tokens: tuple[str, ...] = tuple(expect.get("prop_tokens") or ())
    extra_prop_tokens: tuple[str, ...] = tuple(expect.get("extra_prop_tokens") or ())
    for idx in expect.get("check_prop_on") or []:
        row = by_idx.get(idx)
        if not row:
            flaws.append(f"missing_clip:{idx}")
            continue
        blob = _hold_blob(row["cfg"])
        if prop_tokens and not _any_token(blob, prop_tokens):
            flaws.append(f"prop_missing_in_hold:clip{idx}:{prop_tokens[0]}")
        if extra_prop_tokens and not _any_token(blob, extra_prop_tokens):
            flaws.append(
                f"second_prop_missing_in_hold:clip{idx}:{extra_prop_tokens[0]}"
            )
        # Enforce must reinject into degraded agent prompt.
        out_p = str(row["prompt_out"] or "").lower()
        if prop_tokens and not _any_token(out_p, prop_tokens):
            flaws.append(f"prop_missing_after_enforce:clip{idx}:{prop_tokens[0]}")
        if extra_prop_tokens and not _any_token(out_p, extra_prop_tokens):
            flaws.append(
                f"second_prop_missing_after_enforce:clip{idx}:{extra_prop_tokens[0]}"
            )
        # "sets down the X" must not keep "down …" glued onto the prop label.
        props = _hold_props(row["cfg"])
        for key, item in props.items():
            label = str((item or {}).get("label") or key).lower().strip()
            if label.startswith("down ") or label.startswith("down_"):
                flaws.append(f"sets_down_label_pollution:clip{idx}:{label!r}")

    for idx in expect.get("forbid_prop_on") or []:
        row = by_idx.get(idx)
        if not row:
            continue
        blob = _hold_blob(row["cfg"])
        if prop_tokens and _any_token(blob, prop_tokens):
            flaws.append(f"setting_leak_prop:clip{idx}:{prop_tokens[0]}")

    if expect.get("path_must_not_contaminate"):
        # Check clip1 hold label and any later hold that should carry the prop.
        targets = [1] + list(expect.get("check_prop_on") or [])
        for idx in targets:
            row = by_idx.get(idx)
            if not row:
                continue
            props = _hold_props(row["cfg"])
            labels = " ".join(
                str((v or {}).get("label") or k) for k, v in props.items()
            ).lower()
            for bad in _PATH_CONTAMINATION:
                if bad in labels and not _any_token(labels, prop_tokens):
                    flaws.append(f"path_contamination:clip{idx}:{bad}")
                    break
            # Stronger: if prop tokens absent but any path noun present as sole label.
            if props and prop_tokens and not _any_token(labels, prop_tokens):
                if any(bad in labels for bad in _PATH_CONTAMINATION):
                    flaws.append(f"path_won_over_prop:clip{idx}")

    for idx, cid in expect.get("sit_open_standing") or []:
        row = by_idx.get(idx)
        if not row:
            flaws.append(f"missing_clip:{idx}")
            continue
        posture = _opening_posture(row["shot"], cid)
        if posture == "seated" or posture == "kneeling":
            # kneel_transition expects opening standing before kneel
            if family == "kneel_transition" and posture == "kneeling":
                flaws.append(f"opening_already_result:{cid}:kneeling")
            elif posture == "seated":
                flaws.append(f"opening_already_seated:{cid}")

    for idx, cid, needle in expect.get("place_must_contain") or []:
        row = by_idx.get(idx)
        if not row:
            continue
        place = _end_place(row["shot"], cid)
        if needle.lower() not in place:
            flaws.append(f"place_conflict_unresolved:{cid}:want={needle}:got={place!r}")

    return flaws


@pytest.mark.parametrize("case_id", range(_MATRIX_SIZE))
def test_continuity_adversarial_backend_matrix(case_id: int) -> None:
    """Fail when the real ensure→stamp→enforce path drops continuity."""
    flaws = evaluate_continuity_case(case_id)
    family = _decode(case_id)[1]
    assert not flaws, f"case={case_id} family={family}: " + "; ".join(flaws)


def test_adversarial_matrix_size_and_pipeline_import() -> None:
    assert _MATRIX_SIZE == 10_000
    # Smoke: one case hits real modules.
    flaws = evaluate_continuity_case(0)
    assert isinstance(flaws, list)


def summarize_adversarial_failures(
    *, limit_examples: int = 3
) -> dict[str, Any]:
    """Run all 10k and bucket flaws (for __main__ / manual diagnosis)."""
    by_code: Counter[str] = Counter()
    by_family: Counter[str] = Counter()
    examples: dict[str, list[tuple[int, str]]] = defaultdict(list)
    failed = 0
    for case_id in range(_MATRIX_SIZE):
        flaws = evaluate_continuity_case(case_id)
        if not flaws:
            continue
        failed += 1
        family = _decode(case_id)[1]
        by_family[family] += 1
        for flaw in flaws:
            code = flaw.split(":")[0]
            by_code[code] += 1
            if len(examples[code]) < limit_examples:
                examples[code].append((case_id, flaw))
    return {
        "total": _MATRIX_SIZE,
        "failed_cases": failed,
        "passed_cases": _MATRIX_SIZE - failed,
        "by_code": dict(by_code.most_common()),
        "by_family": dict(by_family.most_common()),
        "examples": {k: v for k, v in examples.items()},
    }


if __name__ == "__main__":
    report = summarize_adversarial_failures()
    print(
        f"continuity adversarial: {report['passed_cases']}/{report['total']} passed, "
        f"{report['failed_cases']} failed"
    )
    print("by_code:", report["by_code"])
    print("by_family:", report["by_family"])
    for code, exs in report["examples"].items():
        print(f"  examples[{code}]:", exs)
