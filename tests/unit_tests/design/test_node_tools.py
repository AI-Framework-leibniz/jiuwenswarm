# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Host side of the designer member tools (``design.node_tools``) and the
media guarantee's member-call recovery."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from openjiuwen.agent_teams.workflow.engine.backends.base import AgentResult

from jiuwenswarm.server.runtime.design import node_tools
from jiuwenswarm.server.runtime.design.context import get_design_context_registry
from jiuwenswarm.server.runtime.design.event_bridge import DesignEventBridge
from jiuwenswarm.server.runtime.design.media_guarantee import MediaGuaranteeBackend
from jiuwenswarm.server.runtime.design.node_tools import (
    NODE_OUTPUT_SCHEMA,
    NodeRunEnv,
    generate_node_output,
    read_node_context,
    submit_node_output,
    ticket_line,
)
from jiuwenswarm.server.runtime.designer.handlers.types import NodeResult

_GRAPH_ID = "g_tools"
_RUN_ID = "run_tools"


def _graph() -> dict[str, Any]:
    return {
        "graph_id": _GRAPH_ID,
        "title": "Tea ad",
        "metadata": {"approved_brief": "APPROVED BRIEF", "style_lock": "ink wash"},
        "nodes": [
            {"id": "n_brief", "type": "text", "label": "Brief",
             "config": {"pipeline": "brief", "prompt": "write the brief"}},
            {"id": "n_hero", "type": "image", "label": "Hero",
             "config": {"pipeline": "character", "prompt": "draw the hero"}},
        ],
        "edges": [{"id": "e1", "source": "n_brief", "target": "n_hero"}],
    }


class _Store:
    def save_run(self, run: dict[str, Any]) -> dict[str, Any]:
        return run


@pytest.fixture
def env(tmp_path: Path):
    graph = _graph()
    run = {"run_id": _RUN_ID, "graph_id": _GRAPH_ID, "status": "running", "node_states": {}}
    bridge = DesignEventBridge(run, None, store=_Store(), graph=graph)
    context = get_design_context_registry().bind("sess_tools", _GRAPH_ID)
    context.node_run_env = NodeRunEnv(graph=graph, run=run, bridge=bridge, media_root=tmp_path)
    yield context.node_run_env
    context.node_run_env = None
    get_design_context_registry().drop("sess_tools")


def _ticket(node_id: str) -> str:
    return f"## task\n{ticket_line(_GRAPH_ID, _RUN_ID, node_id)}\nmore text"


class _FakeHandler:
    def __init__(self, tmp_path: Path, *, fail: bool = False) -> None:
        self.tmp_path = tmp_path
        self.fail = fail
        self.seen_prompts: list[str] = []

    async def execute(self, node, ctx):
        cfg = node["config"]
        self.seen_prompts.append(cfg["prompt"])
        if self.fail:
            raise RuntimeError("model down")
        if cfg.get("pipeline") == "brief":
            path = self.tmp_path / f"{node['id']}.md"
            path.write_text(f"BRIEF FROM {cfg['prompt']}", encoding="utf-8")
            ref = {"kind": "text", "uri": path.as_uri(), "mime_type": "text/markdown"}
        else:
            path = self.tmp_path / f"{node['id']}.png"
            path.write_bytes(b"\x89PNG\r\n\x1a\n")
            ref = {"kind": "image", "uri": path.as_uri(), "mime_type": "image/png"}
            cfg["last_wan_prompt"] = f"locked: {cfg['prompt']}"
        return NodeResult(output_ref=ref, output_refs=[ref], message="done")


@pytest.fixture
def handler(monkeypatch, tmp_path: Path):
    fake = _FakeHandler(tmp_path)
    monkeypatch.setattr(
        "jiuwenswarm.server.runtime.designer.handlers.get_node_handler", lambda _node: fake
    )
    return fake


async def test_ticket_errors(env):
    assert (await read_node_context("no ticket here"))["error"] == "invalid_shot_ticket"
    bad_run = ticket_line(_GRAPH_ID, "other_run", "n_brief")
    assert (await read_node_context(bad_run))["error"] == "ticket_run_mismatch"
    missing = ticket_line(_GRAPH_ID, _RUN_ID, "n_nope")
    assert (await read_node_context(missing))["error"] == "ticket_node_not_found"
    wrong_member = await generate_node_output(_ticket("n_brief"), member="character", prompt="x")
    assert wrong_member["success"] is False
    assert wrong_member["error"] == "ticket_member_mismatch"


async def test_no_active_run():
    result = await read_node_context(ticket_line("g_unbound", _RUN_ID, "n1"))
    assert result["error"] == "no_active_run"


async def test_read_node_context_packet(env):
    packet = await read_node_context(_ticket("n_brief"))
    assert packet["node"]["id"] == "n_brief"
    assert packet["node"]["output_kind"] == "text"
    assert packet["approved_text"] == "APPROVED BRIEF"
    assert packet["locks"]["style_lock"] == "ink wash"
    assert packet["prompt_limit"] is None
    hero = await read_node_context(_ticket("n_hero"))
    assert hero["node"]["output_kind"] == "image"
    assert hero["prompt_limit"]["kind"] == "image"


async def test_generate_then_submit_media(env, handler):
    gen = await generate_node_output(
        _ticket("n_hero"), member="character", prompt="hero in rain", subject="a girl"
    )
    assert gen["success"] is True, gen
    assert gen["image_uri"].endswith("n_hero.png")
    assert gen["prompt_source"] == "host_composed"
    assert handler.seen_prompts == ["a girl\nhero in rain"]
    hero = next(n for n in env.graph["nodes"] if n["id"] == "n_hero")
    assert hero["config"]["prompt"] == "draw the hero"
    assert hero["config"]["last_wan_prompt"].startswith("locked:")

    sub = await submit_node_output(_ticket("n_hero"), uri=gen["image_uri"], text="hero ready")
    assert sub["success"] is True and sub["status"] == "completed"
    state = env.run["node_states"]["n_hero"]
    assert state["output_ref"]["uri"] == gen["image_uri"]
    assert state["text"] == "hero ready"
    assert env.bridge.produced_for("n_hero")["output_ref"]["uri"] == gen["image_uri"]


async def test_submit_text_uses_generated_file(env, handler):
    gen = await generate_node_output(_ticket("n_brief"), member="brief", prompt="tea ad")
    assert gen["success"] is True and gen["prompt_source"] == "argument"
    sub = await submit_node_output(_ticket("n_brief"), text="ignored summary")
    assert sub["success"] is True
    assert env.run["node_states"]["n_brief"]["text"] == "BRIEF FROM tea ad"


async def test_submit_requires_own_generation(env, handler, tmp_path: Path):
    assert (await submit_node_output(_ticket("n_hero")))["error"] == "not_generated"
    await generate_node_output(_ticket("n_hero"), member="character", prompt="p")
    other = tmp_path / "elsewhere.png"
    other.write_bytes(b"\x89PNG")
    rejected = await submit_node_output(_ticket("n_hero"), uri=other.as_uri())
    assert rejected["error"] == "uri_not_generated_by_this_node"
    assert "output_ref" not in env.run["node_states"].get("n_hero", {})


async def test_generation_failure_is_recorded(env, monkeypatch, tmp_path: Path):
    failing = _FakeHandler(tmp_path, fail=True)
    monkeypatch.setattr(
        "jiuwenswarm.server.runtime.designer.handlers.get_node_handler", lambda _node: failing
    )
    gen = await generate_node_output(_ticket("n_hero"), member="character", prompt="p")
    assert gen["success"] is False
    assert gen["error"].startswith("generation_failed")
    assert "model down" in env.bridge.generation_failure_for("n_hero")


# ── media guarantee: member-call recovery ─────────────────────────


class _RaisingInner:
    async def run(self, prompt, opts, schema_json, *, call_key=None):
        raise RuntimeError("worker ended without structured_output")


class _ReceiptInner:
    async def run(self, prompt, opts, schema_json, *, call_key=None):
        return AgentResult(text="ok", structured={"output_ref": {"kind": "text", "uri": "x"}})


def _guarantee(env: NodeRunEnv, inner: Any) -> MediaGuaranteeBackend:
    return MediaGuaranteeBackend(
        inner, graph=env.graph, run=env.run, bridge=env.bridge, media_root=env.media_root
    )


async def test_recover_receipt_from_submit(env, handler):
    gen = await generate_node_output(_ticket("n_hero"), member="character", prompt="p")
    await submit_node_output(_ticket("n_hero"), uri=gen["image_uri"])
    result = await _guarantee(env, _RaisingInner()).run(
        "p", {"label": "n_hero"}, NODE_OUTPUT_SCHEMA
    )
    assert result.structured["output_ref"]["uri"] == gen["image_uri"]


async def test_failed_generation_fails_node_without_retry(env, monkeypatch, tmp_path: Path):
    failing = _FakeHandler(tmp_path, fail=True)
    monkeypatch.setattr(
        "jiuwenswarm.server.runtime.designer.handlers.get_node_handler", lambda _node: failing
    )
    await generate_node_output(_ticket("n_hero"), member="character", prompt="p")
    result = await _guarantee(env, _RaisingInner()).run(
        "p", {"label": "n_hero"}, NODE_OUTPUT_SCHEMA
    )
    assert result.skipped is True
    assert env.run["node_states"]["n_hero"]["status"] == "failed"


async def test_unrelated_worker_error_reraises(env):
    with pytest.raises(RuntimeError):
        await _guarantee(env, _RaisingInner()).run("p", {"label": "n_hero"}, NODE_OUTPUT_SCHEMA)


async def test_text_member_without_submit_fails(env):
    result = await _guarantee(env, _ReceiptInner()).run(
        "p", {"label": "n_brief"}, NODE_OUTPUT_SCHEMA
    )
    assert result.skipped is True
    state = env.run["node_states"]["n_brief"]
    assert state["status"] == "failed"
    assert "submit_node_output" in state["error"]


def test_module_exports():
    assert set(node_tools.MEMBER_OUTPUT_KIND) == {
        "brief", "storyboard", "character", "scene", "clip", "compose",
    }
