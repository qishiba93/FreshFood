"""
backend/routers/carbon.py
减碳排行榜与个人绿色厨房账本路由 (需求 12)
核心机制: 每周一 00:00:00 动态自然周无锁重置，精准聚合 Top 20
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from backend.database import get_db
from backend.models import User, UserCarbonLog
from backend.auth import get_current_user
from backend.services.carbon_service import convert_to_environmental_equivalents

router = APIRouter(prefix="/api/carbon", tags=["减碳账本与周榜"])

def get_current_week_start() -> datetime:
    """获取本周一 00:00:00 的绝对时间"""
    now = datetime.now()
    monday_date = now.date() - timedelta(days=now.weekday())
    return datetime.combine(monday_date, datetime.min.time())

# 1. 获取本周减碳排行榜 (Top 20 + 自动周一重置)
@router.get("/leaderboard/top20")
async def get_weekly_carbon_leaderboard(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    week_start = get_current_week_start()
    week_end = week_start + timedelta(days=7)

    # 查询本周有减碳明细的所有用户聚合数据
    stmt = (
        select(
            UserCarbonLog.user_id,
            User.username,
            func.sum(UserCarbonLog.carbon_saved_grams).label("total_carbon_g"),
            func.count(UserCarbonLog.id).label("cook_times")
        )
        .join(User, User.id == UserCarbonLog.user_id)
        .where(UserCarbonLog.created_at >= week_start)
        .group_by(UserCarbonLog.user_id, User.username)
        .order_by(desc("total_carbon_g"))
    )

    res = await db.execute(stmt)
    all_rankings = res.all()

    top_20_list = []
    my_rank = None
    my_weekly_carbon = 0.0

    for idx, row in enumerate(all_rankings, start=1):
        u_id, u_name, c_grams, c_times = row
        c_grams_float = float(c_grams or 0.0)
        equiv = convert_to_environmental_equivalents(c_grams_float)

        item_data = {
            "rank": idx,
            "user_id": u_id,
            "username": u_name,
            "carbon_saved_kg": equiv["carbon_saved_kg"],
            "carbon_saved_g": equiv["carbon_saved_g"],
            "tree_days": equiv["tree_days"],
            "cook_times": c_times,
            "is_me": (u_id == user.id)
        }

        if idx <= 20:
            top_20_list.append(item_data)

        if u_id == user.id:
            my_rank = idx
            my_weekly_carbon = c_grams_float

    # 当前用户状态计算
    if my_rank is None:
        my_equiv = convert_to_environmental_equivalents(0.0)
        my_stat = {
            "rank": "未上榜",
            "carbon_saved_kg": 0.0,
            "tree_days": 0.0,
            "is_recorded": False
        }
    else:
        my_equiv = convert_to_environmental_equivalents(my_weekly_carbon)
        my_stat = {
            "rank": my_rank,
            "carbon_saved_kg": my_equiv["carbon_saved_kg"],
            "tree_days": my_equiv["tree_days"],
            "is_recorded": True
        }

    return {
        "cycle_info": {
            "week_start": week_start.strftime("%Y-%m-%d 00:00"),
            "week_reset_next": week_end.strftime("%Y-%m-%d 00:00"),
            "status": "本周实时更新中 (下周一 00:00 自动归零新一轮统计)"
        },
        "my_stat": my_stat,
        "top20": top_20_list
    }

# 2. 个人减碳成就卡片 (本周 + 历史全周期)
@router.get("/my-summary")
async def get_my_carbon_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    week_start = get_current_week_start()

    # 1. 本周累计
    stmt_week = select(func.sum(UserCarbonLog.carbon_saved_grams)).where(
        UserCarbonLog.user_id == user.id,
        UserCarbonLog.created_at >= week_start
    )
    week_g = (await db.execute(stmt_week)).scalar_one_or_none() or 0.0

    # 2. 历史总累计
    stmt_all = select(func.sum(UserCarbonLog.carbon_saved_grams)).where(
        UserCarbonLog.user_id == user.id
    )
    all_g = (await db.execute(stmt_all)).scalar_one_or_none() or 0.0

    return {
        "this_week": convert_to_environmental_equivalents(float(week_g)),
        "all_time": convert_to_environmental_equivalents(float(all_g))
    }