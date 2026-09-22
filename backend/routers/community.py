"""
backend/routers/community.py
美食生活社区路由
包含: 上传成品图、发帖由AI自动研判真伪生成菜谱、分页列表、单帖详情、
      点赞防重、评论发布与作者删评、违规举报(拦截举报自己动态)、动态删除
"""
import os
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from backend.database import get_db
from backend.models import CommunityPost, PostLike, PostComment, CommunityReport, User, UserActivity
from backend.schemas import CommunityPostCreate, PostCommentCreate, CommunityReportCreate
from backend.services.ai_service import verify_dish_and_generate_recipe
from backend.auth import get_current_user

router = APIRouter(prefix="/api/community", tags=["美食生活社区"])

UPLOAD_COMMUNITY_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "uploads", "community")
os.makedirs(UPLOAD_COMMUNITY_DIR, exist_ok=True)

# 1. 上传动态成品图片
@router.post("/upload-image")
async def upload_community_dish_image(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user)
):
    contents = await file.read()
    ext = os.path.splitext(file.filename)[-1] or ".jpg"
    unique_name = f"dish_{uuid.uuid4().hex[:12]}{ext}"
    target_path = os.path.join(UPLOAD_COMMUNITY_DIR, unique_name)

    with open(target_path, "wb") as f:
        f.write(contents)

    relative_url = f"/static/uploads/community/{unique_name}"
    return {"message": "图片上传成功", "image_url": relative_url}

# 2. 发布动态 (由 AI 自动研判是否是一道菜，是则逆向生成菜谱，否则不生成)
@router.post("/posts")
async def create_community_post(
    req: CommunityPostCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    image_filename = os.path.basename(req.image_url) if req.image_url else ""
    image_abs_path = os.path.join(UPLOAD_COMMUNITY_DIR, image_filename) if image_filename else None

    # 调用 AI 多模态研判：判断图片与文字是否为真实菜肴
    matched_recipe = await verify_dish_and_generate_recipe(
        title=req.title.strip(),
        content=req.content.strip(),
        image_abs_path=image_abs_path
    )

    new_post = CommunityPost(
        user_id=user.id,
        title=req.title.strip(),
        content=req.content.strip(),
        image_url=req.image_url.strip(),
        recipe_data=matched_recipe,  # 若是一道菜则绑定生成的完整菜谱，否则为 None
        likes_count=0,
        status=1
    )
    db.add(new_post)
    db.add(UserActivity(user_id=user.id, activity_type="post", note=f"发布美食动态:{new_post.title}"))
    await db.commit()
    await db.refresh(new_post)

    tip_msg = "动态发布成功，AI已为您生成专属制作菜谱！" if matched_recipe else "动态发布成功！"
    return {
        "message": tip_msg,
        "post_id": new_post.id,
        "is_dish": bool(matched_recipe)
    }

# 3. 分页查询社区动态
@router.get("/posts")
async def list_community_posts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    offset = (page - 1) * page_size
    stmt = (
        select(CommunityPost, User.username)
        .join(User, User.id == CommunityPost.user_id)
        .where(CommunityPost.status == 1)
        .order_by(desc(CommunityPost.created_at))
        .offset(offset)
        .limit(page_size)
    )
    records = (await db.execute(stmt)).all()

    post_ids = [r[0].id for r in records]
    my_liked_ids = set()
    if post_ids:
        like_stmt = select(PostLike.post_id).where(
            PostLike.user_id == user.id,
            PostLike.post_id.in_(post_ids)
        )
        my_liked_ids = set((await db.execute(like_stmt)).scalars().all())

    result = []
    for post, author_name in records:
        cnt_stmt = select(func.count(PostComment.id)).where(PostComment.post_id == post.id, PostComment.status == 1)
        c_count = (await db.execute(cnt_stmt)).scalar() or 0
        result.append({
            "id": post.id,
            "title": post.title,
            "content": post.content,
            "image_url": post.image_url,
            "has_recipe": bool(post.recipe_data),
            "recipe_data": post.recipe_data,
            "author_id": post.user_id,
            "author_name": author_name,
            "likes_count": post.likes_count,
            "comment_count": c_count,
            "is_liked": (post.id in my_liked_ids),
            "is_author": (post.user_id == user.id),
            "created_at": post.created_at.strftime("%Y-%m-%d %H:%M") if post.created_at else ""
        })
    return result

# 4. 获取单篇帖子详情 (供食友查阅与一键收藏菜谱)
@router.get("/posts/{post_id}")
async def get_community_post_detail(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    stmt = (
        select(CommunityPost, User.username)
        .join(User, User.id == CommunityPost.user_id)
        .where(CommunityPost.id == post_id, CommunityPost.status == 1)
    )
    record = (await db.execute(stmt)).first()
    if not record:
        raise HTTPException(status_code=404, detail="该动态不存在或已被下架")
    post, author_name = record

    like_stmt = select(PostLike).where(PostLike.post_id == post_id, PostLike.user_id == user.id)
    is_liked = (await db.execute(like_stmt)).scalar_one_or_none() is not None

    return {
        "id": post.id,
        "title": post.title,
        "content": post.content,
        "image_url": post.image_url,
        "recipe_data": post.recipe_data,
        "author_id": post.user_id,
        "author_name": author_name,
        "likes_count": post.likes_count,
        "is_liked": is_liked,
        "is_author": (post.user_id == user.id),
        "created_at": post.created_at.strftime("%Y-%m-%d %H:%M:%S") if post.created_at else ""
    }

# 5. 点赞与取消点赞
@router.post("/posts/{post_id}/like")
async def toggle_post_like(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    post_stmt = select(CommunityPost).where(CommunityPost.id == post_id, CommunityPost.status == 1)
    post = (await db.execute(post_stmt)).scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="动态不存在")

    like_stmt = select(PostLike).where(PostLike.post_id == post_id, PostLike.user_id == user.id)
    like = (await db.execute(like_stmt)).scalar_one_or_none()

    if like:
        await db.delete(like)
        post.likes_count = max(0, post.likes_count - 1)
        is_liked = False
    else:
        db.add(PostLike(post_id=post_id, user_id=user.id))
        post.likes_count += 1
        is_liked = True
        db.add(UserActivity(user_id=user.id, activity_type="like", note=f"点赞动态ID:{post_id}"))

    await db.commit()
    return {"is_liked": is_liked, "likes_count": post.likes_count}

# 6. 发表评论
@router.post("/posts/{post_id}/comments")
async def add_post_comment(
    post_id: int,
    req: PostCommentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    post_stmt = select(CommunityPost).where(CommunityPost.id == post_id, CommunityPost.status == 1)
    post = (await db.execute(post_stmt)).scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="动态不存在")

    c = PostComment(post_id=post_id, user_id=user.id, content=req.content.strip(), status=1)
    db.add(c)
    db.add(UserActivity(user_id=user.id, activity_type="comment", note=f"评论动态:{post.title}"))
    await db.commit()
    await db.refresh(c)
    return {
        "message": "评论成功",
        "id": c.id,
        "author_name": user.username,
        "content": c.content,
        "created_at": c.created_at.strftime("%Y-%m-%d %H:%M")
    }

# 7. 获取动态评论列表
@router.get("/posts/{post_id}/comments")
async def list_post_comments(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    post_stmt = select(CommunityPost).where(CommunityPost.id == post_id)
    post = (await db.execute(post_stmt)).scalar_one_or_none()
    is_post_owner = (post and post.user_id == user.id)
    is_admin = (user.role in ["admin", "super_admin"] or user.id == 1 or user.username == "admin")

    stmt = (
        select(PostComment, User.username)
        .join(User, User.id == PostComment.user_id)
        .where(PostComment.post_id == post_id, PostComment.status == 1)
        .order_by(PostComment.created_at.asc())
    )
    records = (await db.execute(stmt)).all()

    return [
        {
            "id": c.id,
            "author_id": c.user_id,
            "author_name": u_name,
            "content": c.content,
            "is_me": (c.user_id == user.id),
            "can_delete": (c.user_id == user.id or is_post_owner or is_admin),
            "created_at": c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else ""
        }
        for c, u_name in records
    ]

# 8. 删除评论 (评论人本人、发帖人、系统管理员均享有删除权)
@router.delete("/comments/{comment_id}")
async def delete_post_comment(
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    stmt = select(PostComment).where(PostComment.id == comment_id)
    c = (await db.execute(stmt)).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="评论不存在或已被删除")

    post_stmt = select(CommunityPost).where(CommunityPost.id == c.post_id)
    post = (await db.execute(post_stmt)).scalar_one_or_none()

    is_post_owner = (post and post.user_id == user.id)
    is_comment_owner = (c.user_id == user.id)
    is_admin = (user.role in ["admin", "super_admin"] or user.id == 1 or user.username == "admin")

    if not (is_post_owner or is_comment_owner or is_admin):
        raise HTTPException(status_code=403, detail="无权删除该评论，仅作者本人或发帖者可删除")

    await db.delete(c)
    await db.commit()
    return {"message": "评论已成功删除"}

# 9. 提交违规举报 (核心修复: 严格禁止举报用户自己发布的帖子)
@router.post("/posts/{post_id}/report")
async def report_community_post(
    post_id: int,
    req: CommunityReportCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    post_stmt = select(CommunityPost).where(CommunityPost.id == post_id)
    post = (await db.execute(post_stmt)).scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="被举报的动态不存在")

    # 严密防线: 用户绝对不能举报自己发布的动态
    if post.user_id == user.id:
        raise HTTPException(status_code=400, detail="您不能举报自己发布的动态！如需修改可直接删除动态。")

    # 仅拦截当前正处于 pending(待审核) 状态的重复提交；已结单的举报允许再次提交新工单
    pending_check = select(CommunityReport).where(
        CommunityReport.post_id == post_id,
        CommunityReport.reporter_id == user.id,
        CommunityReport.status == "pending"
    )
    if (await db.execute(pending_check)).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="您已提交过对该内容的举报，管理员正在核实处置中，请勿重复提交！")

    report = CommunityReport(
        post_id=post_id,
        reporter_id=user.id,
        reason=req.reason,
        detail=req.detail.strip() if req.detail else "食友提交违规审核",
        status="pending"
    )
    db.add(report)
    db.add(UserActivity(user_id=user.id, activity_type="report", note=f"举报动态ID:{post_id}(理由:{req.reason})"))
    await db.commit()

    return {"message": "举报已成功提交！管理员控制台已收到工单并将核实处置。"}

# 10. 删除自己的动态 (删除后不影响已被其他食友收藏保存的菜谱)
@router.delete("/posts/{post_id}")
async def delete_community_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    stmt = select(CommunityPost).where(CommunityPost.id == post_id)
    post = (await db.execute(stmt)).scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="动态不存在")

    is_admin = (user.role in ["admin", "super_admin"] or user.id == 1 or user.username == "admin")
    if post.user_id != user.id and not is_admin:
        raise HTTPException(status_code=403, detail="无权删除他人的美食动态")

    title = post.title
    await db.delete(post)
    await db.commit()
    return {"message": f"动态「{title}」已彻底删除"}