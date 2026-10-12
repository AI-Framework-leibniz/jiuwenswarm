"""Clips get this storyboard row + locks only — no previous-clip content."""

from __future__ import annotations


def test_compose_reference_clip_prompt_has_no_previous_beat() -> None:
    from jiuwenswarm.server.runtime.designer.pipeline.reference_led import (
        compose_reference_clip_prompt,
        reference_prompt_issues,
    )

    cfg = {
        "clip_index": 3,
        "clip_action": "Dad bows his head and prays",
        "camera": "medium",
        "timeline": "10-16s",
        "duration_sec": 6,
        "style_lock": {"look": "cartoonish", "medium": "stylized_animation"},
        "previous_action": "Dad walks in and sits",
        "previous_end_state": {"pose": "Dad is seated"},
        "already_done": ["Mom set the bowls"],
        "reference_call_mode": "r2v",
        "reference_prompt_contract": "character",
    }
    prompt = compose_reference_clip_prompt(cfg)
    assert "Dad bows his head and prays" in prompt
    assert "continues from" not in prompt.lower()
    assert "must not repeat" not in prompt.lower()
    assert "Dad walks in and sits" not in prompt
    assert "Mom set the bowls" not in prompt
    assert "missing_continuation" not in reference_prompt_issues(prompt, cfg)
    assert "missing_previous_end" not in reference_prompt_issues(prompt, cfg)


def test_strip_previous_clip_fields_clears_reference_led_carry() -> None:
    from jiuwenswarm.server.runtime.designer.pipeline.clip_story_state import (
        strip_previous_clip_fields,
    )

    out = strip_previous_clip_fields(
        {
            "clip_action": "pray",
            "speech_line": "Amen.",
            "previous_action": "sit down",
            "previous_end_state": "seated",
            "already_done": ["shot1"],
            "beat_done": ["onset"],
            "previous_clip_speech": "hello",
            "seat_anchors": {"char_1": {"zone": "head"}},
        }
    )
    assert out["clip_action"] == "pray"
    assert out["speech_line"] == "Amen."
    assert out["seat_anchors"]["char_1"]["zone"] == "head"
    assert "previous_action" not in out
    assert "previous_end_state" not in out
    assert "already_done" not in out
    assert "beat_done" not in out
    assert "previous_clip_speech" not in out


def test_positive_continuity_is_this_row_locks() -> None:
    from jiuwenswarm.server.runtime.designer.pipeline.wan_prompt_hygiene import (
        positive_continuity_clause,
    )

    text = positive_continuity_clause(
        {
            "clip_action": "Dad prays",
            "camera": "push-in",
            "speech_line": "Amen.",
            "on_screen": ["char_1"],
        },
        characters=[{"id": "char_1", "name": "Dad"}],
    )
    assert "THIS STORYBOARD ROW LOCKS" in text
    assert "continues the same film" not in text.lower()
    assert "Dad prays" in text
    assert "Amen." in text


def test_assignment_clause_omits_already_done() -> None:
    from jiuwenswarm.server.runtime.designer.pipeline.clip_prompt_handoff import (
        this_shot_assignment_clause,
        same_scene_prompt_gate_clause,
    )

    assign = this_shot_assignment_clause(
        clip_index=2,
        action="Dad sits",
        camera="medium",
        speech_line="There he is.",
        already_done=["Mom set the bowls"],
    )
    assert "Dad sits" in assign
    assert "Mom set the bowls" not in assign
    assert "Already finished" not in assign

    gate = same_scene_prompt_gate_clause(
        clip_index=2,
        this_action="Dad sits",
        already_done=["Mom set the bowls"],
        has_prior=True,
    )
    assert "Mom set the bowls" not in gate
    assert "ALREADY FINISHED" not in gate
    assert "previous clip" in gate.lower()
