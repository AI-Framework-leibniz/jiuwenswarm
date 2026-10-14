# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, AsyncIterator

from openjiuwen.core.foundation.tool.base import Tool, ToolCard

from support import args_of, file_uri_ok, ticket_of


class SubmitNodeOutput(Tool):
    """Accept a file URI and report that the graph writer is not bound yet."""

    def __init__(self) -> None:
        super().__init__(
            ToolCard(
                id="submit_node_output",
                name="submit_node_output",
                description="把产物写回执行图。uri 必须是 file:// 绝对路径。",
                input_params={
                    "type": "object",
                    "properties": {
                        "shot_ticket": {"type": "string"},
                        "uri": {"type": "string"},
                        "extra_uris": {"type": "array", "items": {"type": "string"}},
                        "text": {"type": "string"},
                        "label": {"type": "string"},
                    },
                    "required": ["shot_ticket"],
                    "additionalProperties": False,
                },
                parallel_safe=False,
            )
        )

    async def invoke(self, inputs: Any, **kwargs: Any) -> dict:
        del kwargs
        try:
            data = args_of(inputs)
            if ticket_of(data) is None:
                return {"success": False, "status": "rejected", "output_ref": None, "error": "missing_shot_ticket"}
            uri = data.get("uri")
            if uri is not None and not file_uri_ok(uri):
                return {"success": False, "status": "rejected", "output_ref": None, "error": "uri_must_be_file_absolute"}
            extras = data.get("extra_uris") or []
            if not isinstance(extras, list) or any(not file_uri_ok(item) for item in extras if item):
                return {"success": False, "status": "rejected", "output_ref": None, "error": "extra_uris_must_be_file_absolute"}
            return {"success": False, "status": "unbound", "output_ref": None, "error": "graph_writer_unbound"}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "status": "rejected", "output_ref": None, "error": str(exc)}

    async def stream(self, inputs: Any, **kwargs: Any) -> AsyncIterator[dict]:
        yield await self.invoke(inputs, **kwargs)
