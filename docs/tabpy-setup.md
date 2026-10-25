# TabPy: установка и подключение к Tableau

TabPy — analytics extension: Tableau отправляет табличные данные на Python-сервер, сервер выполняет функцию и возвращает колонку результатов обратно в визуализацию. В этом проекте TabPy закрывает то, чего в Tableau нет нативно: доверительные интервалы Уилсона, прогноз кривой удержания, экстраполяцию LTV и z-тест двух пропорций.

## 1. Что даёт TabPy в этом проекте

| Метрика | Нативно в Tableau | Через TabPy | Почему TabPy |
|---|---|---|---|
| Retention rate по когортам | Да: `SUM([is_active]) / COUNT([user_id])` | `retention_rate` | Одна null-безопасная формула с broadcasting: `cohort_size <= 0` даёт `null`, а не деление на ноль |
| 95% Wilson CI (нижняя/верхняя граница) | Нет | `wilson_lower`, `wilson_upper` | В Tableau нет функции Уилсона; нормальная аппроксимация на малых `n` выводит границы за [0, 1] |
| Прогноз кривой удержания | Нет | `retention_forecast` | Нужно сглаживание и продолжение ряда за пределы наблюдённых периодов |
| LTV на горизонте | Нет | `ltv_at_horizon` | Экстраполяция revenue/user на периоды, которых нет в данных |
| z-тест двух пропорций (p-value) | Нет | `ztest_two_proportions` | Tableau не считает p-value для сравнения двух долей |

Функции живут в `tabpy_functions.py` в корне проекта и публикуются в словаре `ENDPOINTS`; скрипт `tabpy/deploy.py` регистрирует их на сервере.

## 2. Установка

TabPy — это сервер и клиент в одном пакете. Есть два способа.

**Способ A — optional-группа проекта.** В `pyproject.toml` объявлена группа `tabpy`:

```bash
uv sync --extra tabpy        # поставить declared optional-зависимость
# или, если нужно добавить её в pyproject заново:
uv add --optional tabpy
```

**Способ B — отдельное окружение (рекомендуется для «серверной» машины).** TabPy не обязан жить в том же venv, что анализ:

```bash
python -m venv .venv-tabpy
.venv-tabpy/bin/pip install tabpy
```

Требуется Python 3.10–3.14. В проекте закреплён Python 3.14 (`.python-version`), так что оба способа совместимы.

`uv.lock` после добавления extra не пересчитан: первый `uv run` / `uv sync` после `uv lock` обновит его и втянет зависимости TabPy. До этого момента рабочий venv остаётся без TabPy — это ожидаемо.

Важно: endpoint-функции выполняются **на сервере**, в окружении TabPy. Если функция использует `numpy`/`pandas`, они должны быть установлены именно там, где запущен `tabpy`, а не только в окружении ноутбука.

## 3. Запуск

```bash
tabpy --config=tabpy/tabpy.conf
```

Если TabPy стоит в отдельном venv:

```bash
.venv-tabpy/bin/tabpy --config=tabpy/tabpy.conf
```

Конфиг лежит в `tabpy/tabpy.conf`, порт по умолчанию — `9004`.

> **Предупреждение из README TabPy.** Связка «аутентификация выключена + `TABPY_EVALUATE_ENABLE = true`» означает удалённое выполнение произвольного Python (RCE) для любого, кто дотянется до порта. Это допустимо только на локальной машине в доверенной сети. Флаг `tabpy --disable-auth-warning` отключает интерактивное предупреждение сервера и нужен только для неинтерактивного старта при осознанно принятом риске — сам риск он не снимает.

## 4. Проверка живости

```bash
curl -s http://localhost:9004/status
curl -s http://localhost:9004/info
```

- `/status` — состояние загруженных endpoints. `{}` означает: сервер жив, но ни один endpoint не задеплоен (это нормально до первого деплоя, и это не ошибка).
- Для каждого endpoint `/status` отдаёт `version`, `type`, `status`, `last_error`. Значения `status`: `LoadSuccessful` — функция загружена и готова; `LoadFailed` — загрузка упала, причина в `last_error`; `LoadInProgress` — ещё грузится.
- `/info` — метаданные сервера: имя, `server_version`, `state_path`, поддерживаемые версии API. Если запрос уходит с неверными credentials, вместо JSON придёт 401.

## 5. Деплой функций

Сначала план без сети:

```bash
uv run python tabpy/deploy.py --dry-run
```

Затем сам деплой (сервер уже запущен):

```bash
uv run python tabpy/deploy.py --url http://localhost:9004/
```

- `--override` передеплоит существующие endpoints; версия каждого увеличится на 1 (`v1 → v2`).
- Без `--override` уже задеплоенные endpoints пропускаются с `[skip]` — это защита от случайной перезаписи.
- Если включена аутентификация, добавьте `--username` и `--password` (или переменную окружения `TABPY_PASSWORD`; флаг приоритетнее).
- `uv run python tabpy/deploy.py --list` печатает текущие endpoints сервера.

Сменить только описание, не поднимая версию, можно через `update_endpoint_info`:

```bash
uv run python -c "from tabpy.tabpy_tools.client import Client; Client('http://localhost:9004/').update_endpoint_info('wilson_lower', description='Lower Wilson bound')"
```

## 6. Подключение Tableau

**Tableau Desktop 10.1+.** Help → Settings and Performance → Manage Analytics Extension Connection → указать host `localhost` и port `9004` (схема `http`).

**Tableau Server 2020.2+.** Settings → Analytics Extensions → добавить подключение с тем же host/port.

**Tableau Server ≤ 2018.1.** Настройка через `tabadmin`:

```bash
tabadmin set vizqlserver.extsvc.host localhost
tabadmin set vizqlserver.extsvc.port 9004
tabadmin configure
tabadmin start
```

## 7. Использование

Готовые calculated fields и их привязка к данным — в [`tableau/calculated_fields.md`](../tableau/calculated_fields.md). Общий принцип: поле вызывает `SCRIPT_*` с именем endpoint'а из `ENDPOINTS`, а аргументы передаются как агрегированные колонки текущей визуализации.

## 8. Безопасность

| Механизм | Ключи конфига | Что делает |
|---|---|---|
| Парольный файл | `TABPY_PWD_FILE` | Сервер начинает требовать credentials. Файл — строки `username hash` (PBKDF2); пользователи добавляются командой `tabpy-user add -u <user> -p <password> -f <pwdfile>`. После правки файла сервер надо перезапустить |
| OAuth / JWT | `TABPY_OAUTH_ENABLED`, `TABPY_OAUTH_ISSUER`, `TABPY_OAUTH_JWKS_URI`, `TABPY_OAUTH_AUDIENCE` | Проверка Bearer-токена от IdP. `ISSUER` и `JWKS_URI` обязательны, `AUDIENCE` задаёт границу авторизации |
| HTTPS | `TABPY_TRANSFER_PROTOCOL = https` + `TABPY_CERTIFICATE_FILE` / `TABPY_KEY_FILE` (PEM), `TABPY_MINIMUM_TLS_VERSION` | Шифрование трафика; без него credentials и данные запросов идут открытым текстом |
| Ограничение размера запроса | `TABPY_MAX_REQUEST_SIZE_MB` | Отклоняет слишком большие тела запросов (в конфиге проекта — 20 МБ) |

Парольный файл должен быть доступен на чтение только учётной записи, под которой работает TabPy. На рабочей машине с выключенной аутентификацией не выставляйте порт `9004` за пределы localhost.

## 9. Дебаг

| Симптом | Причина | Фикс |
|---|---|---|
| `401 Unauthorized` | Включена аутентификация, клиент не передал credentials | Задать `--username`/`--password` или `TABPY_PASSWORD`; в Tableau — те же credentials в настройках подключения |
| `404` на `/evaluate` | `TABPY_EVALUATE_ENABLE = false` | Включить ключ в `tabpy/tabpy.conf` и перезапустить сервер |
| `404` на endpoint (например, `/query/wilson_lower`) | Endpoint не задеплоен либо имя/арность не совпали | Сверить имя через `curl -s http://localhost:9004/status`; передеплоить `tabpy/deploy.py` |
| `400 "Variables names should follow the format _arg1, _arg2, _argN"` | В `SCRIPT_*` использованы позиционные аргументы `_arg1...` не по порядку или с пропуском | Перенумеровать аргументы строго `_arg1`, `_arg2`, ... без пропусков |
| `TimeoutError` | Скрипт работает дольше лимита | Увеличить `TABPY_EVALUATE_TIMEOUT` (в проекте 60 с) или упростить вычисление |
| `500 Object of type ndarray is not JSON serializable` | Функция вернула numpy-массив | Вернуть `list`: `arr.tolist()` (в `tabpy_functions.py` уже так и сделано) |
| `Wrong number of rows` | Длина результата не равна числу строк визуализации и не равна 1 | Вернуть список длины broadcast (по строкам) или одно значение; проверить длины входных колонок |
| `400 Error when changing TabPy state: invalid interpolation syntax` | В докстринге функции есть символ `%` — TabPy подставляет его через `%`-форматирование | Писать `1.0` вместо `100%` (или экранировать как `%%`) |
| `LoadFailed: No module named 'tabpy_functions'` | cloudpickle сериализует функцию по ссылке на модуль, а у сервера нет проектного пути в `sys.path` | `deploy.py` уже вызывает `cloudpickle.register_pickle_by_value(tabpy_functions)`; деплой только через него, не руками |
| `TypeError: got an unexpected keyword argument '_arg1'` | Таблица вызывает endpoint именованными аргументами `_arg1.._argN`, а у функции «человеческие» имена параметров | Каждый entry point в `ENDPOINTS` — адаптер с параметрами `_arg1.._argN`; не деплоить «читаемые» функции напрямую |
| `ValueError: horizon must be an integer >= 1` при запросе по REST | Константа пришла списком из одного элемента (`{"_arg3": [12]}`), как это делает REST-клиент | Функции разворачивают одноэлементный список (`_scalar`); при ручном `curl` можно слать и скаляр |

## 10. Проверено на живом сервере

Прогон 2026-10-25 на `tabpy==2.16.0` (Python 3.12, отдельный venv, порт 9104, парольная аутентификация включена):

| Что проверялось | Результат |
|---|---|
| Старт с `TABPY_PWD_FILE` | стартует; `/status` и `/info` без credentials → 401 |
| `deploy.py` без кредов | `[error] ... (401)` и exit code 1 |
| `deploy.py --override` с кредами | 6 endpoints, 0 failed |
| `GET /status` после деплоя | все 6 — `LoadSuccessful` |
| `POST /query/wilson_lower` | `[0.40383, 0.06567, null]` |
| `POST /query/ltv_at_horizon` | `[42.7497]` |
| `POST /query/ztest_two_proportions` | `[0.6758]` |
| `POST /query/retention_rate` | `[0.835]` |

`SCRIPT_*` внутри Tableau Desktop не прогонялись — проверена REST-поверхность, которой Tableau пользуется.

Источники: [TabPy server-config.md](https://github.com/tableau/TabPy/blob/master/docs/server-config.md), [Tableau: configure R and TabPy](https://help.tableau.com/current/server/en-us/config_r_tabpy.htm).
