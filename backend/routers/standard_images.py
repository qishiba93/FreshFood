"""
backend/routers/standard_images.py
标准食材图库管理路由 (需求 11: 管理员统一负责维护与上传)
"""
import os
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from backend.database import get_db
from backend.models import StandardFoodImage, User
from backend.schemas import StandardFoodImageCreate
from backend.auth import get_current_admin_user
from backend.storage import STANDARDS_DIR

router = APIRouter(prefix="/api/admin/food-images", tags=["标准食材图库管理 (管理员专属)"])

# 1. 上传标准食材封面高清图
@router.post("/upload-file")
async def upload_standard_image_file(
    file: UploadFile = File(...),
    admin: User = Depends(get_current_admin_user)
):
    contents = await file.read()
    ext = os.path.splitext(file.filename)[-1] or ".jpg"
    unique_name = f"std_{uuid.uuid4().hex[:12]}{ext}"
    target_path = os.path.join(str(STANDARDS_DIR), unique_name)

    with open(target_path, "wb") as f:
        f.write(contents)

    relative_url = f"/static/standards/{unique_name}"
    return {"message": "标准图片上传成功", "image_url": relative_url}

# 2. 收录标准食材条目
@router.post("")
async def create_standard_food_image(
    req: StandardFoodImageCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    clean_name = req.food_name.strip()
    stmt = select(StandardFoodImage).where(StandardFoodImage.food_name == clean_name)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail=f"标准食材「{clean_name}」已存在于图库中！")

    std_item = StandardFoodImage(
        food_name=clean_name,
        synonyms=req.synonyms.strip() if req.synonyms else None,
        category=req.category,
        image_url=req.image_url.strip()
    )
    db.add(std_item)
    await db.commit()
    await db.refresh(std_item)
    return {"message": f"成功收录标准食材「{clean_name}」", "id": std_item.id}

# 3. 关键词/类别检索标准图库
@router.get("")
async def list_standard_food_images(
    kw: Optional[str] = None,
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    stmt = select(StandardFoodImage).order_by(StandardFoodImage.id.desc())
    if kw and kw.strip():
        kw_clean = f"%{kw.strip()}%"
        stmt = stmt.where(
            or_(
                StandardFoodImage.food_name.like(kw_clean),
                StandardFoodImage.synonyms.like(kw_clean)
            )
        )
    if category and category != "all":
        stmt = stmt.where(StandardFoodImage.category == category)

    res = await db.execute(stmt)
    return res.scalars().all()

# 4. 从图库中删除条目
@router.delete("/{std_id}")
async def delete_standard_food_image(
    std_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    stmt = select(StandardFoodImage).where(StandardFoodImage.id == std_id)
    item = (await db.execute(stmt)).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="图库条目不存在")

    name = item.food_name
    await db.delete(item)
    await db.commit()
    return {"message": f"已从标准图库中清除「{name}」"}
