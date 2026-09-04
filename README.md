# Когортный анализ удержания и LTV

Когортный анализ на синтетических данных: удержание пользователей, кривые
оттока и выручка/LTV по когортам прихода. Пайплайн на Python (pandas +
matplotlib/seaborn) плюс выгрузка, готовая к загрузке в **Tableau**.

> Данные синтетические — сгенерированы детерминированно (`seed=42`),
> воспроизводятся из кода. Бизнес-сценабий: monthly-активность нового юзера
> с момента регистрации.

## Модель данных

Одна строка — один «пользователь × месяц наблюдения»:

| Поле          | Тип      | Описание                                              |
|---------------|----------|-------------------------------------------------------|
| `user_id`     | int      | идентификатор пользователя                            |
| `cohort_month`| date     | месяц прихода (ключ когорты, выводится из `join_date`)|
| `join_date`   | date     | дата регистрации (первое число месяца)               |
| `period`      | int      | месяцев с прихода (0 = месяц регистрации)             |
| `is_active`   | int 0/1  | активен ли пользователь в этом месяце                 |
| `revenue`     | int      | выручка за месяц (0, если не активен)                 |

`cohort_month` выводится из `join_date` (а не отдельным случайным полем),
как в реальном продакшене. Младшие когорты наблюдались меньше месяцев —
матрица удержания треугольная.

## Методология

- **Период 0 = 100 % удержания по определению.** Все активны в месяц прихода.
  Кривая убывает с периода 1: `retention(p) = 0.85 · 0.75^(p-1)`.
- **Выручка:** активный месяц → `Poisson(λ=10)`; неактивный → 0.
- **Размеры когорт:** число уникальных `user_id` в `period == 0`.
- **ARPU** = средняя выручка на user-period; **LTV** = суммарная выручка
  когорты / размер когорты.

## Метрики

| Метрика | Где | Что показывает |
|---|---|---|
| Размер когорты | `cohort_sizes()` | приток пользователей по месяцам |
| Матрица удержания | `retention_matrix()` | % активных, когорта × период |
| Кривые удержания | `retention_matrix()` (линиями) | скорость оттока |
| Выручка / ARPU / LTV | `revenue_by_cohort()` | монетизация по когортам |

## Запуск

Требуется `uv` и Python ≥ 3.10.

```bash
uv sync --all-groups               # зависимости (+ dev: jupyter/ipykernel/nbformat)
uv run python cohort_analysis.py   # текстовый summary метрик
uv run jupyter notebook            # открыть tableau_cohort_analysis.ipynb
```

Перегенерировать ноутбук с выводами:

```bash
uv run python -m ipykernel install --sys-prefix --name cohort-py   # один раз
uv run jupyter nbconvert --to notebook --execute --inplace \
    --ExecutePreprocessor.kernel_name=cohort-py tableau_cohort_analysis.ipynb
```

## Tableau

```bash
uv run python tableau_export.py
```

Создаёт в `tableau/`:

- `cohort_export.csv` — плоская таблица, идеальный shape для Tableau
  (доб. `cohort_label` и `period_date` — календарный месяц наблюдения);
- `cohort_extract.hyper` — Tableau Hyper-экстракт (через официальный
  Tableau Hyper API). Загружается через *Connect to Data → Tableau Extract*.

**Как построить когортный heatmap в Tableau:** Columns = `period`,
Rows = `cohort_label` (или `cohort_month`), Marks = Square, Color = AVG(`is_active`),
Text = `% of Total` по строке. Либо `period_date` на Columns для календарной оси.

## Tableau Public: дашборд и публикация

Сборка 4-вью дашборда в Tableau Public Desktop и публикация по публичной ссылке.

**0. Подготовка данных**

```bash
uv run python tableau_export.py    # обновить tableau/cohort_extract.hyper
open tableau/cohort_extract.hyper  # открыть Tableau Public Desktop с данными
```

**1. Подключение данных**

- Tableau Public Desktop → *Connect to Data → Tableau Extract* → выбрать
  `tableau/cohort_extract.hyper`. Либо открыть `.hyper` двойным кликом.

**2. Четыре вью (листы)**

| Лист | Тип | Поля |
|---|---|---|
| Retention heatmap | Square | Columns = `period`, Rows = `cohort_label`, Color = AVG(`is_active`), Text = `% of Total` (по строке) |
| Cohort sizes | Bar | Columns = `cohort_label`, Rows = COUNTD(`user_id`), Filter = `period` = 0 |
| Retention curves | Line | Columns = `period`, Rows = AVG(`is_active`), Color = `cohort_label` |
| LTV | Bar | Columns = `cohort_label`, Rows = SUM(`revenue`) / COUNTD(`user_id`) |

**3. Дашборд**

- New Dashboard → 4 листа тайлами (heatmap крупнее, остальные в ряд).
- Заголовок «Cohort Retention & LTV»; опционально фильтр по `cohort_label`.

**4. Публикация**

- *File → Save to Tableau Public* → вход в аккаунт (бесплатно) → Publish.
- Ссылка вида `https://public.tableau.com/views/<name>/...` — вставить в README.

## Структура проекта

```
tableau_cohort_analysis/
├── cohort_analysis.py            # генерация данных + функции метрик (+ CLI summary)
├── tableau_export.py             # Tableau-выгрузка: CSV + .hyper extract
├── tableau_cohort_analysis.ipynb # нарратив: генерация → метрики → viz → выводы
├── cohort_data.csv                # плоский датасет (выход ноутбука)
├── tableau/                       # артефакты выгрузки (CSV + .hyper)
├── images/                        # скриншоты для README
├── pyproject.toml                 # зависимости + ruff
└── README.md
```

## Что было улучшено

| До | После |
|----|-------|
| README — только заголовок | полная документация: модель, методология, запуск, Tableau |
| Ноутбук — 1 гигант-ячейка без текста | 14 ячеек: markdown-нарратив + изолированные шаги |
| `cohort` — отдельное случайное поле, дублировало `join_date` | `cohort_month` выводится из `join_date` |
| Удержание в period 0 = 80 % (некорректно) | period 0 = 100 % по конвенции |
| Heatmap рендерил `nan%` в пустых ячейках | NaN замаскированы |
| Только retention-heatmap | + размеры когорт, кривые удержания, ARPU/LTV |
| Нет Tableau (несмотря на название) | CSV + Hyper-экстракт, инструкция по сборке view |
| Не воспроизводимо | `uv` + `pyproject.toml` + `.python-version` |

## Ограничения

- Данные синтетические — паттерны удержания заданы формулой, не выведены
  из реального поведения.
- LTV младших когорт занижен из-за короткой истории наблюдения; сравнивать
  LTV корректно только при равном «возрасте» когорты.
- `.hyper`-экстракт генерируется локально; для публикации на Tableau Server
  / Cloud нужен Tableau Server Client Library (`tableau-server-client`) —
  не входит в scope.