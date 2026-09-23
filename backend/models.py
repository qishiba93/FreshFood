"""
backend/models.py
ORM 数据模型定义
包含: 用户账户、健康画像、在库食材、收藏菜谱(长文本指标)、备菜清单、标准图库、减碳账本、社区发帖、点赞防重、评论、风控举报、审计日志
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON, ForeignKey, UniqueConstraint
from backend.database import Base

class User(Base):
    """用户账户表"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(64), unique=True, index=True, nullable=False, comment="用户名")
    hashed_password = Column(String(128), nullable=False, comment="哈希密码")
    role = Column(String(16), nullable=False, default="user", comment="角色: super_admin / admin / user")
    status = Column(Integer, nullable=False, default=1, comment="状态: 1-正常, 0-禁用")
    created_at = Column(DateTime, default=datetime.now, comment="注册时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

class UserHealthProfile(Base):
    """家庭成员健康状况画像表"""
    __tablename__ = "user_health_profiles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="归属账户ID")
    member_name = Column(String(64), nullable=False, comment="成员称呼")
    relation = Column(String(32), nullable=False, default="self", comment="关系: self / parent / child / spouse / other")
    conditions = Column(JSON, nullable=False, default=list, comment="自主输入的身体状况标签列表(JSON格式存储)")
    dietary_notes = Column(String(255), nullable=True, comment="其他特殊忌口或医嘱备忘")
    is_primary = Column(Integer, default=0, comment="是否是本人主档案: 1-是, 0-否")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

class PantryItem(Base):
    """冰箱在库食材表"""
    __tablename__ = "pantry_items"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True, comment="归属用户ID")
    name = Column(String(64), nullable=False, index=True, comment="食材通用名")
    location = Column(String(32), nullable=False, index=True, comment="存放位置: refrigeration(冷藏) / freezer(冷冻)")
    initial_weight = Column(Float, nullable=False, default=0.0, comment="初始录入克重")
    remaining_weight = Column(Float, nullable=False, default=0.0, comment="当前剩余克重")
    unit = Column(String(16), nullable=False, default="克", comment="计量单位")
    expire_at = Column(DateTime, nullable=False, index=True, comment="保质期截止时间")
    image_url = Column(String(255), nullable=True, comment="图片路径 (标准图库优先，实拍图兜底)")
    created_at = Column(DateTime, default=datetime.now, comment="录入时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

class FavoriteRecipe(Base):
    """收藏菜谱表 (升级指标字段为Text长文本，彻底解决甲状腺控碘医嘱过长无法入库的问题)"""
    __tablename__ = "favorite_recipes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True, comment="归属用户ID")
    recipe_name = Column(String(128), nullable=False, index=True, comment="菜品名称")
    category = Column(String(32), default="custom", comment="分类")
    difficulty = Column(String(64), nullable=True, comment="难度与耗时")
    calories = Column(Text, nullable=True, comment="热量或首要健康指标(升级为Text长文本)")
    glycemic_info = Column(Text, nullable=True, comment="升糖或临床调理医嘱指标(升级为Text长文本)")
    ingredients_needed = Column(JSON, nullable=False, comment="主配料配比清单")
    pantry_staples = Column(Text, nullable=True, comment="常备调料")
    cooking_steps = Column(JSON, nullable=False, comment="做菜步骤")
    chef_tips = Column(Text, nullable=True, comment="大厨秘诀")
    created_at = Column(DateTime, default=datetime.now, comment="收藏时间")

class ShoppingItem(Base):
    """备菜采购清单表"""
    __tablename__ = "shopping_list"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True, comment="归属用户ID")
    name = Column(String(64), nullable=False, comment="需采买名称")
    amount = Column(String(64), nullable=True, comment="采买数量")
    source_recipe = Column(String(128), nullable=True, comment="来源菜谱")
    created_at = Column(DateTime, default=datetime.now, comment="加入清单时间")

class StandardFoodImage(Base):
    """官方统一标准食材图库表"""
    __tablename__ = "standard_food_images"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    food_name = Column(String(64), index=True, nullable=False, comment="标准食材名")
    synonyms = Column(String(255), nullable=True, comment="同义词/别名 (逗号分隔)")
    category = Column(String(32), default="other", comment="品类分类")
    image_url = Column(String(255), nullable=False, comment="标准高清图相对路径或URL")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

class UserCarbonLog(Base):
    """用户减碳明细账本表"""
    __tablename__ = "user_carbon_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="归属用户ID")
    item_name = Column(String(64), nullable=False, comment="消耗食材名")
    weight_grams = Column(Float, nullable=False, comment="消耗克重")
    carbon_saved_grams = Column(Float, nullable=False, comment="减碳贡献克数 (克 CO2e)")
    food_category = Column(
        String(16),
        nullable=False,
        default="vegetarian",
        index=True,
        comment="食材分类: vegetarian / non_vegetarian",
    )
    source_recipe = Column(String(128), nullable=True, comment="关联制作菜名")
    created_at = Column(DateTime, default=datetime.now, index=True, comment="发生时间")

class CommunityPost(Base):
    """美食社区做菜分享表"""
    __tablename__ = "community_posts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="发布作者ID")
    title = Column(String(128), nullable=False, comment="动态标题/菜品名")
    content = Column(Text, nullable=False, comment="做菜心得与体会")
    image_url = Column(String(255), nullable=False, comment="菜品成品图片")
    recipe_data = Column(JSON, nullable=True, comment="绑定的菜谱完整JSON数据")
    likes_count = Column(Integer, default=0, comment="点赞总数")
    status = Column(Integer, default=1, comment="状态: 1-正常展示, 0-违规下架屏蔽")
    created_at = Column(DateTime, default=datetime.now, index=True, comment="发布时间")

class PostLike(Base):
    """社区点赞防重记录表"""
    __tablename__ = "community_post_likes"
    __table_args__ = (UniqueConstraint('post_id', 'user_id', name='uq_post_user_like'),)

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now)

class PostComment(Base):
    """社区评论留言表"""
    __tablename__ = "community_post_comments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(String(500), nullable=False, comment="评论内容")
    status = Column(Integer, default=1, comment="1-正常, 0-屏蔽")
    created_at = Column(DateTime, default=datetime.now, index=True)

class CommunityReport(Base):
    """社区内容举报风控表"""
    __tablename__ = "community_reports"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=False, index=True, comment="被举报帖子ID")
    reporter_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="举报人ID")
    reason = Column(String(64), nullable=False, comment="举报分类: violence/porn/spam/unrelated/other")
    detail = Column(String(255), nullable=True, comment="补充说明")
    status = Column(String(16), default="pending", comment="审核状态: pending-待审核 / approved-已下架 / rejected-已驳回")
    admin_note = Column(String(255), nullable=True, comment="管理员审核批注")
    created_at = Column(DateTime, default=datetime.now, index=True, comment="举报时间")
    handled_at = Column(DateTime, nullable=True, comment="处理时间")

class UserActivity(Base):
    """全局用户行为操作审计表"""
    __tablename__ = "user_activities"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="操作用户ID")
    activity_type = Column(String(32), nullable=False, comment="add / consume / collect / post / like / comment / report / login")
    note = Column(String(255), nullable=True, comment="操作详细说明")
    created_at = Column(DateTime, default=datetime.now, index=True, comment="操作发生时间")
