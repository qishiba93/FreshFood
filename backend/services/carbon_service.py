"""
backend/services/carbon_service.py
AI 驱动的食材全生命周期碳足迹 (LCA) 动态估算中枢
通过 DeepSeek 大语言模型，针对每次消耗的具体生鲜食材、烹饪场景与克重，实时推演避免变质浪费所产生的减碳贡献
"""
import os
import json
import re
import httpx
from typing import Dict, List, Any, Tuple
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL") or f"{os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com').rstrip('/')}/v1/chat/completions"
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

SYSTEM_CARBON_AI_PROMPT = """你是一名国际权威的食品全生命周期环境影响评价 (LCA) 科学家与碳中和算法专家。
用户将向你提供用户在厨房实际消耗、挽救并利用的食材信息（名称、消耗克重、关联菜品）。
你需要根据农业种植/畜牧养殖、冷链物流、加工包装以及若变质填埋产生的甲烷温室气体效应，科学动态估算本次按需利用避免食物浪费所产生的【减碳贡献值】（单位：克 CO2e）。

【估算原则】：
1. 严谨遵循国际温室气体核算体系：
   - 红肉类（牛羊肉）碳排放极高，每克食材减碳贡献通常在 20~60g CO2e 之间；
   - 禽肉、水产海鲜次之，每克食材约 5~12g CO2e；
   - 蛋奶豆制品适中，每克食材约 2~6g CO2e；
   - 果蔬类碳排较低但极易腐烂发酵产气，每克食材约 0.5~2.0g CO2e。
2. 必须输出纯合法 JSON 格式，严禁包含任何 Markdown 标记（如 ```json 等）。
"""

def clean_llm_json(raw_text: str) -> dict:
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
    except Exception:
        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise

# 1. AI 单项食材消耗碳值推算
async def ai_estimate_carbon_single(food_name: str, weight_grams: float, recipe_name: str = "家常料理") -> Tuple[float, str]:
    """
    调用 AI 实时估算单种食材的减碳当量
    返回: (减碳克数, 科学推算理由)
    """
    user_prompt = f"""
请评估以下食材在家庭烹饪中按需食用、避免变质丢弃所产生的减碳当量：
【食材名称】：{food_name}
【消耗重量】：{weight_grams} 克
【制作菜肴】：{recipe_name}

请严格按如下纯 JSON 输出：
{{
  "carbon_saved_grams": 450.5,
  "reason": "简述该食材养殖/种植及保鲜特性的减碳机理(30字以内)"
}}
"""
    try:
        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_CARBON_AI_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3,
            "response_format": {"type": "json_object"}
        }
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(DEEPSEEK_API_URL, headers=headers, json=payload)
            if resp.status_code == 200:
                data = clean_llm_json(resp.json()["choices"][0]["message"]["content"])
                return float(data.get("carbon_saved_grams", weight_grams * 2.0)), data.get("reason", "AI 动态核算完成")
    except Exception as e:
        print(f"[Carbon AI Fallback Warning]: AI单项估算异常或超时: {e}")

    # 网络异常时的平滑底线兜底算法
    fallback_factor = 25.0 if any(k in food_name for k in ["牛", "羊"]) else (7.0 if any(k in food_name for k in ["肉", "鸡", "鱼", "虾"]) else 1.2)
    return round(weight_grams * fallback_factor, 1), "基于食品生命周期标准算法核算"

# 2. AI 批量食材消耗一次性打包核算
async def ai_estimate_carbon_batch(items: List[Dict[str, Any]], recipe_name: str = "定制佳肴") -> Tuple[float, Dict[int, float], str]:
    """
    调用 AI 一次性推算多项做菜食材的总减碳与明细
    返回: (总减碳克数, {item_id: 该项减碳克数}, 全局绿色减碳洞察评语)
    """
    items_desc = "\n".join([f"- ID:{it['id']} | 食材: {it['name']} | 消耗量: {it['weight']}克" for it in items])
    user_prompt = f"""
用户正在制作菜品「{recipe_name}」，本次批量消耗的食材清单如下：
{items_desc}

请对上述每一项食材分别推算减碳克数，并计算总减碳克数。输出纯 JSON 格式：
{{
  "total_carbon_saved_grams": 1250.0,
  "overall_insight": "AI一句话绿色点评（如：本次菜品重点避免了牛羊肉变质产生的高额碳排）",
  "breakdown": [
    {{"id": 1, "carbon_saved_grams": 800.0}},
    {{"id": 2, "carbon_saved_grams": 450.0}}
  ]
}}
"""
    try:
        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_CARBON_AI_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3,
            "response_format": {"type": "json_object"}
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(DEEPSEEK_API_URL, headers=headers, json=payload)
            if resp.status_code == 200:
                data = clean_llm_json(resp.json()["choices"][0]["message"]["content"])
                total = float(data.get("total_carbon_saved_grams", 0.0))
                insight = data.get("overall_insight", "AI绿色厨房核算完成")
                mapping = {}
                for b in data.get("breakdown", []):
                    mapping[int(b["id"])] = float(b.get("carbon_saved_grams", 0.0))
                return total, mapping, insight
    except Exception as e:
        print(f"[Carbon AI Batch Fallback]: 批量AI推算超时或异常: {e}")

    # 降级处理
    total = 0.0
    mapping = {}
    for it in items:
        w = it["weight"]
        factor = 25.0 if any(k in it["name"] for k in ["牛", "羊"]) else (7.0 if any(k in it["name"] for k in ["肉", "鸡", "鱼", "虾"]) else 1.2)
        val = round(w * factor, 1)
        mapping[it["id"]] = val
        total += val
    return round(total, 1), mapping, "绿色低碳烹饪，有效减少厨余损耗！"

# 3. 生态等价物折算
def convert_to_environmental_equivalents(carbon_saved_grams: float) -> dict:
    kg = round(carbon_saved_grams / 1000.0, 2)
    tree_days = round(carbon_saved_grams / 50.0, 1)  # 1棵成年大树日吸收约 50g CO2
    car_km = round(carbon_saved_grams / 150.0, 1)     # 私家车每公里约 150g CO2
    phone_charges = int(carbon_saved_grams / 8.0)

    return {
        "carbon_saved_kg": kg,
        "carbon_saved_g": carbon_saved_grams,
        "tree_days": tree_days,
        "car_km": car_km,
        "phone_charges": phone_charges
    }
