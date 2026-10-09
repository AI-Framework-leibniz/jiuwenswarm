from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.server.runtime.designer.handlers import common
from jiuwenswarm.server.runtime.designer import model_tools
from jiuwenswarm.server.runtime.gateway_adapter import designer_adapter
from jiuwenswarm.server.runtime.session.project_store import Project


def _workspace_payload(project_dir: str) -> dict:
    return {
        "project": {
            "project_id": "proj_design",
            "project_dir": project_dir,
            "name": "Design",
            "work_mode": "design",
        },
        "session": {
            "session_id": "design_session",
            "project_id": "proj_design",
            "project_dir": project_dir,
            "title": "Design",
            "work_mode": "design",
        },
        "graph": {
            "graph_id": "graph_design",
            "project_id": "proj_design",
            "nodes": [],
            "edges": [],
        },
        "messages": [],
    }


def test_pair_design_canvases_keeps_chat_canvases_separate():
    sessions = [
        {"session_id": "s1", "created_at": 1, "title": "One"},
        {"session_id": "s2", "created_at": 2, "title": "Two"},
    ]
    graphs = [
        {"graph_id": "g1", "updated_at": 10, "metadata": {"session_id": "s1"}},
        {"graph_id": "g1-old", "updated_at": 5, "metadata": {"session_id": "s1"}},
        {"graph_id": "g2", "updated_at": 30, "metadata": {"session_id": "s2"}},
    ]

    pairs = designer_adapter._pair_design_canvases(sessions, graphs)

    assert [
        (item["session"]["session_id"], item["graph"]["graph_id"]) for item in pairs
    ] == [("s1", "g1"), ("s2", "g2")]


def test_pair_design_canvases_adopts_a_legacy_graph():
    pairs = designer_adapter._pair_design_canvases(
        [{"session_id": "s1", "created_at": 1, "title": "Legacy"}],
        [{"graph_id": "g-legacy", "created_at": 4, "updated_at": 4, "metadata": {}}],
    )

    assert pairs[0]["graph"]["graph_id"] == "g-legacy"


def test_get_design_workspace_returns_only_the_requested_session(monkeypatch):
    project = Project(
        project_id="proj_design",
        name="Design",
        project_dir="D:/design",
        work_mode="design",
    )
    sessions = [
        {
            "session_id": "s1",
            "project_id": "proj_design",
            "work_mode": "design",
            "created_at": 1,
            "title": "One",
        },
        {
            "session_id": "s2",
            "project_id": "proj_design",
            "work_mode": "design",
            "created_at": 2,
            "title": "Two",
        },
    ]
    graphs = [
        {
            "graph_id": "g1",
            "project_id": "proj_design",
            "title": "One",
            "updated_at": 10,
            "nodes": [],
            "metadata": {"session_id": "s1"},
        },
        {
            "graph_id": "g2",
            "project_id": "proj_design",
            "title": "Two",
            "updated_at": 20,
            "nodes": [],
            "metadata": {"session_id": "s2"},
        },
    ]
    monkeypatch.setattr(
        designer_adapter.project_store,
        "get_project_by_id",
        lambda project_id, cache_bust=False: project if project_id == project.project_id else None,
    )
    monkeypatch.setattr(
        "jiuwenswarm.server.runtime.session.session_metadata.collect_all_sessions_metadata",
        lambda: sessions,
    )
    monkeypatch.setattr(designer_adapter._store, "list_graphs_for_project", lambda project_id: graphs)
    monkeypatch.setattr(designer_adapter._store, "get_latest_run_for_graph", lambda graph_id: None)
    monkeypatch.setattr(
        designer_adapter,
        "_design_workspace_messages",
        lambda session_id: [{"id": session_id, "content": session_id}],
    )

    payload, error, code = designer_adapter._get_design_workspace(
        {"project_id": "proj_design", "session_id": "s2"}
    )

    assert error is None
    assert code is None
    assert payload is not None
    assert payload["session"]["session_id"] == "s2"
    assert payload["graph"]["graph_id"] == "g2"
    assert payload["messages"] == [{"id": "s2", "content": "s2"}]
    assert [item["session_id"] for item in payload["sessions"]] == ["s1", "s2"]


def test_default_project_can_host_a_design_canvas(monkeypatch):
    sessions = [
        {
            "session_id": "design_default",
            "project_id": "default",
            "work_mode": "design",
            "created_at": 1,
            "title": "画布 1",
        }
    ]
    graphs = [
        {
            "graph_id": "g-default",
            "project_id": "default",
            "title": "画布 1",
            "updated_at": 10,
            "nodes": [],
            "metadata": {"session_id": "design_default"},
        }
    ]
    monkeypatch.setattr(
        designer_adapter.project_store,
        "get_project_by_id",
        lambda project_id, cache_bust=False: None,
    )
    monkeypatch.setattr(
        "jiuwenswarm.server.runtime.session.session_metadata.collect_all_sessions_metadata",
        lambda: sessions,
    )
    monkeypatch.setattr(
        designer_adapter._store,
        "list_graphs_for_project",
        lambda project_id: graphs if project_id == "default" else [],
    )
    monkeypatch.setattr(designer_adapter._store, "get_latest_run_for_graph", lambda graph_id: None)
    monkeypatch.setattr(designer_adapter, "_design_workspace_messages", lambda session_id: [])

    payload, error, code = designer_adapter._get_design_workspace(
        {"project_id": "default", "session_id": "design_default"}
    )

    assert error is None
    assert code is None
    assert payload is not None
    assert payload["project"]["project_id"] == "default"
    assert payload["session"]["session_id"] == "design_default"
    assert payload["graph"]["graph_id"] == "g-default"


def test_default_session_rehomes_a_graph_saved_under_another_project(monkeypatch):
    sessions = [
        {
            "session_id": "design_default",
            "project_id": "default",
            "work_mode": "design",
            "created_at": 1,
            "title": "晨光咖啡",
        }
    ]
    foreign = {
        "graph_id": "g-foreign",
        "project_id": "proj_stray",
        "title": "晨光咖啡",
        "updated_at": 10,
        "nodes": [{"id": "n1"}],
        "metadata": {"session_id": "design_default"},
    }
    saved: list[dict] = []
    hidden: list[str] = []
    stray = Project(
        project_id="proj_stray",
        name="stray",
        project_dir="",
        work_mode="design",
    )

    monkeypatch.setattr(
        designer_adapter.project_store,
        "get_project_by_id",
        lambda project_id, cache_bust=False: stray if project_id == "proj_stray" else None,
    )
    monkeypatch.setattr(
        designer_adapter.project_store,
        "hide_project",
        lambda project_id: hidden.append(project_id),
    )
    monkeypatch.setattr(
        "jiuwenswarm.server.runtime.session.session_metadata.collect_all_sessions_metadata",
        lambda: sessions,
    )
    monkeypatch.setattr(
        designer_adapter._store,
        "list_graphs_for_project",
        lambda project_id: [],
    )
    monkeypatch.setattr(designer_adapter._store, "list_graphs", lambda: [foreign])
    monkeypatch.setattr(
        designer_adapter._store,
        "save_graph",
        lambda graph: saved.append(dict(graph)) or dict(graph),
    )
    monkeypatch.setattr(designer_adapter._store, "get_latest_run_for_graph", lambda graph_id: None)
    monkeypatch.setattr(designer_adapter, "_design_workspace_messages", lambda session_id: [])

    payload, error, code = designer_adapter._get_design_workspace(
        {"project_id": "default", "session_id": "design_default"}
    )

    assert error is None
    assert code is None
    assert payload is not None
    assert payload["graph"]["graph_id"] == "g-foreign"
    assert payload["graph"]["project_id"] == "default"
    assert saved and saved[0]["project_id"] == "default"
    assert hidden == ["proj_stray"]


def test_project_assets_are_shared_and_skip_text():
    assets = designer_adapter._graph_media_assets(
        {
            "graph_id": "g1",
            "metadata": {
                "user_references": [
                    {"kind": "image", "uri": "file:///a.png", "filename": "a.png"},
                ]
            },
            "nodes": [
                {
                    "id": "n1",
                    "config": {},
                    "output_ref": {
                        "kind": "text",
                        "uri": "file:///brief.md",
                        "mime_type": "text/markdown",
                        "label": "brief.md",
                    },
                },
                {
                    "id": "n2",
                    "config": {},
                    "output_ref": {
                        "kind": "video",
                        "uri": "file:///clip.mp4",
                        "label": "clip",
                    },
                },
            ],
        },
        None,
        "s1",
    )

    uris = [item["uri"] for item in assets]
    assert uris == ["file:///a.png", "file:///clip.mp4"]
    assert all(item["session_id"] == "s1" for item in assets)


def test_graph_workspace_uses_authoritative_project_directory(tmp_path, monkeypatch):
    root = tmp_path / "agent"
    project_dir = root / "workspace" / "design" / "managed-project"
    project_dir.mkdir(parents=True)
    project = Project(
        project_id="proj_design",
        name="Design",
        project_dir=str(project_dir),
        work_mode="design",
    )
    monkeypatch.setattr(common, "get_agent_root_dir", lambda: root)
    monkeypatch.setattr(
        common.project_store,
        "get_project_by_id",
        lambda project_id, cache_bust=False: project if project_id == project.project_id else None,
    )

    directory = common.graph_workspace_dir(
        {
            "project_id": project.project_id,
            "metadata": {"project_dir": str(tmp_path / "attacker-controlled")},
        }
    )

    assert directory == project_dir / "assets"
    assert directory.is_dir()


def test_graph_workspace_rejects_design_project_outside_managed_root(tmp_path, monkeypatch):
    root = tmp_path / "agent"
    project = Project(
        project_id="proj_design",
        name="Design",
        project_dir=str(tmp_path / "outside"),
        work_mode="design",
    )
    monkeypatch.setattr(common, "get_agent_root_dir", lambda: root)
    monkeypatch.setattr(
        common.project_store,
        "get_project_by_id",
        lambda project_id, cache_bust=False: project,
    )

    with pytest.raises(ValueError, match="outside the managed root"):
        common.graph_workspace_dir({"project_id": project.project_id})


@pytest.mark.asyncio
async def test_workspace_create_token_is_serialized_and_reused(tmp_path, monkeypatch):
    payload = _workspace_payload(str(tmp_path / "workspace"))
    create_count = 0

    async def create_once(request, params):
        nonlocal create_count
        create_count += 1
        await asyncio.sleep(0.05)
        return payload, None, None

    monkeypatch.setattr(designer_adapter, "get_agent_root_dir", lambda: tmp_path)
    monkeypatch.setattr(designer_adapter, "_create_design_workspace_once", create_once)
    monkeypatch.setattr(
        designer_adapter,
        "_get_design_workspace",
        lambda params: (payload, None, None),
    )
    request = AgentRequest(request_id="request", channel_id="web")
    params = {
        "prompt": "Build a storyboard",
        "create_token": "stable-token",
        "model_name": "selected-model",
    }

    first, second = await asyncio.gather(
        designer_adapter._create_design_workspace(request, params),
        designer_adapter._create_design_workspace(request, params),
    )

    assert create_count == 1
    assert first == second == (payload, None, None)


@pytest.mark.asyncio
async def test_receipt_failure_rolls_back_committed_workspace(tmp_path, monkeypatch):
    payload = _workspace_payload(str(tmp_path / "workspace"))
    rollbacks: list[dict] = []

    async def create_once(request, params):
        return payload, None, None

    def fail_receipt(token, signature, workspace):
        raise OSError("disk full")

    monkeypatch.setattr(designer_adapter, "get_agent_root_dir", lambda: tmp_path)
    monkeypatch.setattr(designer_adapter, "_create_design_workspace_once", create_once)
    monkeypatch.setattr(designer_adapter, "_write_workspace_receipt", fail_receipt)
    monkeypatch.setattr(
        designer_adapter,
        "_rollback_design_workspace",
        lambda **kwargs: rollbacks.append(kwargs),
    )
    request = AgentRequest(request_id="request", channel_id="web")

    result = await designer_adapter._create_design_workspace(
        request,
        {"prompt": "Build a storyboard", "create_token": "receipt-failure"},
    )

    assert result[0] is None
    assert result[2] == "INTERNAL_ERROR"
    assert "disk full" in str(result[1])
    assert rollbacks == [
        {
            "project_id": "proj_design",
            "project_dir": str(tmp_path / "workspace"),
            "session_id": "design_session",
            "graph_id": "graph_design",
        }
    ]


@pytest.mark.asyncio
async def test_selected_model_context_reaches_designer_model_calls(monkeypatch):
    for key in ("API_KEY", "OPENAI_API_KEY", "API_BASE", "OPENAI_API_BASE"):
        monkeypatch.setenv(key, "")
    monkeypatch.setattr(
        model_tools,
        "list_configured_models",
        lambda: [
            {
                "id": "selected-model",
                "model_name": "selected-model",
                "api_base": "",
                "index": 0,
            },
            {
                "id": "default-model",
                "model_name": "default-model",
                "api_base": "",
                "index": 1,
            },
        ],
    )
    monkeypatch.setattr(model_tools, "get_config", lambda: {})

    with model_tools.use_preferred_designer_model("selected-model"):
        result = await model_tools.call_model_tool(
            prompt="prompt",
            system="system",
        )

    assert result["model"] == "selected-model"
    assert result["model_name"] == "selected-model"


@pytest.mark.asyncio
async def test_chat_auto_run_failure_is_returned_in_summary(monkeypatch):
    graph = {
        "graph_id": "graph_design",
        "project_id": "proj_design",
        "metadata": {},
        "nodes": [],
        "edges": [],
    }

    async def fake_leader_chat(*args, **kwargs):
        return {
            "graph": graph,
            "changed": False,
            "summary": "Updated workflow",
            "run_node_ids": ["node_1"],
        }

    from jiuwenswarm.server.runtime.designer import leader_chat as leader_chat_module

    monkeypatch.setattr(leader_chat_module, "run_leader_chat", fake_leader_chat)
    monkeypatch.setattr(
        "jiuwenswarm.server.runtime.designer.model_tools.require_llm",
        lambda: None,
    )
    monkeypatch.setattr(designer_adapter._store, "get_graph", lambda graph_id: graph)
    monkeypatch.setattr(
        designer_adapter._executor,
        "reconcile_loaded_graph",
        lambda loaded: loaded,
    )
    monkeypatch.setattr(
        designer_adapter,
        "_start_run",
        lambda params: (None, "unable to start", "INTERNAL_ERROR"),
    )
    request = AgentRequest(request_id="request", channel_id="web")

    payload, error, code = await designer_adapter._chat_graph(
        request,
        {"graph_id": graph["graph_id"], "message": "Update it"},
    )

    assert error is None
    assert code is None
    assert payload is not None
    assert payload["summary"] == "Updated workflow (unable to start)"


def test_bootstrap_rejects_project_dir_outside_the_design_root(tmp_path, monkeypatch):
    managed = tmp_path / "agent"
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    monkeypatch.setattr(designer_adapter, "get_agent_root_dir", lambda: managed)
    design_root = managed / "workspace" / "design"
    design_root.mkdir(parents=True)
    good = design_root / "my-film"
    good.mkdir()

    assert designer_adapter._is_managed_design_project_dir(str(good)) is True
    assert designer_adapter._is_managed_design_project_dir(str(design_root)) is False
    assert designer_adapter._is_managed_design_project_dir(str(outside)) is False
    assert designer_adapter._is_managed_design_project_dir("/tmp") is False

    created: list[str] = []
    monkeypatch.setattr(
        designer_adapter.project_store,
        "create_project_checked",
        lambda name, project_dir, work_mode: created.append(project_dir)
        or (SimpleNamespace(project_id="p1", project_dir=project_dir, work_mode=work_mode), False),
    )
    payload, error, code = designer_adapter._bootstrap_graph(
        {"prompt": "a film", "project_dir": str(outside), "work_mode": "design"},
        "web",
        {"source": "llm"},
    )

    assert payload is None
    assert code == "BAD_REQUEST"
    assert "managed workspace" in str(error)
    assert created == []


def test_canvas_title_uses_model_phrase_not_the_prompt():
    from jiuwenswarm.server.runtime.designer.node_labels import usable_story_title

    prompt = "帮我做一支雨夜里侦探追凶的短片，要有三个镜头和结尾反转"
    assert usable_story_title("雨夜追凶", prompt) == "雨夜追凶"
    assert usable_story_title(prompt, prompt) == ""
    assert usable_story_title(prompt[:40], prompt) == ""

    graph = {
        "title": prompt[:80],
        "metadata": {"script_analysis": {"story_name": "雨夜追凶"}},
    }
    assert designer_adapter._stamp_canvas_title(graph, prompt) == "雨夜追凶"
    assert graph["title"] == "雨夜追凶"

    echoed = {"title": prompt[:80], "metadata": {"script_analysis": {"story_name": prompt}}}
    assert designer_adapter._stamp_canvas_title(echoed, prompt) == ""
    assert echoed["title"] == "设计项目"
    assert designer_adapter._replacement_display_title(
        "AT10 第3镜首次生成",
        prompt,
        "雨夜追凶",
    ) == ""
    assert designer_adapter._replacement_display_title(prompt, prompt, "雨夜追凶") == "雨夜追凶"
    assert designer_adapter._replacement_display_title("A" * 50, "", "雨夜追凶") == "雨夜追凶"
    assert designer_adapter._replacement_display_title("AT10", "", "雨夜追凶") == ""


def test_design_references_and_assets_use_session_uploads(tmp_path, monkeypatch):
    sessions = tmp_path / "agent" / "sessions"
    monkeypatch.setattr(
        "jiuwenswarm.server.runtime.attachments.media_attachments.get_agent_sessions_dir",
        lambda: sessions,
    )
    refs = designer_adapter._design_reference_dir("design_abc", str(tmp_path / "unused"))
    assert refs == sessions / "design_abc" / "uploads"
    assert refs.is_dir()
    assert designer_adapter._design_reference_dir("", str(tmp_path / "proj")) == (
        tmp_path / "proj" / ".designer" / "refs"
    )

    upload = sessions / "design_abc" / "uploads"
    (upload / "still.png").write_bytes(b"png")
    (upload / "notes.txt").write_bytes(b"skip")
    assets: list[dict] = []
    seen: set[str] = set()
    designer_adapter._append_session_upload_assets("design_abc", assets, seen)
    assert len(assets) == 1
    assert assets[0]["filename"] == "still.png"
    assert assets[0]["kind"] == "image"
    assert assets[0]["session_id"] == "design_abc"
    assert assets[0]["source"] == "uploaded"
