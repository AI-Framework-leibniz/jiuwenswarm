# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Unbound design tasks must mount under virtual default_design, not empty id."""

from __future__ import annotations

from pathlib import Path

import pytest

from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.common.work_mode import DEFAULT_PROJECT_ID_DESIGN, DESIGN_WORK_MODE
from jiuwenswarm.server.runtime.gateway_adapter import designer_adapter as adapter


@pytest.fixture()
def design_roots(tmp_path, monkeypatch):
    root = tmp_path / "agent-root"
    sessions = root / "sessions"
    root.mkdir()
    sessions.mkdir()
    monkeypatch.setattr("jiuwenswarm.common.utils.get_agent_root_dir", lambda: root)
    monkeypatch.setattr("jiuwenswarm.common.utils.get_agent_sessions_dir", lambda: sessions)
    monkeypatch.setattr(adapter, "get_agent_root_dir", lambda: root)
    monkeypatch.setattr(adapter, "get_agent_sessions_dir", lambda: sessions)
    monkeypatch.setattr(
        "jiuwenswarm.server.runtime.session.session_metadata.get_agent_sessions_dir",
        lambda: sessions,
    )
    monkeypatch.setattr(
        "jiuwenswarm.server.runtime.designer.graph_store.get_agent_root_dir",
        lambda: root,
    )
    monkeypatch.setattr(
        adapter,
        "_design_team_workspace",
        lambda session_id: root / "teams" / session_id / "team-workspace",
    )
    return root, sessions


@pytest.mark.asyncio
async def test_create_workspace_without_project_returns_default_design(design_roots):
    request = AgentRequest(
        request_id="req-1",
        channel_id="web",
        req_method=ReqMethod.DESIGNER_WORKSPACE_CREATE,
        params={"prompt": "一只猫的旅行短片", "create_token": "tok-1"},
        user_id="u1",
    )
    payload, error, code = await adapter._create_design_workspace_once(request, request.params)
    assert error is None, error
    assert code is None
    assert payload is not None
    assert payload["project"]["project_id"] == DEFAULT_PROJECT_ID_DESIGN
    assert payload["session"]["project_id"] == DEFAULT_PROJECT_ID_DESIGN
    assert payload["project"]["project_dir"] == ""
    assert payload["session"]["session_id"].startswith("design_")
    # Same as 9989a5e (then "default"): persist the virtual mount id on disk.
    from jiuwenswarm.server.runtime.session.session_metadata import get_session_metadata

    meta = get_session_metadata(payload["session"]["session_id"])
    assert meta is not None
    assert meta.get("project_id") == DEFAULT_PROJECT_ID_DESIGN
    assert not str(meta.get("project_dir") or "").strip()
    assert meta.get("work_mode") == DESIGN_WORK_MODE


def test_resolve_design_task_dir_defaults_to_default_design(design_roots):
    project_id, name, refs_dir, leader_dir = adapter._resolve_design_task_dir({}, "design_abc")
    assert project_id == DEFAULT_PROJECT_ID_DESIGN
    assert name == "默认项目"
    assert Path(refs_dir).name == "refs"
    assert "team-workspace" in leader_dir.replace("\\", "/")


def test_get_design_workspace_accepts_default_design(design_roots, monkeypatch):
    session_id = "design_sess_1"
    graph = {
        "schema_version": "designer-execution-graph.v1",
        "graph_id": "g_1",
        "project_id": "",
        "title": "短片",
        "description": "prompt",
        "nodes": [],
        "edges": [],
        "metadata": {"session_id": session_id, "work_mode": DESIGN_WORK_MODE},
        "created_at": 1,
        "updated_at": 1,
    }
    sessions = [
        {
            "session_id": session_id,
            "title": "短片",
            "project_id": "",
            "work_mode": DESIGN_WORK_MODE,
            "created_at": 1.0,
        }
    ]
    monkeypatch.setattr(
        "jiuwenswarm.server.runtime.session.session_metadata.collect_all_sessions_metadata",
        lambda: sessions,
    )
    monkeypatch.setattr(adapter._store, "list_graphs", lambda: [graph])
    monkeypatch.setattr(adapter._store, "list_graphs_for_project", lambda _pid: [])
    monkeypatch.setattr(adapter._store, "get_latest_run_for_graph", lambda _gid: None)
    monkeypatch.setattr(adapter, "_design_workspace_messages", lambda _sid: [])
    monkeypatch.setattr(adapter, "_stamp_canvas_title", lambda g, _p: g.get("title") or "")

    payload, error, code = adapter._get_design_workspace(
        {"project_id": DEFAULT_PROJECT_ID_DESIGN, "session_id": session_id}
    )
    assert error is None, error
    assert code is None
    assert payload is not None
    assert payload["project"]["project_id"] == DEFAULT_PROJECT_ID_DESIGN
    assert payload["session"]["session_id"] == session_id


def test_public_design_project_payload_normalizes_unbound():
    assert adapter._public_design_project_payload(None)["project_id"] == DEFAULT_PROJECT_ID_DESIGN
