"""
backend/services/food_image_service.py
食材标准图片智能匹配与落图策略 (增强版：模糊容错、纯化抽取、本地标准图库优先)
"""
import os
import re
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models import StandardFoodImage
from backend.services.algorithms import fuzzy_ingredient_similarity

CATEGORY_DEFAULT_PLACEHOLDERS = {
    "meat": "/static/uploads/defaults/meat_default.png",
    "seafood": "/static/uploads/defaults/seafood_default.png",
    "vegetable": "/static/uploads/defaults/veg_default.png",
    "fruit": "/static/uploads/defaults/fruit_default.png",
    "staple": "/static/uploads/defaults/staple_default.png",
    "other": "/static/uploads/defaults/food_default.png"
}

class ResolvedImageResult:
    def __init__(self, final_url: str, is_from_standard: bool, matched_standard_name: Optional[str] = None):
        self.final_url = final_url
        self.is_from_standard = is_from_standard
        self.matched_standard_name = matched_standard_name

def clean_food_raw_name(raw_name: str) -> str:
    """去除数量、重量、修饰词等干扰，提取核心食材通用名"""
    text = raw_name.strip()
    # 过滤数量如: 500克、1斤、2个、300g等
    text = re.sub(r'\d+(\.\d+)?\s*(克|g|千克|kg|斤|两|个|只|根|块|盒|袋|把|头|包)?', '', text, flags=re.IGNORECASE)
    # 过滤常见前缀修饰
    text = re.sub(r'^(新鲜的?|精选|有机|手作|特级|野生|冷冻|速冻|生鲜|优质|家常|纯)', '', text)
    # 过滤多余符号
    text = re.sub(r'[()（）\[\]\s]', '', text)
    return text.strip() or raw_name.strip()

async def resolve_food_image(
    db: AsyncSession,
    food_name: str,
    user_uploaded_url: Optional[str] = None
) -> ResolvedImageResult:
    """
    落图核心规则:
    1. 优先查管理员维护的标准食材图库 (standard_food_images 表)；
    2. 支持去干扰纯化、精确对齐、同义词库包含、子串交叉包含以及 Levenshtein 模糊算法相似度；
    3. 未命中图库时，若用户有实拍图则使用实拍图；
    4. 兜底使用系统本地分类占位图。
    """
    raw_clean = food_name.strip()
    purified_name = clean_food_raw_name(raw_clean)

    stmt = select(StandardFoodImage)
    res = await db.execute(stmt)
    all_standards = res.scalars().all()

    best_match: Optional[StandardFoodImage] = None
    highest_score: float = 0.0

    for item in all_standards:
        std_name = item.food_name.strip()
        synonyms = [s.strip() for s in (item.synonyms or "").replace("，", ",").split(",") if s.strip()]
        all_candidate_names = [std_name] + synonyms

        # 1. 绝对精确匹配 (不管是原词还是纯化词)
        if raw_clean in all_candidate_names or purified_name in all_candidate_names:
            best_match = item
            break

        # 2. 交叉双向包含匹配
        matched_by_contain = False
        for c_name in all_candidate_names:
            if c_name in purified_name or purified_name in c_name:
                best_match = item
                matched_by_contain = True
                break
        if matched_by_contain:
            break

        # 3. 算法模糊相似度对齐 (阈值 >= 0.6)
        for c_name in all_candidate_names:
            score = fuzzy_ingredient_similarity(purified_name, c_name)
            if score > highest_score and score >= 0.6:
                highest_score = score
                best_match = item

    # 决策 1: 命中管理员标准图库
    if best_match and best_match.image_url:
        return ResolvedImageResult(
            final_url=best_match.image_url,
            is_from_standard=True,
            matched_standard_name=best_match.food_name
        )

    # 决策 2: 使用用户实拍图
    if user_uploaded_url and user_uploaded_url.strip():
        return ResolvedImageResult(
            final_url=user_uploaded_url.strip(),
            is_from_standard=False,
            matched_standard_name=None
        )

    # 决策 3: 兜底占位图
    return ResolvedImageResult(
        final_url=CATEGORY_DEFAULT_PLACEHOLDERS["other"],
        is_from_standard=False,
        matched_standard_name=None
    )