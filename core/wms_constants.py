"""
Общие константы WMS: процессы и типы услуг. Одинаковые для TG и MAX (как the_bot_wms).
"""
# Поле «WMS service» в заявке «Изменение настроек системы WMS»: задаётся пользователем при создании,
# допускаются только два значения (как в the_bot_wms).
WMS_SERVICE_TYPES = {
    "wms_service_topology": "Изменение топологии",
    "wms_service_other": "Другие настройки",
}

# Процессы WMS (как в the_bot_wms) — для Jira customfield_13803 нужны точные значения
WMS_PROCESSES = {
    "proc_placement": "Размещение",
    "proc_reserve": "Резерв",
    "proc_receiving": "Приемка",
    "proc_pick": "Отбор",
    "proc_control": "Контроль",
    "proc_shipment": "Отгрузка",
    "proc_replenishment": "Пополнение",
    "proc_inventory": "Инвентаризация",
    "proc_app": "Приложение WMS",
    "proc_report": "Проблемы с отчетом WMS",
    "proc_assembly": "Сборка",
    "proc_other": "Другое",
}
