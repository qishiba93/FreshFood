# FreshFood / 智鲜厨房 OS

FastAPI 全栈智能厨房应用，包含食材库存、AI 菜谱、家庭健康画像、采购清单、减碳账本、美食社区和管理员后台。

## 本地启动

1. 复制 `.env.example` 为 `.env` 并填写数据库和 AI 密钥。
2. 安装依赖：`pip install -r requirements.txt`
3. 启动：`uvicorn backend.main:app --host 0.0.0.0 --port 8000`
4. 访问：`http://localhost:8000`

## Docker

```bash
docker build -t freshfood .
docker run --rm -p 8000:8000 --env-file .env freshfood
```

## 魔搭创空间部署（国内免费）

创建一个 **Docker SDK** 类型的公开创空间并选择免费 CPU，然后把本仓库同步到创空间。平台通过 `Dockerfile` 启动根目录的 `app.py`，服务监听 `0.0.0.0:7860`。

在创空间设置中添加以下 Secrets：

- `DEEPSEEK_API_KEY`
- `VISION_API_KEY`
- `SECRET_KEY`
- `BOOTSTRAP_ADMIN_PASSWORD`

再添加普通变量 `BOOTSTRAP_ADMIN_USERNAME=admin`。数据库和上传图片默认保存在魔搭持久目录 `/mnt/workspace/freshfood`，无需另外创建数据库。

首次启动时会导入演示数据，包括 `user1`、`user2`、`user3` 的健康档案、库存、菜谱、社区和减碳数据。已有账号和业务数据不会被覆盖；自动创建的演示账号初始密码为 `123456`。
