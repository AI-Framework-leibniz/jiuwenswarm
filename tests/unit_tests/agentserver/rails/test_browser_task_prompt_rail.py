# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Browser rail identifies browser_agent from public card fields."""

from __future__ import annotations

from types import SimpleNamespace

from jiuwenswarm.agents.harness.common.rails.browser_task_prompt_rail import (
    BrowserTaskPromptRail,
)


def test_has_browser_agent_reads_agent_card_or_card() -> None:
    agent = SimpleNamespace(
        deep_config=SimpleNamespace(
            subagents=[
                SimpleNamespace(agent_card=SimpleNamespace(name="general")),
                SimpleNamespace(card=SimpleNamespace(name="browser_agent")),
            ]
        )
    )
    assert BrowserTaskPromptRail._has_browser_agent(agent) is True


def test_has_browser_agent_reads_dict_card() -> None:
    agent = SimpleNamespace(
        deep_config=SimpleNamespace(
            subagents=[SimpleNamespace(agent_card={"name": "browser_agent"})]
        )
    )
    assert BrowserTaskPromptRail._has_browser_agent(agent) is True


def test_has_browser_agent_false_without_browser() -> None:
    agent = SimpleNamespace(
        deep_config=SimpleNamespace(
            subagents=[SimpleNamespace(agent_card=SimpleNamespace(name="code"))]
        )
    )
    assert BrowserTaskPromptRail._has_browser_agent(agent) is False
