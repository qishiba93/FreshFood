"""
backend/routers/admin_audit.py
管理员风控审核中台与全局操作日志审计路由
包含: 违规举报工单按帖聚合处置台、全员行为操作审计日志
【核心修复】：
完美修复“管理员驳回举报后，用户再次举报该帖子，管理端无法接收/无法再次处置”的聚合状态穿透Bug。
"""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from backend.database import get_db
from backend.models import CommunityReport, CommunityPost, User, UserActivity
from backend.schemas import ReportHandleRequest
from backend.auth import get_current_admin_user

router = APIRouter(prefix="/api/admin/audit", tags=["管理员风控与行为审计"])

# 1. 获取违规举报工单列表 (核心修复：支持反复驳回后再次举报的动态状态穿透与精准聚合)
@router.get("/reports")
async def list_community_reports(
    status_filter: Optional[str] = Query("all", description="all / pending / approved / rejected"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    # 先按创建时间倒序查出所有举报记录及其关联信息
    stmt = (
        select(
            CommunityReport,
            User.username.label("reporter_name"),
            CommunityPost.title.label("post_title"),
            CommunityPost.image_url.label("post_image"),
            CommunityPost.content.label("post_content"),
            CommunityPost.status.label("post_status")
        )
        .join(User, User.id == CommunityReport.reporter_id)
        .join(CommunityPost, CommunityPost.id == CommunityReport.post_id)
        .order_by(desc(CommunityReport.created_at), desc(CommunityReport.id))
    )

    res = await db.execute(stmt)
    records = res.all()

    reason_map = {
        "violence": "血腥暴力 / 令人不适",
        "porn": "低俗色情",
        "spam": "广告垃圾 / 恶意引流",
        "unrelated": "与美食烹饪无关的内容",
        "other": "其他违规"
    }

    # 按 post_id 进行聚合
    grouped_posts = {}

    for report, reporter_name, title, img, content, post_status in records:
        pid = report.post_id

        # 若是该帖子第一次被扫描到（由于按照 created_at desc 排序，第一条就是该帖子最新的举报）
        if pid not in grouped_posts:
            grouped_posts[pid] = {
                "id": report.id,                 # 默认挂载最新举报的 ID
                "post_id": pid,
                "post_title": title,
                "post_image": img,
                "post_content": content,
                "post_status": post_status,
                "status": report.status,          # 最新一条工单的状态
                "has_pending": (report.status == "pending"), # 是否存在未处理工单
                "admin_note": report.admin_note or "",
                "created_at": report.created_at.strftime("%Y-%m-%d %H:%M:%S") if report.created_at else "",
                "handled_at": report.handled_at.strftime("%Y-%m-%d %H:%M:%S") if report.handled_at else "",
                "reporters_list": []
            }

        # 如果后续遍历发现了处于 pending 状态的工单，而卡片当前不是 pending，强行提升为 pending 并将主控 id 切换为该待办工单
        if report.status == "pending" and grouped_posts[pid]["status"] != "pending":
            grouped_posts[pid]["status"] = "pending"
            grouped_posts[pid]["has_pending"] = True
            grouped_posts[pid]["id"] = report.id
            grouped_posts[pid]["created_at"] = report.created_at.strftime("%Y-%m-%d %H:%M:%S") if report.created_at else ""

        grouped_posts[pid]["reporters_list"].append({
            "report_id": report.id,
            "reporter_id": report.reporter_id,
            "reporter_name": reporter_name,
            "status": report.status,
            "reason_code": report.reason,
            "reason_text": reason_map.get(report.reason, report.reason),
            "detail": report.detail or "无附加说明",
            "created_at": report.created_at.strftime("%Y-%m-%d %H:%M:%S") if report.created_at else ""
        })

    report_list = []
    for pid, post_group in grouped_posts.items():
        # 【关键过滤】：根据聚合后的最终状态筛选
        if status_filter and status_filter != "all":
            # 如果筛选的是 pending，但该帖名下没有待处理项，则跳过
            if status_filter == "pending" and post_group["status"] != "pending":
                continue
            # 如果筛选其他状态（如 approved / rejected），但当前状态不符，则跳过
            if status_filter != "pending" and post_group["status"] != status_filter:
                continue

        reporters = post_group["reporters_list"]

        # 统计去重后的举报人名单
        unique_usernames = []
        for r in reporters:
            if r["reporter_name"] not in unique_usernames:
                unique_usernames.append(r["reporter_name"])

        total_count = len(unique_usernames)

        if total_count <= 3:
            reporters_display = "、".join(unique_usernames)
        else:
            reporters_display = f"{'、'.join(unique_usernames[:3])} 等 {total_count} 人"

        post_group["total_reporters_count"] = total_count
        post_group["reporters_display"] = reporters_display
        report_list.append(post_group)

    # 待处理的帖子排在最前面展示
    report_list.sort(key=lambda x: (x["status"] != "pending", x["created_at"]), reverse=False)

    return report_list

# 2. 处理举报工单 (一键处置该帖子名下的所有待审工单)
@router.post("/reports/{report_id}/handle")
async def handle_community_report(
    report_id: int,
    req: ReportHandleRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    stmt = select(CommunityReport).where(CommunityReport.id == report_id)
    report = (await db.execute(stmt)).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="举报工单不存在")

    post_stmt = select(CommunityPost).where(CommunityPost.id == report.post_id)
    post = (await db.execute(post_stmt)).scalar_one_or_none()

    if req.action == "approve_hide":
        if post:
            post.status = 0
        msg = "已判定违规，该动态已立即下架屏蔽！"
        final_status = "approved"

    elif req.action == "approve_delete":
        if post:
            await db.delete(post)
        msg = "已判定严重违规，该动态已被彻底物理删除！"
        final_status = "approved"

    elif req.action == "reject":
        if post:
            post.status = 1  # 驳回举报，恢复公开正常展示
        msg = "举报已被驳回，该动态已恢复并在社区正常展示。"
        final_status = "rejected"

    else:
        raise HTTPException(status_code=400, detail="无效的处理动作")

    # 批处理：该帖子名下所有处于待处理(pending)状态的举报，统统结单置为本次处置的状态
    all_reports_stmt = select(CommunityReport).where(
        CommunityReport.post_id == report.post_id,
        CommunityReport.status == "pending"
    )
    all_pending = (await db.execute(all_reports_stmt)).scalars().all()
    now_time = datetime.now()

    for r in all_pending:
        r.status = final_status
        r.admin_note = req.admin_note
        r.handled_at = now_time

    # 确保当前传进来的工单状态也是最终状态
    report.status = final_status
    report.admin_note = req.admin_note
    report.handled_at = now_time

    await db.commit()
    return {"message": msg, "report_id": report.id, "status": final_status}

# 3. 全局用户全周期操作日志检索
@router.get("/logs")
async def list_system_operation_logs(
    days: int = Query(7, ge=1, le=90, description="时间跨度: 近 N 天"),
    activity_type: Optional[str] = Query("all", description="操作分类过滤"),
    user_id: Optional[int] = Query(None, description="指定用户ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    start_date = datetime.now() - timedelta(days=days)
    stmt = (
        select(UserActivity, User.username)
        .join(User, User.id == UserActivity.user_id)
        .where(UserActivity.created_at >= start_date)
        .order_by(desc(UserActivity.created_at))
    )

    if activity_type and activity_type != "all":
        stmt = stmt.where(UserActivity.activity_type == activity_type)

    if user_id:
        stmt = stmt.where(UserActivity.user_id == user_id)

    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)

    res = await db.execute(stmt)
    records = res.all()

    type_cn_map = {
        "add": "食材入库/建档",
        "consume": "做菜核销消耗",
        "collect": "菜谱收藏",
        "post": "社区发布动态",
        "like": "点赞互动",
        "comment": "发表评论",
        "report": "提交风控举报",
        "login": "登录系统"
    }

    logs = []
    for act, u_name in records:
        logs.append({
            "id": act.id,
            "user_id": act.user_id,
            "username": u_name,
            "activity_type": act.activity_type,
            "activity_name": type_cn_map.get(act.activity_type, act.activity_type),
            "note": act.note or "",
            "created_at": act.created_at.strftime("%Y-%m-%d %H:%M:%S") if act.created_at else ""
        })

    return logs