"""Логика бота ФТ24АР52ЭО: расписание + Д/З + админка. Формат HTML для Telegram."""
import json
import os
from datetime import date, timedelta, datetime

try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Europe/Chisinau")
except Exception:
    LOCAL_TZ = None

ADMIN_IDS = [5634691608]

# Неделя Пн 31.08 – Вс 06.09 = числитель
SEMESTER_START = date(2026, 8, 31)
START_WEEK_IS_NUMERATOR = True

WEEKDAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

PAIR_TIMES = {
    1: ("8:00", "9:20"),
    2: ("9:40", "11:00"),
    3: ("11:25", "12:45"),
    4: ("13:05", "14:25"),
}

MON = [
    (2, "МДК.04.01 Монтаж, наладка, обслуживание и ремонт (лк)", "Баранова С.К.", "Э* 228а"),
    (3, "Электрические машины и электропривод (лк)", "Боровик Т.И.", "Э* 228а"),
    (4, "МДК.02.01 Планирование работ по эксплуатации (лк)", "Костантиновская А.В.", "Э* 228а"),
]
TUE_BASE = [
    (1, "МДК.02.01 Планирование работ по эксплуатации (лк)", "Костантиновская А.В.", "312А К.8"),
    (2, "Физическая культура (пр)", "Выходец Н.С.", "Сп.зал ФТИ"),
]
TUE_NUM = [(3, "Электротехника и электроника (лб)", "Баранова С.К.", "312А К.8")]
TUE_DEN = [(3, "МДК.02.02 Разработка документации (лк)", "Костантиновская А.В.", "312А К.8")]
WED = [
    (1, "МДК.02.01 Планирование работ (пр)", "Костантиновская А.В.", "Э* 228а"),
    (2, "МДК.02.02 Разработка документации (пр)", "Костантиновская А.В.", "Э* 228а"),
    (3, "Электрические машины и электропривод (лк)", "Боровик Т.И.", "Э* 229"),
]
THU = [
    (2, "Электрические машины и электропривод (лб)", "Боровик Т.И.", "Э* 2"),
    (3, "МДК.04.01 Монтаж, наладка и ремонт (пр)", "Баранова С.К.", "Э* 2"),
    (4, "Английский в проф. деятельности (пр)", "Жосан Д.К.", "Э* 2"),
]
FRI_BASE = [
    (2, "Электротехника и электроника (пр)", "Баранова С.К.", "Э* 3"),
    (3, "Электротехника и электроника (пр)", "Баранова С.К.", "Э* 3"),
]
FRI_NUM_1 = (1, "Электрические машины и электропривод (лб)", "Боровик Т.И.", "Э* 3")
FRI_DEN_1 = (1, "МДК.02.02 Разработка документации (лк)", "Костантиновская А.В.", "Э* 3")
SAT_BASE = [
    (2, "МДК.02.02 Разработка документации", "Костантиновская А.В.", "Э* 221"),
    (3, "МДК.02.01 Планирование работ (пр)", "Костантиновская А.В.", "Э* 221"),
]
SAT_NUM_4 = (4, "Электрические машины и электропривод (лб)", "Боровик Т.И.", "Э* 221")
SAT_DEN_4 = (4, "МДК.04.01 Монтаж, наладка и ремонт (лб)", "Баранова С.К.", "Э* 221")

SCHEDULE = {
    "числитель": {
        0: MON, 1: TUE_BASE + TUE_NUM, 2: WED, 3: THU,
        4: [FRI_NUM_1] + FRI_BASE, 5: SAT_BASE + [SAT_NUM_4], 6: [],
    },
    "знаменатель": {
        0: MON, 1: TUE_BASE + TUE_DEN, 2: WED, 3: THU,
        4: [FRI_DEN_1] + FRI_BASE, 5: SAT_BASE + [SAT_DEN_4], 6: [],
    },
}

# Разовая правка: в субботу 05.09.2026 только 2 и 3 пары (4-й нет).
# В следующую субботу все как обычно.
DEFAULT_OVERRIDES = {
    "2026-09-05": [list(l) for l in SAT_BASE],
}

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_data.json")
_data = {"overrides": {}, "homework": [], "hw_next_id": 1}
_states: dict[int, dict] = {}


def _load():
    global _data
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            _data["overrides"] = loaded.get("overrides", {})
            _data["homework"] = loaded.get("homework", [])
            _data["hw_next_id"] = loaded.get("hw_next_id", 1)
    except Exception:
        pass


def _save():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(_data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


_load()


def is_admin(user_id: int) -> bool:
    try:
        return int(user_id) in ADMIN_IDS
    except Exception:
        return False


def get_week_type(day: date) -> str:
    delta = (day - SEMESTER_START).days
    if delta < 0:
        return "знаменатель" if day.isocalendar().week % 2 == 0 else "числитель"
    week_num = delta // 7
    is_num = (week_num % 2 == 0) == START_WEEK_IS_NUMERATOR
    return "числитель" if is_num else "знаменатель"


def fmt_room(room: str) -> str:
    return (room or "").replace("Э* ", "Э-").replace("Э*", "Э-")


def pair_time(num: int) -> str:
    t = PAIR_TIMES.get(num)
    return f"{t[0]}-{t[1]}" if t else ""


def fmt_lesson(lesson) -> str:
    num, name, teacher, room = lesson
    return (
        f"<b>{num} пара {pair_time(num)}</b>\n"
        f"📚 {name}\n"
        f"👉🏻 {teacher}\n"
        f"❗️аудитория {fmt_room(room)}❗️"
    )


def fmt_lesson_short(lesson) -> str:
    num, name, teacher, room = lesson
    return f"{num} пара ({pair_time(num)}) — {name} | {fmt_room(room)}"


def _norm_lessons(raw) -> list:
    out = []
    for l in raw or []:
        out.append([l[0], l[1], l[2], l[3]])
    return out


def get_lessons_for_date(day: date) -> tuple[list, bool]:
    """Возвращает (пары, is_override)."""
    key = day.isoformat()
    if key in _data["overrides"]:
        return [tuple(l) for l in _data["overrides"][key]], True
    if key in DEFAULT_OVERRIDES:
        return [tuple(l) for l in DEFAULT_OVERRIDES[key]], True
    wt = get_week_type(day)
    return list(SCHEDULE[wt].get(day.weekday(), [])), False


def get_schedule_text(day: date) -> str:
    wt = get_week_type(day)
    lessons, ov = get_lessons_for_date(day)
    badge = "🔴 <b>ЧИСЛИТЕЛЬ</b>" if wt == "числитель" else "🔵 <b>ЗНАМЕНАТЕЛЬ</b>"
    mark = " ✏️" if ov else ""
    header = f"📅 <b>{WEEKDAYS[day.weekday()]}, {day.strftime('%d.%m')}</b>\n{badge}{mark}\n➖➖➖➖➖➖➖"
    if not lessons:
        return header + "\n😴 Пар нет — отдыхай!"
    body = "\n\n".join(fmt_lesson(l) for l in lessons)
    return header + "\n\n" + body


def get_week_schedule_text(today: date) -> str:
    wt = get_week_type(today)
    badge = "🔴 <b>ЧИСЛИТЕЛЬ</b>" if wt == "числитель" else "🔵 <b>ЗНАМЕНАТЕЛЬ</b>"
    monday = today - timedelta(days=today.weekday())
    parts = [f"🗓 <b>Расписание на неделю</b>\n{badge}\n➖➖➖➖➖➖➖"]
    for wd in range(6):
        d = monday + timedelta(days=wd)
        lessons, ov = get_lessons_for_date(d)
        mark = " ✏️" if ov else ""
        parts.append(f"\n<b>{WEEKDAYS[wd]} ({d.strftime('%d.%m')})</b>{mark}")
        if not lessons:
            parts.append("😴 —")
        else:
            for l in lessons:
                parts.append(f"• {fmt_lesson_short(l)}")
    return "\n".join(parts)


def _to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def get_local_now() -> datetime:
    return datetime.now(tz=LOCAL_TZ) if LOCAL_TZ else datetime.now()


def get_now_status(today: date | None = None, now: datetime | None = None) -> str:
    today = today or (now.date() if now else get_local_now().date())
    now = now or get_local_now()
    cur = now.hour * 60 + now.minute
    wt = get_week_type(today)
    lessons = sorted(get_lessons_for_date(today)[0], key=lambda l: l[0])
    badge = "🔴 <b>ЧИСЛИТЕЛЬ</b>" if wt == "числитель" else "🔵 <b>ЗНАМЕНАТЕЛЬ</b>"
    header = f"⏰ <b>Сейчас {now.strftime('%H:%M')}, {WEEKDAYS[today.weekday()]} {today.strftime('%d.%m')}</b>\n{badge}\n➖➖➖➖➖➖➖"
    if not lessons:
        return header + "\n😴 Сегодня пар нет."
    spans = []
    for num, name, teacher, room in lessons:
        s, e = PAIR_TIMES.get(num, ("0:00", "0:00"))
        spans.append((_to_minutes(s), _to_minutes(e), num, name, teacher, room))
    for s, e, num, name, teacher, room in spans:
        if s <= cur < e:
            return (header + f"\n🟢 <b>Сейчас идет {num} пара ({PAIR_TIMES[num][0]}-{PAIR_TIMES[num][1]})</b>\n"
                    + fmt_lesson((num, name, teacher, room)))
    if cur < spans[0][0]:
        num, name, teacher, room = spans[0][2], spans[0][3], spans[0][4], spans[0][5]
        return (header + f"\n⏳ <b>Пары еще не начались. Первая — {num} пара в {PAIR_TIMES[num][0]}</b>\n\n"
                + fmt_lesson((num, name, teacher, room)))
    for i, (s, e, num, name, teacher, room) in enumerate(spans):
        if cur >= e and i + 1 < len(spans) and cur < spans[i + 1][0]:
            nn, nn_name, nn_t, nn_r = spans[i + 1][2], spans[i + 1][3], spans[i + 1][4], spans[i + 1][5]
            return (header + f"\n☕ <b>Перемена. Следующая — {nn} пара в {PAIR_TIMES[nn][0]}</b>\n\n"
                    + fmt_lesson((nn, nn_name, nn_t, nn_r)))
    return header + "\n🏁 <b>Пары на сегодня закончились.</b>"


# ---------- Д/З ----------
def hw_list_text() -> str:
    hw = _data["homework"]
    if not hw:
        return "📝 <b>Домашние задания</b>\n➖➖➖➖➖➖➖\nПока пусто. Отдыхай 😎"
    parts = ["📝 <b>Домашние задания</b>\n➖➖➖➖➖➖➖"]
    for h in hw:
        parts.append(f"\n<b>#{h['id']} {h['subject']}</b>\n{h['text']}")
    return "\n".join(parts)


def hw_add(subject: str, text: str) -> int:
    used = {h["id"] for h in _data["homework"]}
    hid = 1
    while hid in used:
        hid += 1
    _data["homework"].append({"id": hid, "subject": subject, "text": text})
    _data["homework"].sort(key=lambda h: h["id"])
    _data["hw_next_id"] = max(used | {hid}) + 1 if used or hid else 2
    _save()
    return hid


def hw_delete(hid: int) -> bool:
    for i, h in enumerate(_data["homework"]):
        if h["id"] == hid:
            _data["homework"].pop(i)
            _save()
            return True
    return False


# ---------- Правки расписания ----------
def set_day_override(day: date, lessons: list) -> None:
    _data["overrides"][day.isoformat()] = _norm_lessons(lessons)
    _save()


def clear_day_override(day: date) -> bool:
    if day.isoformat() in _data["overrides"]:
        del _data["overrides"][day.isoformat()]
        _save()
        return True
    return False


def remove_pair_for_date(day: date, pair_num: int) -> bool:
    lessons, _ = get_lessons_for_date(day)
    new = [l for l in lessons if l[0] != pair_num]
    if len(new) == len(lessons):
        return False
    set_day_override(day, new)
    return True


def replace_pair_for_date(day: date, pair_num: int, name: str, teacher: str, room: str) -> None:
    lessons, _ = get_lessons_for_date(day)
    new = [l for l in lessons if l[0] != pair_num]
    new.append((pair_num, name, teacher, room))
    new.sort(key=lambda l: l[0])
    set_day_override(day, new)


def list_overrides_text() -> str:
    keys = sorted(set(list(_data["overrides"].keys()) + list(DEFAULT_OVERRIDES.keys())))
    if not keys:
        return "✏️ Правок нет — расписание обычное."
    parts = ["✏️ <b>Правки расписания:</b>"]
    for k in keys:
        d = date.fromisoformat(k)
        lessons, _ = get_lessons_for_date(d)
        src = "админ" if k in _data["overrides"] else "авто"
        if not lessons:
            parts.append(f"\n• {d.strftime('%d.%m')} ({WEEKDAYS[d.weekday()]}) — выходной [{src}]")
        else:
            pairs = ", ".join(str(l[0]) for l in lessons)
            parts.append(f"\n• {d.strftime('%d.%m')} ({WEEKDAYS[d.weekday()]}) — пары: {pairs} [{src}]")
    return "\n".join(parts)


def parse_day(text: str, today: date) -> date | None:
    t = (text or "").strip().lower()
    if n in ("сегодня", "today"):
        return today
    if n in ("завтра", "tomorrow"):
        return today + timedelta(days=1)
    # ДД.ММ или ДД.ММ.ГГГГ
    import re
    m = re.match(r"(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?", t)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
        year = today.year if not y else (2000 + int(y) if len(y) == 2 else int(y))
        try:
            return date(year, mo, d)
        except ValueError:
            return None
    return None


BASE_KEYBOARD = [["Сегодня", "Завтра"], ["Неделя", "Сейчас"], ["Расписание", "📝 Д/З"]]

# Inline-кнопки: (текст, callback_data)
MAIN_INLINE = [
    [("📅 Сегодня", "cmd:today"), ("📅 Завтра", "cmd:tomorrow")],
    [("🔢 Неделя", "cmd:week"), ("⏰ Сейчас", "cmd:now")],
    [("🗓 Расписание", "cmd:schedule"), ("📝 Д/З", "cmd:hw")],
]
ADMIN_INLINE = [
    [("➕ ДЗ", "adm:hw_add"), ("🗑 ДЗ", "adm:hw_del")],
    [("❌ Отмена пары", "adm:cancel"), ("✏️ Замена", "adm:replace")],
    [("📅 Выходной", "adm:off"), ("↩️ Сброс", "adm:reset")],
    [("📋 Правки", "adm:list"), ("🚪 Выйти", "adm:exit")],
]


def inline_main(user_id: int):
    kb = [[{"text": t, "callback_data": d} for t, d in row] for row in MAIN_INLINE]
    if is_admin(user_id):
        kb.append([{"text": "⚙️ Админка", "callback_data": "adm:menu"}])
    return kb


def inline_admin():
    return [[{"text": t, "callback_data": d} for t, d in row] for row in ADMIN_INLINE]


def get_keyboard(user_id: int, admin_mode: bool = False):
    if admin_mode and is_admin(user_id):
        return inline_admin()
    return inline_main(user_id)


def normalize_cmd(text: str) -> str:
    """Срезает префиксы '.'/'/' и '@имябота', приводит к нижнему регистру."""
    t = (text or "").strip().lower()
    t = t.lstrip("./")
    if "@" in t:
        t = t.split("@", 1)[0]
    return t.strip()


ADMIN_MENU_TEXT = (
    "⚙️ <b>Админка</b>\n"
    "➖➖➖➖➖➖➖\n"
    "➕ ДЗ — добавить домашку\n"
    "🗑 ДЗ — удалить домашку\n"
    "❌ Отмена пары — убрать пару в конкретный день\n"
    "✏️ Замена — заменить/создать пару в конкретный день\n"
    "📅 Выходной — отменить все пары в день\n"
    "↩️ Сброс — вернуть день к обычному расписанию\n"
    "📋 Правки — показать все правки\n"
    "🚪 Выйти — выйти из админки"
)


def process_message(user_id: int, text: str, today: date | None = None,
                    now: datetime | None = None, chat_type: str = "private") -> tuple:
    today = today or (now.date() if now else get_local_now().date())
    raw = (text or "").strip()
    t = raw.lower()
    n = normalize_cmd(raw)
    is_cmd = raw.startswith(("/", "."))
    is_group = chat_type in ("group", "supergroup")
    admin = is_admin(user_id)
    st = _states.get(user_id, {})

    def to_menu(msg: str):
        _states[user_id] = {"mode": "admin_menu"}
        return msg + "\n\n" + ADMIN_MENU_TEXT, inline_admin()

    # --- admin FSM ---
    if admin and st.get("mode"):
        mode = st["mode"]
        if n in ("отмена", "🚪 выйти", "выйти", "cancel"):
            _states.pop(user_id, None)
            return "🚪 Вышел из админки.", get_keyboard(user_id)
        if mode == "admin_menu":
            if n in ("➕ дз", "добавить дз", "➕", "д3"):
                _states[user_id] = {"mode": "hw_subject"}
                return "📝 Напиши <b>предмет</b> (например: Монтаж):", inline_admin()
            if n in ("🗑 дз", "удалить дз", "удалить"):
                if not _data["homework"]:
                    return to_menu("Домашки нет — удалять нечего.")
                _states[user_id] = {"mode": "hw_delete"}
                return hw_list_text() + "\n\nНапиши <b>номер</b> для удаления (например: 3):", inline_admin()
            if n in ("❌ отмена пары", "отмена пары"):
                _states[user_id] = {"mode": "ov_date_cancel"}
                return "Напиши <b>дату</b>: Сегодня / Завтра / ДД.ММ:", inline_admin()
            if n in ("✏️ замена", "замена", "замена пары"):
                _states[user_id] = {"mode": "ov_date_replace"}
                return "Напиши <b>дату</b>: Сегодня / Завтра / ДД.ММ:", inline_admin()
            if n in ("📅 выходной", "выходной", "день выходной"):
                _states[user_id] = {"mode": "ov_date_off"}
                return "Напиши <b>дату</b> выходного: Сегодня / Завтра / ДД.ММ:", inline_admin()
            if n in ("↩️ сброс", "сброс", "сброс дня"):
                _states[user_id] = {"mode": "ov_date_reset"}
                return "Напиши <b>дату</b> для сброса: Сегодня / Завтра / ДД.ММ:", inline_admin()
            if n in ("📋 правки", "правки", "показать правки"):
                return to_menu(list_overrides_text())
            return ADMIN_MENU_TEXT, inline_admin()
        if mode == "hw_subject":
            if not raw:
                return "Пусто. Напиши предмет:", inline_admin()
            _states[user_id] = {"mode": "hw_text", "subject": raw}
            return f"Предмет: <b>{raw}</b>\nТеперь напиши <b>текст домашки</b>:", inline_admin()
        if mode == "hw_text":
            hid = hw_add(st.get("subject", "Без предмета"), raw)
            return to_menu(f"✅ Домашка <b>#{hid}</b> добавлена.")
        if mode == "hw_delete":
            import re
            m = re.search(r"\d+", t)
            if not m:
                return "Нужен номер. Например: 3", inline_admin()
            ok = hw_delete(int(m.group()))
            return to_menu("✅ Удалено." if ok else "❌ Нет домашки с таким номером.")
        if mode == "ov_date_cancel":
            d = parse_day(raw, today)
            if not d:
                return "Не понял дату. Напиши: Сегодня / Завтра / ДД.ММ", inline_admin()
            lessons, _ = get_lessons_for_date(d)
            if not lessons:
                return to_menu(f"{d.strftime('%d.%m')} — пар и так нет.")
            _states[user_id] = {"mode": "ov_pair_cancel", "day": d.isoformat()}
            pairs = "\n".join(f"• {fmt_lesson_short(l)}" for l in lessons)
            return f"📅 {d.strftime('%d.%m')}:\n{pairs}\n\nНапиши <b>номер пары</b> для отмены:", inline_admin()
        if mode == "ov_pair_cancel":
            import re
            m = re.search(r"\d+", t)
            if not m:
                return "Нужен номер пары. Например: 4", inline_admin()
            d = date.fromisoformat(st["day"])
            ok = remove_pair_for_date(d, int(m.group()))
            return to_menu(f"✅ Пара отменена на {d.strftime('%d.%m')}." if ok else "❌ Такой пары в этот день нет.")
        if mode == "ov_date_off":
            d = parse_day(raw, today)
            if not d:
                return "Не понял дату. Напиши: Сегодня / Завтра / ДД.ММ", inline_admin()
            set_day_override(d, [])
            return to_menu(f"✅ {d.strftime('%d.%m')} — выходной.")
        if mode == "ov_date_reset":
            d = parse_day(raw, today)
            if not d:
                return "Не понял дату. Напиши: Сегодня / Завтра / ДД.ММ", inline_admin()
            clear_day_override(d)
            if d.isoformat() in DEFAULT_OVERRIDES:
                return to_menu(f"↩️ {d.strftime('%d.%m')} — сброс к авто-правке (см. 📋 Правки).")
            return to_menu(f"↩️ {d.strftime('%d.%m')} — обычное расписание.")
        if mode == "ov_date_replace":
            d = parse_day(raw, today)
            if not d:
                return "Не понял дату. Напиши: Сегодня / Завтра / ДД.ММ", inline_admin()
            lessons, _ = get_lessons_for_date(d)
            _states[user_id] = {"mode": "ov_pair_replace", "day": d.isoformat()}
            pairs = "\n".join(f"• {fmt_lesson_short(l)}" for l in lessons) or "пар нет"
            return f"📅 {d.strftime('%d.%m')}:\n{pairs}\n\nНапиши <b>номер пары</b> для замены/создания:", inline_admin()
        if mode == "ov_pair_replace":
            import re
            m = re.search(r"\d+", t)
            if not m:
                return "Нужен номер пары. Например: 3", inline_admin()
            _states[user_id] = {"mode": "ov_pair_new", "day": st["day"], "pair": int(m.group())}
            return ("Напиши замену в формате:\n<b>Дисциплина | Преподаватель | Аудитория</b>\n"
                    "Например: Электротехника (пр) | Баранова С.К. | Э-3"), inline_admin()
        if mode == "ov_pair_new":
            parts = [p.strip() for p in raw.split("|")]
            if len(parts) != 3 or not all(parts):
                return "Формат: <b>Дисциплина | Преподаватель | Аудитория</b>", inline_admin()
            d = date.fromisoformat(st["day"])
            replace_pair_for_date(d, st["pair"], parts[0], parts[1], parts[2])
            return to_menu(f"✅ {d.strftime('%d.%m')}, {st['pair']} пара — обновлена.")

    # --- в группах реагируем только на команды (/... или ....), иначе игнор ---
    if is_group and not is_cmd:
        return None, None

    # --- вход в админку ---
    if n in ("admin", "⚙️ админка", "админка", "админ"):
        if not admin:
            return "⛔ Нет доступа.", get_keyboard(user_id)
        _states[user_id] = {"mode": "admin_menu"}
        return ADMIN_MENU_TEXT, inline_admin()

    # --- прямые команды админки без входа в меню ---
    if admin and not st.get("mode"):
        if n in ("➕ дз", "добавить дз", "➕"):
            _states[user_id] = {"mode": "hw_subject"}
            return "📝 Напиши <b>предмет</b> (например: Монтаж):", inline_admin()
        if n in ("🗑 дз", "удалить дз", "удалить"):
            if not _data["homework"]:
                return "Домашки нет — удалять нечего.", get_keyboard(user_id)
            _states[user_id] = {"mode": "hw_delete"}
            return hw_list_text() + "\n\nНапиши <b>номер</b> для удаления (например: 3):", inline_admin()
        if n in ("❌ отмена пары", "отмена пары"):
            _states[user_id] = {"mode": "ov_date_cancel"}
            return "Напиши <b>дату</b>: Сегодня / Завтра / ДД.ММ:", inline_admin()
        if n in ("✏️ замена", "замена", "замена пары"):
            _states[user_id] = {"mode": "ov_date_replace"}
            return "Напиши <b>дату</b>: Сегодня / Завтра / ДД.ММ:", inline_admin()
        if n in ("📅 выходной", "выходной", "день выходной"):
            _states[user_id] = {"mode": "ov_date_off"}
            return "Напиши <b>дату</b> выходного: Сегодня / Завтра / ДД.ММ:", inline_admin()
        if n in ("↩️ сброс", "сброс", "сброс дня"):
            _states[user_id] = {"mode": "ov_date_reset"}
            return "Напиши <b>дату</b> для сброса: Сегодня / Завтра / ДД.ММ:", inline_admin()
        if n in ("📋 правки", "правки", "показать правки"):
            return list_overrides_text(), get_keyboard(user_id)

    # --- обычные команды ---
    if n in ("start", "старт", "привет"):
        txt = ("👋 Привет! Я бот группы <b>ФТ24АР52ЭО</b>\n\n"
               "Что умею:\n📅 <b>Сегодня</b> — пары на сегодня\n📅 <b>Завтра</b> — пары на завтра\n"
               "🔢 <b>Неделя</b> — числитель или знаменатель\n⏰ <b>Сейчас</b> — какая пара идет\n"
               "🗓 <b>Расписание</b> — вся неделя\n📝 <b>Д/З</b> — домашка\n\n"
               "В группе пиши с точкой: <b>.завтра</b>, <b>.сейчас</b> — или жми кнопки ⬇️")
        return txt, get_keyboard(user_id, bool(st.get("mode")))
    if n in ("help", "помощь", "хелп"):
        return ("В личке можно просто: Сегодня, Завтра, Неделя, Сейчас, Расписание, Д/З\n"
                "В группе — с точкой: <b>.сегодня .завтра .неделя .сейчас .расписание .дз</b>\n"
                "Слэш тоже работает: /today /tomorrow /week /now /schedule /hw",
                get_keyboard(user_id, bool(st.get("mode"))))
    if n in ("week", "неделя", "числитель", "знаменатель"):
        wt = get_week_type(today)
        badge = "🔴 <b>ЧИСЛИТЕЛЬ</b> (нечетная)" if wt == "числитель" else "🔵 <b>ЗНАМЕНАТЕЛЬ</b> (четная)"
        return f"📅 Сегодня <b>{today.strftime('%d.%m.%Y')}</b>\n{badge}", get_keyboard(user_id, bool(st.get("mode")))
    if n in ("today", "сегодня", "седня"):
        return get_schedule_text(today), get_keyboard(user_id, bool(st.get("mode")))
    if n in ("tomorrow", "tomorow", "завтра"):
        return get_schedule_text(today + timedelta(days=1)), get_keyboard(user_id, bool(st.get("mode")))
    if n in ("now", "сейчас", "пара", "какая пара", "что сейчас", "щас", "ща"):
        return get_now_status(today, now), get_keyboard(user_id, bool(st.get("mode")))
    if n in ("schedule", "расписание", "все", "вся неделя", "на неделю"):
        return get_week_schedule_text(today), get_keyboard(user_id, bool(st.get("mode")))
    if n in ("hw", "📝 д/з", "д/з", "дз", "домашка", "домашнее задание", "д/з 📝"):
        return hw_list_text(), get_keyboard(user_id, bool(st.get("mode")))
    return "🤔 Не понял\nНапиши: <b>Сегодня</b>, <b>Завтра</b>, <b>Неделя</b>, <b>Сейчас</b>, <b>Расписание</b> или <b>📝 Д/З</b>", get_keyboard(user_id, bool(st.get("mode")))


def process_callback(user_id: int, data: str, today: date | None = None,
                     now: datetime | None = None) -> tuple:
    """Нажатие inline-кнопки -> (текст, inline-клавиатура)."""
    today = today or (now.date() if now else get_local_now().date())
    d = (data or "").strip()
    admin = is_admin(user_id)

    main = {
        "cmd:today": lambda: (get_schedule_text(today), get_keyboard(user_id)),
        "cmd:tomorrow": lambda: (get_schedule_text(today + timedelta(days=1)), get_keyboard(user_id)),
        "cmd:week": lambda: process_message(user_id, "неделя", today, now, "private"),
        "cmd:now": lambda: (get_now_status(today, now), get_keyboard(user_id)),
        "cmd:schedule": lambda: (get_week_schedule_text(today), get_keyboard(user_id)),
        "cmd:hw": lambda: (hw_list_text(), get_keyboard(user_id)),
    }
    if d in main:
        return main[d]()

    if d == "adm:menu":
        if not admin:
            return "⛔ Нет доступа.", inline_main(user_id)
        _states[user_id] = {"mode": "admin_menu"}
        return ADMIN_MENU_TEXT, inline_admin()
    if d == "adm:exit":
        _states.pop(user_id, None)
        return "🚪 Вышел из админки.", get_keyboard(user_id)
    if not admin:
        return "⛔ Нет доступа.", inline_main(user_id)
    if d == "adm:hw_add":
        _states[user_id] = {"mode": "hw_subject"}
        return "📝 Напиши <b>предмет</b> (например: Монтаж):", inline_admin()
    if d == "adm:hw_del":
        if not _data["homework"]:
            return "Домашки нет — удалять нечего.", inline_admin()
        _states[user_id] = {"mode": "hw_delete"}
        return hw_list_text() + "\n\nНапиши <b>номер</b> для удаления:", inline_admin()
    if d == "adm:cancel":
        _states[user_id] = {"mode": "ov_date_cancel"}
        return "Напиши <b>дату</b>: Сегодня / Завтра / ДД.ММ:", inline_admin()
    if d == "adm:replace":
        _states[user_id] = {"mode": "ov_date_replace"}
        return "Напиши <b>дату</b>: Сегодня / Завтра / ДД.ММ:", inline_admin()
    if d == "adm:off":
        _states[user_id] = {"mode": "ov_date_off"}
        return "Напиши <b>дату</b> выходного: Сегодня / Завтра / ДД.ММ:", inline_admin()
    if d == "adm:reset":
        _states[user_id] = {"mode": "ov_date_reset"}
        return "Напиши <b>дату</b> для сброса: Сегодня / Завтра / ДД.ММ:", inline_admin()
    if d == "adm:list":
        _states[user_id] = {"mode": "admin_menu"}
        return list_overrides_text() + "\n\n" + ADMIN_MENU_TEXT, inline_admin()
    return "🤔 Неизвестная кнопка.", get_keyboard(user_id)


def handle_text(text: str, today: date | None = None, now: datetime | None = None) -> str:
    txt, _ = process_message(0, text, today, now)
    return txt or ""
