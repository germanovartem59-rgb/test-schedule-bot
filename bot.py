"""Локальный запуск бота через polling. Для теста на своем ПК."""
import os
import time
import requests
from schedule_logic import handle_text

API = "https://api.telegram.org/bot{token}/{method}"


def send_message(token: str, chat_id: int, text: str):
    keyboard = {
        "keyboard": [["Сегодня", "Завтра"], ["Неделя"]],
        "resize_keyboard": True,
    }
    requests.post(
        API.format(token=token, method="sendMessage"),
        json={"chat_id": chat_id, "text": text, "reply_markup": keyboard, "parse_mode": "HTML"},
        timeout=15,
    )


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
                chat_id = msg.get("chat", {}).get("id")
                if chat_id and text:
                    answer = handle_text(text)
                    send_message(token, chat_id, answer)
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
