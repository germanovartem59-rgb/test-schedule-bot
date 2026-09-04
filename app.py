"""Сайт-панель для продажи телефонов в супергруппах-барахолках.
Запуск локально:  python app.py   ->  http://127.0.0.1:5000
На Render: gunicorn api.index:app (api/index.py импортирует app ниже)
"""
import os
import time
import random
import threading
from functools import wraps
from flask import Flask, request, jsonify, session, redirect, Response

import envfix
envfix.load_dotenv()  # подхватить .env ДО чтения настроек и импорта poster

import market_db as db
import poster

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "phone-market-secret-123")

ADMIN_LOGIN = os.getenv("ADMIN_LOGIN", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------------- auth ----------------
def login_required(fn):
    @wraps(fn)
    def w(*a, **kw):
        if not session.get("auth"):
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "need login"}), 401
            return redirect("/login")
        return fn(*a, **kw)
    return w

# ---------------- autopost loop ----------------
_autopost_state = {"last_run": 0}

def autopost_worker():
    while True:
        try:
            time.sleep(60)
            s = db.get_settings()
            if s.get("autopost_on") != "1":
                continue
            interval = max(5, int(s.get("autopost_interval_min") or 60))
            if time.time() - _autopost_state["last_run"] < interval * 60:
                continue
            phones = db.list_phones(only_active=True)
            groups = [g for g in db.list_groups() if g["active"]]
            if not phones or not groups:
                continue
            phone = random.choice(phones)
            text = db.build_text(phone, s)
            delay = int(s.get("delay_sec") or 15)
            res = poster.broadcast(phone, groups, text, delay)
            for r in res:
                db.log_post(phone["id"], r["group_id"], r["group"], phone["title"],
                            "ok" if r["ok"] else "error", r.get("error", ""))
                db.mark_group_post(r["group_id"], r["ok"], r.get("error", ""))
            _autopost_state["last_run"] = time.time()
        except Exception:
            pass

threading.Thread(target=autopost_worker, daemon=True).start()

# ---------------- pages ----------------
@app.get("/login")
def login_page():
    return Response(LOGIN_HTML, mimetype="text/html")

@app.post("/login")
def do_login():
    if request.is_json:
        d = request.json or {}
        lg, pw = d.get("login", ""), d.get("password", "")
    else:
        lg, pw = request.form.get("login", ""), request.form.get("password", "")
    if lg == ADMIN_LOGIN and pw == ADMIN_PASSWORD:
        session["auth"] = True
        if request.is_json:
            return jsonify({"ok": True})
        return redirect("/")
    if request.is_json:
        return jsonify({"ok": False, "error": "Неверный логин или пароль"}), 403
    return Response(LOGIN_HTML.replace("<!--ERR-->", "<p class='err'>Неверный логин или пароль</p>"), mimetype="text/html")

@app.get("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.get("/")
def root():
    if not session.get("auth"):
        return redirect("/login")
    return Response(INDEX_HTML, mimetype="text/html")

# ---------------- API ----------------
@app.get("/api/stats")
@login_required
def api_stats():
    s = db.stats()
    s["tg_ok"] = poster.is_configured()
    s["autopost_on"] = db.get_settings().get("autopost_on") == "1"
    return jsonify({"ok": True, **s, "posts": db.list_posts(12)})

@app.get("/api/phones")
@login_required
def api_phones():
    return jsonify({"ok": True, "items": db.list_phones()})

@app.post("/api/phones")
@login_required
def api_phone_add():
    d = request.json or {}
    if not d.get("title"):
        return jsonify({"ok": False, "error": "Нужно название"}), 400
    pid = db.add_phone(d.get("title"), d.get("price", 0), d.get("currency", "₽"),
                       d.get("condition", "б/у"), d.get("memory", ""), d.get("akb", ""),
                       d.get("description", ""), d.get("photo", ""), d.get("status", "active"))
    return jsonify({"ok": True, "id": pid})

@app.put("/api/phones/<int:pid>")
@login_required
def api_phone_upd(pid):
    db.update_phone(pid, **(request.json or {}))
    return jsonify({"ok": True})

@app.delete("/api/phones/<int:pid>")
@login_required
def api_phone_del(pid):
    db.delete_phone(pid)
    return jsonify({"ok": True})

@app.get("/api/groups")
@login_required
def api_groups():
    return jsonify({"ok": True, "items": db.list_groups()})

@app.post("/api/groups")
@login_required
def api_group_add():
    d = request.json or {}
    gid = db.add_group(d.get("title", ""), d.get("username", ""), d.get("topic", ""))
    if not gid:
        return jsonify({"ok": False, "error": "Такая группа уже есть или пустая ссылка"}), 400
    return jsonify({"ok": True, "id": gid})

@app.patch("/api/groups/<int:gid>")
@login_required
def api_group_toggle(gid):
    d = request.json or {}
    if "topic" in d:
        db.set_group_topic(gid, d.get("topic", ""))
        return jsonify({"ok": True})
    v = db.toggle_group(gid)
    return jsonify({"ok": True, "active": v})

@app.delete("/api/groups/<int:gid>")
@login_required
def api_group_del(gid):
    db.delete_group(gid)
    return jsonify({"ok": True})

@app.get("/api/logs")
@login_required
def api_logs():
    return jsonify({"ok": True, "items": db.list_posts(150)})

@app.get("/api/settings")
@login_required
def api_get_settings():
    return jsonify({"ok": True, "settings": db.get_settings()})

@app.post("/api/settings")
@login_required
def api_save_settings():
    db.save_settings(request.json or {})
    return jsonify({"ok": True})

@app.post("/api/preview/<int:pid>")
@login_required
def api_preview(pid):
    ph = db.get_phone(pid)
    if not ph:
        return jsonify({"ok": False, "error": "Нет телефона"}), 404
    return jsonify({"ok": True, "text": db.build_text(ph, db.get_settings())})

@app.post("/api/check-tg")
@login_required
def api_check():
    return jsonify(poster.check_connection())

@app.post("/api/post-now")
@login_required
def api_post_now():
    d = request.json or {}
    ph = db.get_phone(int(d.get("phone_id", 0)))
    if not ph:
        return jsonify({"ok": False, "error": "Выбери телефон"}), 400
    all_g = db.list_groups()
    ids = set(d.get("group_ids") or [])
    groups = [g for g in all_g if (not ids or g["id"] in ids) and g["active"]]
    if not groups:
        return jsonify({"ok": False, "error": "Нет активных групп"}), 400
    s = db.get_settings()
    text = d.get("text") or db.build_text(ph, s)
    delay = int(d.get("delay_sec") or s.get("delay_sec") or 15)
    # чтобы сайт не висел — постим в фоне, сразу отвечаем
    def _bg():
        res = poster.broadcast(ph, groups, text, delay)
        for r in res:
            db.log_post(ph["id"], r["group_id"], r["group"], ph["title"],
                        "ok" if r["ok"] else "error", r.get("error", ""))
            db.mark_group_post(r["group_id"], r["ok"], r.get("error", ""))
    threading.Thread(target=_bg, daemon=True).start()
    return jsonify({"ok": True, "msg": f"Рассылка запущена в {len(groups)} групп(ы). Смотри Историю."})

@app.post("/api/upload")
@login_required
def api_upload():
    f = request.files.get("photo")
    if not f:
        return jsonify({"ok": False, "error": "Нет файла"}), 400
    name = f"{int(time.time())}_{f.filename}".replace(" ", "_")
    path = os.path.join(UPLOAD_DIR, name)
    f.save(path)
    return jsonify({"ok": True, "url": f"/static/uploads/{name}", "path": path})

@app.get("/static/uploads/<path:n>")
def uploads(n):
    p = os.path.join(UPLOAD_DIR, n)
    if not os.path.exists(p):
        return "no", 404
    with open(p, "rb") as f:
        data = f.read()
    ext = n.rsplit(".", 1)[-1].lower() if "." in n else "jpg"
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(ext, "image/jpeg")
    return Response(data, mimetype=mime)


LOGIN_HTML = """<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PhoneMarket — вход</title><script src="https://cdn.tailwindcss.com"></script></head>
<body class="min-h-screen flex items-center justify-center bg-[#0b1020] text-white" style="background:radial-gradient(1000px 500px at 20% 10%,#4f46e533,transparent),radial-gradient(800px 400px at 90% 90%,#06b6d433,transparent),#0b1020">
<form method="post" class="w-[360px] p-8 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-xl shadow-2xl">
<div class="text-3xl font-black mb-1">📱 Phone<span class="text-indigo-400">Market</span></div>
<p class="text-sm text-slate-400 mb-6">Панель барахолки · супергруппы</p>
<!--ERR-->
<input name="login" placeholder="Логин" value="admin" class="w-full px-4 py-3 rounded-xl bg-black/40 border border-white/10 outline-none focus:border-indigo-500 mb-3">
<input name="password" type="password" placeholder="Пароль" class="w-full px-4 py-3 rounded-xl bg-black/40 border border-white/10 outline-none focus:border-indigo-500 mb-4">
<button class="w-full py-3 rounded-xl font-bold bg-gradient-to-r from-indigo-500 to-cyan-400 hover:opacity-90">Войти →</button>
<p class="text-xs text-slate-500 mt-4">Логин: <b>admin</b> · Пароль: <b>admin</b></p>
</form></body></html>"""

INDEX_HTML = """<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0b1020">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>PhoneMarket — панель барахолки</title><script src="https://cdn.tailwindcss.com"></script>
<style>body{font-family:Inter,system-ui} .glass{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.09);backdrop-filter:blur(14px)} .navbtn.on{background:linear-gradient(90deg,#6366f1,#22d3ee);color:#fff} input,textarea,select{font-size:16px!important} button{min-height:40px} ::-webkit-scrollbar{width:8px;height:8px}::-webkit-scrollbar-thumb{background:#334155;border-radius:8px}</style></head>
<body class="min-h-screen text-slate-100" style="background:radial-gradient(1000px 500px at 10% 0%,#4f46e522,transparent),radial-gradient(900px 500px at 100% 100%,#06b6d422,transparent),#0b1020">
<div class="flex min-h-screen">
<aside class="w-60 shrink-0 p-4 hidden md:flex flex-col gap-2">
<div class="text-2xl font-black px-2 py-3">📱 Phone<span class="text-indigo-400">Market</span></div>
<button data-tab="dash" class="navbtn on text-left px-4 py-2.5 rounded-xl hover:bg-white/5">📊 Дашборд</button>
<button data-tab="phones" class="navbtn text-left px-4 py-2.5 rounded-xl hover:bg-white/5">📦 Каталог</button>
<button data-tab="groups" class="navbtn text-left px-4 py-2.5 rounded-xl hover:bg-white/5">👥 Группы</button>
<button data-tab="send" class="navbtn text-left px-4 py-2.5 rounded-xl hover:bg-white/5">🚀 Рассылка</button>
<button data-tab="logs" class="navbtn text-left px-4 py-2.5 rounded-xl hover:bg-white/5">🧾 История</button>
<button data-tab="settings" class="navbtn text-left px-4 py-2.5 rounded-xl hover:bg-white/5">⚙️ Настройки</button>
<div class="mt-auto text-xs text-slate-500 px-2">Юзербот · супергруппы<br><a href="/logout" class="underline">выйти</a></div>
</aside>
<main class="flex-1 p-4 md:p-8 max-w-6xl mx-auto w-full pb-32 md:pb-8">
<nav class="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-[#0f172a]/95 backdrop-blur border-t border-white/10" style="padding-bottom:env(safe-area-inset-bottom)">
<div class="grid grid-cols-6 px-1 pt-1.5">
<button data-mtab="dash" onclick="show('dash')" class="flex flex-col items-center gap-0.5 py-1.5 text-[10px] leading-none">📊<span>Главная</span></button>
<button data-mtab="phones" onclick="show('phones')" class="flex flex-col items-center gap-0.5 py-1.5 text-[10px] leading-none">📦<span>Каталог</span></button>
<button data-mtab="groups" onclick="show('groups')" class="flex flex-col items-center gap-0.5 py-1.5 text-[10px] leading-none">👥<span>Группы</span></button>
<button data-mtab="send" onclick="show('send')" class="flex flex-col items-center gap-0.5 py-1.5 text-[10px] leading-none">🚀<span>Пост</span></button>
<button data-mtab="logs" onclick="show('logs')" class="flex flex-col items-center gap-0.5 py-1.5 text-[10px] leading-none">🧾<span>Лог</span></button>
<button data-mtab="settings" onclick="show('settings')" class="flex flex-col items-center gap-0.5 py-1.5 text-[10px] leading-none">⚙️<span>Настр.</span></button>
</div></nav>

<section id="tab-dash">
<div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
<div class="glass rounded-2xl p-5"><div class="text-sm text-slate-400">Телефонов</div><div id="stPhones" class="text-3xl font-black">–</div></div>
<div class="glass rounded-2xl p-5"><div class="text-sm text-slate-400">Активных групп</div><div id="stGroups" class="text-3xl font-black">–</div></div>
<div class="glass rounded-2xl p-5"><div class="text-sm text-slate-400">Постов за 24ч</div><div id="stToday" class="text-3xl font-black text-emerald-400">–</div></div>
<div class="glass rounded-2xl p-5"><div class="text-sm text-slate-400">Ошибок</div><div id="stErr" class="text-3xl font-black text-rose-400">–</div></div>
</div>
<div class="grid lg:grid-cols-2 gap-4">
<div class="glass rounded-2xl p-5"><div class="flex justify-between items-center mb-3"><h3 class="font-bold">🤖 Юзербот</h3><button onclick="checkTg()" class="px-3 py-1.5 rounded-lg bg-white/10 text-sm">Проверить связь</button></div><div id="tgStatus" class="text-sm text-slate-400">Нажми «Проверить связь». Нужны API_ID / API_HASH / SESSION_STRING.</div></div>
<div class="glass rounded-2xl p-5"><h3 class="font-bold mb-3">⚡ Быстрый старт</h3><ol class="text-sm text-slate-300 space-y-1.5 list-decimal ml-5"><li>Добавь группы-барахолки во вкладке <b>Группы</b></li><li>Добавь телефоны во вкладке <b>Каталог</b></li><li>Жми <b>Рассылка → Опубликовать</b></li><li>Включи <b>Автопостинг</b> в Настройках</li></ol></div>
</div>
<div class="glass rounded-2xl p-5 mt-4"><h3 class="font-bold mb-3">🕘 Последние посты</h3><div id="lastPosts" class="text-sm space-y-2"></div></div>
</section>

<section id="tab-phones" class="hidden">
<div class="glass rounded-2xl p-5 mb-4"><h3 class="font-bold mb-3">➕ Новый телефон</h3>
<div class="grid md:grid-cols-4 gap-2">
<input id="pTitle" placeholder="iPhone 13 128GB" class="px-3 py-2 rounded-xl bg-black/40 border border-white/10">
<input id="pPrice" type="number" placeholder="Цена 45000" class="px-3 py-2 rounded-xl bg-black/40 border border-white/10">
<input id="pMemory" placeholder="256 GB" class="px-3 py-2 rounded-xl bg-black/40 border border-white/10">
<input id="pAkb" placeholder="АКБ 100%" class="px-3 py-2 rounded-xl bg-black/40 border border-white/10">
<select id="pCond" class="px-3 py-2 rounded-xl bg-black/40 border border-white/10"><option>новый</option><option selected>б/у</option><option>идеал</option><option>под ремонт</option></select>
</div>
<textarea id="pDesc" placeholder="Все рабочее✅&#10;Face ID ✅ (каждая фишка с новой строки, торг допиши тут же)" class="w-full mt-2 px-3 py-2 rounded-xl bg-black/40 border border-white/10" rows="3"></textarea>
<div class="flex gap-2 mt-2 flex-wrap">
<input id="pPhoto" placeholder="Фото: https://... или /static/uploads/..." class="flex-1 min-w-[220px] px-3 py-2 rounded-xl bg-black/40 border border-white/10">
<input type="file" id="pFile" accept="image/*" class="text-xs">
<button onclick="addPhone()" class="px-5 py-2 rounded-xl font-bold bg-gradient-to-r from-indigo-500 to-cyan-400">Добавить</button>
</div></div>
<div id="phoneGrid" class="grid md:grid-cols-2 xl:grid-cols-3 gap-4"></div>
</section>

<section id="tab-groups" class="hidden">
<div class="glass rounded-2xl p-5 mb-4"><h3 class="font-bold mb-3">➕ Добавить супергруппу</h3>
<div class="flex gap-2 flex-wrap"><input id="gTitle" placeholder="Название (Барахолка ПМР)" class="flex-1 px-3 py-2 rounded-xl bg-black/40 border border-white/10 min-w-[180px]">
<input id="gUser" placeholder="@baraholka или ссылка t.me/.../топик/..." class="flex-1 px-3 py-2 rounded-xl bg-black/40 border border-white/10 min-w-[180px]">
<input id="gTopic" placeholder="Топик (напр. 6369, пусто = общий чат)" class="px-3 py-2 rounded-xl bg-black/40 border border-white/10 w-56">
<button onclick="addGroup()" class="px-5 py-2 rounded-xl font-bold bg-gradient-to-r from-emerald-500 to-cyan-400">Добавить</button></div>
<p class="text-xs text-slate-500 mt-2">Можно вставить ссылку на сообщение из топика (t.me/группа/6369/...) — группа и топик разберутся сами. Твой аккаунт должен состоять в группе.</p></div>
<div id="groupList" class="grid md:grid-cols-2 gap-3"></div>
</section>

<section id="tab-send" class="hidden">
<div class="glass rounded-2xl p-5"><h3 class="font-bold mb-3">🚀 Рассылка объявления</h3>
<div class="grid lg:grid-cols-2 gap-4">
<div><label class="text-xs text-slate-400">1. Выбери телефон</label><div id="sendPhones" class="space-y-2 max-h-72 overflow-auto mt-1"></div>
<label class="text-xs text-slate-400">2. Задержка между группами (сек)</label><input id="sDelay" type="number" value="15" class="w-full mt-1 px-3 py-2 rounded-xl bg-black/40 border border-white/10"></div>
<div><label class="text-xs text-slate-400">3. Группы (пусто = все активные)</label><div id="sendGroups" class="space-y-1 max-h-44 overflow-auto mt-1 mb-2"></div>
<label class="text-xs text-slate-400">4. Предпросмотр текста</label><pre id="preview" class="whitespace-pre-wrap text-sm bg-black/50 border border-white/10 rounded-xl p-3 min-h-[140px]"></pre>
<div class="flex gap-2 mt-3"><button onclick="doPreview()" class="px-4 py-2 rounded-xl bg-white/10">👁 Предпросмотр</button>
<button onclick="doPost()" class="flex-1 py-2 rounded-xl font-bold bg-gradient-to-r from-indigo-500 via-fuchsia-500 to-cyan-400">📢 Опубликовать</button></div>
<div id="sendMsg" class="text-sm mt-2"></div></div>
</div></div>
</section>

<section id="tab-logs" class="hidden"><div class="glass rounded-2xl p-5"><div class="flex justify-between items-center mb-3"><h3 class="font-bold">🧾 История рассылок</h3><button onclick="loadLogs()" class="px-3 py-1.5 rounded-lg bg-white/10 text-sm">Обновить</button></div><div id="logList" class="space-y-2 text-sm"></div></div></section>

<section id="tab-settings" class="hidden"><div class="glass rounded-2xl p-5 max-w-2xl">
<h3 class="font-bold mb-3">⚙️ Настройки</h3>
<div class="grid grid-cols-2 gap-2">
<input id="sContact" placeholder="Контакт @username" class="px-3 py-2 rounded-xl bg-black/40 border border-white/10">
<input id="sCity" placeholder="Город" class="px-3 py-2 rounded-xl bg-black/40 border border-white/10">
<input id="sDelay2" placeholder="Задержка сек" class="px-3 py-2 rounded-xl bg-black/40 border border-white/10">
<input id="sInterval" placeholder="Автопост каждые N мин" class="px-3 py-2 rounded-xl bg-black/40 border border-white/10">
</div>
<input id="sSign" placeholder="Подпись" class="w-full mt-2 px-3 py-2 rounded-xl bg-black/40 border border-white/10">
<textarea id="sTpl" rows="6" class="w-full mt-2 px-3 py-2 rounded-xl bg-black/40 border border-white/10 text-sm"></textarea>
<p class="text-xs text-slate-500 mt-1">Переменные: {title} {price} {currency} {memory} {akb} {condition} {description} {city} {contact} {signature}</p>
<label class="flex items-center gap-2 mt-3 text-sm"><input type="checkbox" id="sAuto"> 🔁 Автопостинг включён (случайный телефон по всем группам)</label>
<button onclick="saveSettings()" class="mt-3 px-6 py-2 rounded-xl font-bold bg-gradient-to-r from-emerald-500 to-cyan-400">Сохранить</button>
<span id="setMsg" class="text-sm ml-2"></span></div></section>
</main></div>
<script>
let PHONES=[],GROUPS=[],SEL_PHONE=null,SEL_GROUPS=new Set();
const $=id=>document.getElementById(id);
document.querySelectorAll('.navbtn').forEach(b=>b.onclick=()=>show(b.dataset.tab));
function show(t){document.querySelectorAll('.navbtn').forEach(b=>b.classList.toggle('on',b.dataset.tab===t));document.querySelectorAll('[data-mtab]').forEach(b=>{b.style.color=b.dataset.mtab===t?'#67e8f9':'#94a3b8';});['dash','phones','groups','send','logs','settings'].forEach(k=>$('tab-'+k).classList.toggle('hidden',k!==t));if(t==='logs')loadLogs();window.scrollTo(0,0);}
async function j(u,o){const r=await fetch(u,o);if(r.status===401){location='/login';return{}}return r.json();}
async function load(){const s=await j('/api/stats');if(!s.ok)return;$('stPhones').textContent=s.phones;$('stGroups').textContent=s.groups;$('stToday').textContent=s.today;$('stErr').textContent=s.errors;$('lastPosts').innerHTML=(s.posts||[]).map(p=>`<div class="flex justify-between bg-black/30 rounded-lg px-3 py-2"><span>📱 ${p.phone_title} → ${p.group_name}</span><span class="${p.status==='ok'?'text-emerald-400':'text-rose-400'}">${p.status==='ok'?'✓':'✗ '+(p.error||'').slice(0,60)}</span></div>`).join('')||'Пока пусто';
const ph=await j('/api/phones');PHONES=ph.items||[];renderPhones();const g=await j('/api/groups');GROUPS=g.items||[];renderGroups();const st=await j('/api/settings');fillSettings(st.settings||{});}
function renderPhones(){$('phoneGrid').innerHTML=PHONES.map(p=>`<div class="glass rounded-2xl overflow-hidden">${p.photo?`<img src="${p.photo}" class="h-44 w-full object-cover">`:`<div class="h-24 flex items-center justify-center text-4xl bg-black/30">📱</div>`}<div class="p-4"><div class="font-bold">${p.title}</div><div class="text-sm text-slate-400">${p.memory||''}${p.akb?' · Акб '+p.akb:''}</div><div class="text-lg font-black text-emerald-400 mt-1">${p.price} ${p.currency}</div><div class="text-xs text-slate-500 truncate">${p.description||''}</div><div class="flex gap-2 mt-3"><button onclick="previewCard(${p.id})" class="text-xs px-3 py-1.5 rounded-lg bg-white/10">👁 Текст</button><button onclick="toggleStatus(${p.id},'${p.status}')" class="text-xs px-3 py-1.5 rounded-lg bg-white/10">${p.status==='active'?'⏸ Скрыть':'▶ Показать'}</button><button onclick="delPhone(${p.id})" class="text-xs px-3 py-1.5 rounded-lg bg-rose-500/20 text-rose-300">Удалить</button></div></div></div>`).join('')||'<p class="text-slate-500">Добавь первый телефон 👆</p>';
$('sendPhones').innerHTML=PHONES.filter(p=>p.status==='active').map(p=>`<label class="flex items-center gap-2 bg-black/30 rounded-lg px-3 py-2 text-sm cursor-pointer"><input type="radio" name="sp" onchange="selPhone(${p.id})"> <b>${p.title}</b> <span class="text-emerald-400 ml-auto">${p.price}</span></label>`).join('');}
function renderGroups(){$('groupList').innerHTML=GROUPS.map(g=>`<div class="glass rounded-2xl p-4 flex items-center gap-3"><div class="text-2xl">${g.active?'✅':'⏸'}</div><div class="flex-1"><div class="font-bold">${g.title} ${g.topic?`<span class="text-xs font-normal px-2 py-0.5 rounded-full bg-fuchsia-500/20 text-fuchsia-300">топик ${g.topic}</span>`:''}</div><div class="text-xs text-slate-400">${g.username}</div>${g.last_error?`<div class="text-xs text-rose-400">⚠ ${g.last_error.slice(0,80)}</div>`:''}<div class="flex gap-1 mt-1 items-center"><input id="topic-${g.id}" value="${g.topic||''}" placeholder="ID топика" class="w-28 text-xs px-2 py-1 rounded-lg bg-black/40 border border-white/10"><button onclick="setTopic(${g.id})" class="text-xs px-2 py-1 rounded-lg bg-white/10">OK</button></div></div><button onclick="toggleGroup(${g.id})" class="text-xs px-3 py-1.5 rounded-lg bg-white/10">Вкл/Выкл</button><button onclick="delGroup(${g.id})" class="text-xs px-3 py-1.5 rounded-lg bg-rose-500/20 text-rose-300">✕</button></div>`).join('')||'<p class="text-slate-500">Добавь группы-барахолки 👆</p>';
$('sendGroups').innerHTML=GROUPS.filter(g=>g.active).map(g=>`<label class="flex items-center gap-2 text-sm bg-black/30 rounded-lg px-3 py-1.5"><input type="checkbox" checked onchange="selGroup(${g.id},this.checked)"> ${g.title} <span class="text-slate-500">${g.username}${g.topic?' · топик '+g.topic:''}</span></label>`).join('');SEL_GROUPS=new Set(GROUPS.filter(g=>g.active).map(g=>g.id));}
function selPhone(id){SEL_PHONE=id;doPreview();} function selGroup(id,on){on?SEL_GROUPS.add(id):SEL_GROUPS.delete(id);}
async function addPhone(){let photo=$('pPhoto').value.trim();const f=$('pFile').files[0];if(f){const fd=new FormData();fd.append('photo',f);const r=await fetch('/api/upload',{method:'POST',body:fd});const d=await r.json();if(d.ok)photo=d.path;}$('pPhoto').value=photo;
const r=await j('/api/phones',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:$('pTitle').value,price:+$('pPrice').value||0,memory:$('pMemory').value,akb:$('pAkb').value,condition:$('pCond').value,description:$('pDesc').value,photo})});if(r.ok){$('pTitle').value=$('pPrice').value=$('pDesc').value=$('pAkb').value='';load();}}
async function delPhone(id){if(!confirm('Удалить?'))return;await j('/api/phones/'+id,{method:'DELETE'});load();}
async function toggleStatus(id,st){await j('/api/phones/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:st==='active'?'hidden':'active'})});load();}
async function previewCard(id){show('send');SEL_PHONE=id;doPreview();}
async function addGroup(){const r=await j('/api/groups',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:$('gTitle').value,username:$('gUser').value,topic:$('gTopic').value})});if(!r.ok){alert(r.error);return;}$('gTitle').value=$('gUser').value=$('gTopic').value='';load();}
async function setTopic(id){const v=document.getElementById('topic-'+id).value;await j('/api/groups/'+id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({topic:v})});load();}
async function toggleGroup(id){await j('/api/groups/'+id,{method:'PATCH'});load();}
async function delGroup(id){if(!confirm('Удалить группу?'))return;await j('/api/groups/'+id,{method:'DELETE'});load();}
async function doPreview(){if(!SEL_PHONE){$('preview').textContent='Выбери телефон слева';return;}const r=await j('/api/preview/'+SEL_PHONE,{method:'POST'});$('preview').textContent=r.text||'';}
async function doPost(){if(!SEL_PHONE){$('sendMsg').textContent='⚠ Выбери телефон';return;}$('sendMsg').textContent='⏳ Рассылка запущена...';const r=await j('/api/post-now',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone_id:SEL_PHONE,group_ids:[...SEL_GROUPS],delay_sec:+$('sDelay').value||15,text:$('preview').textContent})});$('sendMsg').textContent=r.ok?'✅ '+r.msg:'❌ '+(r.error||'ошибка');}
async function loadLogs(){const r=await j('/api/logs');$('logList').innerHTML=(r.items||[]).map(p=>`<div class="flex justify-between gap-2 bg-black/30 rounded-lg px-3 py-2"><span>${new Date(p.created_at*1000).toLocaleString('ru')} · <b>${p.phone_title}</b> → ${p.group_name}</span><span class="${p.status==='ok'?'text-emerald-400':'text-rose-400'}">${p.status==='ok'?'✓ OK':'✗ '+(p.error||'').slice(0,100)}</span></div>`).join('')||'Пусто';}
function fillSettings(s){$('sContact').value=s.contact||'';$('sCity').value=s.city||'';$('sDelay2').value=s.delay_sec||15;$('sInterval').value=s.autopost_interval_min||60;$('sSign').value=s.signature||'';$('sTpl').value=s.template||'';$('sAuto').checked=s.autopost_on==='1';}
async function saveSettings(){const r=await j('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({contact:$('sContact').value,city:$('sCity').value,delay_sec:$('sDelay2').value,autopost_interval_min:$('sInterval').value,signature:$('sSign').value,template:$('sTpl').value,autopost_on:$('sAuto').checked?'1':'0'})});$('setMsg').textContent=r.ok?'✅ Сохранено':'❌ Ошибка';}
async function checkTg(){$('tgStatus').textContent='⏳ Проверяю...';const r=await j('/api/check-tg',{method:'POST'});$('tgStatus').innerHTML=r.ok?`✅ Подключено как <b>${r.name}</b>`:`❌ ${r.error||'ошибка'} <br><span class="text-xs">Получи API_ID/HASH на my.telegram.org, SESSION_STRING через gen_session.py</span>`;}
load();show('dash');
</script></body></html>"""

if __name__ == "__main__":
    db.init_db()
    print("📱 PhoneMarket: http://127.0.0.1:5000  (пароль: admin123 если не задан ADMIN_PASSWORD)")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
