"""Webhook-версия для хостинга Render + миниапп админа."""
import hashlib
import hmac
import json
import os
import sys
import time
import requests
from datetime import date, timedelta
from urllib.parse import parse_qsl
from flask import Flask, request, jsonify, Response

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import schedule_logic as SL
from schedule_logic import process_message, process_callback

app = Flask(__name__)
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
API = "https://api.telegram.org/bot{token}/{method}"
_last_bot_msg: dict[int, int] = {}


def api_call(method: str, payload: dict):
    try:
        return requests.post(
            API.format(token=BOT_TOKEN, method=method), json=payload, timeout=15
        ).json()
    except Exception:
        return {}


def show_new(chat_id: int, text: str, kb):
    """Команда текстом: удалить прошлое сообщение бота и отправить новое снизу."""
    prev = _last_bot_msg.pop(chat_id, None)
    if prev:
        api_call("deleteMessage", {"chat_id": chat_id, "message_id": prev})
    show_edit(chat_id, text, kb, edit_id=None)


def show_edit(chat_id: int, text: str, kb, edit_id: int | None = None):
    """Нажатие кнопки: отредактировать сообщение на месте."""
    markup = {"inline_keyboard": kb} if kb else None
    mid = edit_id or _last_bot_msg.get(chat_id)
    if mid:
        r = api_call("editMessageText", {
            "chat_id": chat_id, "message_id": mid,
            "text": text, "parse_mode": "HTML", "reply_markup": markup,
        })
        if r.get("ok"):
            _last_bot_msg[chat_id] = mid
            return
    r = api_call("sendMessage", {
        "chat_id": chat_id, "text": text,
        "parse_mode": "HTML", "reply_markup": markup,
    })
    new_id = (r.get("result") or {}).get("message_id")
    if new_id:
        _last_bot_msg[chat_id] = new_id


def clear_old_keyboard(chat_id: int):
    try:
        r = api_call("sendMessage", {
            "chat_id": chat_id, "text": "⌨️",
            "reply_markup": {"remove_keyboard": True},
        })
        mid = (r.get("result") or {}).get("message_id")
        if mid:
            api_call("deleteMessage", {"chat_id": chat_id, "message_id": mid})
    except Exception:
        pass


@app.get("/")
def index():
    return "Bot is alive. POST /webhook for Telegram updates."


@app.post("/webhook")
def webhook():
    upd = request.get_json(force=True, silent=True) or {}
    if not BOT_TOKEN:
        return jsonify(ok=True)
    # --- нажатие inline-кнопки ---
    cb = upd.get("callback_query")
    if cb:
        msg = cb.get("message", {}) or {}
        chat = msg.get("chat", {}) or {}
        chat_id = chat.get("id")
        mid = msg.get("message_id")
        user = cb.get("from", {}) or {}
        api_call("answerCallbackQuery", {"callback_query_id": cb.get("id")})
        if chat_id:
            answer, kb = process_callback(user.get("id", 0), cb.get("data", ""))
            show_edit(chat_id, answer, kb, edit_id=mid)
        return jsonify(ok=True)
    # --- обычное сообщение ---
    msg = upd.get("message", {})
    text = msg.get("text", "")
    chat = msg.get("chat", {}) or {}
    chat_id = chat.get("id")
    chat_type = chat.get("type", "private")
    user = msg.get("from", {}) or {}
    if chat_id and text:
        answer, kb = process_message(user.get("id", 0), text, chat_type=chat_type)
        if answer is not None:
            low = text.strip().lower().lstrip("./").split("@")[0]
            if low in ("start", "старт", "привет"):
                clear_old_keyboard(chat_id)
            show_new(chat_id, answer, kb)
    return jsonify(ok=True)


# ---------------- Миниапп админа ----------------
def check_init_data(init_data: str):
    """Проверяет подпись Telegram WebApp. Возвращает user_id админа или None."""
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        recv_hash = pairs.pop("hash", "")
        if not recv_hash or not BOT_TOKEN:
            return None
        check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, recv_hash):
            return None
        if abs(time.time() - int(pairs.get("auth_date", "0"))) > 86400:
            return None
        uid = (json.loads(pairs.get("user", "{}")) or {}).get("id", 0)
        return uid if SL.is_admin(uid) else None
    except Exception:
        return None


def mini_state():
    today = SL.get_local_now().date()
    monday = today - timedelta(days=today.weekday())
    days = []
    for i in range(7):
        d = monday + timedelta(days=i)
        lessons, ov = SL.get_lessons_for_date(d)
        days.append({"date": d.isoformat(), "wd": SL.WEEKDAYS[d.weekday()],
                     "override": bool(ov),
                     "lessons": [{"n": l[0], "name": l[1], "teacher": l[2], "room": l[3]} for l in lessons]})
    return {"today": today.isoformat(), "week_type": SL.get_week_type(today),
            "days": days, "overrides": SL.list_overrides_text(),
            "homework": SL._data.get("homework", []), "retakes": SL.get_retakes()}


@app.get("/mini")
def mini_page():
    return Response(MINI_HTML, mimetype="text/html")


@app.post("/mini/api")
def mini_api():
    d = request.get_json(force=True, silent=True) or {}
    uid = check_init_data(d.get("initData", ""))
    if not uid:
        return jsonify({"ok": False, "error": "Нет доступа. Открой через кнопку в боте."}), 403
    action = d.get("action", "")
    try:
        if action == "state":
            return jsonify({"ok": True, "state": mini_state()})
        if action == "hw_add":
            hid = SL.hw_add(d.get("subject", ""), d.get("text", ""))
            return jsonify({"ok": True, "id": hid, "state": mini_state()})
        if action == "hw_del":
            return jsonify({"ok": SL.hw_delete(int(d.get("id", 0))), "state": mini_state()})
        if action == "pair_cancel":
            day = date.fromisoformat(d.get("date", ""))
            return jsonify({"ok": SL.remove_pair_for_date(day, int(d.get("pair", 0))), "state": mini_state()})
        if action == "pair_replace":
            day = date.fromisoformat(d.get("date", ""))
            SL.replace_pair_for_date(day, int(d.get("pair", 0)), d.get("name", ""),
                                     d.get("teacher", ""), d.get("room", ""))
            return jsonify({"ok": True, "state": mini_state()})
        if action == "day_off":
            SL.set_day_override(date.fromisoformat(d.get("date", "")), [])
            return jsonify({"ok": True, "state": mini_state()})
        if action == "day_reset":
            SL.clear_day_override(date.fromisoformat(d.get("date", "")))
            return jsonify({"ok": True, "state": mini_state()})
        if action == "retake_add":
            dates = [x.strip() for x in str(d.get("dates", "")).replace(",", " ").split() if x.strip()]
            rid = SL.retake_add(d.get("group", ""), d.get("subject", ""), d.get("teacher", ""),
                                dates, d.get("time", ""), d.get("room", ""))
            return jsonify({"ok": True, "id": rid, "state": mini_state()})
        if action == "retake_del":
            return jsonify({"ok": SL.retake_delete(int(d.get("id", 0))), "state": mini_state()})
        return jsonify({"ok": False, "error": "Неизвестное действие"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:200]}), 400


MINI_HTML = """<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Админка ФТ24АР52ЭО</title><script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>*{box-sizing:border-box}body{margin:0;font-family:system-ui;background:#0b1020;color:#f1f5f9;padding:12px;padding-bottom:40px}
h2{margin:4px 0 10px;font-size:18px}.card{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);border-radius:14px;padding:12px;margin-bottom:10px}
.row{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}input,select,textarea{font-size:16px;width:100%;padding:9px 10px;margin:4px 0;border-radius:10px;border:1px solid rgba(255,255,255,.15);background:#00000066;color:#fff}
button{font-size:15px;padding:10px 14px;border-radius:10px;border:0;font-weight:700;cursor:pointer}
.b{background:linear-gradient(90deg,#6366f1,#22d3ee);color:#fff}.g{background:#ffffff18;color:#fff}.r{background:#f43f5e33;color:#fda4af}.gr{color:#94a3b8;font-size:13px}
.tabs{display:flex;gap:6px;margin-bottom:12px}.tabs button{flex:1;background:#ffffff10;color:#fff}.tabs button.on{background:linear-gradient(90deg,#6366f1,#22d3ee)}
.mut{color:#94a3b8;font-size:13px}.ok{color:#34d399}.err{color:#f87171}.pair{border-left:3px solid #6366f1;padding:6px 8px;margin:6px 0;background:#00000040;border-radius:0 10px 10px 0}</style></head>
<body>
<h2>⚙️ Админка расписания</h2>
<div class="tabs"><button id="t-days" class="on" onclick="tab('days')">📅 Пары</button><button id="t-hw" onclick="tab('hw')">📝 ДЗ</button><button id="t-rt" onclick="tab('rt')">📝 Пересдачи</button></div>
<div id="msg" class="mut"></div>
<div id="v-days"></div><div id="v-hw" style="display:none"></div><div id="v-rt" style="display:none"></div>
<script>
const tg = window.Telegram ? window.Telegram.WebApp : null;
if (tg) { tg.expand(); }
const $ = id => document.getElementById(id);
let S = null;
function say(t, ok){ $('msg').innerHTML = '<span class="'+(ok===false?'err':'ok')+'">'+t+'</span>'; }
async function api(action, p){
  p = p || {};
  p.initData = tg ? tg.initData : '';
  p.action = action;
  const r = await fetch('/mini/api', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(p)});
  const d = await r.json();
  if (!d.ok) { say('❌ '+(d.error||'ошибка'), false); return null; }
  if (d.state) { S = d.state; render(); }
  return d;
}
function tab(t){
  ['days','hw','rt'].forEach(k => { $('v-'+k).style.display = k===t ? 'block' : 'none'; $('t-'+k).className = k===t ? 'on' : ''; });
}
function esc(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;'); }
function render(){
  if (!S) return;
  $('v-days').innerHTML = '<div class="mut">Неделя: '+esc(S.week_type)+'</div>' + S.days.map(d =>
    '<div class="card"><b>'+esc(d.wd)+' ('+d.date.slice(8)+'.'+d.date.slice(5,7)+')</b>' + (d.override?' ✏️':'') +
    (d.lessons.length ? d.lessons.map(l => '<div class="pair"><b>'+l.n+' пара</b> — '+esc(l.name)+'<br><span class="mut">'+esc(l.teacher)+' · '+esc(l.room)+'</span><div class="row"><button class="r" onclick="pairCancel(\\''+d.date+'\\','+l.n+')">Отмена</button></div></div>').join('')
    : '<div class="mut">Пар нет</div>') +
    '<div class="row"><input id="rp-'+d.date+'" placeholder="№ пары для замены" style="max-width:110px"><input id="rn-'+d.date+'" placeholder="Дисциплина"><input id="rt-'+d.date+'" placeholder="Преподаватель"><input id="rm-'+d.date+'" placeholder="Аудитория"><button class="b" onclick="pairReplace(\\''+d.date+'\\')">Заменить</button><button class="g" onclick="dayOff(\\''+d.date+'\\')">Выходной</button><button class="g" onclick="dayReset(\\''+d.date+'\\')">Сброс</button></div></div>'
  ).join('');
  $('v-hw').innerHTML = '<div class="card"><b>➕ Новая домашка</b><input id="hs" placeholder="Предмет"><input id="ht" placeholder="Текст"><div class="row"><button class="b" onclick="hwAdd()">Добавить</button></div></div>' +
    (S.homework.length ? S.homework.map(h => '<div class="card"><b>#'+h.id+' '+esc(h.subject)+'</b><br>'+esc(h.text)+'<div class="row"><button class="r" onclick="hwDel('+h.id+')">Удалить</button></div></div>').join('') : '<div class="mut">Пусто</div>');
  $('v-rt').innerHTML = '<div class="card"><b>➕ Пересдача</b><input id="rg" placeholder="Группа"><input id="rs" placeholder="Дисциплина"><input id="rh" placeholder="Преподаватель"><input id="rd" placeholder="Даты через пробел ДД.ММ.ГГ"><div class="row"><input id="rm2" placeholder="Время" style="max-width:110px"><input id="rr" placeholder="Аудитория"></div><div class="row"><button class="b" onclick="rtAdd()">Добавить</button></div></div>' +
    S.retakes.map(r => '<div class="card"><b>#'+r.id+' '+esc(r.subject)+'</b> ('+esc(r.group)+')<br><span class="mut">'+esc(r.teacher)+' · '+esc((r.dates||[]).join(', '))+' · '+esc(r.time)+' · '+esc(r.room)+'</span><div class="row"><button class="r" onclick="rtDel('+r.id+')">Удалить</button></div></div>').join('');
}
async function pairCancel(date, n){ if(!confirm('Отменить '+n+' пару '+date+'?'))return; await api('pair_cancel',{date:date,pair:n}); }
async function pairReplace(date){ const n=+$('rp-'+date).value; if(!n){say('Укажи № пары',false);return;} await api('pair_replace',{date:date,pair:n,name:$('rn-'+date).value,teacher:$('rt-'+date).value,room:$('rm-'+date).value}); say('✅ Готово',true); }
async function dayOff(date){ if(!confirm('Выходной '+date+'?'))return; await api('day_off',{date:date}); }
async function dayReset(date){ await api('day_reset',{date:date}); }
async function hwAdd(){ if(!$('hs').value){say('Нужен предмет',false);return;} await api('hw_add',{subject:$('hs').value,text:$('ht').value}); }
async function hwDel(id){ if(!confirm('Удалить #'+id+'?'))return; await api('hw_del',{id:id}); }
async function rtAdd(){ await api('retake_add',{group:$('rg').value,subject:$('rs').value,teacher:$('rh').value,dates:$('rd').value,time:$('rm2').value,room:$('rr').value}); }
async function rtDel(id){ if(!confirm('Удалить #'+id+'?'))return; await api('retake_del',{id:id}); }
(async function(){ say('Загрузка…'); const d = await api('state',{}); if(d) say(''); })();
</script></body></html>"""
