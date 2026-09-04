"""SQLite-слой для барахолки телефонов. Без внешних зависимостей."""
import os
import sqlite3
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "market.db")


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _conn() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS phones(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            price INTEGER NOT NULL DEFAULT 0,
            currency TEXT DEFAULT '₽',
            condition TEXT DEFAULT 'б/у',
            memory TEXT DEFAULT '',
            akb TEXT DEFAULT '',
            description TEXT DEFAULT '',
            photo TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            created_at INTEGER DEFAULT 0
        )""")
        # миграция для старых баз: колонка АКБ
        try:
            c.execute("ALTER TABLE phones ADD COLUMN akb TEXT DEFAULT ''")
        except Exception:
            pass
        c.execute("""
        CREATE TABLE IF NOT EXISTS groups(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT DEFAULT '',
            username TEXT NOT NULL UNIQUE,
            topic TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            last_post_at INTEGER DEFAULT 0,
            last_error TEXT DEFAULT ''
        )""")
        # миграция для старых баз: колонка топика
        try:
            c.execute("ALTER TABLE groups ADD COLUMN topic TEXT DEFAULT ''")
        except Exception:
            pass
        c.execute("""
        CREATE TABLE IF NOT EXISTS posts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_id INTEGER DEFAULT 0,
            group_id INTEGER DEFAULT 0,
            group_name TEXT DEFAULT '',
            phone_title TEXT DEFAULT '',
            status TEXT DEFAULT 'ok',
            error TEXT DEFAULT '',
            created_at INTEGER DEFAULT 0
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        )""")
        defaults = {
            "contact": "@username",
            "city": "Кишинёв",
            "signature": "",
            "delay_sec": "15",
            "autopost_on": "0",
            "autopost_interval_min": "60",
            "template": "{title}\n{memory}\nАкб {akb}\n{description}\nЦена:{price}{currency}",
        }
        for k, v in defaults.items():
            c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
        # кто уже пользовался старым шаблоном с эмодзи — обновляем на стиль KNYAZ
        OLD_TPL = "📱 <b>{title}</b>\n\n💾 Память: {memory}\n📦 Состояние: {condition}\n📍 Город: {city}\n💰 Цена: {price} {currency}\n\n{description}\n\n☎️ Связь: {contact}\n{signature}"
        try:
            c.execute("UPDATE settings SET value=? WHERE key='template' AND value=?",
                      (defaults["template"], OLD_TPL))
        except Exception:
            pass
        c.commit()


def _row_to_dict(r):
    return dict(r) if r is not None else None


# ---- phones ----
def add_phone(title, price, currency="₽", condition="б/у", memory="", akb="", description="", photo="", status="active"):
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO phones(title,price,currency,condition,memory,akb,description,photo,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (title.strip(), int(price or 0), currency, condition, memory, akb, description, photo, status, int(time.time())),
        )
        c.commit()
        return cur.lastrowid


def list_phones(only_active=False):
    with _conn() as c:
        q = "SELECT * FROM phones ORDER BY id DESC"
        if only_active:
            q = "SELECT * FROM phones WHERE status='active' ORDER BY id DESC"
        return [_row_to_dict(r) for r in c.execute(q).fetchall()]


def get_phone(pid):
    with _conn() as c:
        return _row_to_dict(c.execute("SELECT * FROM phones WHERE id=?", (pid,)).fetchone())


def update_phone(pid, **fields):
    allowed = {"title", "price", "currency", "condition", "memory", "akb", "description", "photo", "status"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return False
    vals.append(pid)
    with _conn() as c:
        c.execute(f"UPDATE phones SET {', '.join(sets)} WHERE id=?", vals)
        c.commit()
        return True


def delete_phone(pid):
    with _conn() as c:
        c.execute("DELETE FROM phones WHERE id=?", (pid,))
        c.commit()


def parse_group_link(raw: str):
    """Разбирает @username или ссылку t.me в (username, topic).
    Примеры:
      @baraholka -> (@baraholka, '')
      https://t.me/baraholka_pmr_pridnestrovie/6369/1023337 -> (@baraholka_pmr_pridnestrovie, '6369')
      https://t.me/c/1234567/89 -> (-1001234567, '')
      https://t.me/c/1234567/89?thread=5 -> (-1001234567, '5')
    """
    import re
    from urllib.parse import urlparse, parse_qs
    u = (raw or "").strip()
    if not u:
        return None, ""
    if "t.me/" not in u and "telegram.me/" not in u:
        if not u.startswith("@") and not u.lstrip("-").isdigit():
            u = "@" + u
        return u, ""
    if "://" not in u:
        u = "https://" + u
    try:
        p = urlparse(u)
        parts = [x for x in p.path.split("/") if x]
        q = parse_qs(p.query)
        thread = (q.get("thread") or [""])[0]
        if not parts:
            return None, ""
        if parts[0] == "c" and len(parts) >= 2 and parts[1].isdigit():
            # приватная группа: t.me/c/XXXX/...
            return "-100" + parts[1], thread if thread.isdigit() else ""
        name = "@" + parts[0]
        topic = ""
        if len(parts) >= 3 and parts[1].isdigit():
            # форум: t.me/name/ТОПИК/сообщение
            topic = parts[1]
        elif thread.isdigit():
            topic = thread
        return name, topic
    except Exception:
        return None, ""


# ---- groups ----
def add_group(title, username, topic=""):
    u = (username or "").strip()
    if not u:
        return None
    auto_topic = ""
    if "t.me/" in u or "telegram.me/" in u:
        u, auto_topic = parse_group_link(u)
        if not u:
            return None
    elif not u.startswith("@") and not u.lstrip("-").isdigit():
        u = "@" + u
    if not topic:
        topic = auto_topic
    with _conn() as c:
        try:
            cur = c.execute("INSERT INTO groups(title,username,topic) VALUES(?,?,?)",
                            (title.strip() or u, u, (topic or "").strip()))
            c.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None


def list_groups():
    with _conn() as c:
        return [_row_to_dict(r) for r in c.execute("SELECT * FROM groups ORDER BY id DESC").fetchall()]


def toggle_group(gid):
    with _conn() as c:
        r = c.execute("SELECT active FROM groups WHERE id=?", (gid,)).fetchone()
        if not r:
            return None
        new = 0 if r["active"] else 1
        c.execute("UPDATE groups SET active=? WHERE id=?", (new, gid))
        c.commit()
        return new


def set_group_topic(gid, topic):
    with _conn() as c:
        c.execute("UPDATE groups SET topic=? WHERE id=?", ((topic or "").strip(), gid))
        c.commit()


def delete_group(gid):
    with _conn() as c:
        c.execute("DELETE FROM groups WHERE id=?", (gid,))
        c.commit()


def mark_group_post(gid, ok=True, error=""):
    import time as _t
    with _conn() as c:
        if ok:
            c.execute("UPDATE groups SET last_post_at=?, last_error='' WHERE id=?", (int(_t.time()), gid))
        else:
            c.execute("UPDATE groups SET last_error=? WHERE id=?", ((error or "")[:500], gid))
        c.commit()


# ---- posts log ----
def log_post(phone_id, group_id, group_name, phone_title, status="ok", error=""):
    with _conn() as c:
        c.execute(
            "INSERT INTO posts(phone_id,group_id,group_name,phone_title,status,error,created_at) VALUES(?,?,?,?,?,?,?)",
            (phone_id, group_id, group_name, phone_title, status, (error or "")[:800], int(time.time())),
        )
        c.commit()


def list_posts(limit=100):
    with _conn() as c:
        return [_row_to_dict(r) for r in c.execute("SELECT * FROM posts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]


def stats():
    import time as _t
    day_ago = int(_t.time()) - 86400
    with _conn() as c:
        phones = c.execute("SELECT COUNT(*) v FROM phones WHERE status='active'").fetchone()["v"]
        groups = c.execute("SELECT COUNT(*) v FROM groups WHERE active=1").fetchone()["v"]
        today = c.execute("SELECT COUNT(*) v FROM posts WHERE created_at>? AND status='ok'", (day_ago,)).fetchone()["v"]
        errors = c.execute("SELECT COUNT(*) v FROM posts WHERE status='error'").fetchone()["v"]
        return {"phones": phones, "groups": groups, "today": today, "errors": errors}


# ---- settings ----
def get_settings():
    with _conn() as c:
        return {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings").fetchall()}


def save_settings(data: dict):
    with _conn() as c:
        for k, v in data.items():
            c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))
        c.commit()


def build_text(phone: dict, s: dict) -> str:
    tpl = s.get("template") or "{title}\n{memory}\nАкб {akb}\n{description}\nЦена:{price}{currency}"
    try:
        text = tpl.format(
            title=phone.get("title", ""),
            price=phone.get("price", ""),
            currency=phone.get("currency", "₽"),
            condition=phone.get("condition", ""),
            memory=phone.get("memory", ""),
            akb=phone.get("akb", ""),
            description=phone.get("description", ""),
            city=s.get("city", ""),
            contact=s.get("contact", ""),
            signature=s.get("signature", ""),
        )
    except Exception:
        text = f"{phone.get('title','')}\n{phone.get('memory','')}\n{phone.get('description','')}\nЦена:{phone.get('price','')}{phone.get('currency','₽')}"
    # чистим пустые строки: если АКБ/память не заполнены — строка пропадает, а не висит пустой
    lines = [l.rstrip() for l in text.split("\n")]
    lines = [l for l in lines if l.strip() not in ("", "Акб", "АКБ", "АКБ ", "Акб ")]
    return "\n".join(lines).strip()


init_db()
