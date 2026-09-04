"""Логика бота ФТ24АР52ЭО: числитель/знаменатель + расписание. Формат HTML для Telegram."""
from datetime import date, timedelta, datetime, time as dtime

try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Europe/Chisinau")
except Exception:
    LOCAL_TZ = None

# Неделя Пн 31.08 – Вс 06.09 = числитель (эта неделя числитель, следующая знаменатель)
SEMESTER_START = date(2026, 8, 31)
START_WEEK_IS_NUMERATOR = True

WEEKDAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

# Расписание звонков: номер пары -> (начало, конец)
PAIR_TIMES = {
    1: ("8:00", "9:20"),
    2: ("9:40", "11:00"),
    3: ("11:25", "12:45"),
    4: ("13:05", "14:25"),
}

# Каждый урок: (номер пары, дисциплина, преподаватель, аудитория)
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
        0: MON,
        1: TUE_BASE + TUE_NUM,
        2: WED,
        3: THU,
        4: [FRI_NUM_1] + FRI_BASE,
        5: SAT_BASE + [SAT_NUM_4],
        6: [],
    },
    "знаменатель": {
        0: MON,
        1: TUE_BASE + TUE_DEN,
        2: WED,
        3: THU,
        4: [FRI_DEN_1] + FRI_BASE,
        5: SAT_BASE + [SAT_DEN_4],
        6: [],
    },
}


def get_week_type(day: date) -> str:
    delta = (day - SEMESTER_START).days
    if delta < 0:
        return "знаменатель" if day.isocalendar().week % 2 == 0 else "числитель"
    week_num = delta // 7
    is_num = (week_num % 2 == 0) == START_WEEK_IS_NUMERATOR
    return "числитель" if is_num else "знаменатель"


def fmt_room(room: str) -> str:
    return room.replace("Э* ", "Э-").replace("Э*", "Э-")


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


def get_schedule_text(day: date) -> str:
    wt = get_week_type(day)
    lessons = SCHEDULE[wt].get(day.weekday(), [])
    badge = "🔴 <b>ЧИСЛИТЕЛЬ</b>" if wt == "числитель" else "🔵 <b>ЗНАМЕНАТЕЛЬ</b>"
    header = f"📅 <b>{WEEKDAYS[day.weekday()]}, {day.strftime('%d.%m')}</b>\n{badge}\n➖➖➖➖➖➖➖"
    if not lessons:
        return header + "\n😴 Пар нет — отдыхай!"
    body = "\n\n".join(fmt_lesson(l) for l in lessons)
    return header + "\n\n" + body


def get_week_schedule_text(today: date) -> str:
    wt = get_week_type(today)
    badge = "🔴 <b>ЧИСЛИТЕЛЬ</b>" if wt == "числитель" else "🔵 <b>ЗНАМЕНАТЕЛЬ</b>"
    parts = [f"🗓 <b>Расписание на неделю</b>\n{badge}\n➖➖➖➖➖➖➖"]
    for wd in range(6):  # Пн-Сб
        lessons = SCHEDULE[wt].get(wd, [])
        parts.append(f"\n<b>{WEEKDAYS[wd]}</b>")
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
    now = datetime.now(tz=LOCAL_TZ) if LOCAL_TZ else datetime.now()
    return now


def get_now_status(today: date | None = None, now: datetime | None = None) -> str:
    today = today or (now.date() if now else get_local_now().date())
    now = now or get_local_now()
    cur = now.hour * 60 + now.minute

    wt = get_week_type(today)
    lessons = sorted(SCHEDULE[wt].get(today.weekday(), []), key=lambda l: l[0])
    badge = "🔴 <b>ЧИСЛИТЕЛЬ</b>" if wt == "числитель" else "🔵 <b>ЗНАМЕНАТЕЛЬ</b>"
    header = f"⏰ <b>Сейчас {now.strftime('%H:%M')}, {WEEKDAYS[today.weekday()]} {today.strftime('%d.%m')}</b>\n{badge}\n➖➖➖➖➖➖➖"

    if not lessons:
        return header + "\n😴 Сегодня пар нет."

    spans = []
    for num, name, teacher, room in lessons:
        s, e = PAIR_TIMES.get(num, ("0:00", "0:00"))
        spans.append((_to_minutes(s), _to_minutes(e), num, name, teacher, room))

    # Идет пара?
    for s, e, num, name, teacher, room in spans:
        if s <= cur < e:
            return (
                header
                + f"\n🟢 <b>Сейчас идет {num} пара ({PAIR_TIMES[num][0]}-{PAIR_TIMES[num][1]})</b>\n"
                + fmt_lesson((num, name, teacher, room))
            )
    # До первой?
    if cur < spans[0][0]:
        num, name, teacher, room = spans[0][2], spans[0][3], spans[0][4], spans[0][5]
        return (
            header
            + f"\n⏳ <b>Пары еще не начались. Первая — {num} пара в {PAIR_TIMES[num][0]}</b>\n\n"
            + fmt_lesson((num, name, teacher, room))
        )
    # Перемена / после?
    for i, (s, e, num, name, teacher, room) in enumerate(spans):
        if cur >= e and i + 1 < len(spans) and cur < spans[i + 1][0]:
            nn, nn_name, nn_t, nn_r = spans[i + 1][2], spans[i + 1][3], spans[i + 1][4], spans[i + 1][5]
            return (
                header
                + f"\n☕ <b>Перемена. Следующая — {nn} пара в {PAIR_TIMES[nn][0]}</b>\n\n"
                + fmt_lesson((nn, nn_name, nn_t, nn_r))
            )
    return header + "\n🏁 <b>Пары на сегодня закончились.</b>"


def handle_text(text: str, today: date | None = None, now: datetime | None = None) -> str:
    today = today or (now.date() if now else get_local_now().date())
    t = (text or "").strip().lower()

    if t in ("/start", "старт", "привет"):
        return (
            "👋 Привет! Я бот группы <b>ФТ24АР52ЭО</b>\n\n"
            "Что умею:\n"
            "📅 <b>Сегодня</b> — пары на сегодня\n"
            "📅 <b>Завтра</b> — пары на завтра\n"
            "🔢 <b>Неделя</b> — числитель или знаменатель\n"
            "⏰ <b>Сейчас</b> — какая пара идет\n"
            "🗓 <b>Расписание</b> — вся неделя\n\n"
            "Жми кнопку ниже ⬇️"
        )
    if t in ("/help", "помощь", "help"):
        return "Команды: /today /tomorrow /week /now /schedule\nИли кнопки: Сегодня, Завтра, Неделя, Сейчас, Расписание"
    if t in ("/week", "неделя", "числитель", "знаменатель"):
        wt = get_week_type(today)
        badge = "🔴 <b>ЧИСЛИТЕЛЬ</b> (нечетная)" if wt == "числитель" else "🔵 <b>ЗНАМЕНАТЕЛЬ</b> (четная)"
        return f"📅 Сегодня <b>{today.strftime('%d.%m.%Y')}</b>\n{badge}"
    if t in ("/today", "сегодня"):
        return get_schedule_text(today)
    if t in ("/tomorrow", "завтра"):
        return get_schedule_text(today + timedelta(days=1))
    if t in ("/now", "сейчас", "пара", "какая пара", "что сейчас", "щас", "ща"):
        return get_now_status(today, now)
    if t in ("/schedule", "расписание", "все", "вся неделя", "на неделю"):
        return get_week_schedule_text(today)
    return "🤔 Не понял\nНапиши: <b>Сегодня</b>, <b>Завтра</b>, <b>Неделя</b>, <b>Сейчас</b> или <b>Расписание</b>"
