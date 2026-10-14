# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, AsyncIterator

from openjiuwen.core.foundation.tool.base import Tool, ToolCard

from support import args_of, ticket_of


class GenerateCharacter(Tool):
    """One generation call for this member. A second call returns an error dict."""

    def __init__(self) -> None:
        super().__init__(
            ToolCard(
                id="generate_character",
                name="generate_character",
                description="按票据和提示生成一次产物。失败时返回字典，不抛异常。",
                input_params={
                    "type": "object",
                    "properties": {"shot_ticket": {"type": "string"}, "prompt": {"type": "string"}, "subject": {"type": "string", "description": "这一张设定图上的主体"}},
                    "required": ["shot_ticket", "prompt"],
                    "additionalProperties": False,
                },
                parallel_safe=False,
            )
        )
        self._used = False

    async def invoke(self, inputs: Any, **kwargs: Any) -> dict:
        del kwargs
        prompt = ""
        try:
            data = args_of(inputs)
            prompt = data.get("prompt") if isinstance(data.get("prompt"), str) else ""
            if data.get("__node_guard_reject__") == "generate_already_called" or self._used:
                self._used = True
                return {
                    "success": False,
                    "image_uri": None,
                    "sent_prompt": prompt,
                    "prompt_source": "argument",
                    "error": "generate_already_called",
                }
            if ticket_of(data) is None:
                return {
                    "success": False,
                    "image_uri": None,
                    "sent_prompt": prompt,
                    "prompt_source": "argument",
                    "error": "missing_shot_ticket",
                }
            if not prompt.strip():
                return {
                    "success": False,
                    "image_uri": None,
                    "sent_prompt": prompt,
                    "prompt_source": "argument",
                    "error": "missing_prompt",
                }
            self._used = True
            return {
                "success": False,
                "image_uri": None,
                "sent_prompt": prompt,
                "prompt_source": "argument",
                "error": "generator_unbound",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "success": False,
                "image_uri": None,
                "sent_prompt": prompt,
                "prompt_source": "argument",
                "error": str(exc),
            }

    async def stream(self, inputs: Any, **kwargs: Any) -> AsyncIterator[dict]:
        yield await self.invoke(inputs, **kwargs)
