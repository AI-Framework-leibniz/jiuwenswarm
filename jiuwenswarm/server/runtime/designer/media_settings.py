# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Canvas-wide video and image generation settings.

``graph.metadata.video_settings`` and ``graph.metadata.image_settings`` are the
only stored copies. Every clip and still call reads them here at call time, so
one change applies to every node on the canvas. Clip length is not a setting:
each clip takes its own storyboard timeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from jiuwenswarm.server.runtime.designer.media_generation import IMAGE_RATIOS, configured_model
from jiuwenswarm.server.runtime.designer.pipeline.model_capacity import (
    VideoModelCapacity,
    active_video_capacity,
    default_ratio,
    ratio_value,
    snap_ratio,
    snap_resolution,
)

VIDEO_SETTINGS_KEY = "video_settings"
IMAGE_SETTINGS_KEY = "image_settings"
DEFAULT_IMAGE_RATIO = "16:9"

# About one megapixel per still keeps image calls cheap.
_IMAGE_SIZES = {
    "16:9": "1024x576",
    "9:16": "576x1024",
    "1:1": "1024x1024",
    "4:3": "1024x768",
    "3:4": "768x1024",
    "3:2": "1152x768",
    "2:3": "768x1152",
    "21:9": "1792x768",
}


class MediaSettingsError(ValueError):
    """A settings patch names a field or value the active models do not accept."""


@dataclass(frozen=True)
class VideoSettings:
    aspect_ratio: str
    resolution: str

    def as_dict(self) -> dict[str, str]:
        return {"aspect_ratio": self.aspect_ratio, "resolution": self.resolution}


@dataclass(frozen=True)
class ImageSettings:
    aspect_ratio: str

    @property
    def size(self) -> str:
        return _IMAGE_SIZES[self.aspect_ratio]

    def as_dict(self) -> dict[str, str]:
        return {"aspect_ratio": self.aspect_ratio}


def _stored(graph: Mapping[str, Any] | None, key: str) -> dict[str, Any]:
    meta = graph.get("metadata") if isinstance(graph, Mapping) else None
    raw = meta.get(key) if isinstance(meta, Mapping) else None
    return dict(raw) if isinstance(raw, Mapping) else {}


def default_video_settings(capacity: VideoModelCapacity | None = None) -> VideoSettings:
    cap = capacity or active_video_capacity()
    return VideoSettings(aspect_ratio=default_ratio(cap), resolution=cap.default_resolution)


def video_settings(
    graph: Mapping[str, Any] | None, capacity: VideoModelCapacity | None = None
) -> VideoSettings:
    """Stored canvas video settings, snapped onto the active video model."""
    cap = capacity or active_video_capacity()
    raw = _stored(graph, VIDEO_SETTINGS_KEY)
    return VideoSettings(
        aspect_ratio=snap_ratio(str(raw.get("aspect_ratio") or ""), cap),
        resolution=snap_resolution(str(raw.get("resolution") or ""), cap),
    )


def snap_image_ratio(requested: str) -> str:
    raw = str(requested or "").strip()
    if raw in IMAGE_RATIOS:
        return raw
    target = ratio_value(raw)
    if target is None:
        return DEFAULT_IMAGE_RATIO
    return min(IMAGE_RATIOS, key=lambda item: abs((ratio_value(item) or 0.0) - target))


def image_settings(graph: Mapping[str, Any] | None) -> ImageSettings:
    """Stored canvas image settings."""
    raw = _stored(graph, IMAGE_SETTINGS_KEY)
    return ImageSettings(aspect_ratio=snap_image_ratio(str(raw.get("aspect_ratio") or "")))


def _pick(value: Any, allowed: tuple[str, ...], field: str) -> str:
    token = str(value or "").strip()
    for item in allowed:
        if item.lower() == token.lower():
            return item
    raise MediaSettingsError(f"{field} must be one of {', '.join(allowed)}; got {token!r}")


def _check_fields(patch: Mapping[str, Any], allowed: set[str], kind: str) -> None:
    unknown = sorted(set(patch) - allowed)
    if unknown:
        raise MediaSettingsError(f"unknown {kind} setting(s): {', '.join(unknown)}")


def write_media_settings(
    graph: dict[str, Any],
    *,
    video: VideoSettings | None = None,
    image: ImageSettings | None = None,
) -> None:
    meta = graph.get("metadata") if isinstance(graph.get("metadata"), dict) else {}
    meta = dict(meta)
    if video is not None:
        meta[VIDEO_SETTINGS_KEY] = video.as_dict()
    if image is not None:
        meta[IMAGE_SETTINGS_KEY] = image.as_dict()
    graph["metadata"] = meta


def update_media_settings(
    graph: dict[str, Any],
    *,
    video: Mapping[str, Any] | None = None,
    image: Mapping[str, Any] | None = None,
    capacity: VideoModelCapacity | None = None,
) -> None:
    """Apply a partial settings patch. Values the active models reject raise."""
    if video is not None and not isinstance(video, Mapping):
        raise MediaSettingsError("video_settings must be an object")
    if image is not None and not isinstance(image, Mapping):
        raise MediaSettingsError("image_settings must be an object")
    cap = capacity or active_video_capacity()
    next_video = None
    if video:
        _check_fields(video, {"aspect_ratio", "resolution"}, "video")
        current = video_settings(graph, cap)
        next_video = VideoSettings(
            aspect_ratio=(
                _pick(video["aspect_ratio"], cap.ratios, "video aspect_ratio")
                if "aspect_ratio" in video
                else current.aspect_ratio
            ),
            resolution=(
                _pick(video["resolution"], cap.resolutions, "video resolution")
                if "resolution" in video
                else current.resolution
            ),
        )
    next_image = None
    if image:
        _check_fields(image, {"aspect_ratio"}, "image")
        next_image = ImageSettings(
            aspect_ratio=_pick(image["aspect_ratio"], IMAGE_RATIOS, "image aspect_ratio")
        )
    write_media_settings(graph, video=next_video, image=next_image)


def clip_durations(graph: dict[str, Any], run: dict[str, Any] | None = None) -> dict[str, int]:
    """Seconds each storyboard clip node will be generated at, read like the clip handler does."""
    from jiuwenswarm.common.schema.designer_graph import PIPELINE_CLIP, node_pipeline
    from jiuwenswarm.server.runtime.designer.handlers.clip import shot_duration_seconds
    from jiuwenswarm.server.runtime.designer.handlers.types import NodeExecutionContext

    out: dict[str, int] = {}
    for node in graph.get("nodes") or []:
        if node_pipeline(node) != PIPELINE_CLIP:
            continue
        ctx = NodeExecutionContext(graph=graph, run_id="", node_id=str(node["id"]), run=run)
        out[str(node["id"])] = shot_duration_seconds(ctx, node)
    return out


def media_capabilities(
    graph: dict[str, Any] | None = None, run: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Values the toolbar may offer, plus this canvas's effective settings and clip lengths."""
    cap = active_video_capacity()
    out: dict[str, Any] = {
        "video": {
            "configured_model": configured_model("video"),
            "model_id": cap.model_id,
            "provider": cap.provider,
            "ratios": list(cap.ratios),
            "resolutions": list(cap.resolutions),
            "default_ratio": default_ratio(cap),
            "default_resolution": cap.default_resolution,
            "min_sec": cap.min_sec,
            "max_sec": cap.max_sec,
            "default_sec": cap.default_sec,
        },
        "image": {
            "ratios": list(IMAGE_RATIOS),
            "default_ratio": DEFAULT_IMAGE_RATIO,
        },
    }
    if graph is not None:
        out["settings"] = {
            "video": video_settings(graph, cap).as_dict(),
            "image": image_settings(graph).as_dict(),
        }
        out["clip_durations"] = clip_durations(graph, run)
    return out
