"""
backend/routers/chat.py
AI 厨房专属智能管家对话路由 (全能稳健调度版)
包含：
1. 严格领域护栏与礼貌合理拒答兜底（绝不出现空回复或无视用户）
2. 智能上下文指代支持：不仅能加减备菜、入库冰箱，还能识别“放到下层/冷冻/换位置”并动态更新冰箱温区
3. 多层异常与空文本兜底保障
"""
import os
import json
import re
import httpx
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, desc
from backend.database import get_db
from backend.models import User, ShoppingItem, PantryItem, UserActivity
from backend.auth import get_current_user
from backend.services.food_image_service import resolve_food_image

router = APIRouter(prefix="/api/chat", tags=["AI 智能厨房对话"])

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL") or f"{os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com').rstrip('/')}/v1/chat/completions"
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# 严密而温暖的 System Prompt
KITCHEN_ASSISTANT_SYSTEM_PROMPT = """你是一名精通中华八大菜系、食材全温区储鲜学与临床营养医学的专属智能主厨管家（智鲜厨房 OS）。

【核心使命与领域护栏】：
1. 你的专业领域严格专注于：家庭食材保鲜、双门冰箱温区管理、菜谱火候调料指导、烹饪防翻车救场、备菜采购清单调度。
2. 遇到完全无关的话题（如写代码、股票投资、政治历史、八卦娱乐、数理化题目等）：
   - 必须礼貌而明确地告知用户该话题超出了厨房大厨的智能职责范围，并主动引导用户咨询做菜、保鲜或备菜相关需求。
   - 例：“抱歉呀，作为您的专属厨房智能大厨，我的专业技能专注于食材保鲜、美味菜谱烹饪、火候掌控与厨房备菜调度。计算机编程/其他话题不在我的服务范围内。请问今天有什么食材需要我帮您规划做法或存入冰箱吗？”

【厨房自然语言控制协议 (Actions Protocol)】：
用户常会使用口语下达指令，甚至结合前文进行代词指代（例如前文刚放入鲫鱼，用户接着说“放到下层吧”、“放冷冻吧”）。
你必须在 actions 中输出合法的操作动作：

1. add_shopping: 用户想买、加入备菜清单的物品。
   例：[{"name": "生抽", "amount": "1瓶"}]
2. remove_shopping: 用户想从备菜清单中移除/划掉的物品名列表。
   例：["西红柿", "大蒜"]
3. clear_all_shopping: 用户明确要求“清空备菜清单”时设为 true，否则为 false。
4. store_to_pantry: 将食材存入冰箱（用户表示买到了/放冰箱等）：
   - name: 食材名（纯净中文名，不带数量）
   - location: "refrigeration" (上层/冷藏保鲜) 或 "freezer" (下层/深冷冷冻)
   - weight: 估算克重(数值)，未说明时肉类默认500.0，果蔬默认300.0
   - unit: 默认 "克"
   - shelf_life_days: 建议保质期天数(冷藏一般2-5天，冷冻一般30-90天)
5. move_pantry_item: 用户要求更改冰箱内已有食材的温区/层级（如“放到下层吧”、“改成冷冻”、“放上层保鲜”等）：
   - name: 目标食材名（若用户使用代词如“它/这个/放到下层”，需结合前序对话找出正在讨论的食材名）
   - target_location: "refrigeration" (挪到上层/冷藏) 或 "freezer" (挪到下层/冷冻)
   - new_shelf_life_days: 转移到新温区后的重置保质天数(冷藏一般2-3天，冷冻一般60天)

【格式硬性规范】：
必须输出纯合法 JSON 格式，严禁包含任何 Markdown 标记（如 ```json 等），且 reply 字段绝对不能为空字符串：
{
  "is_refused": false,
  "reply": "温暖、详尽且有明确答复内容的大厨回复(绝对禁止为空)...",
  "actions": {
    "add_shopping": [],
    "remove_shopping": [],
    "clear_all_shopping": false,
    "store_to_pantry": [],
    "move_pantry_item": []
  }
}
"""

class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户提问内容")
    history: Optional[List[ChatMessage]] = Field(default=[], description="历史对话上下文")
    recipe_context: Optional[Dict[str, Any]] = Field(default=None, description="从菜谱跳转过来的菜谱上下文")
    memory_summary: Optional[str] = Field(default=None, description="长对话前序压缩记忆摘要")

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
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass

    return {
        "is_refused": False,
        "reply": text if text else "大厨已收到您的要求，正在为您处理。",
        "actions": {
            "add_shopping": [],
            "remove_shopping": [],
            "clear_all_shopping": False,
            "store_to_pantry": [],
            "move_pantry_item": []
        }
    }

@router.post("/kitchen-assistant")
async def chat_with_kitchen_assistant(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    user_input = req.message.strip()

    # 1. 组装 System Prompt 与长历史
    system_content = KITCHEN_ASSISTANT_SYSTEM_PROMPT
    if req.memory_summary and req.memory_summary.strip():
        system_content += f"\n\n【前序对话长期记忆摘要】：\n{req.memory_summary.strip()}"

    messages_payload = [{"role": "system", "content": system_content}]

    # 注入菜谱跳转上下文
    if req.recipe_context:
        r_name = req.recipe_context.get("recipe_name", "定制佳肴")
        r_json_str = json.dumps(req.recipe_context, ensure_ascii=False)
        context_prompt = (
            f"【用户当前正准备烹饪此菜品】：\n"
            f"菜名：《{r_name}》\n"
            f"菜谱原始数据：{r_json_str}\n"
            f"用户点击了「详细一点」进入咨询，请以此菜品为核心提供保姆级细化精讲！"
        )
        messages_payload.append({"role": "system", "content": context_prompt})

    # 保留最近 12 轮交互，确保上下文指代（“它/放到下层吧”）能够精准识别前文提到的食材
    if req.history:
        for h in req.history[-12:]:
            messages_payload.append({"role": h.role, "content": h.content})

    messages_payload.append({"role": "user", "content": user_input})

    # 2. 调用大模型
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages_payload,
        "temperature": 0.35,
        "response_format": {"type": "json_object"}
    }

    parsed = {}
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(DEEPSEEK_API_URL, headers=headers, json=payload)
            if resp.status_code == 200:
                raw_body = resp.json()["choices"][0]["message"]["content"]
                parsed = clean_llm_json(raw_body)
            else:
                parsed = {
                    "is_refused": False,
                    "reply": "大厨服务器正在繁忙调度中，请稍后再试一次哦。",
                    "actions": {}
                }
    except Exception as e:
        parsed = {
            "is_refused": False,
            "reply": f"大厨连接厨房网络稍有延迟，请稍后重新发送一次。(详情: {str(e)[:60]})",
            "actions": {}
        }

    # 多字段容错提取 reply，确保绝对不为空
    reply_text = (
        parsed.get("reply") or
        parsed.get("content") or
        parsed.get("message") or
        parsed.get("answer") or
        ""
    ).strip()

    is_refused = parsed.get("is_refused", False)
    actions = parsed.get("actions", {}) or {}

    # 终极保底：如果大模型依然输出了空字符串，给出友好合理指引
    if not reply_text:
        if is_refused:
            reply_text = "抱歉呀，此对话并非智鲜大厨的智能服务范围。我只专注于食材保鲜、冰箱管理与烹饪菜谱相关咨询。请问有什么厨房需求我可以协助您吗？"
        else:
            reply_text = "好的，我已经为您记录并调整了操作！还有什么食材或烹饪问题需要协助吗？"

    executed_summary = []

    # 3. 意图调度执行（原子事务）
    if not is_refused and isinstance(actions, dict):
        now = datetime.now()

        # A. 清空备菜清单
        if actions.get("clear_all_shopping"):
            await db.execute(delete(ShoppingItem).where(ShoppingItem.user_id == user.id))
            executed_summary.append("已清空全部备菜清单")

        # B. 删除指定备菜食材
        remove_items = actions.get("remove_shopping", []) or []
        for r_name in remove_items:
            clean_r = str(r_name).strip()
            if clean_r:
                stmt = delete(ShoppingItem).where(
                    ShoppingItem.user_id == user.id,
                    ShoppingItem.name.like(f"%{clean_r}%")
                )
                await db.execute(stmt)
                executed_summary.append(f"从备菜清单移除「{clean_r}」")

        # C. 新增备菜食材
        add_items = actions.get("add_shopping", []) or []
        if add_items:
            existing_stmt = select(ShoppingItem.name).where(ShoppingItem.user_id == user.id)
            existing_names = set((await db.execute(existing_stmt)).scalars().all())
            added_names = []

            for it in add_items:
                name = str(it.get("name") or "").strip()
                amount = str(it.get("amount") or "适量").strip()
                if name and name not in existing_names:
                    db.add(ShoppingItem(
                        user_id=user.id,
                        name=name,
                        amount=amount,
                        source_recipe="AI 对话管家"
                    ))
                    existing_names.add(name)
                    added_names.append(f"{name}({amount})")

            if added_names:
                executed_summary.append(f"加入备菜清单: {'、'.join(added_names)}")

        # D. 将食材入库至冰箱（新买入）
        store_items = actions.get("store_to_pantry", []) or []
        if store_items:
            stored_names = []
            for item in store_items:
                food_name = str(item.get("name") or "").strip()
                if not food_name:
                    continue

                location = item.get("location") if item.get("location") in ["refrigeration", "freezer"] else "refrigeration"
                try:
                    weight = float(item.get("weight") or 300.0)
                except Exception:
                    weight = 300.0
                unit = str(item.get("unit") or "克")
                try:
                    shelf_days = float(item.get("shelf_life_days") or (3.0 if location == "refrigeration" else 45.0))
                except Exception:
                    shelf_days = 3.0

                expire_at = now + timedelta(days=shelf_days)

                # 优先匹配管理员标准图库
                img_res = await resolve_food_image(db=db, food_name=food_name, user_uploaded_url=None)

                pantry_obj = PantryItem(
                    user_id=user.id,
                    name=food_name,
                    location=location,
                    initial_weight=weight,
                    remaining_weight=weight,
                    unit=unit,
                    expire_at=expire_at,
                    image_url=img_res.final_url
                )
                db.add(pantry_obj)

                # 同步删去备菜清单中的对应食材
                await db.execute(
                    delete(ShoppingItem).where(
                        ShoppingItem.user_id == user.id,
                        ShoppingItem.name.like(f"%{food_name}%")
                    )
                )

                loc_desc = "上层 · 果蔬冷藏室" if location == "refrigeration" else "下层 · 深冷速冻室"
                stored_names.append(f"{food_name}（{weight}{unit}，存入{loc_desc}，保质{shelf_days}天）")

            if stored_names:
                executed_summary.append(f"入库冰箱: {'；'.join(stored_names)}，并已移出备菜")

        # E. 【核心新增】：调整冰箱内已有食材的温区（如“放到下层吧 / 改冷冻”）
        move_items = actions.get("move_pantry_item", []) or []
        if move_items:
            moved_names = []
            for m_item in move_items:
                target_food = str(m_item.get("name") or "").strip()
                target_loc = m_item.get("target_location")
                if target_loc not in ["refrigeration", "freezer"]:
                    target_loc = "freezer"

                # 查找用户冰箱中该食材的最新一条记录
                p_query = (
                    select(PantryItem)
                    .where(PantryItem.user_id == user.id)
                    .order_by(desc(PantryItem.id))
                )
                if target_food:
                    p_query = p_query.where(PantryItem.name.like(f"%{target_food}%"))

                res = await db.execute(p_query)
                item_to_move = res.scalars().first()

                if item_to_move:
                    item_to_move.location = target_loc
                    try:
                        new_days = float(m_item.get("new_shelf_life_days") or (60.0 if target_loc == "freezer" else 3.0))
                    except Exception:
                        new_days = 60.0 if target_loc == "freezer" else 3.0

                    item_to_move.expire_at = now + timedelta(days=new_days)
                    loc_cn = "下层 · 深冷速冻室" if target_loc == "freezer" else "上层 · 果蔬冷藏室"
                    moved_names.append(f"「{item_to_move.name}」已移动至{loc_cn}（保质期自适应更新为 {new_days} 天）")

            if moved_names:
                executed_summary.append(" | ".join(moved_names))

        if executed_summary:
            db.add(UserActivity(
                user_id=user.id,
                activity_type="add",
                note=f"AI对话联动调度:{' | '.join(executed_summary)}"
            ))
            await db.commit()

            tip_str = "\n\n---\n📋 **【厨房智能调度中心】**：\n" + "\n".join([f"- {s}" for s in executed_summary])
            reply_text += tip_str

    return {
        "is_refused": is_refused,
        "reply": reply_text,
        "actions_executed": executed_summary
    }
