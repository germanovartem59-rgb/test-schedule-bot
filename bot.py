"""Локальный запуск бота через polling. Для теста на своем ПК."""
import os
import time
import requests
from schedule_logic import process_message, process_callback

API = "https://api.telegram.org/bot{token}/{method}"
_last_bot_msg: dict[int, int] = {}


def api(token: str, method: str, payload: dict):
    try:
        return requests.post(
            API.format(token=token, method=method), json=payload, timeout=15
        ).json()
    except Exception as e:
        print("api error:", e)
        return {}


def show(token: str, chat_id: int, text: str, kb, edit_id: int | None = None):
    """Показать сообщение: отредактировать старое или отправить новое."""
    markup = {"inline_keyboard": kb} if kb else None
    mid = edit_id or _last_bot_msg.get(chat_id)
    if mid:
        r = api(token, "editMessageText", {
            "chat_id": chat_id, "message_id": mid,
            "text": text, "parse_mode": "HTML", "reply_markup": markup,
        })
        if r.get("ok"):
            _last_bot_msg[chat_id] = mid
            return
    r = api(token, "sendMessage", {
        "chat_id": chat_id, "text": text,
        "parse_mode": "HTML", "reply_markup": markup,
    })
    new_id = (r.get("result") or {}).get("message_id")
    if new_id:
        _last_bot_msg[chat_id] = new_id


def clear_old_keyboard(token: str, chat_id: int):
    """Убирает залипшую reply-клавиатуру у пользователя (один раз)."""
    try:
        r = requests.post(
            API.format(token=token, method="sendMessage"),
            json={"chat_id": chat_id, "text": "⌨️",
                  "reply_markup": {"remove_keyboard": True}},
            timeout=15,
        ).json()
        mid = (r.get("result") or {}).get("message_id")
        if mid:
            requests.post(
                API.format(token=token, method="deleteMessage"),
                json={"chat_id": chat_id, "message_id": mid},
                timeout=10,
            )
    except Exception:
        pass


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
                # --- нажатие inline-кнопки ---
                cb = upd.get("callback_query")
                if cb:
                    msg = cb.get("message", {}) or {}
                    chat = msg.get("chat", {}) or {}
                    chat_id = chat.get("id")
                    mid = msg.get("message_id")
                    user = cb.get("from", {}) or {}
                    api(token, "answerCallbackQuery", {"callback_query_id": cb.get("id")})
                    if chat_id:
                        answer, kb = process_callback(user.get("id", 0), cb.get("data", ""))
                        show(token, chat_id, answer, kb, edit_id=mid)
                    continue
                # --- обычное сообщение ---
                msg = upd.get("message", {})
                text = msg.get("text", "")
                chat = msg.get("chat", {}) or {}
                chat_id = chat.get("id")
                chat_type = chat.get("type", "private")
                user = msg.get("from", {}) or {}
                if chat_id and text:
                    answer, kb = process_message(user.get("id", 0), text, chat_type=chat_type)
                    if answer is None:
                        continue  # в группе обычный текст игнорим
                    low = text.strip().lower().lstrip("./").split("@")[0]
                    if low in ("start", "старт", "привет"):
                        clear_old_keyboard(token, chat_id)
                    show(token, chat_id, answer, kb)
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
