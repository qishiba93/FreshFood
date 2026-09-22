"""
backend/services/vision_service.py
生鲜多模态识图与智能双温区保质期推导
"""
import os
import json
import base64
import re
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

vision_client = AsyncOpenAI(
    api_key=os.getenv("AI_API_KEY") or os.getenv("VISION_API_KEY"),
    base_url=os.getenv("VISION_BASE_URL", "https://api.deepseek.com")
)
VISION_MODEL = os.getenv("VISION_MODEL", "deepseek-flash")

def clean_json(text: str) -> str:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    else:
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            text = text[start:end+1]
    return text

async def recognize_and_decide(image_bytes: bytes, filename: str) -> dict:
    base64_img = base64.b64encode(image_bytes).decode('utf-8')
    ext = filename.lower().split('.')[-1]

    mime_map = {"png": "image/png", "webp": "image/webp", "jpeg": "image/jpeg", "jpg": "image/jpeg"}
    mime_type = mime_map.get(ext, "image/jpeg")
    data_url = f"data:{mime_type};base64,{base64_img}"

    system_prompt = (
        "你是一名精通食品物理学、家庭膳食保鲜与智能冰箱温区决策的专家。\n"
        "请观察并识别图像中的食材，根据【食品大类物理质地】推导存放温区与保质天数。\n\n"
        "【科学决策规范 (严禁偏向单一温区)】：\n"
        "1. 【推荐保鲜冷藏 (refrigeration)】：新鲜绿叶蔬菜、菌菇瓜果、鲜奶鲜蛋、发酵豆品、短期即食熟食（冷藏最佳 1~7 天）。\n"
        "2. 【推荐深冷速冻 (freezer)】：硬质冻肉、原切牛羊排肉块、水产海鲜虾蟹、未烹生水饺/汤圆等速冻半成品、雪糕冰饮（冷冻耐储 30~180 天）。\n"
        "3. 【双温区保质期联动】：必须同时输出该食材在冷藏条件下的建议天数，以及转入冷冻条件下的建议天数！\n\n"
        "【输出格式纯合法 JSON】：\n"
        "{\n"
        '  "food_name": "食材通用中文名",\n'
        '  "location": "refrigeration 或 freezer",\n'
        '  "shelf_life_days": 推荐温区下的建议天数,\n'
        '  "shelf_life_days_refrig": 该食物若放冷藏保鲜室的适宜天数(如 2.5 或 4.0),\n'
        '  "shelf_life_days_freezer": 该食物若放冷冻速冻室的适宜天数(如 30.0 或 60.0)\n'
        "}"
    )

    user_prompt = "请观察图片识别食品，推导其通用名、推荐温区以及双温区各自对应的科学保质天数。输出纯JSON："

    response = await vision_client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": data_url}}
                ]
            }
        ],
        temperature=0.1
    )

    raw_content = response.choices[0].message.content
    parsed_json = json.loads(clean_json(raw_content))

    food_name = parsed_json.get("food_name") or parsed_json.get("name") or "生鲜食材"
    location = parsed_json.get("location") or "refrigeration"
    if location not in ["refrigeration", "freezer"]:
        location = "refrigeration"

    # 安全解析天数
    try:
        shelf_life_days = float(parsed_json.get("shelf_life_days") or 3.0)
    except Exception:
        shelf_life_days = 3.0

    try:
        refrig_days = float(parsed_json.get("shelf_life_days_refrig") or (shelf_life_days if location == "refrigeration" else 3.0))
    except Exception:
        refrig_days = 3.0

    try:
        freezer_days = float(parsed_json.get("shelf_life_days_freezer") or (shelf_life_days if location == "freezer" else 45.0))
    except Exception:
        freezer_days = 45.0

    return {
        "food_name": food_name,
        "location": location,
        "shelf_life_days": shelf_life_days,
        "shelf_life_days_refrig": refrig_days,
        "shelf_life_days_freezer": freezer_days
    }
