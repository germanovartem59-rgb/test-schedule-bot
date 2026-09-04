"""Подхват .env без внешних зависимостей (для локального запуска).
На Render используются настоящие Env Vars — они в приоритете и не перезаписываются.
"""
import os


def load_dotenv(path=None):
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        if not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as f:
            for line in f.read().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass
