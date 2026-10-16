from __future__ import annotations

from pathlib import Path

import pytest

import designswarm.host as design_host_module
import jiuwenswarm.common.utils as utils
from designswarm.common.schema.agent import AgentResponse as DesignAgentResponse
from designswarm.common.schema.message import ReqMethod as DesignReqMethod
from designswarm.server.runtime.design.team_bridge import (
    ensure_designer_agent_group_installed,
)
from jiuwenswarm.common.schema.agent import AgentRequest
from jiuwenswarm.common.schema.message import ReqMethod
from jiuwenswarm.design_host import (
    DESIGNER_AGENT_GROUP,
    JiuwenswarmDesignHost,
    install_design_host,
)
from jiuwenswarm.server.runtime import extension_package_manager as catalog
from jiuwenswarm.server.runtime.gateway_adapter import designer_adapter


@pytest.fixture
def jiuwenswarm_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(utils, "_workspace_base_dir", tmp_path / ".jiuwenswarm")
    monkeypatch.setattr(design_host_module, "_host", None)
    return utils.get_user_workspace_dir()


@pytest.fixture
def host(jiuwenswarm_home: Path) -> JiuwenswarmDesignHost:
    return install_design_host()


def _built_in_designer() -> Path:
    return catalog._built_in_root(catalog._AGENT_GROUP_KIND) / DESIGNER_AGENT_GROUP


def test_entry_point_resolves_the_jiuwenswarm_host(jiuwenswarm_home: Path) -> None:
    assert isinstance(design_host_module.get_host(), JiuwenswarmDesignHost)


def test_host_storage_layout_is_the_jiuwenswarm_layout(host: JiuwenswarmDesignHost) -> None:
    assert host.user_workspace_dir() == utils.get_user_workspace_dir()
    assert host.agent_root_dir() == utils.get_agent_root_dir()
    assert host.agent_sessions_dir() == utils.get_agent_sessions_dir()
    assert host.agent_workspace_dir() == utils.get_agent_workspace_dir()
    assert host.default_project_session_workspace_dir("s1") == (
        utils.get_default_project_session_workspace_dir("s1")
    )
    assert host.env_file() == utils.get_env_file()


def test_host_session_and_project_seams_are_jiuwenswarm_modules(
    host: JiuwenswarmDesignHost,
) -> None:
    from designswarm.server.runtime.session import project_store as design_project_store

    from jiuwenswarm.server.runtime.session import project_store, session_history, session_metadata

    assert host.project_store() is project_store
    assert host.session_metadata() is session_metadata
    assert host.session_history() is session_history
    assert design_project_store.list_projects is project_store.list_projects


@pytest.mark.asyncio
async def test_host_push_goes_through_the_agent_websocket_server(
    host: JiuwenswarmDesignHost, monkeypatch: pytest.MonkeyPatch
) -> None:
    from jiuwenswarm.server.agent_ws_server import AgentWebSocketServer

    sent: list[dict] = []

    class _Server:
        async def send_push(self, message: dict) -> bool:
            sent.append(message)
            return True

    monkeypatch.setattr(AgentWebSocketServer, "get_instance", classmethod(lambda cls: _Server()))

    await host.send_push({"session_id": "s1", "payload": {"event_type": "designer.run.updated"}})

    assert sent == [{"session_id": "s1", "payload": {"event_type": "designer.run.updated"}}]


def test_designer_group_installs_from_the_core_package(host: JiuwenswarmDesignHost) -> None:
    host.install_agent_group({"id": DESIGNER_AGENT_GROUP})

    installed = _built_in_designer()
    core_package = host.agent_groups_resources_dir() / DESIGNER_AGENT_GROUP
    assert (installed / "manifest.json").read_text(encoding="utf-8") == (
        core_package / "manifest.json"
    ).read_text(encoding="utf-8")
    assert not list(installed.rglob("__pycache__"))
    assert host.resolve_agent_group_dir(DESIGNER_AGENT_GROUP) == installed.resolve()
    assert catalog.resolve_agent_group_dir(DESIGNER_AGENT_GROUP) == installed.resolve()


def test_pre_designswarm_designer_copy_is_refreshed(host: JiuwenswarmDesignHost) -> None:
    host.install_agent_group({"id": DESIGNER_AGENT_GROUP})
    stale_tool = _built_in_designer() / "tools" / "legacy_tool.py"
    stale_tool.parent.mkdir(parents=True, exist_ok=True)
    stale_tool.write_text(
        "from jiuwenswarm.server.runtime.designer.graph_store import DesignerGraphStore\n",
        encoding="utf-8",
    )
    fresh_host = JiuwenswarmDesignHost()
    design_host_module.set_host(fresh_host)

    with pytest.raises(ValueError, match="predates designswarm-core"):
        fresh_host.resolve_agent_group_dir(DESIGNER_AGENT_GROUP)

    ensure_designer_agent_group_installed()

    assert not stale_tool.exists()
    assert fresh_host.resolve_agent_group_dir(DESIGNER_AGENT_GROUP) == (
        _built_in_designer().resolve()
    )


def test_adapter_maps_requests_field_for_field() -> None:
    request = AgentRequest(
        request_id="r1",
        channel_id="web",
        session_id="s1",
        chat_id="c1",
        req_method=ReqMethod.DESIGNER_GRAPH_GET,
        params={"graph_id": "g1"},
        is_stream=False,
        timestamp=12.5,
        metadata={"k": "v"},
        user_id="u1",
    )

    mapped = designer_adapter.to_design_request(request)

    assert mapped.req_method is DesignReqMethod.DESIGNER_GRAPH_GET
    assert (mapped.request_id, mapped.channel_id, mapped.session_id, mapped.chat_id) == (
        "r1",
        "web",
        "s1",
        "c1",
    )
    assert mapped.params == {"graph_id": "g1"}
    assert (mapped.timestamp, mapped.metadata, mapped.user_id) == (12.5, {"k": "v"}, "u1")


def test_adapter_methods_are_jiuwenswarm_methods_served_by_the_core() -> None:
    jiuwenswarm_methods = {method.value for method in ReqMethod}
    core_methods = designer_adapter._core.DesignerAdapter.methods

    assert designer_adapter.DesignerAdapter.methods == core_methods
    assert ReqMethod.DESIGNER_WORKSPACE_CREATE.value in core_methods
    assert core_methods <= jiuwenswarm_methods


@pytest.mark.asyncio
async def test_adapter_delegates_to_the_core(
    host: JiuwenswarmDesignHost, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = []

    async def core_handle(self, request):
        seen.append(request)
        return DesignAgentResponse(
            request_id=request.request_id,
            channel_id=request.channel_id,
            ok=True,
            payload={"graph": {"graph_id": "g1"}},
            metadata=request.metadata,
        )

    monkeypatch.setattr(designer_adapter._core.DesignerAdapter, "handle", core_handle)
    request = AgentRequest(
        request_id="r1",
        channel_id="web",
        req_method=ReqMethod.DESIGNER_GRAPH_GET,
        params={"graph_id": "g1"},
        agent_ref="ref",
    )

    response = await designer_adapter.DesignerAdapter().handle(request)

    assert seen[0].req_method is DesignReqMethod.DESIGNER_GRAPH_GET
    assert response.ok is True
    assert response.payload == {"graph": {"graph_id": "g1"}}
    assert response.agent_ref == "ref"


@pytest.mark.asyncio
async def test_adapter_rejects_non_designer_methods(host: JiuwenswarmDesignHost) -> None:
    request = AgentRequest(request_id="r1", channel_id="web", req_method=ReqMethod.CHAT_SEND)

    response = await designer_adapter.DesignerAdapter().handle(request)

    assert response.ok is False
    assert response.payload["code"] == "NOT_IMPLEMENTED"
