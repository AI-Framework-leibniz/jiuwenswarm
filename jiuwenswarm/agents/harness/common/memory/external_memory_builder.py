# Copyright (c) Huawei Technologies Co., Ltd. 2025. All rights reserved.

"""Builder for ExternalMemoryRail — single entry point, config-driven.

Dispatches on `memory.external.provider`:
  - openjiuwen  -> OpenJiuwenMemoryProvider (builds its own KV/Vector/DB from config)
  - mem0        -> Mem0MemoryProvider
  - openviking  -> OpenVikingMemoryProvider
  - <plugin>    -> user-installed plugin from ~/.jiuwenswarm/plugins/memory/
  - ""          -> disabled (returns None)

Any failure returns None — the main flow is never blocked.
"""

import logging
import os
from typing import Any, Dict, Optional

from .external_memory_config import (
    build_openjiuwen_provider_config,
    get_external_memory_config,
)

logger = logging.getLogger(__name__)

_BUILTIN_PROVIDERS = {"openjiuwen", "mem0", "openviking", "officeace_cloud"}


def build_external_memory_rail(
    config: Optional[Dict[str, Any]] = None,
    workspace_dir: str = ".",
    session_id: Optional[str] = None,
    runtime_config: Optional[Dict[str, str]] = None,
) -> Optional[Any]:
    """Build an ExternalMemoryRail from config, or None if disabled/failed.

    Args:
        config: Full config dict (memory.external.* selects the provider).
        workspace_dir: Agent workspace directory.
        session_id: Per-session id (thread↔session). Passed to the rail so
            provider.initialize uses the relay-claw session_id; officeace_cloud
            also uses it for the cloud memory session. Other providers ignore it.
        runtime_config: Per-session credentials (api_key/space_id/base_url) for
            officeace_cloud, supplied by relay-claw via chat.send params. Only
            the officeace_cloud builder reads these; other providers are unaffected.
    """
    try:
        from openjiuwen.harness.rails import ExternalMemoryRail
    except Exception as exc:
        logger.warning("[ExternalMemoryBuilder] ExternalMemoryRail import failed: %s", exc)
        return None

    ext_cfg = get_external_memory_config(config)
    provider_name = ext_cfg.get("provider", "")
    if not provider_name:
        return None

    provider = None
    try:
        if provider_name == "openjiuwen":
            provider = _build_openjiuwen_provider(ext_cfg, config)
        elif provider_name == "mem0":
            provider = _build_mem0_provider(ext_cfg)
        elif provider_name == "openviking":
            provider = _build_openviking_provider(ext_cfg)
        elif provider_name == "lakebase":
            provider = _build_lakebase_provider(ext_cfg)
        elif provider_name == "officeace_cloud":
            provider = _build_officeace_cloud_provider(ext_cfg, runtime_config=runtime_config)
        else:
            provider = _load_plugin_provider(provider_name, ext_cfg.get("allowed_plugins") or None)
    except Exception as exc:
        logger.warning(
            "[ExternalMemoryBuilder] build provider '%s' failed: %s",
            provider_name, exc,
        )
        return None

    if provider is None:
        return None

    # Only officeace_cloud consumes the per-session session_id (for its cloud
    # memory session). Other providers (openjiuwen/mem0/openviking/lakebase)
    # must keep their original "__default__" session_id — passing a real
    # session id would change how they tag/scope stored messages, breaking
    # the "do not affect other providers" requirement.
    if provider_name == "officeace_cloud" and session_id:
        rail_session_id = session_id
    else:
        rail_session_id = "__default__"

    try:
        rail = ExternalMemoryRail(
            provider,
            user_id=ext_cfg.get("user_id", "__default__"),
            scope_id=ext_cfg.get("scope_id", "__default__"),
            session_id=rail_session_id,
        )
        logger.info(
            "[ExternalMemoryBuilder] ExternalMemoryRail built (provider=%s, session_id=%s)",
            provider_name,
            (rail_session_id or "default"),
        )
        return rail
    except Exception as exc:
        logger.warning("[ExternalMemoryBuilder] rail construction failed: %s", exc)
        return None


def _build_openjiuwen_provider(ext_cfg: Dict[str, Any], full_config: Optional[Dict[str, Any]] = None):
    from openjiuwen.core.memory.external.openjiuwen_memory_provider import (
        OpenJiuwenMemoryProvider,
    )
    provider_config, scope_config = build_openjiuwen_provider_config(ext_cfg, full_config)
    return OpenJiuwenMemoryProvider(config=provider_config, scope_config=scope_config)


def _build_mem0_provider(ext_cfg: Dict[str, Any]):
    from openjiuwen.core.memory.external.mem0_provider import Mem0MemoryProvider

    mem0_cfg = ext_cfg.get("mem0") or {}
    api_key = mem0_cfg.get("api_key") or os.environ.get("MEM0_API_KEY", "")
    user_id = mem0_cfg.get("user_id") or os.environ.get("MEM0_USER_ID", "jiuwenswarm-user")
    agent_id = mem0_cfg.get("agent_id") or os.environ.get("MEM0_AGENT_ID", "jiuwenswarm")
    rerank = bool(mem0_cfg.get("rerank", True))

    provider = Mem0MemoryProvider(
        api_key=api_key,
        user_id=user_id,
        agent_id=agent_id,
        rerank=rerank,
    )
    if not provider.is_available():
        logger.warning("[ExternalMemoryBuilder] Mem0 unavailable (no API key)")
        return None
    return provider


def _build_openviking_provider(ext_cfg: Dict[str, Any]):
    from openjiuwen.core.memory.external.openviking_memory_provider import (
        OpenVikingMemoryProvider,
    )

    vk_cfg = ext_cfg.get("openviking") or {}
    endpoint = vk_cfg.get("endpoint") or os.environ.get("OPENVIKING_ENDPOINT", "")
    api_key = vk_cfg.get("api_key") or os.environ.get("OPENVIKING_API_KEY", "")
    account = vk_cfg.get("account") or os.environ.get("OPENVIKING_ACCOUNT", "root")
    user = vk_cfg.get("user") or os.environ.get("OPENVIKING_USER", "default")

    provider = OpenVikingMemoryProvider(
        endpoint=endpoint,
        api_key=api_key,
        account=account,
        user=user,
    )
    if not provider.is_available():
        logger.warning("[ExternalMemoryBuilder] OpenViking unavailable (no endpoint)")
        return None
    return provider


def _build_lakebase_provider(ext_cfg: Dict[str, Any]):
    """Build LakeBase (DBay) external memory provider.

    LakeBase provides:
    - Semantic memory storage and retrieval via pgvector
    - Multiple memory types (fact, episode, procedural, etc.)
    - Trait extraction via digest API
    - Multi-workspace support via base switching

    Config shape (memory.external.lakebase):
        api_key: str       # LakeBase API key (required)
        base_url: str      # LakeBase API endpoint (default: localhost:8080)
        base_id: str       # Memory base ID (workspace)
        database_id: str   # Database ID for branching
        timeout: float     # HTTP request timeout
    """
    from openjiuwen.core.memory.external.lakebase_memory_provider import (
        LakeBaseMemoryProvider,
    )

    lb_cfg = ext_cfg.get("lakebase") or {}
    api_key = lb_cfg.get("api_key") or os.environ.get("LAKEBASE_API_KEY", "")
    base_url = lb_cfg.get("base_url") or os.environ.get(
        "LAKEBASE_API_URL", "http://localhost:8080/api/v1"
    )
    base_id = lb_cfg.get("base_id") or os.environ.get("LAKEBASE_MEM_BASE_ID", "mem_default")
    database_id = lb_cfg.get("database_id") or os.environ.get(
        "LAKEBASE_DATABASE_ID", "db_agent_memory"
    )
    timeout = float(lb_cfg.get("timeout") or 60.0)

    if not api_key:
        logger.warning("[ExternalMemoryBuilder] LakeBase unavailable (no api_key)")
        return None

    provider = LakeBaseMemoryProvider(
        api_key=api_key,
        base_url=base_url,
        base_id=base_id,
        database_id=database_id,
        timeout=timeout,
    )

    if not provider.is_available():
        logger.warning("[ExternalMemoryBuilder] LakeBase unavailable (config incomplete)")
        return None

    logger.info(
        "[ExternalMemoryBuilder] LakeBase provider built: base_url=%s, base_id=%s",
        base_url, base_id,
    )
    return provider


def _is_cloud_deployment() -> bool:
    """True if running in cloud deployment form.

    云端（``OFFICE_ACE_DEPLOYMENT=cloud``）与 PC 端（``pc`` 或缺省）的区分：
    * 云端：记忆搜索走 AgentArts SDK，sync_turn 不上报（由 relay-claw 直报）。
    * PC 端：记忆搜索走 chat-service appapi，sync_turn 走 pc-threads 上报。
    """
    return os.environ.get("OFFICE_ACE_DEPLOYMENT", "pc").strip().lower() == "cloud"


def _build_officeace_cloud_provider(
    ext_cfg: Dict[str, Any],
    runtime_config: Optional[Dict[str, str]] = None,
):
    """Build OfficeAce memory provider (cloud or PC form).

    OfficeAce memory is a long-term memory service shared by cloud and PC
    deployments. Per-session credentials (api_key, space_id) are supplied by
    relay-claw via chat.send params and threaded here as ``runtime_config``.
    Since each session owns its own provider instance (session-scoped adapter →
    own rail → own provider), credentials are bound at construction — matching
    the provider's read-only config principle. Static config/env values are a
    fallback for dev/standalone debugging when relay-claw does not supply
    per-session credentials.

    Deployment dispatch:
        cloud → :class:`OfficeAceMemoryCloudProvider` (AgentArts SDK search,
            sync_turn no-op; relay-claw reports conversations directly).
        pc    → :class:`OfficeAceMemoryPcProvider` (chat-service appapi search
            + pc-threads messages sync_turn).

    Args:
        ext_cfg: ``memory.external`` config slice (contains the
            ``officeace_cloud`` sub-section).
        runtime_config: Per-session credentials from relay-claw chat.send params.
            ``api_key`` / ``space_id`` / ``base_url`` override the static
            fallback values.

    Config shape (memory.external.officeace_cloud):
        base_url: str    # OfficeAce memory endpoint
        api_key: str     # static fallback credential (prod = per-session via runtime_config)
        space_id: str    # static fallback space/library id (prod = per-session via runtime_config)
    """
    oa_cfg = ext_cfg.get("officeace_cloud") or {}
    # Per-session credentials + endpoint (from relay-claw chat.send params)
    # take priority over static config/env fallback values.
    rc = runtime_config or {}
    base_url = rc.get("base_url") or oa_cfg.get("base_url") or os.environ.get(
        "AGENTARTS_MEMORY_BASE_URL", ""
    )
    api_key = rc.get("api_key") or oa_cfg.get("api_key") or os.environ.get(
        "AGENTARTS_MEMORY_API_KEY", ""
    )
    space_id = rc.get("space_id") or oa_cfg.get("space_id") or os.environ.get(
        "AGENTARTS_MEMORY_SPACE_ID", ""
    )
    actor_id = rc.get("actor_id") or rc.get("user_id") or ""
    source = "per-session" if rc else "static-fallback"

    if _is_cloud_deployment():
        from openjiuwen.core.memory.external.office_ace_memory_cloud_provider import (
            OfficeAceMemoryCloudProvider,
        )

        provider = OfficeAceMemoryCloudProvider(
            base_url=base_url or None,
            api_key=api_key,
            space_id=space_id,
            actor_id=actor_id,
        )
        logger.info(
            "[ExternalMemoryBuilder] OfficeAce cloud provider built: "
            "base_url=%s, api_key=%s, space_id=%s (source=%s)",
            base_url, bool(api_key), bool(space_id), source,
        )
        return provider

    from openjiuwen.core.memory.external.office_ace_memory_pc_provider import (
        OfficeAceMemoryPcProvider,
    )

    provider = OfficeAceMemoryPcProvider(
        base_url=base_url or None,
        api_key=api_key,
        actor_id=actor_id,
    )
    logger.info(
        "[ExternalMemoryBuilder] OfficeAce pc provider built: "
        "base_url=%s, api_key=%s, actor_id=%s (source=%s)",
        base_url, bool(api_key), bool(actor_id), source,
    )
    return provider


def _load_plugin_provider(name: str, allowed: Optional[list] = None):
    try:
        from .plugin_discovery import load_memory_plugin
    except ImportError:
        logger.warning(
            "[ExternalMemoryBuilder] plugin '%s' requested but plugin_discovery not yet available",
            name,
        )
        return None
    return load_memory_plugin(name, allowed_plugins=allowed)
