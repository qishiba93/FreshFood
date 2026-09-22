"""ModelScope Studio entry point."""
import os


os.environ.setdefault("APP_ENV", "production")
os.environ.setdefault("PERSISTENT_DATA_DIR", "/mnt/workspace/freshfood")

from backend.main import app  # noqa: E402


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7860)
