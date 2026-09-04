"""Одноразовый мастер подключения аккаунта-продавца.
Запуск:  add_account.bat   или   python add_account.py
Спросит: API_ID, API_HASH, номер телефона, код из Telegram, пароль 2FA (если есть).
В конце сам запишет всё в .env — руками ничего править не надо.
"""
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE, ".env")
ENV_EXAMPLE = os.path.join(BASE, ".env.example")


def load_env(path):
    data, order = {}, []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f.read().splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    k = k.strip()
                    if k not in order:
                        order.append(k)
                    data[k] = v.strip()
    return data, order


def save_env(data, order):
    for k in data:
        if k not in order:
            order.append(k)
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        for k in order:
            f.write(f"{k}={data.get(k, '')}\n")
    print(f"\n💾 Сохранено в {ENV_PATH}")


print("=== Подключение Telegram-аккаунта (1 раз) ===\n")
print("1) Возьми API_ID и API_HASH на https://my.telegram.org -> API development tools\n")

data, order = load_env(ENV_PATH if os.path.exists(ENV_PATH) else ENV_EXAMPLE)

cur_id = data.get("API_ID", "")
cur_hash = data.get("API_HASH", "")
api_id = (input(f"API_ID [{cur_id}]: ").strip() or cur_id).strip()
api_hash = (input(f"API_HASH [{cur_hash[:6] + '...' if cur_hash else ''}]: ").strip() or cur_hash).strip()

if not api_id.isdigit() or not api_hash:
    print("\n❌ Нужны нормальные API_ID (цифры) и API_HASH (строка). Возьми на my.telegram.org и запусти снова.")
    raise SystemExit(1)

phone = input("Номер телефона аккаунта (полностью, например +56912345678): ").strip()
digits = phone.replace(" ", "").replace("-", "")
if not re.match(r"^\+\d{7,15}$", digits):
    print(f"\n❌ '{phone}' — это неполный номер. Нужен ПОЛНЫЙ номер с кодом страны.")
    print("Например для Чили: +56912345678 (код +56 + ещё 9 цифр номера).")
    print("У тебя сейчас только код страны без самого номера — допиши цифры.")
    raise SystemExit(1)
phone = digits

print("\nСейчас Telegram пришлёт код в приложение — введи его ниже.")
print("(если включена двухэтапка — после кода спросит пароль)\n")

import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError


async def _login():
    async with TelegramClient(StringSession(), int(api_id), api_hash) as client:
        await client.connect()
        if not await client.is_user_authorized():
            await client.send_code_request(phone)
            code = input("Код из Telegram: ").strip().replace(" ", "")
            try:
                await client.sign_in(phone, code)
            except SessionPasswordNeededError:
                # пароль ВИДЕН (обычный input) — так и задумано
                pwd = input("Пароль двухэтапки (видно): ")
                await client.sign_in(password=pwd)
        me = await client.get_me()
        name = f"{me.first_name or ''} {me.last_name or ''}".strip() or str(me.id)
        print(f"\n✅ Вошёл как: {name} (@{me.username or 'без ника'})")
        return client.session.save()


try:
    sess = asyncio.run(_login())
except Exception as e:
    print(f"\n❌ Не получилось войти: {e}")
    print("Проверь API_ID/API_HASH/номер и попробуй ещё раз.")
    raise SystemExit(1)

print("\nТвоя SESSION_STRING (никому не показывай):\n")
print(sess)

data["API_ID"] = api_id
data["API_HASH"] = api_hash
data["SESSION_STRING"] = sess
if "ADMIN_LOGIN" not in data:
    data["ADMIN_LOGIN"] = "admin"
if "ADMIN_PASSWORD" not in data:
    data["ADMIN_PASSWORD"] = "admin"
save_env(data, order)

print("\n✅ Готово! Перезапусти start.bat и нажми «Проверить связь» в Дашборде.")
