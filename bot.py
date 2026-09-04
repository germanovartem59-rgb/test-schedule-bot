"""Локальный запуск бота через polling. Для теста на своем ПК."""
import os
import time
import requests
from schedule_logic import process_message

API = "https://api.telegram.org/bot{token}/{method}"
_last_bot_msg: dict[int, int] = {}


def delete_prev(token: str, chat_id: int):
    mid = _last_bot_msg.get(chat_id)
    if not mid:
        return
    try:
        requests.post(
            API.format(token=token, method="deleteMessage"),
            json={"chat_id": chat_id, "message_id": mid},
            timeout=10,
        )
    except Exception:
        pass


def send_message(token: str, chat_id: int, text: str, keyboard):
    delete_prev(token, chat_id)
    kb = {"keyboard": keyboard, "resize_keyboard": True}
    try:
        r = requests.post(
            API.format(token=token, method="sendMessage"),
            json={"chat_id": chat_id, "text": text, "reply_markup": kb, "parse_mode": "HTML"},
            timeout=15,
        ).json()
        mid = (r.get("result") or {}).get("message_id")
        if mid:
            _last_bot_msg[chat_id] = mid
    except Exception as e:
        print("send error:", e)


def run_polling(token: str):
    offset = 0
    print("Бот запущен (polling). Нажми Ctrl+C чтобы остановить.")
    while True:
        try:
            r = requests.get(
                API.format(token=token, method="getUpdates"),
                params={"timeout": 30, "offset": offset},
                timeout=35,
            ).json()
            for upd in r.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                text = msg.get("text", "")
                chat = msg.get("chat", {}) or {}
                chat_id = chat.get("id")
                user = msg.get("from", {}) or {}
                user_id = user.get("id", 0)
                if chat_id and text:
                    answer, kb = process_message(user_id, text)
                    send_message(token, chat_id, answer, kb)
        except Exception as e:
            print("Ошибка:", e)
            time.sleep(3)


if __name__ == "__main__":
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        token = input("Вставь токен от @BotFather: ").strip()
    if not token:
        raise SystemExit("Нет токена, выхожу.")
    run_polling(token)
