# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Design-only execution rail: the leader's ``designer_run_graph`` tool.

Mounts exactly one capability — triggering the canvas execution (graph →
swarmflow compilation → run) from the conversation — together with the system
prompt section that teaches when and how to use it. Mounted only on the
team.design leader profile; every other mode never sees it.

The tool wraps :meth:`StoreNodeSpawner.run_graph` (trigger re-entry guard +
per-graph coordinator) and mirrors the canvas run button's three modes:
no args = run every unproduced node, ``node_id`` = single-node rerun
(candidate semantics), ``node_id`` + ``cascade`` = rerun from that node
through its downstream closure.

A full graph run is many worker LLM turns plus media generation, so the
tool starts the trigger on a background task and returns at once, exactly
like the canvas run button. Progress streams to the canvas; the run outcome
is NOT fed back to the leader (no follow-up round). The leader reads results
with ``designer_graph_get`` when the user asks.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from openjiuwen.core.foundation.tool import LocalFunction, ToolCard
from openjiuwen.harness.prompts import PromptSection
from openjiuwen.harness.rails.base import DeepAgentRail

logger = logging.getLogger(__name__)

TOOL_NAME = "designer_run_graph"
SECTION_NAME = "designer_execution"

_PROMPT_CN = """# 画布执行（designer_run_graph）

征得用户同意后，你可以直接触发设计画布的执行（与画布上的运行按钮完全等价）：

- 不带参数：运行所有还没有产出的节点（首次全量运行或补跑新加的节点）。
- 只给 `node_id`：只重跑该节点。新产出进入候选（candidate），等用户在画布上选择"用新结果"还是"保留原结果"；下游节点绝不会跟着重跑。
- `node_id` + `cascade=true`：从该节点起连同它的所有下游一起重跑（结果直接覆盖）；上游节点保持现有产出不变，即使它的产出基于更早的输入也原样使用。

调用约定：
- 工具调用**立即返回**（执行在后台进行），进度实时推送到画布；执行结果不会自动回传给你。
- 同一时刻只允许一个执行；执行中再次调用会被拒绝，此时告诉用户稍候。
- 调用后告诉用户"已开始执行，画布可看进度"，然后结束本轮回复，不要等待结果。
- 用户之后询问结果或反馈失败时，用 designer_graph_get 读取各节点状态与产出，说明失败节点与原因，建议下一步（改提示词重跑该节点 / 从该节点续跑）。
"""

_PROMPT_EN = """# Canvas execution (designer_run_graph)

After the user agrees, you may trigger the canvas execution directly (same
semantics as the canvas run button):

- No args: run every node that has no output yet (first full run, or catch
  up newly added nodes).
- `node_id` only: rerun just that node. The fresh output lands as a
  candidate — the user chooses on the canvas between the new result and the
  original; downstream nodes never re-execute.
- `node_id` + `cascade=true`: rerun that node plus its whole downstream
  closure (outputs overwrite directly); upstream nodes keep their current
  outputs as-is.

Conventions:
- The tool call returns IMMEDIATELY (the run executes in the background);
  progress streams to the canvas. The outcome is NOT delivered back to you.
- Only one execution at a time; a second call while one runs is rejected —
  tell the user to wait.
- After launching, tell the user "execution started, watch the canvas" and
  end your reply; do not wait for the result.
- When the user later asks about results or reports failures, read node
  states and outputs with designer_graph_get, name failed nodes and reasons,
  and suggest the next step (edit the prompt and rerun / rerun from there).
"""


class DesignerExecutionRail(DeepAgentRail):
    """Leader-only execution tool + its prompt section (team.design)."""

    priority = 60

    def __init__(self, *, session_id: str) -> None:
        super().__init__()
        self._session_id = session_id
        self._spawner: Any = None
        self._runs: set[asyncio.Task[Any]] = set()
        self.system_prompt_builder = None
        self._tool: LocalFunction | None = None

    # ------------------------------------------------------------------
    # tool
    # ------------------------------------------------------------------

    def _build_tool(self) -> LocalFunction:
        spawner = self._spawner

        def _on_run_done(task: asyncio.Task[Any]) -> None:
            self._runs.discard(task)
            if not task.cancelled() and task.exception() is not None:
                logger.error(
                    "[DesignerExecutionRail] canvas run crashed: session_id=%s",
                    self._session_id,
                    exc_info=task.exception(),
                )

        async def _run_graph(**kwargs: Any) -> str:
            node_id = str(kwargs.get("node_id") or "").strip()
            cascade = bool(kwargs.get("cascade"))
            if cascade and not node_id:
                return "cascade requires node_id"
            if spawner.is_running():
                return "执行被拒绝：画布上已有执行在进行，等它结束后再触发。"
            mode = "单点重跑" if node_id and not cascade else (
                "从该节点续跑" if node_id else "全量运行"
            )
            task = asyncio.create_task(
                spawner.run_graph(node_ids=[node_id] if node_id else None, cascade=cascade)
            )
            self._runs.add(task)
            task.add_done_callback(_on_run_done)
            return f"已开始{mode}：执行在后台进行，进度实时推送到画布。不要重复调用。"

        card = ToolCard(
            name=TOOL_NAME,
            description=(
                "触发设计画布执行（把当前图编译为工作流并在后台运行）。不带参数="
                "运行所有没有产出的节点；node_id=只重跑该节点（产出进候选，等用户"
                "选择，下游不重跑）；node_id+cascade=true=从该节点起连同其下游一起"
                "重跑（直接覆盖），上游保持现有产出。调用立即返回，执行在后台进行，"
                "结果不会回传。"
            ),
            input_params={
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "cascade": {"type": "boolean"},
                },
            },
        )
        return LocalFunction(card=card, func=_run_graph)

    # ------------------------------------------------------------------
    # rail lifecycle
    # ------------------------------------------------------------------

    def init(self, agent: Any) -> None:
        from jiuwenswarm.server.runtime.design.context import (
            get_design_context_registry,
        )

        context = get_design_context_registry().get(self._session_id)
        if context is None or context.spawner is None:
            logger.warning(
                "[DesignerExecutionRail] session not bound to a designer "
                "graph; tool not mounted: session_id=%s",
                self._session_id,
            )
            return
        self._spawner = context.spawner
        self.system_prompt_builder = getattr(agent, "system_prompt_builder", None)
        self._tool = self._build_tool()
        agent.ability_manager.add_ability(self._tool.card, self._tool)
        logger.info(
            "[DesignerExecutionRail] mounted %s for session %s",
            TOOL_NAME,
            self._session_id,
        )

    def uninit(self, agent: Any) -> None:
        try:
            agent.ability_manager.remove(TOOL_NAME)
        except Exception:  # noqa: BLE001
            logger.debug("[DesignerExecutionRail] tool already absent on uninit")
        if self.system_prompt_builder is not None:
            self.system_prompt_builder.remove_section(SECTION_NAME)
        self._tool = None
        self._spawner = None
        self.system_prompt_builder = None

    async def before_model_call(self, ctx: Any) -> None:
        _ = ctx
        if self.system_prompt_builder is None or self._spawner is None:
            return
        self.system_prompt_builder.add_section(
            PromptSection(
                name=SECTION_NAME,
                content={"cn": _PROMPT_CN, "en": _PROMPT_EN},
                priority=60,
            )
        )


__all__ = ["DesignerExecutionRail", "TOOL_NAME"]
