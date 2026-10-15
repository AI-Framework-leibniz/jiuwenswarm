"""Leaf lock packet surfaces storyboard authority (structured data, not prompt text)."""

from __future__ import annotations


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
