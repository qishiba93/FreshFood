"""
backend/routers/health.py
个人与家庭成员健康档案管理路由 (支撑需求 2、3、4、5)
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.database import get_db
from backend.models import User, UserHealthProfile, UserActivity
from backend.schemas import HealthProfileCreate, HealthProfileUpdate
from backend.auth import get_current_user

router = APIRouter(prefix="/api/health", tags=["家庭健康画像"])

# 1. 查询当前用户下的所有健康档案 (本人 + 家人)
@router.get("/profiles")
async def list_health_profiles(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    stmt = (
        select(UserHealthProfile)
        .where(UserHealthProfile.user_id == user.id)
        .order_by(UserHealthProfile.is_primary.desc(), UserHealthProfile.id.asc())
    )
    res = await db.execute(stmt)
    profiles = res.scalars().all()

    return [
        {
            "id": p.id,
            "member_name": p.member_name,
            "relation": p.relation,
            "conditions": p.conditions or [],
            "dietary_notes": p.dietary_notes or "",
            "is_primary": bool(p.is_primary),
            "created_at": p.created_at.strftime("%Y-%m-%d %H:%M") if p.created_at else ""
        }
        for p in profiles
    ]

# 2. 新增成员健康档案 (或注册后引导首次录入)
@router.post("/profiles")
async def create_health_profile(
    req: HealthProfileCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    # 如果标记为本人主档案，先确保名下其他档案取消 primary 标记
    if req.is_primary == 1 or req.relation == "self":
        req.is_primary = 1
        stmt_reset = (
            select(UserHealthProfile)
            .where(UserHealthProfile.user_id == user.id, UserHealthProfile.is_primary == 1)
        )
        existing_primaries = (await db.execute(stmt_reset)).scalars().all()
        for ep in existing_primaries:
            ep.is_primary = 0

    new_profile = UserHealthProfile(
        user_id=user.id,
        member_name=req.member_name.strip(),
        relation=req.relation,
        conditions=req.conditions or [],
        dietary_notes=req.dietary_notes.strip() if req.dietary_notes else None,
        is_primary=req.is_primary
    )
    db.add(new_profile)
    db.add(UserActivity(
        user_id=user.id,
        activity_type="add",
        note=f"录入健康档案:{new_profile.member_name}({','.join(req.conditions) if req.conditions else '健康'})"
    ))
    await db.commit()
    await db.refresh(new_profile)

    return {
        "message": f"成员「{new_profile.member_name}」的健康档案已保存！",
        "id": new_profile.id,
        "is_primary": bool(new_profile.is_primary)
    }

# 3. 编辑成员健康档案
@router.put("/profiles/{profile_id}")
async def update_health_profile(
    profile_id: int,
    req: HealthProfileUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    stmt = select(UserHealthProfile).where(
        UserHealthProfile.id == profile_id,
        UserHealthProfile.user_id == user.id
    )
    profile = (await db.execute(stmt)).scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="未找到该健康档案")

    if req.member_name is not None:
        profile.member_name = req.member_name.strip()
    if req.relation is not None:
        profile.relation = req.relation
    if req.conditions is not None:
        profile.conditions = req.conditions
    if req.dietary_notes is not None:
        profile.dietary_notes = req.dietary_notes.strip()

    if req.is_primary == 1:
        # 重置其他档案的本人主标记
        stmt_reset = select(UserHealthProfile).where(
            UserHealthProfile.user_id == user.id,
            UserHealthProfile.id != profile.id,
            UserHealthProfile.is_primary == 1
        )
        existing_primaries = (await db.execute(stmt_reset)).scalars().all()
        for ep in existing_primaries:
            ep.is_primary = 0
        profile.is_primary = 1
    elif req.is_primary == 0:
        profile.is_primary = 0

    profile.updated_at = datetime.now()
    await db.commit()

    return {"message": f"健康档案「{profile.member_name}」更新成功"}

# 4. 删除成员健康档案
@router.delete("/profiles/{profile_id}")
@router.post("/profiles/{profile_id}/delete")
async def delete_health_profile(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    stmt = select(UserHealthProfile).where(
        UserHealthProfile.id == profile_id,
        UserHealthProfile.user_id == user.id
    )
    profile = (await db.execute(stmt)).scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="未找到该健康档案")

    deleted_name = profile.member_name
    await db.delete(profile)
    await db.commit()
    return {"message": f"已移除「{deleted_name}」的健康档案"}

# 5. 需求2专属: 检查当前用户是否已有健康档案 (供前端决定是否在刚登录/注册后弹窗引导)
@router.get("/check-onboarding")
async def check_user_onboarding(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    stmt = select(UserHealthProfile).where(UserHealthProfile.user_id == user.id)
    existing = (await db.execute(stmt)).scalars().first()
    return {
        "has_health_profile": existing is not None,
        "username": user.username
    }
