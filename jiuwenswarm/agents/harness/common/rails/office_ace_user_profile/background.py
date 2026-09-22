# coding: utf-8
# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""进程级后台拉取管理器 — 周期拉取云端用户画像概览,生命周期挂在 AgentWebSocketServer。

与 rail 实例解耦:rail 卸载只影响 prompt 注入,后台拉取不中断。
每 tick 先重读 config(``get_office_ace_user_profile_config``),配置热修改即时生效:
* enabled & endpoint/api_key/user_id 齐全 → fetch
* 否则 skip(配置关了/不全就停拉,但不杀任务,等下次 tick 再判)
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from jiuwenswarm.agents.harness.common.memory.external_memory_config import (
    get_office_ace_user_profile_config,
)
from jiuwenswarm.agents.harness.common.rails.office_ace_user_profile.fetcher import (
    UserProfileConfig,
    UserProfileFetcher,
)
from jiuwenswarm.common.utils import logger

# tick 之间最小 sleep 上限(秒),避免 interval 配 0/负值导致 busy-loop
_MIN_TICK_SLEEP_SECONDS = 60


class _UserProfileBackgroundManager:
    """进程级单例后台拉取管理器。

    生命周期由 :meth:`start` / :meth:`stop` 驱动(挂在 ws_server 进程级)。
    rail 不再启动/取消后台任务——``init``/``uninit`` 只管 prompt 段注入。
    """

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task[Any]] = None
        self._stopping = False

    @classmethod
    def get(cls) -> "_UserProfileBackgroundManager":
        """懒单例。"""
        global _manager_instance
        if _manager_instance is None:
            _manager_instance = cls()
        return _manager_instance

    async def start(self) -> None:
        """启动后台周期拉取(幂等:已运行则直接返回)。"""
        if self._task is not None and not self._task.done():
            return
        self._stopping = False
        try:
            self._task = asyncio.create_task(self._loop(), name="user-profile-bg")
            logger.info("[UserProfileBackgroundManager] background task started")
        except RuntimeError:
            # 无事件循环(非 async 上下文)——跳过,不影响主流程
            logger.warning(
                "[UserProfileBackgroundManager] no event loop; task not started",
            )

    async def stop(self) -> None:
        """停止后台任务(幂等)。"""
        self._stopping = True
        task = self._task
        self._task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[UserProfileBackgroundManager] task cancel failed: %s", exc
                )

    async def _loop(self) -> None:
        """周期拉取主循环。每 tick 重读 config,配置热修改即时生效。"""
        from jiuwenswarm.common.config import get_config

        while not self._stopping:
            try:
                cfg = get_office_ace_user_profile_config(get_config())
                interval = max(1, int(cfg.get("fetch_interval_minutes", 10) or 10))
                # enabled 已综合：external memory 开关 + provider=officeace_cloud + 凭证齐全
                if cfg.get("enabled"):
                    fetcher = UserProfileFetcher(UserProfileConfig(**cfg))
                    await fetcher.fetch_once()
                else:
                    logger.debug(
                        "[UserProfileBackgroundManager] skip tick "
                        "(external memory off / provider not officeace_cloud / "
                        "credentials incomplete)",
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "[UserProfileBackgroundManager] tick error: %s", exc
                )
            if self._stopping:
                break
            await asyncio.sleep(max(_MIN_TICK_SLEEP_SECONDS, interval * 60))


_manager_instance: Optional[_UserProfileBackgroundManager] = None


def user_profile_background_manager() -> _UserProfileBackgroundManager:
    """返回进程级单例。"""
    return _UserProfileBackgroundManager.get()


__all__ = ["user_profile_background_manager"]
