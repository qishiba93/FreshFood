import unittest
from datetime import datetime, timedelta
from urllib.parse import quote

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.auth import create_access_token
from backend.database import Base, get_db
from backend.main import app
from backend.models import (
    CommunityPost,
    FavoriteRecipe,
    PantryItem,
    PostComment,
    ShoppingItem,
    StandardFoodImage,
    User,
)


class ButtonRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async def test_db():
            async with self.sessions() as session:
                yield session

        app.dependency_overrides[get_db] = test_db
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

        async with self.sessions() as db:
            admin = User(username="route-admin", hashed_password="unused", role="super_admin")
            owner = User(username="route-owner", hashed_password="unused", role="user")
            other = User(username="route-other", hashed_password="unused", role="user")
            db.add_all([admin, owner, other])
            await db.flush()
            self.headers = {
                user.username: {"X-FreshFood-Token": create_access_token({"sub": user.username})}
                for user in (admin, owner, other)
            }

            self.favorite_name = "番茄/鸡蛋"
            favorite = FavoriteRecipe(
                user_id=owner.id, recipe_name=self.favorite_name,
                ingredients_needed=[], cooking_steps=[],
            )
            favorite_by_id = FavoriteRecipe(
                user_id=owner.id, recipe_name="按 ID 删除",
                ingredients_needed=[], cooking_steps=[],
            )
            pantry = PantryItem(
                user_id=owner.id, name="过期番茄", location="refrigeration",
                initial_weight=100, remaining_weight=100, unit="克",
                expire_at=datetime.now() - timedelta(days=1),
            )
            shopping = ShoppingItem(user_id=owner.id, name="葱")
            post = CommunityPost(
                user_id=owner.id, title="测试动态", content="本地测试",
                image_url="/static/standards/tomato_1.jpg", status=1,
            )
            image = StandardFoodImage(
                food_name="测试标准图", category="vegetable",
                image_url="/static/standards/tomato_1.jpg",
            )
            db.add_all([favorite, favorite_by_id, pantry, shopping, post, image])
            await db.flush()
            comment = PostComment(post_id=post.id, user_id=owner.id, content="测试评论", status=1)
            db.add(comment)
            await db.flush()
            self.ids = {
                "favorite": favorite.id,
                "favorite_by_id": favorite_by_id.id,
                "pantry": pantry.id,
                "shopping": shopping.id,
                "post": post.id,
                "comment": comment.id,
                "image": image.id,
            }
            await db.commit()

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.engine.dispose()

    async def test_post_delete_buttons_reach_authorized_handlers(self):
        owner = self.headers["route-owner"]
        other = self.headers["route-other"]
        admin = self.headers["route-admin"]
        favorite_url = f"/api/recipes/favorites/{self.ids['favorite_by_id']}/delete"

        self.assertEqual((await self.client.post(favorite_url)).status_code, 401)
        self.assertEqual((await self.client.post(favorite_url, headers=other)).status_code, 404)
        self.assertEqual((await self.client.post(favorite_url, headers=owner)).status_code, 200)
        self.assertEqual((await self.client.post(favorite_url, headers=owner)).status_code, 404)

        paths = [
            f"/api/recipes/favorites/by-name/{quote(self.favorite_name, safe='')}/delete",
            f"/api/pantry/items/{self.ids['pantry']}/discard",
            f"/api/shopping/items/{self.ids['shopping']}/delete",
            f"/api/community/comments/{self.ids['comment']}/delete",
            f"/api/community/posts/{self.ids['post']}/delete",
        ]
        for path in paths:
            with self.subTest(path=path):
                response = await self.client.post(path, headers=owner)
                self.assertEqual(response.status_code, 200, response.text)

        image_url = f"/api/admin/food-images/{self.ids['image']}/delete"
        self.assertEqual((await self.client.post(image_url, headers=owner)).status_code, 403)
        self.assertEqual((await self.client.post(image_url, headers=admin)).status_code, 200)


if __name__ == "__main__":
    unittest.main()
