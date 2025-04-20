# hrbot/bot/constants.py

# === Conversation States ===
(
    MAIN_MENU,           # 0 Главное меню
    EVAL_SELECT_QSET,    # 1 Выбор опросника для оценки
    EVAL_SELECT_DEPT,    # 2 Выбор отдела для оценки
    EVAL_SELECT_EMP,     # 3 Выбор сотрудника для оценки
    EVAL_Q,              # 4 Прохождение вопросов оценки
    DEPT_LIST,           # 5 Просмотр списка отделов
    DEPT_EMP_LIST,       # 6 Просмотр сотрудников отдела
    EMP_LIST,            # 7 Просмотр списка всех сотрудников
    PROFILE_MENU,        # 8 Меню настроек профиля
    PROFILE_UPLOAD_PHOTO,# 9 Ожидание фото профиля
    PROFILE_SET_NAME,    # 10 Ожидание имени профиля
    LANG_MENU,           # 11 Меню выбора языка
    SEARCH_INPUT,        # 12 Ожидание ввода для поиска
    SEARCH_RESULTS       # 13 Показ результатов поиска
) = range(14) # Обновили диапазон (было 15, но состояний 14, от 0 до 13)

# === Callback Data Prefixes ===
CB_MAIN = "main"
CB_EVAL_QSET = "eval_qset"
CB_EVAL_DEPT = "eval_dept"
CB_EVAL_EMP = "eval_emp"
CB_DEPT = "dept"
CB_DEPT_EMP = "dept_emp"
CB_USER = "user"
CB_PROFILE = "profile"
CB_LANG = "lang"
CB_SEARCH_RES = "search_res"
CB_NOOP = "noop" # Для кнопок-заглушек

# === Callback Data Patterns (for handler registration) ===
MAIN_CALLBACK = rf"^{CB_MAIN}:(new_eval|show_depts|show_all_users|profile_settings|choose_lang|search_emp|stop|back_main)$"
EVAL_QSET_CALLBACK = rf"^{CB_EVAL_QSET}:(\d+)$"
EVAL_DEPT_CALLBACK = rf"^{CB_EVAL_DEPT}:(\d+)$"
EVAL_EMP_CALLBACK = rf"^{CB_EVAL_EMP}:(\d+)$"
DEPT_CALLBACK = rf"^{CB_DEPT}:(\d+)$"
DEPT_EMP_CALLBACK = rf"^{CB_DEPT_EMP}:(\d+)$"
USER_CALLBACK = rf"^{CB_USER}:(\d+)$"
PROFILE_CALLBACK = rf"^{CB_PROFILE}:(photo|name)$"
LANG_CALLBACK = rf"^{CB_LANG}:([a-zA-Z]{{2}}(?:-[a-zA-Z]{{2}})?)$"
SEARCH_RES_CALLBACK = rf"^{CB_SEARCH_RES}:(\d+)$"
STOP_CALLBACK = rf"^{CB_MAIN}:stop$"
NOOP_CALLBACK = rf"^{CB_NOOP}$"