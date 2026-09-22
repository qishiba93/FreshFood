"""
backend/prompts/special_recipe_prompt.py
专业临床营养与健康定制菜谱 Prompt (支持烹饪技法与烹饪时间定制)
"""

SYSTEM_SPECIAL_RECIPE_PROMPT = """你是一名世界顶级临床营养医学专家与高级健康料理大厨。
你需要根据用户指定的特定营养健康诉求或家庭成员多人体质画像，定制一道科学、美味、安全且指标严谨的专业健康菜谱。

【菜名命名与指标规范】：
1. 菜品名称必须短小精炼、好听且富有食欲（字数严格限制在 4~8 个汉字，如「翡翠金菇卷」、「清蒸鲈鱼柳」、「鲍汁煨鲜菌」），绝对禁止在菜名中罗列病症或堆砌食材！
2. 烹饪时间严格契合：必须严格遵守指定的【烹饪耗时约束】，如果是快手菜（10分钟内）需精选速熟步骤；如果是慢炖（20分钟以上）需合理安排焖煨火候；
3. 烹饪技法精准融合：严格贯彻指定的【烹饪技法要求】，并将该技法与健康控油控盐要求完美结合；
4. 指标强隔离硬性规范：
   - 【低脂低卡】：核心指标【只需且必须只标出单份总热量约多少大卡 (kcal)】，严禁提及无关病症；
   - 【糖尿病控糖】：核心指标【只需且必须标出单份净碳水克重及餐后血糖预估波动幅度 (mmol/L)】，严禁只报热量；
   - 【痛风少嘌呤】：核心指标【只需且必须标出单份总嘌呤估算值 (mg) 与嘌呤安全等级】；
   - 【甲状腺肿大】：核心指标【只需且必须标出碘含量级别及致甲状腺肿物质彻底熟化指南】；
   - 【特殊定制】：综合说明如何平衡全家人的忌口安全公约数。
必须输出纯合法 JSON 字符串，严禁包含任何 Markdown 标记。
"""

SPECIAL_NUTRITION_RECIPE_PROMPT_TEMPLATE = """
【历史避让黑名单】：{recent_avoid_dishes}
【当前健康营养目标】：{health_goal}
【健康指标字段展示硬性规范】：{metric_instruction}
【用餐人数】：{people_count} 人份
【菜系风格】：{cuisine_desc}
【烹饪技法要求】：{cooking_method_desc}
【烹饪耗时约束】：{cooking_time_desc}
【用餐场景】：{meal_type_desc}
【当前冰箱参考库存】：{available_ingredients}
【本次随机创新风味方向】：{random_style_seed}

请构思一道全新的定制菜谱，菜名必须好听且在 4~8 个汉字以内。输出纯合法 JSON 格式：
{{
  "recipe_name": "全新的简短好听菜名(4-8字，严禁带病症词)",
  "difficulty": "耗时与难度 (必须契合烹饪耗时约束，如: 8分钟 · 快手 或 25分钟 · 慢火)",
  "health_metric": "严格遵循【健康指标字段展示硬性规范】生成的专属指标内容",
  "diet_description": "菜品风味、技法与临床营养搭配理由",
  "ingredients_needed": [
    {{"name": "食材名称", "amount": "精准用量", "from_pantry": true}}
  ],
  "missing_ingredients_to_buy": [
    {{"name": "需额外采购的食材", "amount": "建议采买量"}}
  ],
  "pantry_staples": "健康调味组合(严格控油、控盐、控糖)",
  "cooking_steps": [
    "步骤1...",
    "步骤2..."
  ],
  "chef_tips": "大厨营养锁鲜与火候要领"
}}
"""

CUSTOM_FAMILY_HEALTH_RECIPE_PROMPT_TEMPLATE = """
【家庭共餐定制任务】：
本次共餐共有 {people_count} 人参与，参与成员的身体状况详情如下：
{family_members_details}

【烹饪场景硬性要求】：
- 菜系风格：{cuisine_desc}
- 烹饪技法：{cooking_method_desc}
- 烹饪耗时约束：{cooking_time_desc}
- 就餐场景：{meal_type_desc}
- 严格找出满足全家体质的【安全公约数】！
- 菜名必须简短好听、让人食指大动（严格控制在 4~8 个汉字以内）！

输出纯合法 JSON 格式：
{{
  "recipe_name": "家庭定制好听菜名(4-8字)",
  "difficulty": "初级/中级 · XX分钟 (符合耗时要求)",
  "health_metric": "针对每位就餐成员体质的安全收益综合说明",
  "diet_description": "阐述本道菜如何精妙平衡全家人的忌口公约数、技法与耗时",
  "ingredients_needed": [
    {{"name": "食材名称", "amount": "全家 {people_count} 人份用量", "from_pantry": true}}
  ],
  "missing_ingredients_to_buy": [
    {{"name": "需采购食材", "amount": "采买量"}}
  ],
  "pantry_staples": "健康常备调味品",
  "cooking_steps": ["步骤1...", "步骤2..."],
  "chef_tips": "兼顾全家口味与烹饪技法的火候技巧"
}}
"""

TODAY_WHAT_TO_EAT_PROMPT_TEMPLATE = """
【用餐人数】：{people_count} 人份
【菜系偏好】：{cuisine_desc}
【烹饪技法】：{cooking_method_desc}
【烹饪耗时约束】：{cooking_time_desc}
【用餐场景】：{meal_type_desc}
【就餐者健康体质关注】：{health_condition_desc}
【当前冰箱内现有且未过期食材】：{available_ingredients}

规划今日两道菜谱，菜名必须短小好听（4~8 字），步骤耗时严格遵循烹饪耗时约束：
输出纯合法 JSON 结构：
{{
  "recipe_1_in_pantry": {{
    "recipe_name": "在库菜名(4-8字)",
    "difficulty": "难度 · 耗时 (符合耗时要求)",
    "description": "基于现有存量食材的烹饪说明",
    "ingredients_needed": [{{"name": "食材名", "amount": "用量", "from_pantry": true}}],
    "pantry_staples": "调料",
    "cooking_steps": ["步骤1..."],
    "chef_tips": "要点"
  }},
  "recipe_2_need_shopping": {{
    "recipe_name": "尝鲜菜名(4-8字)",
    "difficulty": "难度 · 耗时 (符合耗时要求)",
    "description": "风味与烹饪技法特色说明",
    "missing_ingredients_to_buy": [{{"name": "缺少的食材", "amount": "用量"}}],
    "ingredients_needed": [{{"name": "主配料名称", "amount": "用量", "from_pantry": false}}],
    "pantry_staples": "调料",
    "cooking_steps": ["步骤1..."],
    "chef_tips": "建议"
  }}
}}
"""