# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""配额同步 API（工作区配额策略投影）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from ..core.quota import WorkspaceQuotaPolicyService
from ..schemas.common_schemas import ResponseModel
from ..schemas.quota_schemas import PolicyUpsertRequest
from ..schemas.sync_schemas import make_sync_body
from .deps import (
    SyncContext,
    VerifySyncEnvelopeOnly,
    sync_write_data,
    verify_sync,
)

quota_router = APIRouter()

PolicySyncBody = make_sync_body("PolicySyncBody", PolicyUpsertRequest)


@quota_router.put("/workspace-quota/policies", response_model=ResponseModel)
async def upsert_workspace_quota_policy(
    sync: Annotated[SyncContext, Depends(verify_sync(PolicySyncBody))],
):
    """工作区配额策略投影。管理面不直接调用。"""
    try:
        await WorkspaceQuotaPolicyService().upsert(sync.business)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResponseModel(code=200, message="success", data=sync_write_data(sync, None))


@quota_router.delete(
    "/workspace-quota/policies/{policy_id}", response_model=ResponseModel
)
async def delete_workspace_quota_policy(
    policy_id: str,
    sync: VerifySyncEnvelopeOnly,
):
    try:
        await WorkspaceQuotaPolicyService().delete(policy_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResponseModel(code=200, message="success", data=sync_write_data(sync, None))
