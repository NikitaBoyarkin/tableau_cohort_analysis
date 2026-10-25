# Calculated fields для когортного дашборда

Источник данных: `.hyper`-экстракт, таблица `cohort.cohort_export`.

Колонки (порядок фиксирован):

| Колонка | Тип | Смысл |
|---|---|---|
| `user_id` | int | идентификатор пользователя |
| `cohort_month` | date | первый день месяца входа |
| `cohort_label` | text | `%Y-%m` |
| `join_date` | date | дата регистрации |
| `period` | int | номер периода, 0 = месяц входа |
| `period_date` | date | дата периода |
| `is_active` | int 0/1 | активность в периоде |
| `revenue` | int | выручка в периоде |

Все поля ниже — синтаксис по документации Tableau. Прогон в живом Tableau Desktop не выполнялся.

---

## 1. Нативно vs TabPy

| Метрика | Где считать | Почему |
|---|---|---|
| Retention rate | Нативно | `SUM()/COUNT()` — одна агрегация, Tableau считает мгновенно и без сервера |
| Размер когорты | Нативно | `COUNTD([user_id])`, считается по LOD вьюхи |
| Кумулятивный LTV | Нативно | `RUNNING_SUM` / `WINDOW_SUM` по `period` |
| Средний чек | Нативно | `IF SUM([is_active]) = 0 THEN NULL ELSE SUM([revenue]) / SUM([is_active]) END` |
| Подпись периода | Нативно | конкатенация строки |
| Проверка «период наблюдён» | Нативно | `IF` по `[period]` |
| Прогноз кривой удержания | Только TabPy | подгонка степенной модели — не агрегация Tableau |
| Wilson CI (нижняя/верхняя граница) | Только TabPy | нужны корни и обратная нормальная функция |
| LTV на фиксированном горизонте | Только TabPy | достройка отсутствующих периодов регрессией + нормировка на размер когорты |
| Значимость различия двух когорт | Только TabPy | двусторонний z-тест двух пропорций |

Правило: если метрика выражается через `SUM`/`COUNT`/`COUNTD`/`MIN`/`MAX`/`AVG` и арифметику — делай нативно. TabPy добавляет сетевую задержку, точку отказа и ломает экстракт-производительность.

---

## 2. Соглашения перед вставкой

- `SCRIPT_*` — **table calculation**, не row-level. Агрегация задаётся LOD вьюхи, а не формулой. Аргументы — `SUM()`, `COUNT()`, `COUNTD()`, `AVG()`, `MIN()`, `ATTR()`, никогда сырые колонки.
- Результат обязан быть списком длиной = число строк, отправленных в TabPy, либо длиной 1. `None` внутри списка превращается в null в Tableau — это штатное поведение, не ошибка.
- Partitioning / Compute Using = граница вызова. Каждый pane — отдельный HTTP-запрос к серверу. Больше panes → больше задержка.
- Смешивать aggregate и non-aggregate поля в одном `SCRIPT_*` нельзя — ошибка Tableau, не TabPy. Параметры (`[Имя параметра]`) подставляются как константы и правилу не противоречат.
- Имя endpoint'а сверять с сервером: `curl -s http://localhost:9004/endpoints`.

---

## 3. Готовые calculated fields

### Поле 1. Retention rate (нативно)

```tableau
SUM([is_active]) / COUNT([user_id])
```

- Куда: Rows или Text.
- Compute Using: `cohort_label` по строкам, `period` по столбцам (или наоборот — как в вьюхе).
- Тип: агрегированное, format → Percentage, 1 знак.
- null: не возникает; если `COUNT([user_id]) = 0`, Tableau вернёт ошибку деления — фильтруй пустые когорты.

### Поле 2. Wilson lower bound 95% (TabPy)

```tableau
SCRIPT_REAL("return tabpy.query('wilson_lower', _arg1, _arg2)['response']", SUM([is_active]), COUNT([user_id]))
```

- Куда: Tooltip или второй ряд в Text рядом с retention rate.
- Compute Using: `cohort_label` (partition) × `period` (address).
- null: `None` в ответе = граница не посчитана (обычно `COUNT = 0`) → в Tableau null, полоса доверия в этом периоде не рисуется.
- Формат → Percentage.

### Поле 3. Wilson upper bound 95% (TabPy)

```tableau
SCRIPT_REAL("return tabpy.query('wilson_upper', _arg1, _arg2)['response']", SUM([is_active]), COUNT([user_id]))
```

- Куда: Tooltip или второй ряд.
- Compute Using: как у поля 2 — иначе полосы не совпадут по строкам.
- null: то же, что у нижней границы.

### Поле 4. Прогноз кривой удержания, степенная модель (TabPy)

```tableau
SCRIPT_REAL("return tabpy.query('retention_forecast', _arg1)['response']", AVG([is_active]))
```

- Куда: Rows (вторая ось, dual axis с фактическим retention).
- Compute Using: **только** `cohort_label` (partition), адресация — `period`. Тогда `_arg1` = вся кривая когорты по периодам, а не одна точка.
- `periods` не передаётся: модель берёт сетку `0..n-1` по порядку строк, что совпадает с `[period]` при адресации по `period`.
- Не добавляй `MIN([period])` вторым аргументом: при partitioning по `period` в каждый pane придёт одна точка, и подгонка вырождается (возврат входа как есть).
- null: `None` на периодах, которые модель не покрывает → линия обрывается, это ожидаемо.
- Оговорка: прогноз строится на агрегатах, отправленных в вызов; при мелком pane (мало точек) модель вырождается в плоскую линию.

### Поле 5. LTV на горизонте 12 периодов (TabPy)

```tableau
SCRIPT_REAL("return tabpy.query('ltv_at_horizon', _arg1, _arg2, _arg3)['response']", SUM([revenue]), COUNTD([user_id]), 12)
```

- Куда: Text (KPI-карточка) или Tooltip.
- Compute Using: `cohort_label` (partition), без `period` в address — LTV считается на когорту целиком, а не на строку периода.
- `_arg3` — константа горизонта, не поле: 12 периодов.
- null: `None` = экстраполяция невозможна (размер когорты 0, или наблюдён только один период — повторять выручку нулевого периода было бы завышением на порядок). KPI-карточка показывает null, не 0.
- Возврат длины 1 → Tableau размножит значение на все строки pane.

### Поле 6. Значимость различия двух когорт, двусторонний z-тест (TabPy)

```tableau
SCRIPT_REAL("return tabpy.query('ztest_two_proportions', _arg1, _arg2, _arg3, _arg4)['response']", SUM([is_active]), COUNT([user_id]), SUM([is_active]), COUNT([user_id]))
```

Поле в таком виде корректно **только** при разбиении вьюхи на две когорты.

- Куда: Text (или Tooltip на сравнительном листе).
- Compute Using: `cohort_label` — обязательно. При partitioning по `cohort_label` каждый pane содержит одну когорту, и два набора аргументов должны ссылаться на разные когорты.
- **Ограничение:** внутри одного pane `_arg1.._arg2` и `_arg3.._arg4` считаются по одной и той же когорте — тест вырождается, p ≈ 1. Формула выше — шаблон вызова, а не готовый сравнительный тест. Для честного сравнения нужны значения из двух разных pane.

#### Рабочий вариант: вынести пропорции в параметры

1. Создай параметры (Data pane → Create Parameter), тип Integer/Float:
   - `p_A_successes`, `p_A_trials`, `p_B_successes`, `p_B_trials` — целые.
2. Поле-заглушка для когорты A (на листе с фильтром на когорту A), Compute Using `cohort_label`:

```tableau
SCRIPT_INT("return tabpy.query('ztest_two_proportions', _arg1, _arg2, _arg3, _arg4)['response']", SUM([is_active]), COUNT([user_id]), [p_B_successes], [p_B_trials])
```

3. Симметричное поле для когорты B, Compute Using `cohort_label`:

```tableau
SCRIPT_INT("return tabpy.query('ztest_two_proportions', _arg1, _arg2, _arg3, _arg4)['response']", [p_A_successes], [p_A_trials], SUM([is_active]), COUNT([user_id]))
```

4. Значения в параметры переносишь вручную из листа с retention rate (или через «Parameter Actions»). Параметры — константы, поэтому не нарушают правило агрегации.
5. p-value читается с KPI-карточки; для отображения p ≤ 0.05 добавь поле:

```tableau
IF [p-value] <= 0.05 THEN "значимо" ELSE "не значимо" END
```

где `[p-value]` — сохранённое поле из шага 2/3.

- null: `None` при нулевых `trials` в любом из наборов → тест не определён.

### Поле 7. Подпись периода (нативно)

```tableau
'M' + STR([period])
```

- Куда: Columns (дискретная ось), перед `period` если нужна сортировка по номеру.
- Compute Using: не нужно, row-level (dimension).
- null: не возникает, `[period]` — int без пропусков.
- Сортировка: положи рядом `[period]` как скрытую дискретную ось и сортируй по ней, иначе `'M10'` встанет раньше `'M2'`.

### Поле 8. Проверка «период наблюдён» (нативно)

```tableau
IF [period] <= 11 THEN [is_active] END
```

- Куда: Rows как альтернатива `is_active` для среза «только наблюдаемые периоды».
- Compute Using: не нужно, row-level.
- null: `period > 11` → null, строка выпадает из агрегации. Это и есть цель поля.
- Горизонт 11 согласован с `ltv_at_horizon(..., 12)`; при смене горизонта правь оба места.

---

## 4. Проверка после вставки

| Симптом | Причина | Фикс |
|---|---|---|
| `Wrong number of rows` | длина ответа ≠ числу отправленных строк и ≠ 1 | endpoint вернул скаляр вместо списка, или pane-ы посчитаны по другой гранулярности. Привести возврат к `list` длины `len(_arg1)` в `tabpy_functions.py` |
| 500 `ndarray is not JSON serializable` | endpoint вернул numpy-массив/скаляр без конвертации | в endpoint'е `[float(x) for x in result]` или `result.tolist()` |
| 404 по endpoint'у | имя не совпадает с задеплоенным, сервер не перезапущен после `deploy.py` | сверить `curl -s http://localhost:9004/endpoints`, передеплоить, перезапустить |
| 401 | TabPy запущен с аутентификацией, а Tableau Desktop без логина/пароля | указать host/port и credentials в Tableau → Manage Analytics Extensions, либо запустить сервер без auth для локальной работы |
| Timeout | слишком много pane'ов (Compute Using задан по двум измерениям с большой кардинальностью) | сузить partitioning до `cohort_label`, агрегировать заранее, либо перенести расчёт в нативное поле |
| Пустой столбец вместо чисел | `None` в ответе или null в одном из аргументов (`COUNT = 0`) | отфильтровать пустые когорты, проверить, что аргументы — агрегаты, а не сырые колонки |

---

## 5. Порядок применения

1. Поднять TabPy на `localhost:9004` (порт сверять с настройкой Tableau Desktop).
2. Задеплоить endpoint'ы: `tabpy/deploy.py` (в проекте `tabpy_functions.py` — источник функций).
3. Проверить, что сервер видит функции: `curl -s http://localhost:9004/endpoints`.
4. В Tableau Desktop: Help → Settings and Performance → Manage Analytics Extensions → Connection: `localhost`, порт `9004`.
5. Подключить экстракт `tableau/cohort_extract.hyper`, таблица `cohort.cohort_export`.
6. Вставить поля из раздела 3 (Analysis → Create Calculated Field).
7. Для каждого `SCRIPT_*` задать Compute Using: `cohort_label` (partition) × `period` (address). Поле 5 — только по `cohort_label`.
8. Проверить null'ы: пустые ячейки у Wilson-границ и LTV — ожидаемы при нулевом размере когорты; сплошные null по всему листу — ошибка вызова, смотреть раздел 4.

Установка сервера и деплой: `docs/tabpy-setup.md`.
