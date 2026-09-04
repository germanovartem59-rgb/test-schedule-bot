"""Генератор SESSION_STRING для юзербота.
1. Иди на https://my.telegram.org -> API development tools -> получи API_ID и API_HASH
2. Запусти:  python gen_session.py
3. Введи телефон + код из Telegram -> получишь строку -> вставь в .env как SESSION_STRING
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

API_ID = int(os.getenv("API_ID", "0") or input("API_ID: ").strip() or 0)
API_HASH = os.getenv("API_HASH", "") or input("API_HASH: ").strip()

import asyncio
import getpass
from telethon import TelegramClient
from telethon.sessions import StringSession


async def _main():
    async with TelegramClient(StringSession(), API_ID, API_HASH) as client:
        await client.start(
            code_callback=lambda: input("Код из Telegram: "),
            password_callback=lambda: getpass.getpass("Пароль двухэтапки: "),
        )
        print("\n✅ Готово! Твоя SESSION_STRING:\n")
        print(client.session.save())
        print("\nВставь её в .env / Render Env как SESSION_STRING")


asyncio.run(_main())
