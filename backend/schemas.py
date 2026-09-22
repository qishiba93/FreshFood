"""
backend/schemas.py
Pydantic 数据验证模型规范
覆盖: 用户鉴权、自主身体状况、全省份菜系过滤、烹饪方式、烹饪耗时(需求5)、标准图库、食材核减、减碳核销、社区风控与菜谱溯源
"""
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field

class UserRegisterLogin(BaseModel):
    """用户公开注册与登录参数"""
    username: str = Field(..., min_length=2, max_length=32, description="登录用户名(至少2字符)")
    password: str = Field(..., min_length=4, max_length=64, description="登录密码(至少4字符)")

class AdminCreateUser(BaseModel):
    """管理员开通新账号专用参数"""
    username: str = Field(..., min_length=2, max_length=32, description="开通的账号名")
    password: str = Field(..., min_length=4, max_length=64, description="初始密码")
    role: str = Field("user", pattern="^(admin|user)$", description="分配的角色权限: admin 或 user")

class AdminResetPassword(BaseModel):
    """管理员强制重置用户密码参数"""
    new_password: str = Field(..., min_length=4, max_length=64, description="重置后的新密码")


class HealthProfileCreate(BaseModel):
    """创建健康状况档案 (本人或家庭成员)"""
    member_name: str = Field(..., min_length=1, max_length=32, description="家庭成员称呼 (如: 本人、爸爸、妈妈、宝宝)")
    relation: str = Field("self", pattern="^(self|parent|child|spouse|other)$", description="家庭关系")
    conditions: List[str] = Field(default=[], description="自主填写的身体状况标签列表 (支持文字自由输入，如: 痛风、二型糖尿病、胃炎不能吃生冷)")
    dietary_notes: Optional[str] = Field(None, max_length=255, description="补充忌口医嘱与备忘")
    is_primary: Optional[int] = Field(0, description="是否是本人主档案: 1-是, 0-否")

class HealthProfileUpdate(BaseModel):
    """编辑健康状况档案"""
    member_name: Optional[str] = Field(None, min_length=1, max_length=32, description="修改成员称呼")
    relation: Optional[str] = Field(None, description="修改关系")
    conditions: Optional[List[str]] = Field(None, description="更新身体状况标签")
    dietary_notes: Optional[str] = Field(None, description="更新忌口备忘")
    is_primary: Optional[int] = Field(None, description="是否更新本人标识")

class HealthProfileOut(BaseModel):
    """健康档案前端响应模型"""
    id: int
    member_name: str
    relation: str
    conditions: List[str]
    dietary_notes: Optional[str]
    is_primary: int
    created_at: str

    class Config:
        from_attributes = True


class RecipeFilterParams(BaseModel):
    """常规菜谱多维过滤器 (支持 34 省份菜系、烹饪方式、烹饪耗时与用餐场景)"""
    cuisine: str = Field("chinese", pattern="^(chinese|western)$", description="菜系大类: chinese-中餐, western-西餐")
    sub_cuisine: Optional[str] = Field(None, description="细分省份菜系")
    cooking_method: Optional[str] = Field(None, description="烹饪方式")
    cooking_time: Optional[str] = Field(None, description="烹饪时间: under_10/10_to_20/over_20")
    meal_type: str = Field("dinner", pattern="^(breakfast|lunch|dinner)$", description="用餐时段: breakfast-早餐, lunch-午餐, dinner-晚餐")
    people_count: int = Field(2, ge=1, le=10, description="就餐人数")

class CustomHealthRecipeRequest(BaseModel):
    """特殊定制菜谱请求参数 (勾选家庭成员自动锁定人数 + 烹饪方式 + 烹饪时间)"""
    selected_profile_ids: List[int] = Field(..., min_items=1, description="勾选的有健康关注的家庭成员ID列表")
    cuisine: str = Field("chinese", pattern="^(chinese|western)$", description="菜系大类")
    sub_cuisine: Optional[str] = Field(None, description="细分省份菜系")
    cooking_method: Optional[str] = Field(None, description="烹饪方式")
    cooking_time: Optional[str] = Field(None, description="烹饪时间: under_10/10_to_20/over_20")
    meal_type: str = Field("dinner", pattern="^(breakfast|lunch|dinner)$", description="用餐时段")


class PantryItemCreate(BaseModel):
    """录入生鲜食材"""
    name: str = Field(..., min_length=1, max_length=64, description="食材名称")
    location: str = Field(..., pattern="^(refrigeration|freezer)$", description="存放温区: refrigeration(冷藏) / freezer(冷冻)")
    initial_weight: float = Field(..., gt=0, description="初始称重克重")
    remaining_weight: Optional[float] = Field(None, description="当前剩余克重 (默认等于初始克重)")
    unit: str = Field("克", max_length=16, description="计量单位")
    shelf_life_days: float = Field(..., gt=0, description="保质期天数")
    image_url: Optional[str] = Field(None, description="实拍图片路径 (未匹配到标准图库时使用)")

class DeductWeightRequest(BaseModel):
    """单项食材消耗扣减"""
    deduct_weight: float = Field(..., gt=0, description="实际做菜消耗克重")
    recipe_name: Optional[str] = Field("日常烹饪", description="关联制作的菜品名称")

class BatchDeductItem(BaseModel):
    """批量核销单项清单条目"""
    item_id: int = Field(..., description="在库食材 ID")
    deduct_weight: float = Field(..., gt=0, description="该食材消耗克重")

class BatchDeductRequest(BaseModel):
    """批量食材做菜核销 (原子事务 + AI 动态减碳估算)"""
    recipe_name: Optional[str] = Field("定制佳肴", description="关联制作的菜品名称")
    items: List[BatchDeductItem] = Field(..., min_items=1, description="待扣减的食材列表")


class ShoppingItemBatchCreate(BaseModel):
    """批量导入备菜篮参数"""
    items: List[dict] = Field(..., description="需采购食材数组 (包含 name, amount, source_recipe)")


class FavoriteRecipeCreate(BaseModel):
    """收藏菜谱数据模型"""
    recipe_name: str = Field(..., min_length=1, max_length=128, description="菜品名称")
    category: str = Field("custom", description="菜谱分类: custom/custom_health/gout/goiter/low_fat/diabetic/today")
    difficulty: Optional[str] = Field(None, description="难度与耗时")
    calories: Optional[str] = Field(None, description="热量指标")
    glycemic_info: Optional[str] = Field(None, description="升糖/健康专属评估指标")
    ingredients_needed: List[Any] = Field(default=[], description="主配料配比清单")
    pantry_staples: Optional[str] = Field(None, description="常备调料清单")
    cooking_steps: List[str] = Field(default=[], description="烹饪步骤描述列表")
    chef_tips: Optional[str] = Field(None, description="大厨技巧要点")


class StandardFoodImageCreate(BaseModel):
    """管理员录入标准图库条目"""
    food_name: str = Field(..., min_length=1, max_length=64, description="标准食材名 (如: 番茄)")
    synonyms: Optional[str] = Field(None, description="同义词/别名，英文逗号分隔 (如: 西红柿,小番茄,洋柿子)")
    category: str = Field("other", pattern="^(vegetable|meat|seafood|fruit|staple|other)$", description="品类分类")
    image_url: str = Field(..., min_length=1, description="官方标准高清图本地/服务器路径")


class CommunityPostCreate(BaseModel):
    """发布社区做菜打卡"""
    title: str = Field(..., min_length=1, max_length=128, description="动态标题或菜品名称")
    content: str = Field(..., min_length=1, max_length=1000, description="做菜心得与操作体会")
    image_url: str = Field(..., min_length=1, description="成品菜品实拍图片路径")
    recipe_data: Optional[Dict[str, Any]] = Field(None, description="绑定的完整菜谱对象(JSON，供食友一键收藏)")

class PostCommentCreate(BaseModel):
    """食友互动评论留言"""
    content: str = Field(..., min_length=1, max_length=300, description="评论内容")

class CommunityReportCreate(BaseModel):
    """提交违规内容举报"""
    reason: str = Field(..., pattern="^(violence|porn|spam|unrelated|other)$", description="违规分类: violence(血腥暴力)/porn(低俗)/spam(广告垃圾)/unrelated(无关内容)/other")
    detail: Optional[str] = Field(None, max_length=200, description="详细举报原因描述")

class ReportHandleRequest(BaseModel):
    """管理员处置违规举报工单"""
    action: str = Field(..., pattern="^(approve_hide|approve_delete|reject)$", description="处置动作: approve_hide(下架屏蔽)/approve_delete(物理删除)/reject(驳回举报)")
    admin_note: Optional[str] = Field(None, max_length=200, description="管理员处置批注说明")