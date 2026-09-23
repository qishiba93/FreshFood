# FreshFood 智鲜厨房

FreshFood 是一个由 FastAPI 提供后端和静态前端的智能厨房应用，包含冰箱库存、AI 菜谱、家庭健康档案、采购清单、分类减碳周榜、美食社区和管理员后台。食材核销时由 AI 判断素食或非素食并估算减碳量，分别计入两个周榜。

本文只说明 Windows 本地运行方式。项目不需要单独运行 Node.js 前端开发服务器，前端文件由 FastAPI 直接提供。

## 运行环境

- Windows 10/11
- Python 3.11 或更高版本
- PowerShell
- DeepSeek Chat API 密钥
- DeepSeek Vision API 密钥

本地推荐使用 SQLite，不需要另外安装 MySQL。项目也保留 MySQL 连接能力，已有 MySQL 数据库时可以按下文切换。

## 安装依赖

在项目根目录打开 PowerShell：

```powershell
cd D:\python_project\FreshFood
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

如果 PowerShell 阻止虚拟环境脚本，可以只对当前窗口执行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

然后重新执行：

```powershell
.\.venv\Scripts\Activate.ps1
```

## 配置 `.env`

首次运行先复制配置模板：

```powershell
Copy-Item .env.example .env
```

本地 SQLite 配置建议填写为：

```dotenv
PERSISTENT_DATA_DIR=./data
DATABASE_URL=sqlite+aiosqlite:///./data/freshfood.db
APP_ENV=development
PORT=8000

DEEPSEEK_API_KEY=你的聊天接口密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

VISION_API_KEY=你的视觉接口密钥
VISION_BASE_URL=https://api.deepseek.com
VISION_MODEL=deepseek-flash

SECRET_KEY=请改成随机长字符串
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=请设置管理员密码
```

不要把真实密钥提交到 Git。`.env` 已被 `.gitignore` 忽略。

`PERSISTENT_DATA_DIR=./data` 会让 SQLite 数据库、用户上传图片和运行时文件保存在项目下的 `data` 目录。首次使用新的 `data` 目录时，程序会自动创建数据库表，并导入内置演示数据；以后启动不会重复导入。

如果使用已有 MySQL，把 `DATABASE_URL` 改为：

```dotenv
DATABASE_URL=mysql+aiomysql://用户名:密码@127.0.0.1:3306/freshplate_db?charset=utf8mb4
```

MySQL 必须已经运行，并且数据库 `freshplate_db` 已创建。不要同时把 `DATABASE_URL` 写成 SQLite 地址和 MySQL 地址。

## 启动本地服务

确保虚拟环境已经激活，在项目根目录执行：

```powershell
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

浏览器访问：

- 用户端：http://127.0.0.1:8000/
- 管理端：http://127.0.0.1:8000/admin.html
- 健康检查：http://127.0.0.1:8000/api/healthz

前端、API 和静态图片都由这一个 FastAPI 服务提供。修改 Python 文件后，`--reload` 会自动重启；修改 HTML、CSS 或 JavaScript 后刷新浏览器即可。

## 首次登录与演示数据

如果设置了 `BOOTSTRAP_ADMIN_USERNAME` 和 `BOOTSTRAP_ADMIN_PASSWORD`，第一次启动会自动创建管理员账号。已有管理员不会被覆盖。

新的 SQLite 数据目录首次启动还会导入演示账号：

- `user1` / `123456`
- `user2` / `123456`
- `user3` / `123456`

演示数据包括健康档案、库存、标准食材图库、收藏菜谱、社区帖子、评论、举报、采购清单、减碳记录和审计日志。

## 数据目录

使用 SQLite 时，主要文件位于：

```text
data/
  freshfood.db
  uploads/
  standards/
```

删除 `data` 目录会删除本地账号、业务数据和上传文件。下次启动会重新创建空数据库并再次导入演示数据，请先备份需要保留的内容。

## 停止和重置

在运行服务的 PowerShell 窗口按 `Ctrl+C` 停止本地服务。

仅想重新启动服务时，直接再次执行启动命令即可。想重置本地演示数据时，先停止服务，再删除 `data` 目录，然后重新启动：

```powershell
Remove-Item -Recurse -Force .\data
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

## 常见问题

### 端口 8000 已被占用

换一个端口启动：

```powershell
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8001
```

然后访问 http://127.0.0.1:8001/。

### AI 返回错误

先检查 `.env` 中的 `DEEPSEEK_API_KEY`、`VISION_API_KEY`、接口地址和模型名称，再确认当前网络可以访问 `https://api.deepseek.com`。聊天和图片识别分别使用各自的密钥。

### 页面打不开或接口返回 401

确认服务仍在运行，并重新登录。浏览器保存的旧登录令牌失效时，退出账号后重新登录即可。
