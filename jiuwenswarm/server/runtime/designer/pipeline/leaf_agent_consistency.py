# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Domain-agnostic Hollywood leaf-agent instructions (safe for any brief).

Used by Plan A leaf DeepAgents (deepseek-flash etc.) that may lack vision.
Agents must parse brief + storyboard text, optionally inspect upstream images,
then author a single production-ready visual-model prompt.
"""

from __future__ import annotations

from typing import Any


def _image_limit_clause() -> str:
    try:
        from jiuwenswarm.server.runtime.designer.audio_locks import (
            image_prompt_limit_guidance,
        )

        return image_prompt_limit_guidance()
    except Exception:  # noqa: BLE001
        return (
            "IMAGE PROMPT LIMIT: follow the configured image backend's documented "
            "prompt length."
        )


def _video_limit_clause() -> str:
    try:
        from jiuwenswarm.server.runtime.designer.audio_locks import (
            video_prompt_limit_guidance,
        )

        return video_prompt_limit_guidance()
    except Exception:  # noqa: BLE001
        return (
            "VIDEO PROMPT LIMIT: follow the configured video backend's documented "
            "prompt length."
        )


def hollywood_leaf_instructions(role: str) -> str:
    """Compact continuity bible for leaf agents — no scene-genre hardcodes."""
    r = str(role or "").strip().lower()
    shared = (
        "You are a leaf craft artist under one Director. "
        "The Director owns the brief, storyboard, shot prompts, gates, budgets, "
        "and identity/spatial consistency checks. "
        "You MUST read the STORYBOARD (and BRIEF only when you are the storyboard leaf) "
        "and obey the Director's on_screen cast + setting_id. "
        "If vision tools exist, inspect upstream sheets/scene/prior KF and reconcile conflicts "
        "toward the storyboard (never invent a new cast or set).\n"
        "Non-negotiables:\n"
        "1) STORYBOARD + PRODUCTION LOCK BIBLE first — call read_upstream on "
        "n_storyboard BEFORE any image/video tool. Clips and stills do not re-read the full "
        "brief; the storyboard already carries the shot. Obey style, landmarks, "
        "lighting, crowd, speech_line, on_screen cast, setting_id.\n"
        "2) CAST IDENTITY: one body per character id; match wardrobe/face from the FEW attached "
        "character specs only. Never swap heroes; never clone one face onto two bodies. "
        "Do not request extra character specs for background people.\n"
        "3) SET: same setting_id → same architecture, furniture, window/wall layout, light side, "
        "and landmark screen-side (never teleport landmarks).\n"
        "4) STYLE: obey style_lock / LOCK BIBLE for the entire film; "
        "copy the brief/storyboard medium; if they could not infer one, use their "
        "cartoonish default; "
        "no mid-film medium switch (3D<->2D<->photoreal).\n"
        "5) BLOCKING: honor zones + landmark + CONTACT (bodies on supports, never "
        "through furniture/props); featured subjects face the landmark/action focus. "
        "Pose and placement are AUTHORITY from THIS storyboard row "
        "(start_state / end_state / spatial_anchors / cast_actions / clip_action). "
        "Copy sit vs stand, chair contact, and screen-side exactly — never invent a "
        "different posture (e.g. do not write 'sits' when the row says standing).\n"
        "6) SCREEN AXIS: keep L/R placement stable under pans (180-degree). Do not flip who is left/right.\n"
        "7) THIS CLIP ONLY: write from this storyboard row and the locks on this node. "
        "Do not use text, speech, frames, or locks from any previous clip. "
        "Only name on_screen cast from this row. Never spawn unnamed extras.\n"
        "8) LANGUAGE: use this row's speech_line / speech_by_character verbatim "
        "(empty = silent — do not invent, shorten, or add lines).\n"
        "9) FORMAT: aspect ratio, size, and resolution are canvas settings; never write them in a prompt.\n"
        "10) IMAGE-N: if references exist, name Image 1, Image 2… in attach order in your prompt.\n"
        "11) Finish with designer_node_complete(text=<FINAL visual-model prompt only>). "
        "The pipeline materializes media from that text — make it shot-ready, not a memo.\n"
        f"12) {_image_limit_clause()}\n"
        f"13) {_video_limit_clause()}\n"
    )
    if r in {"character"}:
        return (
            shared
            + "ROLE=character sheet. Write ONE positive Qwen-ready studio portrait prompt "
            "from the locks (name, wardrobe, style). Plain empty backdrop, one person. "
            "Fold wardrobe into 'wearing …' prose — no LOCK banners, no forbid lists, no examples. "
            "Then call_image_model with that prompt only. Finish with designer_node_complete "
            "preferring the PNG uri (text notes are optional debug only)."
        )
    if r == "scene":
        return (
            shared
            + "ROLE=scene specs. Write ONE positive Qwen-ready environment prompt "
            "from the locks (place, lighting/time-of-day, style, props). "
            "Furniture, walls, windows, light, and props as a clear empty room. "
            "No LOCK banners, no forbid lists, no examples. "
            "Then call_image_model with that prompt only. Finish with designer_node_complete "
            "preferring the PNG uri (text notes are optional debug only)."
        )
    if r in {"storyboard", "brief"}:
        return (
            shared
            + "ROLE=storyboard/brief. The BRIEF is your source. Turn it into timed shots with "
            "setting_id, on_screen, offscreen, cast_actions, camera, posture "
            "(stand/sit/walk/lean/…), spatial places, and speech.\n"
            "Each shot window owns its own action, posture, and spoken lines. "
            "Do not restate the same spoken line as the main dialogue of two adjacent "
            "shots unless the brief clearly wants a separate spoken response in the later "
            "window. Make posture and place explicit in cast_actions and start_state for "
            "every shot so clip leaves cannot invent spatial positioning.\n"
            "Downstream clips read the storyboard — not the raw brief."
        )
    if r == "clip":
        return (
            shared
            + "ROLE=clip. Authority is THIS storyboard row + the locks in your JSON "
            "context (clip_action, cast_actions, start_state, end_state, spatial_anchors, "
            "occupancy, speech_line / speech_by_character, camera, costume, scene_specs, "
            "style_lock). Translate that row into ONE positive story-form video prompt "
            "using the configured video model's best practices, then call_video_model. "
            "Do not use any previous clip.\n"
            "FIDELITY: keep the row's action, posture (stand/sit/walk/…), spatial places, "
            "who moves how, camera, and exact spoken words. Do not invent a different "
            "posture or place, do not invent or drop dialogue.\n"
            "FORM (adapt labels to the configured video model): The scene is as in "
            "Image N: <place from this row>. <Name> from Image k, wearing <this row's "
            "wardrobe>, <this row's posture + spatial place>, is <this row's action>. "
            "The camera <this row's move>. <Speaker> says: \"<this row's exact line>\".\n"
            "Positive sentences only — no previous-clip text, no forbid lists, no examples.\n"
            + _video_model_best_practices_extra()
        )
    return shared


def _video_model_best_practices_extra() -> str:
    """Configured-model prompt craft guidance — instructional, not regex gates."""
    try:
        from jiuwenswarm.server.runtime.designer.pipeline.wan_r2v_best_practices import (
            video_model_leaf_skill_block,
        )

        return video_model_leaf_skill_block(role="clip")
    except Exception:  # noqa: BLE001
        try:
            from jiuwenswarm.server.runtime.designer.pipeline.wan_r2v_best_practices import (
                wan_leaf_skill_block,
            )

            return wan_leaf_skill_block(role="clip")
        except Exception:  # noqa: BLE001
            return (
                "CONTACT: bodies never intersect furniture/props; when the shot uses a support "
                "surface, weight rests ON it. Solo sheets are identity — repose only as this "
                "storyboard row requires."
            )


def upstream_image_paths(
    ctx: Any,
    pred_ids: list[str],
    *,
    limit: int = 8,
) -> list[dict[str, str]]:
    """Resolve upstream image file paths for vision inspect / prompt binding."""
    from jiuwenswarm.server.runtime.designer.handlers.common import path_from_uri

    run = getattr(ctx, "run", None) or {}
    states = run.get("node_states") or {}
    graph = getattr(ctx, "graph", None) or {}
    role_by_id = {
        str(n.get("id") or ""): str((n.get("config") or {}).get("role") or "")
        for n in (graph.get("nodes") or [])
        if isinstance(n, dict)
    }
    out: list[dict[str, str]] = []
    for nid in pred_ids:
        st = states.get(nid) or {}
        refs: list[Any] = []
        if isinstance(st.get("output_ref"), dict):
            refs.append(st["output_ref"])
        for r in st.get("output_refs") or []:
            if isinstance(r, dict):
                refs.append(r)
        for ref in refs:
            p = path_from_uri(str(ref.get("uri") or ""))
            if p is None or not p.is_file():
                continue
            if p.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
                continue
            out.append(
                {
                    "node_id": str(nid),
                    "role": role_by_id.get(str(nid), ""),
                    "path": str(p),
                }
            )
            break
        if len(out) >= limit:
            break
    return out
