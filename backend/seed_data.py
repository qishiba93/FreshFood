"""Import the legacy SQL demo content into the production database once."""
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_password_hash
from backend.models import (
    CommunityPost,
    CommunityReport,
    FavoriteRecipe,
    PantryItem,
    PostComment,
    PostLike,
    ShoppingItem,
    StandardFoodImage,
    User,
    UserActivity,
    UserCarbonLog,
    UserHealthProfile,
)


SEED_MARKER = ".demo_seed_v1"


async def _find_one(session: AsyncSession, model, *filters):
    return (await session.execute(select(model).where(*filters))).scalar_one_or_none()


async def seed_demo_data(session: AsyncSession, persistent_dir: str) -> bool:
    """Seed the legacy demo dataset without replacing existing user data."""
    marker = Path(persistent_dir) / SEED_MARKER
    if marker.exists():
        return False

    now = datetime.now()
    users = {}
    for username in ("user1", "user2", "user3"):
        user = await _find_one(session, User, User.username == username)
        if user is None:
            user = User(
                username=username,
                hashed_password=get_password_hash("123456"),
                role="user",
                status=1,
            )
            session.add(user)
            await session.flush()
        users[username] = user

    health_profiles = [
        ("user1", "本人", "self", ["痛风尿酸偏高", "二型糖尿病需控糖"], "严格少肉汤与低果糖饮品", 1),
        ("user1", "爸爸", "parent", ["高血压", "少油少盐"], "清淡饮食，避免高钠调味品", 0),
        ("user1", "妈妈", "parent", ["甲状腺调理"], "避免过量高碘海带紫菜，十字花科煮透食用", 0),
        ("user2", "本人", "self", ["健身减脂", "高蛋白"], "偏好白灼和少油煎烤", 1),
        ("user3", "本人", "self", ["慢性胃炎", "不能吃生冷辛辣"], "以温热炖煮为主", 1),
    ]
    for username, member_name, relation, conditions, notes, is_primary in health_profiles:
        user = users[username]
        existing = await _find_one(
            session,
            UserHealthProfile,
            UserHealthProfile.user_id == user.id,
            UserHealthProfile.member_name == member_name,
        )
        if existing is None:
            session.add(UserHealthProfile(
                user_id=user.id,
                member_name=member_name,
                relation=relation,
                conditions=conditions,
                dietary_notes=notes,
                is_primary=is_primary,
            ))

    image_specs = [
        ("番茄", "西红柿,小番茄,洋柿子", "vegetable", "tomato"),
        ("西兰花", "绿菜花,青花菜", "vegetable", "broccoli"),
        ("鸡胸肉", "冷鲜鸡胸,鸡肉,鸡柳", "meat", "chicken_breast"),
        ("原切牛肉", "牛排,牛里脊,牛腩,肥牛", "meat", "beef"),
        ("鲜鸡蛋", "鸡蛋,洋鸡蛋,土鸡蛋,无菌蛋", "meat", "egg"),
        ("黑虎虾仁", "青虾仁,基围虾,大虾,鲜虾", "seafood", "shrimp"),
        ("黄瓜", "青瓜,水果黄瓜", "vegetable", "cucumber"),
        ("土豆", "马铃薯,洋芋", "vegetable", "potato"),
        ("嫩豆腐", "豆腐,老豆腐,水豆腐,豆干", "vegetable", "tofu"),
        ("胡萝卜", "红萝卜,红参", "vegetable", "carrot"),
        ("五花猪肉", "猪肉,五花肉,里脊肉,排骨", "meat", "pork"),
        ("红富士苹果", "苹果,青苹果,红富士", "fruit", "apple"),
        ("香蕉", "香蕉,芭蕉", "fruit", "banana"),
        ("白蘑菇", "香菇,口蘑,金针菇,平菇", "vegetable", "mushroom"),
        ("洋葱", "圆葱,紫洋葱,白洋葱", "vegetable", "onion"),
        ("菠菜", "小菠菜,绿叶菜", "vegetable", "spinach"),
    ]
    for food_name, synonyms, category, filename in image_specs:
        for image_number in range(1, 4):
            image_url = f"/static/standards/{filename}_{image_number}.jpg"
            existing = await _find_one(
                session,
                StandardFoodImage,
                StandardFoodImage.image_url == image_url,
            )
            if existing is None:
                session.add(StandardFoodImage(
                    food_name=food_name,
                    synonyms=synonyms,
                    category=category,
                    image_url=image_url,
                ))

    pantry_items = [
        ("user1", "鲜嫩鸡胸肉", "refrigeration", 450.0, 450.0, timedelta(days=3), "chicken_breast_1.jpg"),
        ("user1", "新鲜西兰花", "refrigeration", 300.0, 300.0, timedelta(days=2), "broccoli_1.jpg"),
        ("user1", "番茄", "refrigeration", 300.0, 300.0, timedelta(hours=18), "tomato_1.jpg"),
        ("user1", "鲜鸡蛋", "refrigeration", 600.0, 600.0, timedelta(days=7), "egg_1.jpg"),
        ("user1", "原切牛肉", "freezer", 800.0, 600.0, timedelta(days=45), "beef_1.jpg"),
        ("user1", "黑虎虾仁", "freezer", 500.0, 400.0, timedelta(days=60), "shrimp_1.jpg"),
        ("user2", "鲜嫩鸡胸肉", "refrigeration", 500.0, 500.0, timedelta(days=4), "chicken_breast_2.jpg"),
        ("user3", "土豆", "refrigeration", 600.0, 600.0, timedelta(days=10), "potato_1.jpg"),
    ]
    for username, name, location, initial, remaining, expires_in, image_name in pantry_items:
        user = users[username]
        existing = await _find_one(
            session,
            PantryItem,
            PantryItem.user_id == user.id,
            PantryItem.name == name,
        )
        if existing is None:
            session.add(PantryItem(
                user_id=user.id,
                name=name,
                location=location,
                initial_weight=initial,
                remaining_weight=remaining,
                unit="克",
                expire_at=now + expires_in,
                image_url=f"/static/standards/{image_name}",
            ))

    carbon_logs = [
        ("user1", "原切牛肉", 200.0, 12000.0, "黑椒小牛排", "non_vegetarian", timedelta()),
        ("user1", "番茄", 150.0, 210.0, "番茄烩蛋", "vegetarian", timedelta(days=-1)),
        ("user2", "黑虎虾仁", 300.0, 3600.0, "葱油白灼虾", "non_vegetarian", timedelta()),
        ("user2", "鲜嫩鸡胸肉", 250.0, 1375.0, "香草煎鸡胸", "non_vegetarian", timedelta(days=-2)),
        ("user3", "土豆", 300.0, 180.0, "清炒土豆丝", "vegetarian", timedelta()),
    ]
    for username, item_name, weight, carbon, recipe, category, offset in carbon_logs:
        user = users[username]
        existing = await _find_one(
            session,
            UserCarbonLog,
            UserCarbonLog.user_id == user.id,
            UserCarbonLog.item_name == item_name,
            UserCarbonLog.source_recipe == recipe,
        )
        if existing is None:
            session.add(UserCarbonLog(
                user_id=user.id,
                item_name=item_name,
                weight_grams=weight,
                carbon_saved_grams=carbon,
                food_category=category,
                source_recipe=recipe,
                created_at=now + offset,
            ))

    recipes = {
        "虾": {
            "recipe_name": "葱油白灼黑虎虾",
            "difficulty": "初级 · 12分钟",
            "health_metric": "单份总嘌呤约 35mg (低负荷)",
            "ingredients_needed": [{"name": "黑虎虾仁", "amount": "200克"}, {"name": "小葱", "amount": "2根"}],
            "cooking_steps": ["葱白切段炸出清香葱油；", "沸水下黑虎虾仁焯烫50秒卷曲捞起；", "摆盘淋上热葱油与少许生抽。"],
            "chef_tips": "水要滚沸，虾身变红紧绷立即捞出，肉质最嫩。",
        },
        "鸡柳": {
            "recipe_name": "金玉番茄滑鸡柳",
            "difficulty": "初级 · 15分钟",
            "health_metric": "单份热量约 310 kcal",
            "ingredients_needed": [{"name": "鸡胸肉", "amount": "250克"}, {"name": "番茄", "amount": "2个"}],
            "cooking_steps": ["鸡胸切柳少许蛋清抓匀；", "番茄去皮切块炒出红沙红油；", "下鸡柳滑炒变白收汁起锅。"],
            "chef_tips": "番茄加一撮细盐翻炒出沙速度更快。",
        },
    }
    post_specs = [
        ("user1", "葱油白灼黑虎虾", "按照家里的控糖和少嘌呤要求做的，虾肉鲜甜紧实，白灼断生捞出淋葱油，极度下饭！", "/static/standards/shrimp_1.jpg", recipes["虾"], 16, timedelta(hours=-2)),
        ("user2", "金玉番茄滑鸡柳", "低脂高蛋白的减脂大餐，酸甜开胃，浓郁的番茄汁裹满鲜嫩鸡肉，单份热量才310大卡！", "/static/standards/tomato_1.jpg", recipes["鸡柳"], 28, timedelta(hours=-4)),
        ("user3", "推销广告内容", "这是一条供管理员在“违规反馈处置台”测试驳回或下架屏蔽功能的模拟测试广告。", "/static/standards/potato_1.jpg", None, 0, timedelta(days=-1)),
    ]
    posts = {}
    for username, title, content, image_url, recipe_data, likes, offset in post_specs:
        post = await _find_one(session, CommunityPost, CommunityPost.title == title)
        if post is None:
            post = CommunityPost(
                user_id=users[username].id,
                title=title,
                content=content,
                image_url=image_url,
                recipe_data=recipe_data,
                likes_count=likes,
                status=1,
                created_at=now + offset,
            )
            session.add(post)
            await session.flush()
        posts[title] = post

    like_specs = [
        ("葱油白灼黑虎虾", "user2"),
        ("葱油白灼黑虎虾", "user3"),
        ("金玉番茄滑鸡柳", "user1"),
    ]
    for post_title, username in like_specs:
        post, user = posts[post_title], users[username]
        existing = await _find_one(
            session,
            PostLike,
            PostLike.post_id == post.id,
            PostLike.user_id == user.id,
        )
        if existing is None:
            session.add(PostLike(post_id=post.id, user_id=user.id))

    comment_specs = [
        ("葱油白灼黑虎虾", "user2", "成色非常漂亮，原汁原味看着太有食欲了！"),
        ("葱油白灼黑虎虾", "user3", "做法好简单，今晚我也照着做一份！"),
        ("金玉番茄滑鸡柳", "user1", "这个番茄汁太赞了，我也收藏了！"),
    ]
    for post_title, username, content in comment_specs:
        post, user = posts[post_title], users[username]
        existing = await _find_one(
            session,
            PostComment,
            PostComment.post_id == post.id,
            PostComment.user_id == user.id,
            PostComment.content == content,
        )
        if existing is None:
            session.add(PostComment(post_id=post.id, user_id=user.id, content=content, status=1))

    report_post = posts["推销广告内容"]
    report_specs = [
        ("user1", "推销广告导流，与美食烹饪无关，申请下架。", timedelta(minutes=-20)),
        ("user2", "全是营销推广链接，影响社区氛围。", timedelta(minutes=-10)),
    ]
    for username, detail, offset in report_specs:
        user = users[username]
        existing = await _find_one(
            session,
            CommunityReport,
            CommunityReport.post_id == report_post.id,
            CommunityReport.reporter_id == user.id,
            CommunityReport.reason == "spam",
        )
        if existing is None:
            session.add(CommunityReport(
                post_id=report_post.id,
                reporter_id=user.id,
                reason="spam",
                detail=detail,
                status="pending",
                created_at=now + offset,
            ))

    favorite_specs = [
        {
            "recipe_name": "葱油白灼黑虎虾",
            "category": "custom",
            "difficulty": "初级 · 12分钟",
            "calories": "🔥 约 220 kcal",
            "glycemic_info": "单份总嘌呤约 35mg (低负荷)",
            "ingredients_needed": [{"name": "黑虎虾仁", "amount": "200克", "from_pantry": True}, {"name": "小葱", "amount": "2根", "from_pantry": False}],
            "pantry_staples": "热葱油10ml、薄盐生抽5ml",
            "cooking_steps": recipes["虾"]["cooking_steps"],
            "chef_tips": recipes["虾"]["chef_tips"],
        },
        {
            "recipe_name": "清蒸西兰花炖鸡柳",
            "category": "goiter",
            "difficulty": "初级 · 15分钟",
            "calories": None,
            "glycemic_info": "单份碘含量把控在 35mcg 适碘安全范围；临床提示：十字花科蔬菜（西兰花）含有硫苷物质，烹饪前必须在滚沸热水中焯烫熟透 2 分钟以上，以灭活致甲状腺肿物质，确保内分泌代谢安全。",
            "ingredients_needed": [{"name": "鸡胸肉", "amount": "200克", "from_pantry": True}, {"name": "西兰花", "amount": "150克", "from_pantry": True}],
            "pantry_staples": "生姜3片、无碘低钠盐2克、清亮花生油5ml",
            "cooking_steps": ["西兰花洗净切小朵，沸水中彻底焯透捞出沥干；", "鸡胸肉切薄柳抓匀少许蛋清与生姜片；", "蒸锅上汽大火清蒸8分钟出锅淋少许热油。"],
            "chef_tips": "大厨火候：焯烫务必到位，清蒸锁住鸡肉原汁。",
        },
    ]
    for recipe in favorite_specs:
        existing = await _find_one(
            session,
            FavoriteRecipe,
            FavoriteRecipe.user_id == users["user1"].id,
            FavoriteRecipe.recipe_name == recipe["recipe_name"],
        )
        if existing is None:
            session.add(FavoriteRecipe(user_id=users["user1"].id, **recipe))

    shopping_specs = [
        ("优质小葱", "1小把", "葱油白灼黑虎虾"),
        ("薄盐生抽", "1瓶", "厨房基础常备补给"),
    ]
    for name, amount, source in shopping_specs:
        existing = await _find_one(
            session,
            ShoppingItem,
            ShoppingItem.user_id == users["user1"].id,
            ShoppingItem.name == name,
        )
        if existing is None:
            session.add(ShoppingItem(
                user_id=users["user1"].id,
                name=name,
                amount=amount,
                source_recipe=source,
            ))

    activity_specs = [
        ("user1", "add", "录入食材:原切牛肉", timedelta(days=-3)),
        ("user1", "consume", "做菜消耗:原切牛肉(减碳12000g)", timedelta()),
        ("user1", "collect", "收藏菜谱:葱油白灼黑虎虾", timedelta(days=-1)),
        ("user1", "collect", "收藏菜谱:清蒸西兰花炖鸡柳", timedelta(days=-1)),
        ("user1", "post", "发布社区动态:葱油白灼黑虎虾", timedelta(hours=-2)),
        ("user1", "report", "举报动态ID:3(原因:spam)", timedelta(minutes=-20)),
        ("user2", "post", "发布社区动态:金玉番茄滑鸡柳", timedelta(hours=-4)),
        ("user2", "like", "点赞动态ID:1", timedelta(hours=-1)),
        ("user2", "report", "举报动态ID:3(原因:spam)", timedelta(minutes=-10)),
        ("user2", "consume", "做菜消耗:黑虎虾仁(减碳3600g)", timedelta()),
        ("user3", "comment", "评论动态ID:1", timedelta(minutes=-30)),
        ("user3", "consume", "做菜消耗:土豆(减碳180g)", timedelta()),
    ]
    for username, activity_type, note, offset in activity_specs:
        user = users[username]
        existing = await _find_one(
            session,
            UserActivity,
            UserActivity.user_id == user.id,
            UserActivity.activity_type == activity_type,
            UserActivity.note == note,
        )
        if existing is None:
            session.add(UserActivity(
                user_id=user.id,
                activity_type=activity_type,
                note=note,
                created_at=now + offset,
            ))

    await session.commit()
    marker.write_text(now.isoformat(), encoding="ascii")
    return True
