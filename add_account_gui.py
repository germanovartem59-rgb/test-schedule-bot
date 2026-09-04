"""Простое окно для подключения Telegram-аккаунта (одноразово).
Запуск:  add_account_gui.bat   или   python add_account_gui.py
Всё видно: пароль двухэтапки вводится обычным текстом, ничего не прячется.
В конце само сохраняет API_ID / API_HASH / SESSION_STRING в .env
"""
import os
import re
import asyncio
import threading
import tkinter as tk
from tkinter import messagebox

BASE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE, ".env")
ENV_EXAMPLE = os.path.join(BASE, ".env.example")

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    ApiIdInvalidError,
)


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


# фоновый event loop для Telethon (окно при этом не виснет)
loop = asyncio.new_event_loop()


def _run_loop():
    asyncio.set_event_loop(loop)
    loop.run_forever()


threading.Thread(target=_run_loop, daemon=True).start()


def submit(coro, timeout=120):
    return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=timeout)


state = {"client": None, "phone": None, "phone_code_hash": None,
         "api_id": None, "api_hash": None, "need_password": False}

saved_data, saved_order = load_env(ENV_PATH if os.path.exists(ENV_PATH) else ENV_EXAMPLE)

# ---------------- окно ----------------
root = tk.Tk()
root.title("PhoneMarket — подключение аккаунта")
root.geometry("520x640")
root.configure(bg="#0f172a")
root.resizable(False, False)

FG, MUTED, ACCENT = "#f1f5f9", "#94a3b8", "#22d3ee"

tk.Label(root, text="📱 Подключение Telegram-аккаунта", font=("Segoe UI", 14, "bold"),
         bg="#0f172a", fg=FG).pack(pady=(14, 2))
tk.Label(root, text="API ключи берутся на my.telegram.org → API development tools",
         font=("Segoe UI", 9), bg="#0f172a", fg=MUTED).pack(pady=(0, 10))


def field(label, default="", show=""):
    tk.Label(root, text=label, font=("Segoe UI", 10, "bold"), bg="#0f172a", fg=FG).pack(anchor="w", padx=20)
    e = tk.Entry(root, font=("Segoe UI", 11), width=52, show=show,
                 bg="#1e293b", fg=FG, insertbackground=FG, relief="flat")
    e.insert(0, default or "")
    e.pack(padx=20, pady=(2, 10), ipady=4)
    return e


e_api = field("1. API_ID (цифры)", saved_data.get("API_ID", ""))
e_hash = field("2. API_HASH (строка)", saved_data.get("API_HASH", ""))
e_phone = field("3. Номер полностью (например +56912345678)", "+")
e_code = field("4. Код из Telegram (придёт в приложение)", "")
# пароль ВИДЕН специально — show="" (пусто), ничего не прячется
e_pass = field("5. Пароль двухэтапки (виден, если спросит)", "", show="")

status = tk.Label(root, text="Введи API_ID, API_HASH и номер, жми «Отправить код».",
                  font=("Segoe UI", 10), bg="#0f172a", fg=MUTED, wraplength=480, justify="left")
status.pack(padx=20, pady=6, anchor="w")


def set_status(text, color=MUTED):
    status.config(text=text, fg=color)


btn_frame = tk.Frame(root, bg="#0f172a")
btn_frame.pack(pady=6)
b_send = tk.Button(btn_frame, text="📩 Отправить код", font=("Segoe UI", 11, "bold"),
                   bg="#6366f1", fg="white", width=18, relief="flat", cursor="hand2")
b_send.pack(side="left", padx=6, ipady=4)
b_login = tk.Button(btn_frame, text="✅ Войти", font=("Segoe UI", 11, "bold"),
                    bg="#059669", fg="white", width=18, relief="flat", cursor="hand2",
                    state="disabled")
b_login.pack(side="left", padx=6, ipady=4)

tk.Label(root, text="SESSION_STRING (появится после входа, никому не показывай):",
         font=("Segoe UI", 9), bg="#0f172a", fg=MUTED).pack(anchor="w", padx=20)
t_sess = tk.Text(root, font=("Consolas", 8), height=5, width=62,
                 bg="#1e293b", fg=ACCENT, relief="flat", wrap="char")
t_sess.pack(padx=20, pady=(2, 10))
t_sess.config(state="disabled")


def busy(on):
    b_send.config(state="disabled" if on else "normal")
    b_login.config(state="disabled" if on else "normal")


def do_send():
    api_id = e_api.get().strip()
    api_hash = e_hash.get().strip()
    phone = e_phone.get().replace(" ", "").replace("-", "")
    if not api_id.isdigit():
        messagebox.showwarning("Проверка", "API_ID — это цифры с my.telegram.org")
        return
    if not api_hash:
        messagebox.showwarning("Проверка", "Вставь API_HASH с my.telegram.org")
        return
    if not re.match(r"^\+\d{7,15}$", phone):
        messagebox.showwarning(
            "Проверка",
            f"'{phone}' — неполный номер.\nНужен ПОЛНЫЙ номер с кодом страны,\nнапример +56912345678.")
        return
    busy(True)
    set_status("Подключаюсь и отправляю код…")

    def work():
        try:
            async def _go():
                if state["client"] is not None:
                    try:
                        await state["client"].disconnect()
                    except Exception:
                        pass
                client = TelegramClient(StringSession(), int(api_id), api_hash)
                await client.connect()
                sent = await client.send_code_request(phone)
                state.update({"client": client, "phone": phone,
                              "phone_code_hash": sent.phone_code_hash,
                              "api_id": api_id, "api_hash": api_hash,
                              "need_password": False})
                return True, ""
            ok, err = submit(_go()), None
            root.after(0, lambda: _send_done(ok, err))
        except Exception as e:
            root.after(0, lambda: _send_done(False, str(e)))

    threading.Thread(target=work, daemon=True).start()


def _send_done(ok, err):
    busy(False)
    if not ok:
        set_status(f"❌ Не вышло: {err}\nПроверь API_ID / API_HASH / номер.", "#f87171")
        return
    set_status("✅ Код отправлен! Введи его в поле 4 и жми «Войти».", "#34d399")
    b_login.config(state="normal")
    e_code.focus()


def do_login():
    if not state["client"]:
        messagebox.showwarning("Шаг", "Сначала жми «Отправить код».")
        return
    code = e_code.get().strip().replace(" ", "")
    pwd = e_pass.get()  # пароль виден — так и задумано
    if not state["need_password"] and not code:
        messagebox.showwarning("Шаг", "Введи код из Telegram (поле 4).")
        return
    if state["need_password"] and not pwd:
        messagebox.showwarning("Шаг", "Нужен пароль двухэтапки (поле 5).")
        return
    busy(True)
    set_status("Вхожу…")

    def work():
        try:
            async def _go():
                client = state["client"]
                if state["need_password"]:
                    await client.sign_in(password=pwd)
                else:
                    try:
                        await client.sign_in(state["phone"], code,
                                             phone_code_hash=state["phone_code_hash"])
                    except SessionPasswordNeededError:
                        state["need_password"] = True
                        return "need_password"
                me = await client.get_me()
                sess = client.session.save()
                name = f"{me.first_name or ''} {me.last_name or ''}".strip() or str(me.id)
                try:
                    await client.disconnect()
                except Exception:
                    pass
                state["client"] = None
                return ("ok", sess, f"{name} (@{me.username or 'без ника'})")
            res = submit(_go())
            root.after(0, lambda: _login_done(res))
        except Exception as e:
            root.after(0, lambda: _login_done(("error", str(e))))

    threading.Thread(target=work, daemon=True).start()


def _login_done(res):
    busy(False)
    if res == "need_password" or (isinstance(res, tuple) and res[0] == "need_password"):
        set_status("🔑 Telegram просит пароль двухэтапки — введи его в поле 5\n(он виден) и жми «Войти» ещё раз.", "#fbbf24")
        e_pass.focus()
        return
    if isinstance(res, tuple) and res[0] == "error":
        err = res[1]
        if "PhoneCodeInvalid" in err or "PHONE_CODE_INVALID" in err:
            err = "неверный код — проверь цифры и попробуй ещё раз"
        set_status(f"❌ Не получилось войти: {err}", "#f87171")
        return
    _, sess, who = res
    t_sess.config(state="normal")
    t_sess.delete("1.0", "end")
    t_sess.insert("1.0", sess)
    t_sess.config(state="disabled")
    data, order = load_env(ENV_PATH if os.path.exists(ENV_PATH) else ENV_EXAMPLE)
    data["API_ID"] = state["api_id"]
    data["API_HASH"] = state["api_hash"]
    data["SESSION_STRING"] = sess
    data.setdefault("ADMIN_LOGIN", "admin")
    data.setdefault("ADMIN_PASSWORD", "admin")
    save_env(data, order)
    set_status(f"✅ Вошёл как {who}!\nВсё сохранено в .env — перезапусти start.bat.", "#34d399")


b_send.config(command=do_send)
b_login.config(command=do_login)

root.mainloop()
