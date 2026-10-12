# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Gated prior-clip last-frame + speech anti-repeat for Wan continuity.

Last-frame media is used ONLY when the next clip continues the same setting
(soft cut). Hard cuts / new settings break the chain.

Within one scene we accumulate ending images from every prior same-scene clip
(back to the first shot of that setting) so exited cast can still be localized.
The immediate prior ending remains the primary continuity start; older endings
are history refs. The Wan prompt narrates what led to what.

Prior speech is stamped as already-delivered — next clip must not restate it.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Leave headroom for character specs + scene spec in Wan reference_images.
MAX_SCENE_LAST_FRAME_REFS = 4


def _norm_ids(raw: Any) -> list[str]:
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def _on_screen_ids(cfg: dict[str, Any] | None) -> list[str]:
    cfg = cfg if isinstance(cfg, dict) else {}
    ids = _norm_ids(cfg.get("on_screen")) or _norm_ids(cfg.get("character_ids"))
    occ = cfg.get("occupancy") if isinstance(cfg.get("occupancy"), dict) else {}
    if not ids:
        ids = _norm_ids(occ.get("must_appear"))
    return list(dict.fromkeys(ids))


def _setting_id(cfg: dict[str, Any] | None) -> str:
    cfg = cfg if isinstance(cfg, dict) else {}
    return str(cfg.get("setting_id") or "").strip() or "set_1"


def _looks_like_hard_cut(this_cfg: dict[str, Any] | None, prev_cfg: dict[str, Any] | None) -> bool:
    this_cfg = this_cfg if isinstance(this_cfg, dict) else {}
    prev_cfg = prev_cfg if isinstance(prev_cfg, dict) else {}
    blob = " ".join(
        str(x)
        for x in (
            this_cfg.get("clip_action"),
            this_cfg.get("scene_change"),
            this_cfg.get("scene_distinctness"),
            (this_cfg.get("continuity_lock") or {}).get("forbid")
            if isinstance(this_cfg.get("continuity_lock"), dict)
            else "",
            (this_cfg.get("generate") or {}).get("prompt")
            if isinstance(this_cfg.get("generate"), dict)
            else "",
        )
        if x
    ).lower()
    if any(
        tok in blob
        for tok in (
            "hard cut",
            "smash cut",
            "cut to",
            "new location",
            "elsewhere",
            "meanwhile",
            "jump cut to another",
        )
    ):
        return True
    # Different setting always hard for last-frame purposes.
    if _setting_id(this_cfg) != _setting_id(prev_cfg):
        return True
    return False


def should_use_prior_last_frame(
    *,
    this_cfg: dict[str, Any] | None,
    prev_cfg: dict[str, Any] | None,
    require_cast_overlap: bool = True,
) -> bool:
    """Gate: same setting, not a hard cut; optional cast overlap for soft cuts."""
    this_cfg = this_cfg if isinstance(this_cfg, dict) else {}
    prev_cfg = prev_cfg if isinstance(prev_cfg, dict) else {}
    if not prev_cfg:
        return False
    if bool(this_cfg.get("forbid_prior_last_frame")) or bool(
        this_cfg.get("hard_cut")
    ):
        return False
    if _looks_like_hard_cut(this_cfg, prev_cfg):
        return False
    if _setting_id(this_cfg) != _setting_id(prev_cfg):
        return False
    if not require_cast_overlap:
        return True
    prev_cast = set(_on_screen_ids(prev_cfg))
    this_cast = set(_on_screen_ids(this_cfg))
    if not prev_cast or not this_cast:
        # Unknown cast — allow same-setting soft continuity.
        return True
    # Need at least one shared on-screen person (localization target).
    if not (prev_cast & this_cast):
        return False
    return True


def should_keep_scene_frame_chain(
    *,
    later_cfg: dict[str, Any] | None,
    earlier_cfg: dict[str, Any] | None,
) -> bool:
    """Softer gate for history images inside one scene (exited cast allowed)."""
    return should_use_prior_last_frame(
        this_cfg=later_cfg,
        prev_cfg=earlier_cfg,
        require_cast_overlap=False,
    )


def _clip_nodes_sorted(graph: dict[str, Any] | None) -> list[dict[str, Any]]:
    graph = graph if isinstance(graph, dict) else {}
    clips: list[dict[str, Any]] = []
    for node in graph.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        cfg = node.get("config") if isinstance(node.get("config"), dict) else {}
        role = str(cfg.get("role") or "")
        nid = str(node.get("id") or "")
        if role not in {"clip", "video"} and not nid.startswith("n_clip_"):
            continue
        idx = int(cfg.get("clip_index") or 0) or 0
        if idx <= 0:
            continue
        clips.append(node)
    return sorted(
        clips,
        key=lambda n: int((n.get("config") or {}).get("clip_index") or 0) or 0,
    )


def _short_beat(cfg: dict[str, Any] | None, *, limit: int = 140) -> str:
    cfg = cfg if isinstance(cfg, dict) else {}
    raw = str(
        cfg.get("clip_action")
        or cfg.get("character_action")
        or cfg.get("previous_clip_action")
        or ""
    ).strip()
    raw = re.sub(r"\s+", " ", raw)
    return raw[:limit]


def _last_frame_path_for_clip(
    node: dict[str, Any],
    *,
    ctx: Any = None,
) -> Path | None:
    cfg = node.get("config") if isinstance(node.get("config"), dict) else {}
    for key in ("last_frame_path", "previous_clip_last_frame"):
        path = Path(str(cfg.get(key) or "").strip())
        if path.is_file():
            return path.resolve()
    if ctx is None:
        return None
    try:
        from jiuwenswarm.server.runtime.designer.handlers.common import (
            node_output_refs,
            path_from_uri,
        )

        nid = str(node.get("id") or "")
        for ref in node_output_refs(ctx, nid):
            uri = str((ref or {}).get("uri") or "")
            vp = path_from_uri(uri)
            if vp is not None and vp.is_file() and vp.suffix.lower() in {
                ".mp4",
                ".mov",
                ".webm",
            }:
                extracted = extract_last_frame(vp)
                if extracted is not None:
                    return extracted
    except Exception:  # noqa: BLE001
        logger.debug("resolve clip last frame from ctx failed", exc_info=True)
    return None


def _find_ffmpeg() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        exe = str(imageio_ffmpeg.get_ffmpeg_exe() or "").strip()
        return exe or None
    except Exception:  # noqa: BLE001
        return None


def extract_last_frame(video_path: Path, dest: Path | None = None) -> Path | None:
    """Extract near-end frame from a completed clip mp4."""
    src = Path(video_path)
    if not src.is_file():
        return None
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        logger.warning("ffmpeg unavailable; cannot extract prior-clip last frame")
        return None
    out = dest or (src.with_name(f"{src.stem}_lastframe.jpg"))
    out.parent.mkdir(parents=True, exist_ok=True)
    # Seek near end; -sseof works on most ffmpeg builds.
    try:
        proc = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-sseof",
                "-0.15",
                "-i",
                str(src.resolve()),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(out.resolve()),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.returncode == 0 and out.is_file() and out.stat().st_size > 100:
            return out.resolve()
    except Exception:  # noqa: BLE001
        logger.debug("last-frame extract failed", exc_info=True)
    return None


def _normalize_speech(text: str) -> str:
    raw = re.sub(r"\s+", " ", (text or "").strip().lower())
    raw = re.sub(r"[\"'`]+", "", raw)
    return raw.strip(" .,!?;:")


def speech_already_delivered(this_speech: str, prior_speech: str) -> bool:
    """True when this shot would restate prior dialogue (exact or contained)."""
    a = _normalize_speech(this_speech)
    b = _normalize_speech(prior_speech)
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 12 and (a in b or b in a):
        return True
    # High token overlap for short lines.
    ta, tb = set(a.split()), set(b.split())
    if len(ta) >= 3 and len(tb) >= 3:
        overlap = len(ta & tb) / max(1, min(len(ta), len(tb)))
        if overlap >= 0.85:
            return True
    return False


def scrub_restated_speech(cfg: dict[str, Any]) -> dict[str, Any]:
    """Honor forbidden_speech already on this clip. Do not read a previous clip."""
    cfg = dict(cfg or {})
    cfg.pop("previous_clip_speech", None)
    forbid = [
        str(x).strip()
        for x in (cfg.get("forbidden_speech") or [])
        if str(x).strip()
    ]

    this_line = str(cfg.get("speech_line") or "").strip()
    by_char = (
        dict(cfg["speech_by_character"])
        if isinstance(cfg.get("speech_by_character"), dict)
        else {}
    )

    cleared = False
    if this_line and any(speech_already_delivered(this_line, p) for p in forbid):
        cfg["speech_line"] = ""
        cleared = True
    cleaned_by: dict[str, str] = {}
    for cid, line in by_char.items():
        text = str(line or "").strip()
        if text and any(speech_already_delivered(text, p) for p in forbid):
            cleared = True
            continue
        if text:
            cleaned_by[str(cid)] = text
    if by_char and cleaned_by != by_char:
        cfg["speech_by_character"] = cleaned_by
        if not cleaned_by:
            cfg["speech_line"] = ""
    elif cleared and not cleaned_by:
        cfg["speech_by_character"] = {}

    if cleared:
        cfg["speech_continuation_only"] = True
        # Do not append prior-speech notes into already_done (that feeds prompt preambles).
        cfg.pop("already_done", None)
    cfg["forbidden_speech"] = forbid[:8]
    return cfg


def prior_speech_lock_clause(cfg: dict[str, Any] | None) -> str:
    """This clip does not receive another clip's speech."""
    del cfg
    return ""


def last_frame_continuity_clause(
    *,
    used: bool = False,
    path: str = "",
    chain: list[dict[str, Any]] | None = None,
) -> str:
    """Narrate same-scene ending images: what led to what → continue from latest."""
    items = [c for c in (chain or []) if isinstance(c, dict) and str(c.get("path") or "").strip()]
    if not items and not used:
        return ""
    if not items and used:
        return (
            "CONTINUITY FIRST FRAME = last frame of the previous clip "
            f"({path or 'prior ending image'}). "
            "Use it only to localize last-seen people and place. "
            "THIS clip's action/camera come from the storyboard shot — "
            "do not replace that beat with a different plot from the image. "
            "Face/wardrobe authority remains character specs reference images."
        )

    lines: list[str] = [
        "SAME-SCENE CONSISTENCY CHAIN (ending images localize last-seen people/place; "
        "they are NOT the plot for THIS clip):",
    ]
    for i, item in enumerate(items):
        idx = int(item.get("clip_index") or 0) or "?"
        beat = str(item.get("action") or "").strip() or "(prior beat)"
        speech = str(item.get("speech") or "").strip()
        bit = f"- Shot {idx} ENDED here: {beat}"
        if speech:
            bit += f' [speech already delivered: "{speech[:100]}"]'
        if i == len(items) - 1:
            bit += " ← localization of last-seen people/place only."
        else:
            bit += " (history — localize exited / off-screen people who were last seen here)."
        lines.append(bit)
    if len(items) > 1:
        arrow = " → ".join(f"shot {int(c.get('clip_index') or 0)}" for c in items)
        lines.append(f"Beat progression in this setting: {arrow} → THIS shot.")
    lines.append(
        "Do NOT attach these images as Wan refs (they steal character1 and restage a crop). "
        "Identity = on-screen character specs; geography = scene spec LAST; plot = THIS storyboard shot "
        "continuing the previous Wan prompt. People who left stay off-screen — "
        "do not teleport them back or restage walking away unless the storyboard asks."
    )
    return "\n".join(lines)


def collect_same_scene_last_frame_chain(
    cfg: dict[str, Any] | None,
    *,
    graph: dict[str, Any] | None = None,
    ctx: Any = None,
    max_frames: int = MAX_SCENE_LAST_FRAME_REFS,
) -> list[dict[str, Any]]:
    """Oldest→newest gated ending images from the first clip of this setting to N-1.

    Walks prior clips with the same setting_id. A hard cut / setting change breaks
    the chain. Cast overlap is NOT required for history frames (exits allowed);
    the immediate prior image prefers cast overlap when deciding primary continuity,
    but same-setting history is kept for localization.
    """
    cfg = cfg if isinstance(cfg, dict) else {}
    graph = graph if isinstance(graph, dict) else {}
    this_idx = int(cfg.get("clip_index") or 0) or 0
    if this_idx <= 1:
        return []
    if bool(cfg.get("forbid_prior_last_frame")) or bool(cfg.get("hard_cut")):
        return []
    if cfg.get("use_prior_last_frame") is False:
        return []

    priors = [
        n
        for n in _clip_nodes_sorted(graph)
        if int((n.get("config") or {}).get("clip_index") or 0) < this_idx
    ]
    if not priors:
        return []

    # Walk newest→oldest; stop at hard cut / setting break.
    selected_rev: list[dict[str, Any]] = []
    later_cfg: dict[str, Any] = cfg
    for node in reversed(priors):
        pcfg = node.get("config") if isinstance(node.get("config"), dict) else {}
        pcfg = pcfg if isinstance(pcfg, dict) else {}
        if not should_keep_scene_frame_chain(later_cfg=later_cfg, earlier_cfg=pcfg):
            break
        path = _last_frame_path_for_clip(node, ctx=ctx)
        # Fall back to stamped chain entry on this cfg for the immediate prior.
        if path is None and not selected_rev:
            stamped = Path(str(cfg.get("previous_clip_last_frame") or "").strip())
            if stamped.is_file():
                path = stamped.resolve()
        if path is None:
            # Missing media — keep walking for older history if still same scene.
            later_cfg = pcfg
            continue
        selected_rev.append(
            {
                "clip_index": int(pcfg.get("clip_index") or 0) or 0,
                "node_id": str(node.get("id") or ""),
                "path": str(path),
                "action": _short_beat(pcfg),
                "speech": str(pcfg.get("speech_line") or "")[:160],
                "setting_id": _setting_id(pcfg),
            }
        )
        later_cfg = pcfg

    chain = list(reversed(selected_rev))
    # Cap: keep the oldest scene opener + the most recent endings.
    cap = max(1, int(max_frames or MAX_SCENE_LAST_FRAME_REFS))
    if len(chain) > cap:
        chain = [chain[0], *chain[-(cap - 1) :]] if cap > 1 else chain[-1:]
    return chain


def resolve_gated_last_frame_chain(
    cfg: dict[str, Any] | None,
    *,
    graph: dict[str, Any] | None = None,
    ctx: Any = None,
    max_frames: int = MAX_SCENE_LAST_FRAME_REFS,
) -> list[dict[str, Any]]:
    """Previous clip frames are not references for this clip."""
    del cfg, graph, ctx, max_frames
    return []


def chain_paths_newest_first(chain: list[dict[str, Any]] | None) -> list[Path]:
    """Attach order for Wan: newest ending first, then older history."""
    paths: list[Path] = []
    for item in reversed(list(chain or [])):
        if not isinstance(item, dict):
            continue
        p = Path(str(item.get("path") or "").strip())
        if p.is_file():
            resolved = p.resolve()
            if resolved not in paths:
                paths.append(resolved)
    return paths


def stamp_scene_last_frame_chain(
    cfg: dict[str, Any],
    chain: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Persist compact chain metadata on clip config for prompt/rebuild."""
    cfg = dict(cfg or {})
    compact: list[dict[str, Any]] = []
    for item in chain or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        compact.append(
            {
                "clip_index": int(item.get("clip_index") or 0) or 0,
                "node_id": str(item.get("node_id") or ""),
                "path": path,
                "action": str(item.get("action") or "")[:140],
                "speech": str(item.get("speech") or "")[:120],
            }
        )
    cfg["scene_last_frame_chain"] = compact[:MAX_SCENE_LAST_FRAME_REFS]
    if compact:
        cfg["previous_clip_last_frame"] = compact[-1]["path"]
        cfg["use_prior_last_frame"] = True
    return cfg


def chain_prior_speech_across_clips(graph: dict[str, Any]) -> list[str]:
    """Do not copy one clip's speech onto the next. Each row keeps its storyboard line."""
    del graph
    return []


def stamp_last_frame_onto_next_clips(
    graph: dict[str, Any],
    *,
    completed_clip_id: str,
    last_frame_path: str,
    clip_index: int,
    speech_line: str = "",
) -> list[str]:
    """Save this clip's last frame on this clip only. Later clips are not updated."""
    del speech_line
    notes: list[str] = []
    frame = str(last_frame_path or "").strip()
    if not frame:
        return notes
    for node in graph.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        if str(node.get("id") or "") != str(completed_clip_id or ""):
            continue
        cfg = dict(node.get("config") or {})
        cfg["last_frame_path"] = frame
        node["config"] = cfg
        notes.append(f"{completed_clip_id}: saved last_frame_path on this clip only")
        break
    return notes


def resolve_gated_last_frame_path(
    cfg: dict[str, Any] | None,
    *,
    graph: dict[str, Any] | None = None,
    ctx: Any = None,
) -> Path | None:
    """Previous clip frames are not attached to this clip."""
    del cfg, graph, ctx
    return None