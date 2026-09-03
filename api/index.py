"""Webhook-версия для бесплатного хостинга Vercel."""
import os
import sys
import requests
from flask import Flask, request, jsonify

# чтобы импортировался schedule_logic.py из корня проекта
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from schedule_logic import handle_text

app = Flask(__name__)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API = "https://api.telegram.org/bot{token}/{method}"


def send_message(chat_id: int, text: str):
    keyboard = {
        "keyboard": [["Сегодня", "Завтра"], ["Неделя", "Сейчас"], ["Расписание"]],
        "resize_keyboard": True,
    }
    requests.post(
        API.format(token=BOT_TOKEN, method="sendMessage"),
        json={"chat_id": chat_id, "text": text, "reply_markup": keyboard, "parse_mode": "HTML"},
        timeout=15,
    )


@app.get("/")
def index():
    return "Bot is alive. POST /webhook for Telegram updates."


@app.post("/webhook")
def webhook():
    upd = request.get_json(force=True, silent=True) or {}
    msg = upd.get("message", {})
    text = msg.get("text", "")
    chat_id = msg.get("chat", {}).get("id")
    if chat_id and text and BOT_TOKEN:
        send_message(chat_id, handle_text(text))
    return jsonify(ok=True)
