# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""``POST /file-api/upload`` without a token: a Design canvas asset upload.

The canvas sends one ``file`` field as multipart/form-data (see
``uploadDesignerAsset`` in the web frontend). The file is stored under
``<agent root>/uploads/designer/`` - inside the ``/file-api/raw-file`` allowed
roots, so the canvas can preview it - and its absolute path is returned. This
mirrors the Vite dev server's middleware for the same route.
"""

from __future__ import annotations

import mimetypes
import re
import uuid
from pathlib import Path, PureWindowsPath
from typing import Any

from jiuwenswarm.server.runtime.skill.skill_manager import SkillRpcError
from jiuwenswarm.server.runtime.skill.skills_multipart_http import parse_multipart_form

MAX_DESIGNER_UPLOAD_BYTES = 32 * 1024 * 1024
_UNSAFE_FILENAME_CHARS = re.compile(r'[\x00-\x1f\\/:*?"<>|]')


def designer_upload_dir(agent_root: Path) -> Path:
    return Path(agent_root) / "uploads" / "designer"


def _error(status: int, code: str) -> tuple[int, dict[str, Any]]:
    return status, {"error": code, "files": [], "errors": [{"error": code}]}


def _safe_filename(filename: str) -> str:
    # PureWindowsPath strips both "/" and "\" directory parts on every platform.
    base = PureWindowsPath(filename or "").name
    return _UNSAFE_FILENAME_CHARS.sub("_", base)[:120] or "upload.bin"


def handle_designer_upload_http(
    *, content_type: str, body: bytes, upload_dir: Path
) -> tuple[int, dict[str, Any]]:
    """Store the uploaded ``file`` field and describe it.

    Returns:
        ``(status, payload)``: 200 with ``{"ok": True, "files": [{path, filename,
        mime_type, size}], "errors": []}``, or an error status whose payload carries
        ``error`` and ``errors[0].error``.
    """
    if len(body) > MAX_DESIGNER_UPLOAD_BYTES:
        return _error(413, "file_too_large")
    try:
        fields = parse_multipart_form(content_type, body)
    except SkillRpcError:
        return _error(400, "invalid_multipart")
    field = fields.get("file")
    if not isinstance(field, dict):
        return _error(400, "missing_file")
    original = PureWindowsPath(str(field.get("filename") or "")).name
    safe_name = _safe_filename(original)
    content: bytes = field.get("content") or b""
    try:
        upload_dir.mkdir(parents=True, exist_ok=True)
        stored = upload_dir / f"{uuid.uuid4()}_{safe_name}"
        stored.write_bytes(content)
    except OSError:
        return _error(500, "upload_failed")
    mime_type, _ = mimetypes.guess_type(safe_name)
    return 200, {
        "ok": True,
        "files": [{
            "path": str(stored),
            "filename": original or safe_name,
            "mime_type": mime_type or "application/octet-stream",
            "size": len(content),
        }],
        "errors": [],
    }
