"""jiuwenswarm as the host of the DesignSwarm core (``designswarm``).

The design feature (team.design canvas, Director chain, graph runs) lives in
``designswarm-core``. The core reaches its host only through
:class:`designswarm.host.DesignHost`; this subclass answers every seam with
the jiuwenswarm module that owns it. It is advertised under the
``designswarm.host`` entry point group, so every process resolves it on first
use; :func:`install_design_host` installs it eagerly.
"""

from __future__ import annotations

import logging
import shutil
import threading
from pathlib import Path
from types import ModuleType
from typing import Any

from designswarm.host import DesignHost, get_host, set_host

logger = logging.getLogger(__name__)

DESIGNER_AGENT_GROUP = "designer"

# Module prefixes of the design code that moved into designswarm-core. An
# installed designer AgentGroup still importing them predates the move.
_RETIRED_DESIGN_MODULES = (
    "jiuwenswarm.server.runtime.designer",
    "jiuwenswarm.server.runtime.design",
    "jiuwenswarm.agents.harness.design",
    "jiuwenswarm.common.schema.designer_",
)


def _imports_retired_design_modules(package_dir: Path) -> bool:
    for path in package_dir.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if any(prefix in text for prefix in _RETIRED_DESIGN_MODULES):
            return True
    return False


class JiuwenswarmDesignHost(DesignHost):
    """Design core services backed by the jiuwenswarm runtime."""

    def __init__(self) -> None:
        super().__init__()
        self._fresh_designer_dirs: set[Path] = set()
        self._designer_lock = threading.Lock()

    # Storage layout

    def user_workspace_dir(self) -> Path:
        from jiuwenswarm.common.utils import get_user_workspace_dir

        return get_user_workspace_dir()

    def agent_root_dir(self) -> Path:
        from jiuwenswarm.common.utils import get_agent_root_dir

        return get_agent_root_dir()

    def agent_sessions_dir(self) -> Path:
        from jiuwenswarm.common.utils import get_agent_sessions_dir

        return get_agent_sessions_dir()

    def agent_workspace_dir(self) -> Path:
        from jiuwenswarm.common.utils import get_agent_workspace_dir

        return get_agent_workspace_dir()

    def default_project_session_workspace_dir(self, session_id: str | None = None) -> Path:
        from jiuwenswarm.common.utils import get_default_project_session_workspace_dir

        return get_default_project_session_workspace_dir(session_id)

    # Model settings

    def get_config(self) -> dict[str, Any]:
        from jiuwenswarm.common.config import get_config

        return get_config()

    def get_default_models(self, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        from jiuwenswarm.common.config import get_default_models

        return get_default_models(config)

    def get_model_names(self) -> list[str]:
        from jiuwenswarm.common.config import get_model_names

        return get_model_names()

    def resolve_env_vars(self, value: Any) -> Any:
        from jiuwenswarm.common.config import resolve_env_vars

        return resolve_env_vars(value)

    def env_file(self) -> Path:
        from jiuwenswarm.common.utils import get_env_file

        return get_env_file()

    def load_dotenv(self, dotenv_path: str | Path | None, *, override: bool = True) -> bool:
        from jiuwenswarm.dotenv_early import load_dotenv_runtime

        return load_dotenv_runtime(dotenv_path, override=override)

    # Sessions and projects

    def project_store(self) -> ModuleType:
        from jiuwenswarm.server.runtime.session import project_store

        return project_store

    def session_metadata(self) -> ModuleType:
        from jiuwenswarm.server.runtime.session import session_metadata

        return session_metadata

    def session_history(self) -> ModuleType:
        from jiuwenswarm.server.runtime.session import session_history

        return session_history

    # AgentGroup / AgentTemplate packages
    #
    # ``agent_groups_resources_dir`` stays the core's packaged shelf: the
    # designer group ships with designswarm-core, not in jiuwenswarm resources.

    def resolve_agent_group_dir(self, name: Any) -> Path:
        from jiuwenswarm.server.runtime.extension_package_manager import (
            resolve_agent_group_dir,
        )

        resolved = resolve_agent_group_dir(name)
        if str(name) == DESIGNER_AGENT_GROUP and not self._designer_copy_is_fresh(resolved):
            raise ValueError(
                f"agent_group package {name} predates designswarm-core: {resolved}"
            )
        return resolved

    def install_agent_group(self, params: dict[str, Any]) -> None:
        from jiuwenswarm.server.runtime.extension_package_manager import (
            install_agent_group,
        )

        if str(params.get("id") or params.get("name") or "") == DESIGNER_AGENT_GROUP:
            self._seed_designer_built_in()
        install_agent_group(params)

    def resolve_agent_group_member_display_name(
        self, package_dir: Path, member_id: str, *, fallback: str = ""
    ) -> str:
        from jiuwenswarm.server.runtime.extension_package_manager import (
            resolve_agent_group_member_display_name,
        )

        return resolve_agent_group_member_display_name(
            package_dir, member_id, fallback=fallback
        )

    def resolve_agent_template_dir(self, name: Any) -> Path:
        from jiuwenswarm.server.runtime.extension_package_manager import (
            resolve_agent_template_dir,
        )

        return resolve_agent_template_dir(name)

    # Swarm team runtime

    def get_team_manager(self) -> Any:
        from jiuwenswarm.agents.harness.team.team_manager import get_team_manager

        return get_team_manager()

    # Client push

    async def send_push(self, message: dict[str, Any]) -> None:
        from jiuwenswarm.server.agent_ws_server import AgentWebSocketServer

        await AgentWebSocketServer.get_instance().send_push(message)

    # Designer AgentGroup seeding

    def _designer_copy_is_fresh(self, package_dir: Path) -> bool:
        key = package_dir.resolve()
        with self._designer_lock:
            if key in self._fresh_designer_dirs:
                return True
        if _imports_retired_design_modules(key):
            return False
        with self._designer_lock:
            self._fresh_designer_dirs.add(key)
        return True

    def _seed_designer_built_in(self) -> None:
        """Copy the core's designer package over jiuwenswarm's built_in slot.

        jiuwenswarm installs a group by copying it from its own resources
        shelf; the designer group ships with designswarm-core instead, so the
        built_in copy is refreshed from there.
        """
        from jiuwenswarm.server.runtime.extension_package_manager import (
            _AGENT_GROUP_KIND,
            _built_in_root,
            _local_root,
        )

        source_root = self.agent_groups_resources_dir()
        source = source_root / DESIGNER_AGENT_GROUP if source_root is not None else None
        if source is None or not (source / "manifest.json").is_file():
            raise ValueError("designswarm-core ships no designer agent_group package")
        if (_local_root(_AGENT_GROUP_KIND) / DESIGNER_AGENT_GROUP).is_dir():
            return
        target = _built_in_root(_AGENT_GROUP_KIND) / DESIGNER_AGENT_GROUP
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.with_name(f".{DESIGNER_AGENT_GROUP}.staging")
        shutil.rmtree(staging, ignore_errors=True)
        shutil.copytree(
            source, staging, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
        )
        shutil.rmtree(target, ignore_errors=True)
        staging.rename(target)
        with self._designer_lock:
            self._fresh_designer_dirs.discard(target.resolve())


def install_design_host() -> JiuwenswarmDesignHost:
    """Install the jiuwenswarm host unless one is already in place (idempotent)."""
    current = get_host()
    if isinstance(current, JiuwenswarmDesignHost):
        return current
    return set_host(JiuwenswarmDesignHost())  # type: ignore[return-value]


def ensure_designer_agent_group() -> None:
    """Seed/refresh the designer AgentGroup; failures only warn."""
    try:
        install_design_host()
        from designswarm.server.runtime.design.team_bridge import (
            ensure_designer_agent_group_installed,
        )

        ensure_designer_agent_group_installed()
    except Exception as exc:  # noqa: BLE001 - design must not block service start
        logger.warning("designer agent_group install skipped: %s", exc)


__all__ = [
    "DESIGNER_AGENT_GROUP",
    "JiuwenswarmDesignHost",
    "ensure_designer_agent_group",
    "install_design_host",
]
