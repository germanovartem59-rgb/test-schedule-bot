"""Render entrypoint: gunicorn api.index:app"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import app  # noqa: F401  — gunicorn ищет `app` здесь

# для локальной проверки: python api/index.py
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
