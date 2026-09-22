"""
backend/services/ai_service.py
AI 智能生成与多模态视觉研判服务 (支持烹饪技法与烹饪耗时定制)
"""
import os
import json
import re
import random
import base64
import httpx
from typing import Optional, Dict, Any
from dotenv import load_dotenv

from backend.prompts.recipe_prompt import (
    SYSTEM_RECIPE_PROMPT,
    USER_RECIPE_PROMPT_TEMPLATE
)
from backend.prompts.special_recipe_prompt import (
    SYSTEM_SPECIAL_RECIPE_PROMPT,
    SPECIAL_NUTRITION_RECIPE_PROMPT_TEMPLATE,
    CUSTOM_FAMILY_HEALTH_RECIPE_PROMPT_TEMPLATE,
    TODAY_WHAT_TO_EAT_PROMPT_TEMPLATE
)

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("AI_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL") or f"{os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com').rstrip('/')}/v1/chat/completions"
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

COMMUNITY_DISH_AUDIT_SYSTEM_PROMPT = """你是一名兼具五星级主厨素养与美食评论家眼光的顶级烹饪大师。
用户正在社区发布做菜打卡动态，提供了菜品标题、心得描述以及实拍照片。
你需要研判用户发布的内容是否确指一道【真实、合法且可烹饪制作的食物/菜品】。

【核心审核与生成准则】：
1. 真伪严谨断定：
   - 若内容与做菜烹饪无关（如宠物、自拍、风景、营销广告、随意输入的乱码废话），必须判定 is_dish 为 false，其余字段全部置为 null，绝不虚构任何菜谱！
   - 若确实是一道真实的菜品（包含家常自创料理），判定 is_dish 为 true，并根据菜名和描述逆向规划出一份严谨、可操作、风味出色的标准家常菜谱。
2. 菜品命名极简原则：
   - 生成的菜品名称必须简短好听、富有诗意与食欲，字数严格控制在 4 ~ 8 个汉字以内（如「葱香白灼虾」、「金玉翡翠羹」、「酱香小牛排」），严禁包含病症词或堆砌食材名称。
3. 格式规范：必须输出纯合法 JSON 格式，严禁包含任何 Markdown 标记。
"""

def clean_llm_json_response(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        json_match = re.search(r"(\{.*\})", text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        raise ValueError(f"大模型未返回合法的 JSON 内容: {raw_text[:200]}")

async def call_deepseek_llm(system_prompt: str, user_prompt: str) -> dict:
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.65,
        "response_format": {"type": "json_object"}
    }

    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.post(DEEPSEEK_API_URL, headers=headers, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"DeepSeek LLM 请求失败 [{resp.status_code}]: {resp.text}")
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return clean_llm_json_response(content)

# 1. 常规食材协同菜谱生成 (支持烹饪方式 + 烹饪时间)
async def generate_recipe_with_pantry(
    food_name: str,
    remaining_weight: float,
    unit: str,
    people_count: int,
    available_ingredients_with_urgency: str,
    cuisine_desc: str = "中式家常风味",
    cooking_method_desc: str = "大厨推荐适宜技法",
    cooking_time_desc: str = "10~20分钟",
    meal_type_desc: str = "舒适晚餐",
    health_condition_desc: str = "无特殊禁忌，注重营养均衡"
) -> dict:
    user_prompt = USER_RECIPE_PROMPT_TEMPLATE.format(
        food_name=food_name,
        remaining_weight=remaining_weight,
        unit=unit,
        people_count=people_count,
        cuisine_desc=cuisine_desc,
        cooking_method_desc=cooking_method_desc,
        cooking_time_desc=cooking_time_desc,
        meal_type_desc=meal_type_desc,
        health_condition_desc=health_condition_desc,
        available_ingredients_with_urgency=available_ingredients_with_urgency
    )
    return await call_deepseek_llm(SYSTEM_RECIPE_PROMPT, user_prompt)

# 2. 专业特殊菜谱生成 (支持四大单病种 + 烹饪方式 + 烹饪时间)
async def generate_special_recipe(
    recipe_type: str,
    people_count: int,
    available_ingredients: list,
    avoid_dishes: list,
    cuisine_desc: str = "中式家常",
    cooking_method_desc: str = "健康推荐技法",
    cooking_time_desc: str = "10~20分钟",
    meal_type_desc: str = "营养正餐"
) -> dict:
    config_map = {
        "low_fat": {
            "health_goal": "低脂减脂与体态管理",
            "metric_instruction": "【核心硬性指标】：只需且必须只显示单份总热量估算（如：单份约 310 kcal），严禁提及任何升糖、嘌呤、甲状腺无关信息。"
        },
        "diabetic": {
            "health_goal": "糖尿病控糖与稳糖",
            "metric_instruction": "【核心硬性指标】：只需且必须显示单份净碳水克重及餐后血糖预估波动范围（如：净碳水 18.5g，餐后血糖预估波动约 +1.2~1.8 mmol/L），严禁只报热量。"
        },
        "gout": {
            "health_goal": "痛风少嘌呤与尿酸平稳",
            "metric_instruction": "【核心硬性指标】：只需且必须评估单份总嘌呤估算值及等级（如：单份总嘌呤约 35mg · 极低嘌呤负荷，适合高尿酸人群），严格杜绝高嘌呤调料与食材。"
        },
        "goiter": {
            "health_goal": "甲状腺肿大人群专属膳食调理",
            "metric_instruction": "【核心硬性指标】：只需且必须给出单份碘摄入把控级别（微克 mcg）及致甲状腺肿物质灭活指南（十字花科食材必须煮透焯透说明）。"
        }
    }

    style_pool = ["葱香白灼温润流派", "低油清蒸原汁流派", "罗勒柠檬微酸提鲜", "五香慢煨少盐炖煮", "蒜蓉轻炒爽口流派"]
    cfg = config_map.get(recipe_type, config_map["low_fat"])

    user_prompt = SPECIAL_NUTRITION_RECIPE_PROMPT_TEMPLATE.format(
        recent_avoid_dishes="、".join(avoid_dishes) if avoid_dishes else "暂无历史黑名单",
        health_goal=cfg["health_goal"],
        metric_instruction=cfg["metric_instruction"],
        people_count=people_count,
        cuisine_desc=cuisine_desc,
        cooking_method_desc=cooking_method_desc,
        cooking_time_desc=cooking_time_desc,
        meal_type_desc=meal_type_desc,
        available_ingredients="、".join(available_ingredients) if available_ingredients else "暂无在库食材，请自由选用常见生鲜",
        random_style_seed=random.choice(style_pool)
    )
    return await call_deepseek_llm(SYSTEM_SPECIAL_RECIPE_PROMPT, user_prompt)

# 3. 家庭多成员体质特殊定制菜谱生成 (支持烹饪方式 + 烹饪时间)
async def generate_custom_family_health_recipe(
    members_health_list: list,
    people_count: int,
    available_ingredients: list,
    cuisine_desc: str = "中餐",
    cooking_method_desc: str = "全家适宜烹饪方式",
    cooking_time_desc: str = "10~20分钟",
    meal_type_desc: str = "正餐"
) -> dict:
    details_str_list = []
    for m in members_health_list:
        cond_str = "、".join(m.get("conditions", [])) if m.get("conditions") else "体质正常"
        note_str = f"（医嘱/忌口：{m.get('dietary_notes')}）" if m.get("dietary_notes") else ""
        details_str_list.append(f"- 成员【{m.get('member_name')}】({m.get('relation', '家人')}): 健康标签【{cond_str}】{note_str}")

    user_prompt = CUSTOM_FAMILY_HEALTH_RECIPE_PROMPT_TEMPLATE.format(
        people_count=people_count,
        family_members_details="\n".join(details_str_list),
        cuisine_desc=cuisine_desc,
        cooking_method_desc=cooking_method_desc,
        cooking_time_desc=cooking_time_desc,
        meal_type_desc=meal_type_desc,
        available_ingredients="、".join(available_ingredients) if available_ingredients else "暂无参考在库食材",
    )
    return await call_deepseek_llm(SYSTEM_SPECIAL_RECIPE_PROMPT, user_prompt)

# 4. 今日吃啥双轨菜谱生成 (支持烹饪方式 + 烹饪时间)
async def generate_today_eat_recipes(
    available_ingredients: list,
    people_count: int = 2,
    cuisine_desc: str = "中式家常",
    cooking_method_desc: str = "快捷家常烹饪",
    cooking_time_desc: str = "10~20分钟",
    meal_type_desc: str = "晚餐",
    health_condition_desc: str = "健康均衡"
) -> dict:
    user_prompt = TODAY_WHAT_TO_EAT_PROMPT_TEMPLATE.format(
        people_count=people_count,
        cuisine_desc=cuisine_desc,
        cooking_method_desc=cooking_method_desc,
        cooking_time_desc=cooking_time_desc,
        meal_type_desc=meal_type_desc,
        health_condition_desc=health_condition_desc,
        available_ingredients="、".join(available_ingredients) if available_ingredients else "当前冰箱空空如也，请自由发挥"
    )
    return await call_deepseek_llm(SYSTEM_RECIPE_PROMPT, user_prompt)

# 5. 社区发帖菜品智能研判
async def verify_dish_and_generate_recipe(
    title: str,
    content: str,
    image_abs_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    user_prompt = f"""
请仔细研判以下用户在美食生活社区发布的打卡信息：
【菜品标题】：{title}
【心得描述】：{content}
【图片文件名】：{os.path.basename(image_abs_path) if image_abs_path else '无图片'}

请研判该内容是否确系一道真实的做菜成果。输出纯合法 JSON 格式：
{{
  "is_dish": true,
  "recipe_name": "简短好听的菜品名(4-8字，若非菜品则为null)",
  "difficulty": "初级/中级 · XX分钟 (若非菜品则为null)",
  "ingredients_needed": [
    {{"name": "主配料名称", "amount": "适量"}}
  ],
  "pantry_staples": "常用油盐调料",
  "cooking_steps": [
    "步骤1...",
    "步骤2..."
  ],
  "chef_tips": "大厨操作秘诀"
}}
"""
    messages_payload = [{"role": "system", "content": COMMUNITY_DISH_AUDIT_SYSTEM_PROMPT}]

    has_image_base64 = False
    if image_abs_path and os.path.exists(image_abs_path):
        try:
            with open(image_abs_path, "rb") as img_file:
                b64_data = base64.b64encode(img_file.read()).decode("utf-8")
                messages_payload.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"}}
                    ]
                })
                has_image_base64 = True
        except Exception:
            has_image_base64 = False

    if not has_image_base64:
        messages_payload.append({"role": "user", "content": user_prompt})

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages_payload,
        "temperature": 0.3,
        "response_format": {"type": "json_object"}
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(DEEPSEEK_API_URL, headers=headers, json=payload)
            if resp.status_code == 200:
                result = clean_llm_json_response(resp.json()["choices"][0]["message"]["content"])
                if result.get("is_dish") is True and result.get("recipe_name"):
                    return {
                        "recipe_name": result.get("recipe_name"),
                        "difficulty": result.get("difficulty") or "初级 · 15分钟",
                        "ingredients_needed": result.get("ingredients_needed") or [],
                        "pantry_staples": result.get("pantry_staples") or "少油少盐常备调料",
                        "cooking_steps": result.get("cooking_steps") or ["洗净切配食材；", "下锅翻炒至熟透入味起锅。"],
                        "chef_tips": result.get("chef_tips") or "大厨技巧：火候适度，锁鲜出香。"
                    }
    except Exception as e:
        print(f"[AI Dish Verification Warning]: 菜品识别微服务异常: {e}")

    return None
