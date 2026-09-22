"""
backend/routers/shopping.py
备菜清单接口 (按用户隔离、智能去重、安全入库)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.database import get_db
from backend.models import ShoppingItem, User
from backend.schemas import ShoppingItemBatchCreate
from backend.auth import get_current_user

router = APIRouter(prefix="/api/shopping", tags=["备菜清单"])

# 1. 获取当前用户的备菜清单
@router.get("/items")
async def list_shopping_items(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    stmt = (
        select(ShoppingItem)
        .where(ShoppingItem.user_id == user.id)
        .order_by(ShoppingItem.created_at.desc())
    )
    res = await db.execute(stmt)
    return res.scalars().all()

# 2. 批量加购到备菜清单 (按用户排重)
@router.post("/batch")
async def add_shopping_items_batch(
    batch: ShoppingItemBatchCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if not batch.items:
        raise HTTPException(status_code=400, detail="采购清单项为空")

    existing_stmt = select(ShoppingItem.name).where(ShoppingItem.user_id == user.id)
    existing_res = await db.execute(existing_stmt)
    existing_names = set(existing_res.scalars().all())

    added_count = 0
    skipped_count = 0

    try:
        for item in batch.items:
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                amount = str(item.get("amount") or "适量").strip()
                source_recipe = str(item.get("source_recipe") or "定制菜谱").strip()
            else:
                name = str(item).strip()
                amount = "适量"
                source_recipe = "定制菜谱"

            if not name:
                continue

            if name in existing_names:
                skipped_count += 1
                continue

            shop_item = ShoppingItem(
                user_id=user.id,
                name=name,
                amount=amount,
                source_recipe=source_recipe
            )
            db.add(shop_item)
            existing_names.add(name)
            added_count += 1

        await db.commit()

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"保存至备菜清单失败: {str(e)}")

    if added_count == 0 and skipped_count > 0:
        return {
            "message": f"所选的 {skipped_count} 种食材已在备菜篮中，无需重复添加",
            "added_count": 0,
            "skipped_count": skipped_count
        }

    msg = f"成功加入 {added_count} 种食材到备菜清单"
    if skipped_count > 0:
        msg += f"（已自动排重 {skipped_count} 种已有食材）"

    return {
        "message": msg,
        "added_count": added_count,
        "skipped_count": skipped_count
    }

# 3. 删除/核销单个备菜项
@router.delete("/items/{item_id}")
async def delete_shopping_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    stmt = select(ShoppingItem).where(ShoppingItem.id == item_id, ShoppingItem.user_id == user.id)
    res = await db.execute(stmt)
    item = res.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="待办食材项不存在")
    await db.delete(item)
    await db.commit()
    return {"message": "已从备菜清单中移除"}