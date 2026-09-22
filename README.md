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

## Render 部署

仓库根目录的 `render.yaml` 会创建 Web 服务和 PostgreSQL 数据库。部署时在 Render 控制台填写 `AI_API_KEY` 与 `BOOTSTRAP_ADMIN_PASSWORD`，真实密钥不会进入 Git 仓库。

用户上传文件默认保存在容器文件系统。生产环境如需永久保存上传图片，应为服务挂载持久磁盘，或接入对象存储。
