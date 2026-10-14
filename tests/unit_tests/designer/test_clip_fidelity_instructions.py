"""Clip / storyboard LLM instructions require storyboard+lock fidelity (no regex gates)."""

from __future__ import annotations


def test_clip_leaf_instructions_require_exact_posture_and_speech() -> None:
    from jiuwenswarm.server.runtime.designer.pipeline.leaf_agent_consistency import (
        hollywood_leaf_instructions,
    )

    text = hollywood_leaf_instructions("clip").lower()
    assert (
        "spatial" in text
        or "posture" in text
        or "sit/stand" in text
        or "sit vs stand" in text
    )
    assert "exact" in text or "verbatim" in text
    assert "do not invent" in text or "never invent" in text
    assert "previous clip" in text
    assert "best" in text  # best practices
    # Must not be a regex/forbid-list style gate essay.
    assert "re.compile" not in text
    assert "\\b" not in text


def test_storyboard_leaf_instructions_discourage_duplicate_adjacent_speech() -> None:
    from jiuwenswarm.server.runtime.designer.pipeline.leaf_agent_consistency import (
        hollywood_leaf_instructions,
    )

    text = hollywood_leaf_instructions("storyboard").lower()
    assert "adjacent" in text
    assert "sit" in text and "stand" in text
    assert "spoken" in text or "speech" in text


def test_video_model_skill_block_mentions_configured_family() -> None:
    from jiuwenswarm.server.runtime.designer.pipeline.wan_r2v_best_practices import (
        video_model_leaf_skill_block,
        wan_r2v_prompt_formula,
    )

    formula = wan_r2v_prompt_formula().lower()
    assert "posture" in formula or "spatial" in formula or "sit/stand" in formula
    assert "exact line" in formula or "exact" in formula
    assert "sit/stand defaults" not in formula

    block = video_model_leaf_skill_block(role="clip").lower()
    assert "configured video model" in block
    assert "storyboard" in block


def test_same_scene_gate_asks_for_posture_fidelity() -> None:
    from jiuwenswarm.server.runtime.designer.pipeline.clip_prompt_handoff import (
        same_scene_prompt_gate_clause,
    )

    gate = same_scene_prompt_gate_clause(
        clip_index=2,
        this_action="Dad prays while standing",
        this_camera="medium",
        this_speech="Amen.",
    ).lower()
    assert "posture" in gate or "spatial" in gate or "sit/stand" in gate
    assert "best-practice" in gate or "best practice" in gate
    assert "do not invent" in gate


def test_leaf_lock_packet_surfaces_storyboard_authority() -> None:
    from jiuwenswarm.server.runtime.designer.pipeline.production_specs import (
        leaf_lock_packet,
    )

    packet = leaf_lock_packet(
        role="clip",
        clip_index=2,
        analysis={
            "clips": [
                {
                    "clip_index": 2,
                    "action": "Dad bows while standing",
                    "speech_line": "Amen.",
                    "speech_by_character": {"char_1": "Amen."},
                    "cast_actions": {"char_1": "standing, praying"},
                    "start_state": {
                        "seats": {"char_1": {"place": "standing behind his chair"}}
                    },
                }
            ]
        },
    )
    assert packet["clip_action"].startswith("Dad bows")
    assert packet["speech_by_character"]["char_1"] == "Amen."
    assert "standing" in packet["cast_actions"]["char_1"]
    assert "standing" in str(packet["start_state"]).lower()
    fidelity = packet["fidelity_rule"].lower()
    assert "posture" in fidelity or "spatial" in fidelity or "sit/stand" in fidelity
