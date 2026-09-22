"""
backend/routers/recipe.py
菜谱生成路由
支持：中国34省份特色菜系 + 5大西式风味 + 中餐13种经典技法 + 西餐8大经典技法 + 中西动态切换 + 烹饪时间静默推导与早中晚餐智能时间隐形兜底
"""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.database import get_db
from backend.models import PantryItem, FavoriteRecipe, User, UserActivity, UserHealthProfile
from backend.schemas import FavoriteRecipeCreate, CustomHealthRecipeRequest
from backend.services.ai_service import (
    generate_recipe_with_pantry,
    generate_special_recipe,
    generate_custom_family_health_recipe,
    generate_today_eat_recipes
)
from backend.auth import get_current_user

router = APIRouter(prefix="/api/recipes", tags=["智能菜谱与健康定制"])

# ==================== 1. 本地静默烹饪时间推导算法 (用户端不可见，AI 静默读取) ====================
def resolve_cooking_time(meal_type: str, user_cooking_time: Optional[str]) -> str:
    """
    烹饪时间解析规则（纯后端本地逻辑，前端无感知）：
    1. 用户若主动选择了耗时范围 -> 尊重用户选择：
       - under_10: 严格控制在 10 分钟以内
       - 10_to_20: 控制在 10 ~ 20 分钟
       - over_20: 20 分钟以上
    2. 用户未选择耗时（保持默认/推荐） -> 本地静默根据餐别自动兜底指示 AI：
       - 早餐 (breakfast) -> 严格控制在 10 分钟以内（快手轻盈）
       - 午餐 (lunch)     -> 控制在 10 ~ 20 分钟（家常高效）
       - 晚餐 (dinner)    -> 20 分钟以上（慢火细煨充分入味）
    """
    time_clean = (user_cooking_time or "").strip().lower()

    # 用户手动指定了耗时
    if time_clean in ["under_10", "10分钟以内", "小于10分钟", "10分钟内"]:
        return "必须严格控制在 10 分钟以内（极速快手烹调技法，步骤利落干脆，并在 difficulty 标注具体分钟）"
    elif time_clean in ["10_to_20", "10到20分钟", "10-20分钟"]:
        return "烹饪耗时控制在 10 ~ 20 分钟（家常火候适度，兼顾口感与效率，并在 difficulty 标注具体分钟）"
    elif time_clean in ["over_20", "20分钟以上", "大于20分钟"]:
        return "烹饪耗时须在 20 分钟以上（适于慢火细炖、充分煸透或慢烤入味，并在 difficulty 标注具体分钟）"

    # 用户未选耗时，静默根据餐别自动兜底指示给 AI
    meal_clean = (meal_type or "dinner").strip().lower()
    if meal_clean == "breakfast":
        return "严格控制在 10 分钟以内（晨间快手速熟，并在 difficulty 标注具体分钟）"
    elif meal_clean == "lunch":
        return "烹饪耗时控制在 10 ~ 20 分钟（午间家常烹饪节奏，并在 difficulty 标注具体分钟）"
    else:
        return "烹饪耗时须在 20 分钟以上（晚间慢火烹饪充分入味，并在 difficulty 标注具体分钟）"

# ==================== 2. 烹饪方式映射（中餐 13 种经典 + 西餐 8 种经典） ====================
CHINESE_COOKING_METHOD_MAP = {
    "peng": "【烹·急汁脆出】先将主料炸脆或煎熟，再趁热烹入调好清汁，急火快出，使其香气扑鼻，外脆里嫩。",
    "chao": "【炒·镬气快炒】热锅滑油，旺火急炒，食材在极短时间内迅速受热断生，镬气十足，清脆滑爽。",
    "jian": "【煎·香脆微焦】平底微油，中小火慢煎至双面金黄微焦，内里多汁，焦香诱人。",
    "zhu": "【煮·原汤透鲜】以水或高汤为介质慢滚熟化，原汤透味，汤清肉嫩，温润滋补。",
    "zha": "【炸·外酥里嫩】宽油浸润，高温瞬间锁住食材内部水分，呈现外酥里嫩、香脆浓郁的口感。",
    "zheng": "【蒸·清鲜锁水】足气隔水蒸熟，最大程度锁住食材本原鲜味与水分，营养无损，少油低负。",
    "kao": "【烤·焦香多汁】利用干热辐射烘烤，油脂滋滋渗透，形成美拉德反应浓郁焦香，外韧内软。",
    "dun": "【炖·文火慢煨】加入足量鲜汤文火长时慢炖，让胶原与风味分子充分融出，汤醇肉烂，浓郁厚重。",
    "men": "【焖·黄焖软烂】微火盖锅长时间煨烧，使汁浓味厚，食材由表及里极度软烂酥松入味。",
    "chao_water": "【焯·清脆断生】将食材放入开水中短时烫透，去除血沫、草酸或异味，保持脆嫩爽口与色泽。",
    "bian": "【煸·干香透味】不加水或少油，将食材直接入锅受热逼出自身多余水分与油脂，紧致干香而不焦糊。",
    "cuan": "【汆·细料清滚】鲜汤快滚将极嫩细料瞬烫即熟，汤清澈见底，食材滑嫩爽口，鲜香四溢。",
    "liangban": "【凉拌·爽口开胃】将熟化冷却或生鲜食材改刀，调以葱姜蒜、香醋、香油或秘制红油拌和，清爽解腻。"
}

WESTERN_COOKING_METHOD_MAP = {
    "pan_sear": "【香煎/嫩煎 (Pan-sear)】平底厚底锅微油大火封边锁汁，再转中火形成美拉德香脆外壳，内里软嫩多汁。",
    "roast_bake": "【烘烤/焗烤 (Roast/Bake)】烤箱全方位立体干热烘烤或撒芝士焗烤，高温激发油脂与香草浓郁香气，金黄香脆。",
    "braise_stew": "【慢炖/红酒烩 (Braise/Stew)】食材先微煎上色，倒入红酒或高汤盖锅文火细煨，使肉质酥烂入味，浓汁包裹。",
    "sous_vide": "【低温慢煮 (Sous-vide)】真空密封配合恒温水浴长时间熟化，细胞不破损水分零流失，彻底锁住原生鲜嫩原汁。",
    "deep_fry": "【酥炸 (Deep-fry)】裹以面包糠或调味脆浆高温浸炸，外层酥脆掉渣，内部食材紧锁肉汁不干柴。",
    "grill": "【炭烤/扒烤 (Grill)】在高温明火烤架上快速炙烤，留下标志性格子焦痕，带有迷人炭烟熏木香。",
    "toss_salad": "【轻拌沙拉 (Toss)】以特级初榨橄榄油、黑醋、柠檬汁或经典酱汁轻盈翻拌，保留食材清脆本味与鲜艳色泽。",
    "simmer_chowder": "【微沸煨汤 (Simmer/Chowder)】以黄油炒香基底，加入奶油、海鲜或浓汤微沸煨煮，汤质丝滑浓郁醇厚。"
}

COOKING_METHOD_MAP = {**CHINESE_COOKING_METHOD_MAP, **WESTERN_COOKING_METHOD_MAP}

def build_cooking_method_description(method: Optional[str]) -> str:
    if not method or method.strip() in ["", "any", "default", "none", "不限", "推荐"]:
        return "大厨推荐适宜技法（根据食材特质自由选择最契合的烹饪方式）"

    clean_m = method.strip().lower()
    if clean_m in COOKING_METHOD_MAP:
        return COOKING_METHOD_MAP[clean_m]

    for k, v in COOKING_METHOD_MAP.items():
        if k in clean_m or clean_m in k:
            return v

    return f"指定采用【{method}】烹饪技法（步骤与调味必须严格围绕该技法设计）"

# ==================== 3. 菜系风味映射（中餐34省份 + 西餐5大流派） ====================
PROVINCIAL_CUISINE_MAP = {
    "鲁菜": "中国鲁菜流派（发源山东，讲究汤清鲜美、葱香浓郁、尤擅爆炒、葱烧、熘、扒，醇厚鲜咸）",
    "川菜": "中国川菜流派（发源四川，讲究一菜一格、百菜百味，擅调麻辣、鱼香、怪味、红油与复合家常味）",
    "粤菜": "中国粤菜流派（发源广东，讲究清鲜嫩滑爽、原汁原味、注重食材本真鲜度，擅白灼、清蒸、煲汤、快炒）",
    "苏菜": "中国苏菜/淮扬流派（发源江苏，讲究咸甜适度、汁浓不腻、精工细作、原汁原汤、温润高雅）",
    "浙菜": "中国浙菜流派（发源浙江，讲究清爽脆嫩、鲜美滑嫩、注重江南水乡淡雅风味，擅烹河鲜海蔬）",
    "闽菜": "中国闽菜流派（发源福建，讲究鲜香清甜、擅调红糟、善烹海鲜海产、汤菜丰富多样）",
    "湘菜": "中国湘菜流派（发源湖南，讲究香辣酸辣、焦脆腊香、油厚入味、尤擅煨炖小炒与剁椒风味）",
    "徽菜": "中国徽菜流派（发源安徽，讲究重油重色、芡亮味浓、擅长慢火烧炖、山野土产风味醇厚）",
    "东北菜": "中国东北风味（黑龙江/吉林/辽宁，讲究豪放量大、咸鲜醇厚、擅炖、酱、熘，擅长酸菜白肉与酱骨慢炖）",
    "京菜": "中国京菜流派（北京官府与家常风味，讲究酱香浓郁、清脆滑爽、擅扒炸爆烤、兼容并包）",
    "津菜": "中国津菜流派（天津风味，擅烹河海两鲜、咸鲜微甜、芡亮汁紧、软溜扒炒见长）",
    "冀菜": "中国冀菜流派（河北风味，讲究咸鲜适口、质朴浓香、擅长酱汁扒炒与原盅慢炖）",
    "晋菜": "中国晋菜流派（山西风味，讲究咸香适中、擅调老陈醋烹香、风味清香不腻、与杂粮面食绝配）",
    "豫菜": "中国豫菜流派（河南中原风味，讲究五味调和、质味适中、不偏不倚、四平八稳、擅烩煨扒蒸）",
    "内蒙古菜": "中国内蒙古风味（内蒙古大草原流派，以牛羊肉、奶制品为主，讲究炙烤清炖、原汁原味、粗犷浓郁）",
    "鄂菜": "中国鄂菜流派（湖北风味，以水产鱼鲜见长，讲究汁浓芡亮、鲜嫩微辣、善用蒸煨煎炸）",
    "赣菜": "中国赣菜流派（江西风味，讲究原汁原味、油厚不腻、辛辣咸香、尤以瓦罐慢火煨汤著称）",
    "沪菜": "中国本帮菜流派（上海风味，讲究浓油赤酱、咸中带甜、糟醉香浓、虾蟹小海鲜精致制作）",
    "滇菜": "中国滇菜流派（云南风味，讲究鲜嫩清香、酸辣回甘、擅用天然野生菌、香茅草、薄荷与山野草本提香）",
    "黔菜": "中国黔菜流派（贵州风味，讲究辣醇酸美、以糊辣、糟辣、酸汤为灵魂，开胃生津、个性鲜明）",
    "渝菜": "中国重庆江湖菜（讲究麻辣火爆、大盘粗犷、重油亮色、善用鲜青椒、老姜与豆瓣火爆入味）",
    "藏菜": "中国西藏风味（青藏高原流派，讲究清淡醇香、少繁复香料、注重牛羊牦牛及青稞食材本原风味）",
    "陕菜": "中国陕菜流派（陕西三秦风味，讲究鲜香酸辣、浓烈豪放、善用油泼辣子与岐山香醋调味）",
    "陇菜": "中国陇菜流派（甘肃风味，以牛羊肉见长，讲究咸鲜微辣、醇厚绵长、擅烹清真与丝路风味）",
    "青海菜": "中国青海风味（高原特色，牛羊肉与高原青稞结合，讲究原汁原味、砂锅慢煨、酥油清润）",
    "宁夏菜": "中国宁夏风味（回乡风味，以滩羊、枸杞著称，肉质鲜美无膻，讲究手抓白煮、清蒸原香）",
    "新疆菜": "中国新疆风味（丝路风味，擅用孜然、洋葱、番茄与红辣椒，风味浓烈、炙烤多汁）",
    "桂菜": "中国桂菜流派（广西风味，讲究微辣酸鲜、善用酸笋、柠檬、沙姜等果酸发酵香气，山野灵动）",
    "琼菜": "中国琼菜流派（海南风味，以清淡甜美、海味椰香著称，善用白斩、清蒸，注重热带食材鲜嫩）",
    "台菜": "中国台湾风味（讲究清鲜咸甜、擅用黑麻油、九层塔、红糟与三杯技法，具有浓厚海岛古早味）",
    "港澳菜": "中国港澳风味（中西融汇流派，既有粤菜的精致炖汤与避风塘火候，又有西式酱汁复合风味）"
}

WESTERN_CUISINE_MAP = {
    "意式风味": "经典意大利流派（注重初榨橄榄油、番茄、新鲜罗勒、牛至、黑醋与帕玛森奶酪，原汁原味且富有阳光气息）",
    "法式风味": "精致法餐流派（讲究精密火候控制、法式母酱慢熬慢调、红酒与优质黄油渗透，口感醇厚丝滑细腻）",
    "地中海风味": "地中海健康流派（高比例特级初榨橄榄油、新鲜香草、丰富海鲜与时令蔬果，清爽少盐无负担）",
    "美式风味": "美式炙烤与乡村家常（粗犷量大、经典烟熏烤肉酱、黑胡椒与焦香蒜蓉风味，肉香直爽浓郁）",
    "西式轻食": "低卡轻食流派（无油/少油轻煎、低温水浴熟化，配合天然坚果与油醋汁轻拌，保留食材清纯质感）"
}

def build_cuisine_description(cuisine: str, sub_cuisine: Optional[str] = None) -> str:
    if cuisine == "western":
        if sub_cuisine and sub_cuisine.strip():
            sub = sub_cuisine.strip()
            for key, desc in WESTERN_CUISINE_MAP.items():
                if key in sub or sub in key:
                    return desc
            return f"精致西餐料理【{sub}】风格（注重香草调味、煎烤烘焙、保留食材原生质感）"
        return "经典精致西餐料理风味（注重香草调味、煎烤烘焙、保留食材原生质感）"

    if not sub_cuisine or sub_cuisine.strip() in ["", "家常", "通用", "default"]:
        return "经典中式家常风味（五味调和、清爽利落、营养均衡）"

    sub = sub_cuisine.strip()
    for key, desc in PROVINCIAL_CUISINE_MAP.items():
        if key in sub or sub in key:
            return desc

    return f"中国传统中餐【{sub}】特色流派（严格遵循该地区的标志性风味与经典烹饪技法）"

def map_meal_type_desc(m: str) -> str:
    mapping = {
        "breakfast": "早餐",
        "lunch": "午餐",
        "dinner": "晚餐"
    }
    return mapping.get(m, "营养正餐")

async def get_user_health_summary(db: AsyncSession, user_id: int) -> str:
    stmt = select(UserHealthProfile).where(UserHealthProfile.user_id == user_id)
    res = await db.execute(stmt)
    profiles = res.scalars().all()

    if not profiles:
        return "用户未登记特殊健康体质，自由发挥即可"

    summary_parts = []
    for p in profiles:
        if p.conditions:
            conds_cn = []
            for c in p.conditions:
                cn_map = {
                    "gout": "痛风高尿酸(严格低嘌呤)",
                    "diabetes": "糖尿病(低升糖低碳水)",
                    "low_fat": "减脂低卡(低脂少油)",
                    "goiter": "甲状腺肿大(控碘/熟化十字花科)",
                    "hypertension": "高血压(严格少盐)"
                }
                conds_cn.append(cn_map.get(c, c))
            summary_parts.append(f"{p.member_name}关注: {'、'.join(conds_cn)}")
        if p.dietary_notes:
            summary_parts.append(f"{p.member_name}忌口: {p.dietary_notes}")

    return "【家庭体质红线】： " + "；".join(summary_parts) if summary_parts else "体质正常，注重均衡"

async def get_pantry_ingredients_with_urgency(db: AsyncSession, user_id: int, exclude_id: int = None) -> str:
    now = datetime.now()
    stmt = (
        select(PantryItem)
        .where(PantryItem.user_id == user_id, PantryItem.remaining_weight > 0, PantryItem.expire_at > now)
        .order_by(PantryItem.expire_at.asc())
    )
    if exclude_id:
        stmt = stmt.where(PantryItem.id != exclude_id)

    res = await db.execute(stmt)
    items = res.scalars().all()
    if not items:
        return "冰箱内暂无其他辅助食材可用。"

    lines = []
    for item in items:
        hours_left = max(0.1, round((item.expire_at - now).total_seconds() / 3600.0, 1))
        if hours_left <= 48:
            lines.append(f"- 【临期急需消耗】{item.name}（余 {item.remaining_weight}{item.unit}，仅剩 {hours_left} 小时过期！）")
        else:
            lines.append(f"- {item.name}（余 {item.remaining_weight}{item.unit}，保质期剩余约 {round(hours_left/24, 1)} 天）")

    return "\n".join(lines)

async def get_simple_unexpired_ingredients(db: AsyncSession, user_id: int) -> list:
    now = datetime.now()
    stmt = select(PantryItem.name).where(PantryItem.user_id == user_id, PantryItem.remaining_weight > 0, PantryItem.expire_at > now)
    res = await db.execute(stmt)
    return list(set(res.scalars().all()))

async def get_recent_avoid_dishes(db: AsyncSession, user_id: int) -> list:
    stmt = select(FavoriteRecipe.recipe_name).where(FavoriteRecipe.user_id == user_id).order_by(FavoriteRecipe.created_at.desc()).limit(20)
    res = await db.execute(stmt)
    return list(set(res.scalars().all()))

# ==================== 接口区 ====================

@router.get("/cuisines/china-regions")
async def get_chinese_cuisines():
    """向下兼容老接口"""
    return [
        {"name": k, "desc": v.split("（")[1].replace("）", "")}
        for k, v in PROVINCIAL_CUISINE_MAP.items()
    ]

@router.get("/config/options")
async def get_recipe_dynamic_options():
    """
    全新多维中西餐与烹饪技法配置接口
    输出完整的长文本描述，供前端实现多行自动展开（不删任何字）
    """
    return {
        "chinese": {
            "cuisines": [
                {"name": k, "desc": v.split("（")[1].replace("）", "") if "（" in v else v}
                for k, v in PROVINCIAL_CUISINE_MAP.items()
            ],
            "methods": [
                {"key": k, "text": v}
                for k, v in CHINESE_COOKING_METHOD_MAP.items()
            ]
        },
        "western": {
            "cuisines": [
                {"name": k, "desc": v.split("（")[1].replace("）", "") if "（" in v else v}
                for k, v in WESTERN_CUISINE_MAP.items()
            ],
            "methods": [
                {"key": k, "text": v}
                for k, v in WESTERN_COOKING_METHOD_MAP.items()
            ]
        }
    }

# 1. 冰箱在库食材协同生成菜谱 (烹饪方式 + 烹饪时间静默兜底)
@router.get("/pantry-item/{item_id}")
async def get_recipe_for_item(
    item_id: int,
    people_count: int = Query(2, ge=1, le=10, description="用餐人数"),
    cuisine: str = Query("chinese", pattern="^(chinese|western)$", description="菜系大类"),
    sub_cuisine: Optional[str] = Query(None, description="细分省份或西餐风味"),
    cooking_method: Optional[str] = Query(None, description="烹饪方式"),
    cooking_time: Optional[str] = Query(None, description="烹饪耗时: under_10 / 10_to_20 / over_20 (不选则自动隐式兜底)"),
    meal_type: str = Query("dinner", pattern="^(breakfast|lunch|dinner)$", description="餐别"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    stmt = select(PantryItem).where(PantryItem.id == item_id, PantryItem.user_id == user.id)
    item = (await db.execute(stmt)).scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="未找到该食材")

    if item.expire_at <= datetime.now():
        raise HTTPException(status_code=400, detail="该食材已过期变质，出于健康安全考虑，系统拒绝为其生成菜谱，请及时清除！")

    urgency_ingredients_str = await get_pantry_ingredients_with_urgency(db, user.id, exclude_id=item.id)
    health_desc = await get_user_health_summary(db, user.id)
    cuisine_desc = build_cuisine_description(cuisine, sub_cuisine)
    cooking_method_desc = build_cooking_method_description(cooking_method)
    cooking_time_desc = resolve_cooking_time(meal_type, cooking_time)

    recipe_json = await generate_recipe_with_pantry(
        food_name=item.name,
        remaining_weight=item.remaining_weight,
        unit=item.unit,
        people_count=people_count,
        available_ingredients_with_urgency=urgency_ingredients_str,
        cuisine_desc=cuisine_desc,
        cooking_method_desc=cooking_method_desc,
        cooking_time_desc=cooking_time_desc,
        meal_type_desc=map_meal_type_desc(meal_type),
        health_condition_desc=health_desc
    )
    return recipe_json

# 2. 单病种专业定制 (低脂/控糖/痛风/甲状腺 + 烹饪方式 + 烹饪时间静默兜底)
@router.get("/special")
async def get_special_recipe(
    recipe_type: str = Query(..., pattern="^(low_fat|diabetic|gout|goiter)$", description="支持低脂、糖尿病、痛风少嘌呤、甲状腺"),
    people_count: int = Query(2, ge=1, le=10),
    cuisine: str = Query("chinese", pattern="^(chinese|western)$"),
    sub_cuisine: Optional[str] = Query(None, description="细分菜系风味"),
    cooking_method: Optional[str] = Query(None, description="烹饪方式"),
    cooking_time: Optional[str] = Query(None, description="烹饪耗时"),
    meal_type: str = Query("dinner", pattern="^(breakfast|lunch|dinner)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    valid_ingredients = await get_simple_unexpired_ingredients(db, user.id)
    avoid_dishes = await get_recent_avoid_dishes(db, user.id)
    cuisine_desc = build_cuisine_description(cuisine, sub_cuisine)
    cooking_method_desc = build_cooking_method_description(cooking_method)
    cooking_time_desc = resolve_cooking_time(meal_type, cooking_time)

    recipe_json = await generate_special_recipe(
        recipe_type=recipe_type,
        people_count=people_count,
        available_ingredients=valid_ingredients,
        avoid_dishes=avoid_dishes,
        cuisine_desc=cuisine_desc,
        cooking_method_desc=cooking_method_desc,
        cooking_time_desc=cooking_time_desc,
        meal_type_desc=map_meal_type_desc(meal_type)
    )
    return recipe_json

# 3. 特殊定制菜谱 (多成员体质公约数 + 烹饪方式 + 烹饪时间静默兜底)
@router.post("/custom-health")
async def get_custom_family_health_recipe(
    req: CustomHealthRecipeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    stmt = select(UserHealthProfile).where(
        UserHealthProfile.user_id == user.id,
        UserHealthProfile.id.in_(req.selected_profile_ids)
    )
    res = await db.execute(stmt)
    profiles = res.scalars().all()

    if not profiles:
        raise HTTPException(status_code=400, detail="请至少勾选一位已保存的家庭成员健康档案！")

    people_count = len(profiles)
    members_data = [
        {
            "member_name": p.member_name,
            "relation": p.relation,
            "conditions": p.conditions or [],
            "dietary_notes": p.dietary_notes
        }
        for p in profiles
    ]

    valid_ingredients = await get_simple_unexpired_ingredients(db, user.id)
    cuisine_desc = build_cuisine_description(req.cuisine, req.sub_cuisine)
    cooking_method_desc = build_cooking_method_description(req.cooking_method)
    cooking_time_desc = resolve_cooking_time(req.meal_type, req.cooking_time)

    recipe_json = await generate_custom_family_health_recipe(
        members_health_list=members_data,
        people_count=people_count,
        available_ingredients=valid_ingredients,
        cuisine_desc=cuisine_desc,
        cooking_method_desc=cooking_method_desc,
        cooking_time_desc=cooking_time_desc,
        meal_type_desc=map_meal_type_desc(req.meal_type)
    )
    recipe_json["auto_people_count"] = people_count
    return recipe_json

# 4. 今日吃啥双轨推荐 (烹饪方式 + 烹饪时间静默兜底)
@router.get("/today-what-to-eat")
async def get_today_what_to_eat(
    people_count: int = Query(2, ge=1, le=10, description="用餐人数前置确认"),
    cuisine: str = Query("chinese", pattern="^(chinese|western)$"),
    sub_cuisine: Optional[str] = Query(None, description="细分菜系风味"),
    cooking_method: Optional[str] = Query(None, description="烹饪方式"),
    cooking_time: Optional[str] = Query(None, description="烹饪耗时"),
    meal_type: str = Query("dinner", pattern="^(breakfast|lunch|dinner)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    valid_ingredients = await get_simple_unexpired_ingredients(db, user.id)
    health_desc = await get_user_health_summary(db, user.id)
    cuisine_desc = build_cuisine_description(cuisine, sub_cuisine)
    cooking_method_desc = build_cooking_method_description(cooking_method)
    cooking_time_desc = resolve_cooking_time(meal_type, cooking_time)

    recipes = await generate_today_eat_recipes(
        available_ingredients=valid_ingredients,
        people_count=people_count,
        cuisine_desc=cuisine_desc,
        cooking_method_desc=cooking_method_desc,
        cooking_time_desc=cooking_time_desc,
        meal_type_desc=map_meal_type_desc(meal_type),
        health_condition_desc=health_desc
    )
    return recipes

# 5. 收藏菜谱
@router.post("/favorites")
async def save_favorite_recipe(
    fav_in: FavoriteRecipeCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    clean_name = fav_in.recipe_name.strip()
    check_stmt = select(FavoriteRecipe).where(
        FavoriteRecipe.user_id == user.id,
        FavoriteRecipe.recipe_name == clean_name
    )
    existing = (await db.execute(check_stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail=f"菜谱「{clean_name}」已在您的收藏夹中！")

    fav = FavoriteRecipe(
        user_id=user.id,
        recipe_name=clean_name,
        category=fav_in.category or "custom",
        difficulty=fav_in.difficulty,
        calories=fav_in.calories,
        glycemic_info=fav_in.glycemic_info,
        ingredients_needed=fav_in.ingredients_needed or [],
        pantry_staples=fav_in.pantry_staples,
        cooking_steps=fav_in.cooking_steps or [],
        chef_tips=fav_in.chef_tips
    )
    db.add(fav)
    db.add(UserActivity(user_id=user.id, activity_type="collect", note=f"收藏菜谱:{clean_name}"))
    await db.commit()
    await db.refresh(fav)
    return {"message": f"菜谱「{clean_name}」收藏成功！", "id": fav.id}

# 6. 查询收藏夹
@router.get("/favorites")
async def list_favorite_recipes(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    stmt = select(FavoriteRecipe).where(FavoriteRecipe.user_id == user.id).order_by(FavoriteRecipe.created_at.desc())
    res = await db.execute(stmt)
    return res.scalars().all()

# 7. 按 ID 移除收藏
@router.delete("/favorites/{fav_id}")
async def delete_favorite_recipe(
    fav_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    stmt = select(FavoriteRecipe).where(FavoriteRecipe.id == fav_id, FavoriteRecipe.user_id == user.id)
    fav = (await db.execute(stmt)).scalar_one_or_none()
    if not fav:
        raise HTTPException(status_code=404, detail="收藏记录不存在")
    await db.delete(fav)
    await db.commit()
    return {"message": "已从收藏夹中移除", "recipe_name": fav.recipe_name}

# 8. 按名称取消收藏
@router.delete("/favorites/by-name/{recipe_name}")
async def delete_favorite_by_name(
    recipe_name: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    stmt = select(FavoriteRecipe).where(
        FavoriteRecipe.user_id == user.id,
        FavoriteRecipe.recipe_name == recipe_name.strip()
    )
    fav = (await db.execute(stmt)).scalar_one_or_none()
    if not fav:
        raise HTTPException(status_code=404, detail="该菜谱未在收藏夹中")
    await db.delete(fav)
    await db.commit()
    return {"message": "已取消收藏", "id": fav.id}