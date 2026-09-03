"""Общая логика тестового бота: числитель/знаменатель + расписание."""
from datetime import date, timedelta

# Начало семестра. Первая неделя (1-7 сентября) = числитель.
SEMESTER_START = date(2026, 9, 1)
START_WEEK_IS_NUMERATOR = True  # если первая неделя знаменатель - поставь False

# Тестовое расписание. 0=Пн ... 6=Вс. Потом заменишь на свое.
FAKE_SCHEDULE = {
    "числитель": {
        0: ["1. Математика (9:00-10:30, ауд. 101)", "2. Физика (10:40-12:10, ауд. 205)", "3. История (12:40-14:10, ауд. 310)"],
        1: ["1. Программирование (9:00-10:30)", "2. Английский (10:40-12:10)"],
        2: ["1. Физра (9:00-10:30)", "2. Математика (10:40-12:10)", "3. Физика лаб. (12:40-14:10)"],
        3: ["1. Английский (10:40-12:10)", "2. Программирование (12:40-14:10)"],
        4: ["1. История (9:00-10:30)", "2. Математика (10:40-12:10)"],
        5: ["1. Классный час (10:00-11:00)"],
        6: [],
    },
    "знаменатель": {
        0: ["1. Физика (9:00-10:30, ауд. 205)", "2. Математика (10:40-12:10, ауд. 101)"],
        1: ["1. Английский (9:00-10:30)", "2. Программирование (10:40-12:10)", "3. Физра (12:40-14:10)"],
        2: ["1. Программирование (9:00-10:30)", "2. История (10:40-12:10)"],
        3: ["1. Физика (10:40-12:10)", "2. Математика (12:40-14:10)"],
        4: ["1. Проектная работа (9:00-12:10)"],
        5: [],
        6: [],
    },
}

WEEKDAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]


def get_week_type(day: date) -> str:
    """Возвращает 'числитель' или 'знаменатель' для даты."""
    delta_days = (day - SEMESTER_START).days
    if delta_days < 0:
        # До начала семестра считаем по текущей четности
        weeks = abs(delta_days) // 7 + 1
        is_num = (weeks % 2 == 1) != START_WEEK_IS_NUMERATOR if False else None
        # Простой фолбэк: четная неделя года = знаменатель
        return "знаменатель" if day.isocalendar().week % 2 == 0 else "числитель"
    week_num = delta_days // 7  # 0 = первая неделя
    is_numerator = (week_num % 2 == 0) == START_WEEK_IS_NUMERATOR
    return "числитель" if is_numerator else "знаменатель"


def get_schedule_text(day: date) -> str:
    week_type = get_week_type(day)
    lessons = FAKE_SCHEDULE[week_type].get(day.weekday(), [])
    header = f"{WEEKDAYS[day.weekday()]} ({day.strftime('%d.%m')}) — {week_type}\n"
    if not lessons:
        return header + "Пар нет, отдыхай \U0001f60e"
    return header + "\n".join(f"• {l}" for l in lessons)


def handle_text(text: str, today: date | None = None) -> str:
    """Главная функция: текст пользователя -> ответ бота."""
    today = today or date.today()
    t = (text or "").strip().lower()

    if t in ("/start", "старт", "привет"):
        return (
            "Привет! Я тестовый бот \U0001f916\n"
            "Умею:\n"
            "/week — числитель или знаменатель?\n"
            "/today — расписание на сегодня\n"
            "/tomorrow — расписание на завтра\n"
            "Просто напиши: Сегодня, Завтра или Неделя"
        )
    if t in ("/help", "помощь", "help"):
        return "Команды: /start /week /today /tomorrow. Или кнопки: Сегодня, Завтра, Неделя"
    if t in ("/week", "неделя", "числитель", "знаменатель"):
        wt = get_week_type(today)
        return f"Сегодня {today.strftime('%d.%m.%Y')} — {wt} \U0001f4c5"
    if t in ("/today", "сегодня"):
        return get_schedule_text(today)
    if t in ("/tomorrow", "завтра"):
        return get_schedule_text(today + timedelta(days=1))

    return "Не понял \U0001f914\nНапиши: Сегодня, Завтра или Неделя (/help)"
