# Статус реализации плана PLAN_UNIFIED_MAX_BOT.md

Реализация идёт по **п. 7.B** (поэтапный путь от репозитория the_bot_rubik).

## Сделано

### Этап 1: Core API + DTO
- **`core/support/models.py`** — DTO: `Text`, `Menu`, `MenuButton`, `Form`, `FormField`, `Error`.
- **`core/support/api.py`** — фасад `SupportAPI`:
  - `get_start(channel_id, user_id)` — приветствие или главное меню;
  - `get_main_menu(channel_id, user_id)` — кнопки: Поменять пароль, Учётные данные, Комментарии (если есть заявка), Админ;
  - `get_ticket_types_menu(channel_id, user_id)` — меню типов заявок из каталога;
  - `create_ticket(channel_id, user_id, ticket_type_id, form_data)` — создание заявки по типу (пока только `rubik_password_change`).

### Этап 2: Каталог типов заявок
- **`config/ticket_catalog.yaml`** — первый тип: `rubik_password_change` (проект AA, смена пароля).
- **`core/support/ticket_catalog.py`** — загрузка каталога из YAML, fallback на встроенный словарь.

### Подключение Telegram к Core (тонкий адаптер)
- **`adapters/telegram/render.py`** — преобразование DTO в aiogram: `Menu` → `InlineKeyboardMarkup`, `Text`/`Error` → kwargs для `answer`.
- **`handlers/start.py`** — использует `support_api.get_start()` и `support_api.get_main_menu()`, рендер через `adapters.telegram.render`.

### Этап 3: Единый реестр привязок
- **`core/support/issue_binding_registry.py`** — хранение привязок `(channel_id, channel_user_id, issue_key, project_key, ticket_type_id)` в `data/issue_binding_registry.json`.
- При создании заявки на смену пароля вызывается `add_binding("telegram", user_id, issue_key, "AA", "rubik_password_change")`.
- Старый `pending_password_requests.json` по-прежнему используется для уведомлений (обратная совместимость); реестр готов для «Мои заявки» и будущей доставки по каналам.

### Этап 4: «Мои заявки» и комментарии по реестру
- **`core/support/api.py`** — добавлены `get_my_tickets(channel_id, user_id)` и `user_owns_issue(channel_id, user_id, issue_key)`; в главное меню добавлена кнопка «📋 Мои заявки», если у пользователя есть привязки в реестре.
- **`handlers/my_tickets.py`** — обработчики `my_tickets` (список заявок) и `open_issue:KEY` (просмотр комментариев и кнопка «Добавить комментарий»).
- **`handlers/comments.py`** — доступ к «Добавить комментарий» разрешён по реестру привязок (`user_owns_issue`) в дополнение к pending-заявке на смену пароля.
- Роутер **`my_tickets_router`** подключён в **`main.py`**.

### Зависимости
- В **`requirements.txt`** добавлен **PyYAML** для каталога.

---

### Этап 5: Уведомления через интерфейс доставки
- **`core/support/delivery.py`** — интерфейс: `set_delivery(callback)`, `deliver(channel_id, channel_user_id, text, reply_markup)`. Формат `reply_markup`: список рядов кнопок `List[List[dict]]` с ключами `text`, `callback_data`.
- **`core/password_requests.py`** — убрана зависимость от aiogram; `check_statuses_and_notify()` и `check_comments_and_notify()` вызывают `delivery.deliver("telegram", user_id, ...)`. Циклы `run_status_checker_loop()` и `run_comments_checker_loop()` без аргумента `bot`.
- **`main.py`** — регистрация `telegram_deliver`: при `channel_id == "telegram"` отправка через `bot.send_message`; конвертация `reply_markup` в `InlineKeyboardMarkup`.

### Этап 6: Адаптер MAX
- **`adapters/max/`** — точка входа `main_max.py` (run_max_bot), обработчики `handlers.py` (handle_start, handle_main_menu, handle_callback) вызывают `core.support.api`; рендер `render.py` (Menu/Text/Error → dict для MAX). При отсутствии MAX_BOT_TOKEN или SDK (MaxBotAPI / max-bot-api-client) запуск не выполняется (заглушка).

### Этап 7: Каталог WMS/Lupa
- **`config/ticket_catalog.yaml`** — типы `wms_issue` (PW) и `lupa_search` (WHD) с `form_fields` (тема, описание, процесс для WMS; описание, сервис, тип запроса, подразделение, город для Lupa).
- **`core/jira_wms.py`** — создание заявки wms_issue в проекте PW (REST API, поля department, process, service_type «Проблема в работе WMS»).
- **`core/jira_lupa.py`** — создание заявки в WHD (Incident, поля problematic_service, request_type, subdivision, service, address_city).
- **`core/support/api.py`** — `create_ticket` для `wms_issue` и `lupa_search` вызывает эти модули и добавляет привязку в `issue_binding_registry`.
- **`handlers/create_ticket.py`** — кнопка «Создать заявку» в главном меню; меню типов заявок; FSM для WMS (тема → описание → процесс [→ подразделение]) и Lupa (описание → сервис → тип запроса → подразделение → город); выбор «Смена пароля» ведёт в существующий сценарий.
- В **главное меню** добавлена кнопка **«📋 Создать заявку»** (вызов `get_ticket_types_menu`).

---

## Проверка по плану (PLAN_UNIFIED_MAX_BOT, APPEND)

### Функционал: текущий бот vs the_bot_wms / the_bot_lupa

| Компонент | WMS (the_bot_wms) | Lupa (the_bot_lupa) | Текущий Rubik |
|-----------|-------------------|---------------------|----------------|
| Регистрация | full_name → phone → email → department (WMS_DEPARTMENTS) | FIO → email → subdivision → employee_id | Rubik: FIO, login, email, department (Jira), без WMS/Lupa полей |
| Создание заявки | wms_issue, wms_settings, psi_user (PW, JSM, request_type_id) | Incident в WHD, поля 12312/15800/11406/10500/12403 | Только rubik_password_change (AA); wms_issue/lupa_search — «пока не реализовано» |
| «Мои заявки» | JQL + привязка по «Контактное лицо: {name}, {phone}» в description | tasks_users.json (issue_key → user_id) | Единый реестр привязок (issue_binding_registry); только заявки, созданные через бота |
| Уведомления | Цикл ~20 с по JQL (PW, label «поддержка») | Цикл ~20 с по WHD + tasks_users | Только по заявкам смены пароля (pending + реестр), интерфейс доставки без привязки к aiogram |
| Админка | main_admin_id + роль admin в users.json | admins.json, OWNER_ADMIN | ADMIN_IDS из .env |

**Итог:** текущий бот **не повторяет полностью** WMS и Lupa: нет сценариев создания заявок PW/WHD, нет регистрации с WMS_DEPARTMENTS / subdivision / employee_id, нет циклов опроса Jira по PW/WHD. Учтены: единый реестр привязок, каталог типов, доставка через интерфейс, заготовки типов wms_issue/lupa_search в каталоге.

### Проблемы из PLAN_UNIFIED_MAX_BOT (раздел 6): учтено / не учтено

| Проблема (план) | Учтено | Комментарий |
|-----------------|--------|-------------|
| 6.2 Разные проекты/поля (PW, WHD, AA) | Частично | Каталог типов + конфиг JIRA_WMS/JIRA_LUPA; create_ticket для WMS/Lupa не реализован |
| 6.3 Единый каталог 50+ типов | Да | ticket_catalog.yaml, три типа в каталоге |
| 6.4 Админы (WMS/Lupa/Rubik по-разному) | Частично | Только ADMIN_IDS (Rubik); единый admins.json не введён |
| 6.5 FSM и отмена сценария | Частично | /cancel есть; namespace по сценарию не унифицирован |
| 6.6 Уведомления по единому реестру | Да | Реестр привязок, delivery без aiogram; циклы только по AA (смена пароля) |
| 6.7 Идентификация Telegram vs MAX | Задел | Привязка по телефону в user_storage; сценарий привязки MAX по коду не реализован |
| 6.8 Справочники по продукту | Нет | WMS_DEPARTMENTS, справочники Lupa не подгружаются из Core |
| 6.9 Единое хранилище профилей | Частично | user_data.json (Rubik); форматы WMS/Lupa не мигрированы |
| 6.10 Единые сообщения об ошибках | Частично | Тексты в коде/адаптере |
| 6.11 «Мои заявки» по реестру | Да | По issue_binding_registry; доставка по каналу готова |

### Переменные .env по PLAN_UNIFIED_MAX_BOT_APPEND (п. 11)

Все переменные из раздела 11 добавлены в **`.env`** и поддерживаются в **`config.py`**:

- **Telegram:** TELEGRAM_TOKEN (и опционально TELEGRAM_TOKEN_WMS / LUPA / RUBIK); CONFIG читает TELEGRAM_TOKEN или TELEGRAM_TOKEN_RUBIK.
- **MAX:** MAX_BOT_TOKEN, MAX_TOKEN.
- **Админка:** ADMIN_IDS.
- **Jira общие:** JIRA_LOGIN_URL, JIRA_TOKEN; опционально JIRA_USERNAME, JIRA_PASSWORD.
- **Jira AA:** все поля п. 11.1, включая JIRA_AA_FIELD_DEPARTMENT.
- **Jira WMS:** JIRA_WMS_PROJECT_KEY, JIRA_WMS_SERVICE_DESK_ID, JIRA_WMS_FIELD_DEPARTMENT, JIRA_WMS_FIELD_PROCESS, JIRA_WMS_FIELD_SERVICE_TYPE, JIRA_WMS_FIELD_WMS_SETTINGS_SERVICE, JIRA_WMS_FIELD_PSI_USER_FULL_NAME.
- **Jira Lupa:** JIRA_LUPA_PROJECT_KEY, JIRA_LUPA_ISSUE_TYPE, JIRA_LUPA_FIELD_* (PROBLEMATIC_SERVICE, REQUEST_TYPE, SUBDIVISION, SERVICE, ADDRESS_CITY).
- **Прочее:** PASSWORD_STATUS_CHECK_INTERVAL, COMMENTS_CHECK_INTERVAL, ANTISPAM_COOLDOWN, LOG_LEVEL, ENCRYPT_USER_DATA, USER_DATA_ENCRYPTION_KEY (в .env закомментированы; при необходимости раскомментировать).

Алиасы JIRA_PW_* / JIRA_WHD_* в config.py подставлены из JIRA_WMS_* / JIRA_LUPA_* для обратной совместимости.

---

## Дальше по плану

- Подключение MAX SDK в `adapters/max/main_max.py` и регистрация обработчиков при наличии токена.
- Опционально: циклы уведомлений по заявкам PW/WHD (по реестру привязок); загрузка справочников подразделений из Jira для Lupa/WMS.
