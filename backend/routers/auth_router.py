"""
backend/routers/auth_router.py
用户认证、分级运维与全员综合活跃热力大屏中台接口
包含：核心KPI聚合、三餐时段洞察、GitHub风格贡献墙、7x24H交叉打卡矩阵、日期穿透下钻流水
"""
import traceback
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from backend.database import get_db
from backend.models import User, UserActivity
from backend.schemas import UserRegisterLogin, AdminCreateUser, AdminResetPassword
from backend.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user,
    get_current_admin_user,
    get_current_super_admin,
    DUMMY_HASH_PREFIX
)

router = APIRouter(prefix="/api/auth", tags=["用户认证与管理"])

def check_is_super(u: User) -> bool:
    return u.id == 1 or u.username == "admin" or u.role == "super_admin"

# 1. 普通用户公开注册接口 (硬性规定：只能注册普通用户)
@router.post("/register")
async def register(req: UserRegisterLogin, db: AsyncSession = Depends(get_db)):
    clean_username = req.username.strip()

    stmt = select(User).where(User.username == clean_username)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该账号已存在，请重新输入其他账号名称"
        )

    try:
        new_user = User(
            username=clean_username,
            hashed_password=str(get_password_hash(req.password)),
            role="user",
            status=1
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        token = create_access_token({"sub": new_user.username})
        return {
            "message": "注册成功",
            "access_token": token,
            "username": new_user.username,
            "role": "user"
        }
    except Exception as e:
        await db.rollback()
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"注册入库异常: {str(e)}")

# 2. 用户登录
@router.post("/login")
async def login(req: UserRegisterLogin, db: AsyncSession = Depends(get_db)):
    clean_username = req.username.strip()

    stmt = select(User).where(User.username == clean_username)
    user = (await db.execute(stmt)).scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该账号尚未注册，请先点击上方“注册新账号”进行注册"
        )

    if not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="账号或密码错误，请重新输入"
        )

    if user.hashed_password.startswith(DUMMY_HASH_PREFIX):
        user.hashed_password = str(get_password_hash(req.password))
        await db.commit()

    actual_role = "super_admin" if check_is_super(user) else (user.role or "user")
    token = create_access_token({"sub": user.username})
    return {
        "message": "登录成功",
        "access_token": token,
        "username": user.username,
        "role": actual_role
    }

# 3. 获取当前登录者身份
@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    actual_role = "super_admin" if check_is_super(user) else (user.role or "user")
    return {
        "id": user.id,
        "username": user.username,
        "role": actual_role
    }

# ================= 管理员专属功能 =================

# 4. 管理员获取全部用户列表
@router.get("/admin/users")
async def admin_list_users(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    stmt = select(User).order_by(User.id.asc())
    res = await db.execute(stmt)
    users = res.scalars().all()

    admin_is_super = check_is_super(admin)

    user_list = []
    for u in users:
        u_is_super = check_is_super(u)
        u_role = "super_admin" if u_is_super else (u.role or "user")

        if admin_is_super:
            can_manage = (u.id != admin.id)
        else:
            can_manage = (u_role == "user")

        user_list.append({
            "id": u.id,
            "username": u.username,
            "role": u_role,
            "created_at": u.created_at.strftime("%Y-%m-%d %H:%M:%S") if u.created_at else "",
            "can_manage": can_manage
        })
    return user_list

# 5. 管理员新建用户
@router.post("/admin/users")
async def admin_create_user(
    req: AdminCreateUser,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    clean_username = req.username.strip()

    stmt = select(User).where(User.username == clean_username)
    if (await db.execute(stmt)).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该账号名称已存在，请更换")

    admin_is_super = check_is_super(admin)

    if req.role in ["admin", "super_admin"] and not admin_is_super:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足：一般管理员只能注册普通用户，管理员账号必须由超级管理员开通！"
        )

    assigned_role = "admin" if req.role == "admin" else "user"

    new_user = User(
        username=clean_username,
        hashed_password=str(get_password_hash(req.password)),
        role=assigned_role,
        status=1
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    desc_str = "一般管理员" if assigned_role == "admin" else "普通用户"
    return {"message": f"成功开通{desc_str}「{new_user.username}」", "id": new_user.id}

# 6. 管理员重置密码
@router.put("/admin/users/{user_id}/password")
async def admin_reset_user_password(
    user_id: int,
    req: AdminResetPassword,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    stmt = select(User).where(User.id == user_id)
    target_user = (await db.execute(stmt)).scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="目标用户不存在")

    admin_is_super = check_is_super(admin)
    target_is_admin = check_is_super(target_user) or target_user.role == "admin"

    if target_is_admin and not admin_is_super:
        raise HTTPException(status_code=403, detail="权限不足：一般管理员无法重置管理员账号的密码")

    target_user.hashed_password = str(get_password_hash(req.new_password))
    await db.commit()

    return {"message": f"用户「{target_user.username}」的密码已重置成功"}

# 7. 管理员删除用户
@router.delete("/admin/users/{user_id}")
@router.post("/admin/users/{user_id}/delete")
async def admin_delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="严禁删除当前登录的操作者自己")

    stmt = select(User).where(User.id == user_id)
    target_user = (await db.execute(stmt)).scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="目标用户不存在")

    admin_is_super = check_is_super(admin)
    target_is_admin = check_is_super(target_user) or target_user.role == "admin"

    if target_is_admin and not admin_is_super:
        raise HTTPException(status_code=403, detail="权限不足：一般管理员只能删除普通用户，严禁删除管理员！")

    target_name = target_user.username
    await db.delete(target_user)
    await db.commit()

    return {"message": f"用户「{target_name}」及其名下所有食材、菜谱已被物理级联清空"}

# 8. 核心升级：全员多维综合活跃热力大屏 API (丰富版：包含KPI指标、三餐洞察、日期穿透流)
@router.get("/admin/global-heatmap")
async def admin_get_global_heatmap(
    days_range: int = 30,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    now = datetime.now()
    start_date = (now - timedelta(days=days_range - 1)).date()

    # 1. 获取所有普通用户
    users_res = await db.execute(select(User).where(User.role == "user").order_by(User.id.asc()))
    regular_users = users_res.scalars().all()
    user_name_map = {u.id: u.username for u in regular_users}

    # 2. 构建连续日期序列与穿透明细桶
    date_list = []
    calendar_totals = {}
    daily_details = {}

    for i in range(days_range):
        curr_d = start_date + timedelta(days=i)
        d_str = curr_d.strftime("%Y-%m-%d")
        date_list.append({
            "date": d_str,
            "weekday": curr_d.weekday(),
            "month_day": curr_d.strftime("%m/%d")
        })
        calendar_totals[d_str] = 0
        daily_details[d_str] = []

    # 3. 查询时间段内的活跃记录流水
    acts_stmt = (
        select(UserActivity)
        .where(UserActivity.created_at >= datetime.combine(start_date, datetime.min.time()))
        .order_by(desc(UserActivity.created_at))
    )
    acts_res = await db.execute(acts_stmt)
    activities = acts_res.scalars().all()

    # 4. 初始化 7 天 x 24 小时交叉打卡矩阵
    punchcard = [[0 for _ in range(24)] for _ in range(7)]

    # 5. 三餐开火时段统计桶
    breakfast_count = 0   # 6:00 - 9:59
    lunch_count = 0       # 11:00 - 14:59
    dinner_count = 0      # 17:00 - 20:59
    other_period_count = 0

    # 6. 行为分类统计桶
    action_counts = {
        "add": 0,
        "consume": 0,
        "collect": 0,
        "post": 0,
        "like": 0,
        "comment": 0,
        "other": 0
    }

    # 7. 用户独立活跃度桶
    user_map = {
        u.id: {
            "id": u.id,
            "username": u.username,
            "daily": {d["date"]: 0 for d in date_list},
            "latest_act": None,
            "total_acts": 0
        } for u in regular_users
    }

    # 8. 遍历统计
    for act in activities:
        act_date = act.created_at.strftime("%Y-%m-%d")
        act_hour = act.created_at.hour
        act_weekday = act.created_at.weekday()

        if act_date in calendar_totals:
            calendar_totals[act_date] += 1

        punchcard[act_weekday][act_hour] += 1

        # 三餐节奏判断
        if 6 <= act_hour < 10:
            breakfast_count += 1
        elif 11 <= act_hour < 15:
            lunch_count += 1
        elif 17 <= act_hour < 21:
            dinner_count += 1
        else:
            other_period_count += 1

        atype = act.activity_type
        if atype in action_counts:
            action_counts[atype] += 1
        else:
            action_counts["other"] += 1

        if act.user_id in user_map:
            if act_date in user_map[act.user_id]["daily"]:
                user_map[act.user_id]["daily"][act_date] += 1
                user_map[act.user_id]["total_acts"] += 1
            if not user_map[act.user_id]["latest_act"]:
                user_map[act.user_id]["latest_act"] = {
                    "time": act.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "note": act.note or act.activity_type
                }

        # 挂入单日穿透明细 (最多保留前 25 条，兼顾流畅度与完整度)
        if act_date in daily_details and len(daily_details[act_date]) < 25:
            uname = user_name_map.get(act.user_id, f"UID:{act.user_id}")
            daily_details[act_date].append({
                "id": act.id,
                "user_id": act.user_id,
                "username": uname,
                "activity_type": act.activity_type,
                "note": act.note or "操作完成",
                "time": act.created_at.strftime("%H:%M:%S")
            })

    user_matrix_list = list(user_map.values())
    sorted_top = sorted(user_matrix_list, key=lambda x: x["total_acts"], reverse=True)[:5]

    # 9. 计算核心运营看板 KPI
    total_actions = len(activities)
    active_users_count = len([u for u in user_map.values() if u["total_acts"] > 0])
    total_users_count = len(regular_users)

    # 寻找峰值周几和峰值小时
    weekdays_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    max_hour_count = 0
    peak_weekday_name = "周一"
    peak_hour_str = "18:00"

    for w in range(7):
        for h in range(24):
            if punchcard[w][h] > max_hour_count:
                max_hour_count = punchcard[w][h]
                peak_weekday_name = weekdays_cn[w]
                peak_hour_str = f"{h}:00 ~ {h+1}:00"

    return {
        "days_range": days_range,
        "dates": date_list,
        "calendar_totals": calendar_totals,
        "punchcard_matrix": punchcard,
        "action_breakdown": action_counts,
        "users_matrix": user_matrix_list,
        "top_active_users": sorted_top,
        "summary_kpis": {
            "total_actions": total_actions,
            "active_users_count": active_users_count,
            "total_users_count": total_users_count,
            "activity_rate": round(active_users_count / max(1, total_users_count) * 100, 1),
            "peak_weekday": peak_weekday_name,
            "peak_hour": peak_hour_str,
            "peak_hour_count": max_hour_count
        },
        "meal_period_distribution": {
            "breakfast": {
                "name": "晨间轻快早餐 (6:00~10:00)",
                "count": breakfast_count,
                "pct": round(breakfast_count / max(1, total_actions) * 100, 1)
            },
            "lunch": {
                "name": "午间高效正餐 (11:00~15:00)",
                "count": lunch_count,
                "pct": round(lunch_count / max(1, total_actions) * 100, 1)
            },
            "dinner": {
                "name": "晚间透味正餐 (17:00~21:00)",
                "count": dinner_count,
                "pct": round(dinner_count / max(1, total_actions) * 100, 1)
            },
            "other": {
                "name": "夜宵/早起备料与其他",
                "count": other_period_count,
                "pct": round(other_period_count / max(1, total_actions) * 100, 1)
            }
        },
        "daily_details": daily_details
    }
