"""Gateway adapter for the ``designer.*`` RPCs, served by designswarm-core.

The workspace, graph CRUD and run triggers live in
``designswarm.server.runtime.gateway_adapter.designer_adapter``. This adapter
maps the jiuwenswarm envelopes onto the core's field-for-field and back.
"""

from __future__ import annotations

from typing import Any

from designswarm.common.schema.agent import AgentRequest as DesignAgentRequest
from designswarm.common.schema.message import ReqMethod as DesignReqMethod
from designswarm.server.runtime.gateway_adapter import designer_adapter as _core

from jiuwenswarm.common.schema.agent import AgentRequest, AgentResponse
from jiuwenswarm.design_host import install_design_host
from jiuwenswarm.server.runtime.gateway_adapter.base import GatewayAdapter

DESIGNER_AGENT_GROUP = _core.DESIGNER_AGENT_GROUP
sync_design_display_name = _core.sync_design_display_name
sync_design_display_names = _core.sync_design_display_names
hydrate_graph_node_outputs = _core.hydrate_graph_node_outputs


def _method_value(method: Any) -> str | None:
    if method is None:
        return None
    return str(getattr(method, "value", method))


def to_design_request(request: AgentRequest) -> DesignAgentRequest:
    method = _method_value(request.req_method)
    return DesignAgentRequest(
        request_id=request.request_id,
        channel_id=request.channel_id,
        session_id=request.session_id,
        chat_id=request.chat_id,
        req_method=DesignReqMethod(method) if method else None,
        params=request.params,
        is_stream=request.is_stream,
        timestamp=request.timestamp,
        metadata=request.metadata,
        user_id=request.user_id,
    )


def from_design_response(response: Any, request: AgentRequest) -> AgentResponse:
    return AgentResponse(
        request_id=response.request_id,
        channel_id=response.channel_id,
        ok=response.ok,
        payload=response.payload,
        metadata=response.metadata,
        agent_ref=request.agent_ref,
    )


class DesignerAdapter(GatewayAdapter):
    """Designer execution graph adapter (designswarm-core)."""

    methods: frozenset[str] = _core.DesignerAdapter.methods

    def __init__(self) -> None:
        install_design_host()
        self._core = _core.DesignerAdapter()

    async def handle(self, request: AgentRequest) -> AgentResponse:
        method = _method_value(request.req_method)
        if method not in self.methods:
            return AgentResponse(
                request_id=request.request_id,
                channel_id=request.channel_id,
                ok=False,
                payload={"error": f"unsupported method: {method}", "code": "NOT_IMPLEMENTED"},
                metadata=request.metadata,
                agent_ref=request.agent_ref,
            )
        response = await self._core.handle(to_design_request(request))
        return from_design_response(response, request)


__all__ = [
    "DESIGNER_AGENT_GROUP",
    "DesignerAdapter",
    "from_design_response",
    "hydrate_graph_node_outputs",
    "sync_design_display_name",
    "sync_design_display_names",
    "to_design_request",
]
