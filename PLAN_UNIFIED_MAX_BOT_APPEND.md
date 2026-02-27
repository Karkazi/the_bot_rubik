---

## 11. Переменные окружения (.env) для единого бота

Ниже перечислены все переменные, необходимые для объединённого проекта (Support Core + адаптеры MAX и Telegram). Источники: текущий `the_bot_rubik`, `the_bot_wms`, `the_bot_lupa`.

### 11.1 Список переменных (с реальными значениями из проектов)

| Переменная | Назначение | Пример значения |
|------------|------------|------------------|
| **Telegram (три бота)** | | |
| `TELEGRAM_TOKEN_WMS` | Токен бота WMS в Telegram | *не заполнять* |
| `TELEGRAM_TOKEN_LUPA` | Токен бота Lupa в Telegram | *не заполнять* |
| `TELEGRAM_TOKEN_RUBIK` | Токен бота Rubik в Telegram | *не заполнять* |
| **MAX** | | |
| `MAX_TOKEN` | Токен единого support-бота в MAX (один на всё) | *не заполнять* |
| **Админка** | | |
| `ADMIN_IDS` | Telegram ID администраторов через запятую | `472518684` |
| **Jira (общие)** | | |
| `JIRA_LOGIN_URL` | URL Jira | `https://jira.petrovich.tech` |
| `JIRA_TOKEN` | API-токен Jira (Bearer) | *не заполнять* |
| `JIRA_USERNAME` | (опционально) для basic auth, напр. в WMS | *(пусто в WMS)* |
| `JIRA_PASSWORD` | (опционально) для basic auth | *(пусто в WMS)* |
| **Jira AA (Rubik: смена пароля)** | | |
| `JIRA_AA_PROJECT_KEY` | Ключ проекта AA | `AA` |
| `JIRA_AA_ISSUE_TYPE` | Тип задачи | `Задача` |
| `JIRA_AA_ISSUE_TYPE_ID` | ID типа задачи (надёжнее имени) | `10401` |
| `JIRA_AA_ASSIGNEE_USERNAME` | Исполнитель по умолчанию | `Robot_Scripts_PS` |
| `JIRA_AA_SET_ASSIGNEE` | 1 — назначать, 0 — не назначать | `0` |
| `JIRA_AA_SERVICE_DESK_ID` | ID Service Desk | `23` |
| `JIRA_AA_REQUEST_TYPE_ID` | ID типа запроса «Смена пароля» | `964` |
| `JIRA_AA_FIELD_CUSTOMER_REQUEST_TYPE` | Поле типа запроса | `customfield_10500` |
| `JIRA_AA_REQUEST_TYPE_VALUE` | Значение «Смена пароля» | `Смена пароля` |
| `JIRA_AA_FIELD_AD_ACCOUNT` | Поле AD account | `customfield_14320` |
| `JIRA_AA_FIELD_EXISTING_PHONE` | Поле «текущий телефон» | `customfield_13103` |
| `JIRA_AA_FIELD_PASSWORD_NEW` | Поле «новый пароль» | `customfield_17506` |
| `JIRA_AA_FIELD_DEPARTMENT` | Поле подразделения | `customfield_11406` |
| **Jira WMS (при переносе)** | | |
| `JIRA_WMS_PROJECT_KEY` | Ключ проекта WMS | `PW` |
| `JIRA_WMS_SERVICE_DESK_ID` | ID Service Desk WMS | `31` |
| `JIRA_WMS_FIELD_DEPARTMENT` | Подразделение (отдел) | `customfield_18215` |
| `JIRA_WMS_FIELD_PROCESS` | Процесс | `customfield_13803` |
| `JIRA_WMS_FIELD_SERVICE_TYPE` | Тип услуги | `customfield_10500` |
| `JIRA_WMS_FIELD_WMS_SETTINGS_SERVICE` | Тип настройки WMS | `customfield_18402` |
| `JIRA_WMS_FIELD_PSI_USER_FULL_NAME` | ФИО пользователя PSI | `customfield_12406` |
| **Jira Lupa (при переносе)** | | |
| `JIRA_LUPA_PROJECT_KEY` | Ключ проекта Lupa | `WHD` |
| `JIRA_LUPA_ISSUE_TYPE` | Тип задачи | `Incident` |
| `JIRA_LUPA_FIELD_PROBLEMATIC_SERVICE` | Проблемный сервис (Приложение/Сайт) | `customfield_12312` |
| `JIRA_LUPA_FIELD_REQUEST_TYPE` | Тип запроса | `customfield_15800` |
| `JIRA_LUPA_FIELD_SUBDIVISION` | Подразделение | `customfield_11406` |
| `JIRA_LUPA_FIELD_SERVICE` | Сервис (напр. Поиск) | `customfield_10500` |
| `JIRA_LUPA_FIELD_ADDRESS_CITY` | Город | `customfield_12403` |
| **Прочее** | | |
| `PASSWORD_STATUS_CHECK_INTERVAL` | Интервал проверки статуса заявок на пароль (с) | напр. `90` |
| `COMMENTS_CHECK_INTERVAL` | Интервал проверки комментариев (с) | напр. `20` (WMS) |
| `ANTISPAM_COOLDOWN` | Задержка антиспама (с) | напр. `0.5` (WMS) |
| `LOG_LEVEL` | Уровень логирования | напр. `INFO` |
| `ENCRYPT_USER_DATA` | 1 — шифровать персональные поля в покое | *(опционально)* |
| `USER_DATA_ENCRYPTION_KEY` | Ключ шифрования (если включено) | *(опционально)* |

### 11.2 Пример блока для .env (реальные значения, токены — заглушки)

Полный блок со всеми переменными из п. 11.1. Токены оставлены заглушками.

```
# ---- Telegram (три бота) ----
TELEGRAM_TOKEN_WMS=your_telegram_bot_token_wms
TELEGRAM_TOKEN_LUPA=your_telegram_bot_token_lupa
TELEGRAM_TOKEN_RUBIK=your_telegram_bot_token_rubik

# ---- MAX (один токен на весь support-бот) ----
MAX_TOKEN=your_max_bot_token

# ---- Админка ----
ADMIN_IDS=472518684

# ---- Jira (общие) ----
JIRA_LOGIN_URL=https://jira.petrovich.tech
JIRA_TOKEN=your_jira_api_token
# JIRA_USERNAME=
# JIRA_PASSWORD=

# ---- Jira AA (Rubik: смена пароля) ----
JIRA_AA_PROJECT_KEY=AA
JIRA_AA_ISSUE_TYPE=Задача
JIRA_AA_ISSUE_TYPE_ID=10401
JIRA_AA_ASSIGNEE_USERNAME=Robot_Scripts_PS
JIRA_AA_SET_ASSIGNEE=0
JIRA_AA_SERVICE_DESK_ID=23
JIRA_AA_REQUEST_TYPE_ID=964
JIRA_AA_FIELD_CUSTOMER_REQUEST_TYPE=customfield_10500
JIRA_AA_REQUEST_TYPE_VALUE=Смена пароля
JIRA_AA_FIELD_AD_ACCOUNT=customfield_14320
JIRA_AA_FIELD_EXISTING_PHONE=customfield_13103
JIRA_AA_FIELD_PASSWORD_NEW=customfield_17506
JIRA_AA_FIELD_DEPARTMENT=customfield_11406

# ---- Jira WMS (при переносе) ----
JIRA_WMS_PROJECT_KEY=PW
JIRA_WMS_SERVICE_DESK_ID=31
JIRA_WMS_FIELD_DEPARTMENT=customfield_18215
JIRA_WMS_FIELD_PROCESS=customfield_13803
JIRA_WMS_FIELD_SERVICE_TYPE=customfield_10500
JIRA_WMS_FIELD_WMS_SETTINGS_SERVICE=customfield_18402
JIRA_WMS_FIELD_PSI_USER_FULL_NAME=customfield_12406

# ---- Jira Lupa (при переносе) ----
JIRA_LUPA_PROJECT_KEY=WHD
JIRA_LUPA_ISSUE_TYPE=Incident
JIRA_LUPA_FIELD_PROBLEMATIC_SERVICE=customfield_12312
JIRA_LUPA_FIELD_REQUEST_TYPE=customfield_15800
JIRA_LUPA_FIELD_SUBDIVISION=customfield_11406
JIRA_LUPA_FIELD_SERVICE=customfield_10500
JIRA_LUPA_FIELD_ADDRESS_CITY=customfield_12403

# ---- Прочее (интервалы, логи, шифрование) ----
# PASSWORD_STATUS_CHECK_INTERVAL=90
# COMMENTS_CHECK_INTERVAL=20
# ANTISPAM_COOLDOWN=0.5
# LOG_LEVEL=INFO
# ENCRYPT_USER_DATA=0
# USER_DATA_ENCRYPTION_KEY=
```
