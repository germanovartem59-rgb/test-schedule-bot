"""Юзербот для постинга в супергруппы-барахолки от имени твоего аккаунта.

Почему юзербот, а не Bot API:
- боты НЕ могут писать в чужие барахолки, только туда где они админы
- юзербот (Telethon) пишет как человек в любые супергруппы, где ты состоишь

Нужны: API_ID, API_HASH (https://my.telegram.org), SESSION_STRING (gen_session.py)
"""
import os
import asyncio

import envfix
envfix.load_dotenv()  # чтобы работал и при прямом импорте без app.py

API_ID = int(os.getenv("API_ID", "0") or 0)
API_HASH = os.getenv("API_HASH", "")
SESSION_STRING = os.getenv("SESSION_STRING", "")


def is_configured() -> bool:
    return bool(API_ID and API_HASH and SESSION_STRING)


def _client():
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    return TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)


async def _send_one(client, target: str, text: str, photo: str | None, topic=None):
    """Отправка в одну группу. photo может быть URL или локальным путём.
    topic — ID темы форума (топика): пост уйдёт в этот топик, а не в общий чат."""
    import requests, tempfile
    reply_to = None
    try:
        if topic not in (None, "", 0, "0"):
            reply_to = int(topic)
    except (ValueError, TypeError):
        reply_to = None
    fpath = None
    if photo and photo.startswith("http"):
        try:
            r = requests.get(photo, timeout=20)
            if r.ok and r.content:
                suf = ".jpg"
                ct = r.headers.get("Content-Type", "")
                if "png" in ct:
                    suf = ".png"
                elif "webp" in ct:
                    suf = ".webp"
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suf)
                tmp.write(r.content)
                tmp.close()
                fpath = tmp.name
        except Exception:
            fpath = None
    elif photo and os.path.exists(photo):
        fpath = photo
    try:
        if fpath:
            await client.send_file(target, fpath, caption=text, parse_mode="html", reply_to=reply_to)
        else:
            # чистый HTML без <b> ломается редко — шлём как есть
            await client.send_message(target, text, parse_mode="html", reply_to=reply_to)
        return True, ""
    except Exception as e:
        return False, str(e)[:500]
    finally:
        if fpath and photo and photo.startswith("http"):
            try:
                os.remove(fpath)
            except Exception:
                pass


async def _broadcast_async(phone: dict, groups: list[dict], text: str, delay_sec: int):
    from telethon.errors import FloodWaitError, ChatWriteForbiddenError
    res = []
    async with _client() as client:
        for g in groups:
            target = g["username"]
            label = target + (f" (топик {g.get('topic')})" if g.get("topic") else "")
            try:
                ok, err = await _send_one(client, target, text, phone.get("photo") or None, g.get("topic"))
                res.append({"group_id": g["id"], "group": label, "ok": ok, "error": err})
            except FloodWaitError as e:
                res.append({"group_id": g["id"], "group": target, "ok": False, "error": f"FloodWait {e.seconds}с — увеличь задержку"})
                await asyncio.sleep(min(e.seconds, 60))
            except ChatWriteForbiddenError:
                res.append({"group_id": g["id"], "group": target, "ok": False, "error": "Нет прав писать (бан/только чтение)"})
            except Exception as e:
                res.append({"group_id": g["id"], "group": target, "ok": False, "error": str(e)[:300]})
            await asyncio.sleep(max(1, int(delay_sec or 15)))
    return res


def broadcast(phone: dict, groups: list[dict], text: str, delay_sec: int = 15):
    """Синхронная обёртка для Flask. Возвращает список результатов."""
    if not is_configured():
        return [{"group_id": g["id"], "group": g["username"], "ok": False, "error": "Нет API_ID/API_HASH/SESSION_STRING в .env"} for g in groups]
    # новый event loop для потока Flask
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_broadcast_async(phone, groups, text, delay_sec))
    finally:
        try:
            loop.close()
        except Exception:
            pass


async def _check_async():
    async with _client() as client:
        me = await client.get_me()
        return {"ok": True, "name": f"{me.first_name or ''} @{me.username or ''}".strip()}


def check_connection():
    if not is_configured():
        return {"ok": False, "error": "Заполни API_ID / API_HASH / SESSION_STRING"}
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_check_async())
    except Exception as e:
        return {"ok": False, "error": str(e)[:500]}
    finally:
        try:
            loop.close()
        except Exception:
            pass
