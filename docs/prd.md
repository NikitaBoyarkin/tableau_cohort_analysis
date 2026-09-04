# PRD: Tableau Cohort Analysis

**Автор:** NikitaBoyarkin
**Дата:** 2026-09-04
**Статус:** Draft
**Версия:** 1.0

---

## 1. Executive Summary

Портфельный кейс по когортному анализу удержания и LTV: полностью воспроизводимый Python-пайплайн (pandas + matplotlib/seaborn) на детерминированных синтетических данных плюс выгрузка, готовая к загрузке в Tableau (CSV + Hyper-экстракт). Текущее состояние реализовано и верифицировано; документ фиксирует его как спеку (retro) и описывает road-map: подключение реальных данных (CSV), публикация на Tableau Public, автоматизация и готовый workbook.

## 2. Problem Statement

### Текущая ситуация
Реальные pet-проекты по когортному анализу часто недоведены: синтетика недетерминированная, метрики считаются вручную, «Tableau» присутствует только в названии. В кейсе до улучшений удержание в period 0 составляло 80 % (методологическая ошибка), а `cohort_month` дублировал `join_date` случайным полем.

### Влияние на пользователя
- **Кто затронут:** рекрутер/интервьюер на роль Data/BI-аналитика; сам автор (аналитик).
- **Как затронут:** недовоспроизводимый кейс размывает демонстрацию навыка; некорректная методология (period 0 ≠ 100 %) — красный флаг на интервью.
- **Серьёзность:** High для портфолио-цели — методологическая ошибка в retention-метриках дискредитирует весь кейс.

### Бизнес-влияние
- **Стоимость проблемы:** упущенные офферы/прохождение интервью при слабом кейсе.
- **Стратегическая важность:** когортный анализ — базовая компетенция product/data-аналитика; отработанный пайплайн переиспользуется на других проектах.

### Почему решать сейчас
Кейс уже выбран как элемент портфолио (README, ноутбук, Tableau-артефакты). Формальный PRD позволяет (а) задокументировать требования/метрики, (б) превратить «сделанный скрипт» в story для интервью, (в) спланировать расширения без потери качества.

## 3. Goals & Success Metrics

### Goal 1: Воспроизводимость пайплайна
- **Описание:** от пустого окружения до Tableau-артефактов — минимальное число ручных шагов.
- **Метрика:** число команд до `cohort_extract.hyper` и время выполнения.
- **Baseline:** 2 команды (`uv sync --all-groups` → `uv run python tableau_export.py`), < 2 мин.
- **Target:** ≤ 2 команды, ≤ 2 мин (сохраняется).
- **Срок:** достигнуто (2026-08).
- **Метод измерения:** ручной прогон команд на чистом клоне; CI-проверка не требуется.

### Goal 2: Методологическая корректность retention/LTV
- **Описание:** метрики соответствуют канону когортного анализа.
- **Метрика:** retention(period 0) = 100 % по определению; детерминированность при `seed=42` (повторный запуск → идентичный датасет).
- **Baseline:** период 0 = 80 % (до фикса).
- **Target:** период 0 = 100 % (реализовано); повторный запуск даёт идентичный `df` (проверяется `df.equals`).
- **Срок:** достигнуто (2026-08).
- **Метод измерения:** `print_summary` из `cohort_analysis.py`; unit-проверка детерминизма.

### Goal 3: Tableau-publication (road-map)
- **Описание:** дашборд доступен по публичной ссылке (Tableau Public).
- **Метрика:** наличие опубликованного workbook.
- **Baseline:** нет публичной ссылки; только локальные `cohort_export.csv` + `.hyper`.
- **Target:** опубликован ≥ 1 дашборд (retention heatmap + LTV), ссылка в README.
- **Срок:** после Phase 2.
- **Метод измерения:** открываемый URL.

## 4. User Stories

### Story 1: Демонстрация компетенции (портфолио)
**As a** hiring-manager/nterviewer, **I want to** увидеть когортное удержание и LTV с чистыми viz в Tableau, **So that I can** оценить data-storytelling и методологию кандидата.

**Acceptance Criteria:**
- [ ] README объясняет модель данных и методологию за < 3 мин чтения
- [ ] `uv run python cohort_analysis.py` выводит retention-матрицу и LTV без ошибок
- [ ] Tableau-артефакт (`.hyper` или CSV) загружается и строится heatmap по инструкции

**Dependencies:** REQ-001, REQ-002, REQ-003, REQ-004

### Story 2: Быстрый переиспользуемый пайплайн
**As a** автор (data-analyst), **I want to** переносить пайплайн на новые данные без переписывания метрик, **So that I can** считать когорты регулярно.

**Acceptance Criteria:**
- [ ] Метрическая модель (retention/LTV/ARPU) не зависит от источника данных
- [ ] Смена источника (синтетика → CSV) меняет один адаптер, не трогая метрики
- [ ] Schema export-фрейма стабильна (имена/типы колонок фиксированы)

**Dependencies:** REQ-010 (road-map)

### Story 3: Self-serve дашборд (road-map)
**As a** стейкхолдер, **I want to** смотреть когортное удержание без запуска скриптов, **So that I can** отслеживать динамику когорт ежемесячно.

**Acceptance Criteria:**
- [ ] Дашборд обновляется по расписанию без ручного запуска
- [ ] Вью соответствуют README: heatmap, размеры когорт, кривые, LTV
- [ ] Ссылка/URL стабильная для шаринга

**Dependencies:** REQ-020, REQ-021 (road-map)

## 5. Functional Requirements

### Must Have (P0) — реализовано

#### REQ-001: Детерминированная генерация синтетических когортных данных
**Описание:** `generate_data()` создаёт строку «пользователь × месяц наблюдения» с триангулярной матрицей (младшие когорты наблюдаются меньше месяцев).

**Acceptance Criteria:**
- [ ] `seed=42` → повторный вызов возвращает идентичный `pd.DataFrame` (`df.equals` == True)
- [ ] `cohort_month` выводится из `join_date` (DateOffset по месяцам), а не отдельным случайным полем
- [ ] Число периодов у когорты = `min(max_periods, num_cohorts - cohort_index)` (треугольная матрица)
- [ ] Параметры конфигурируемы через `DataConfig` (num_users, num_cohorts, base_retention, decay, revenue_lambda)

**Техническая спецификация:**
```python
cfg = DataConfig(num_users=1000, num_cohorts=10, seed=42)
df = generate_data(cfg)  # 1000 users, треугольная история, 6 колонок
```

**Dependencies:** None

#### REQ-002: Расчёт метрик удержания
**Описание:** размеры когорт, retention-матрица (когорта × период) и blended-кривая удержания.

**Acceptance Criteria:**
- [ ] `cohort_sizes()` возвращает число уникальных `user_id` по когорте, считая только `period == 0`
- [ ] `retention_matrix()` — период 0 равен 1.0 (100 %) по определению
- [ ] NaN-ячейки (когорта ещё не наблюдалась) остаются NaN и маскируются в viz
- [ ] `retention_curves()` — среднее по когортам на период (blended)

**Dependencies:** REQ-001

#### REQ-003: Расчёт монетизации
**Описание:** общая выручка, ARPU и LTV по когортам кумулятивно по всей наблюдаемой истории.

**Acceptance Criteria:**
- [ ] `revenue_by_cohort()` возвращает `users`, `total_revenue`, `arpu`, `ltv` на когорту
- [ ] ARPU = `revenue.mean()`; LTV = `total_revenue / users`
- [ ] Сравнение LTV корректно только для когорт одинакового «возраста» (задокументировано)
- [ ] Выручка неактивного месяца = 0 (реализовано в данных)

**Dependencies:** REQ-001

#### REQ-004: Tableau-выгрузка CSV + .hyper
**Описание:** `tableau_export.py` создаёт плоский export-фрейм и пишет `cohort_export.csv` + `cohort_extract.hyper` (Tableau Hyper API).

**Acceptance Criteria:**
- [ ] CSV содержит 8 колонок со стабильными именами: `user_id, cohort_month, cohort_label, join_date, period, period_date, is_active, revenue`
- [ ] `cohort_label` — строка `%Y-%m`; `period_date` — фактический календарный месяц наблюдения
- [ ] `.hyper` строится через официальный `tableauhyperapi` и открывается через «Connect to Data → Tableau Extract»
- [ ] При отсутствии `tableauhyperapi` скрипт graceful-degradation: CSV пишется, `.hyper` пропускается с сообщением `[skip]`

**Dependencies:** REQ-001

#### REQ-005: Визуализация метрик в ноутбуке
**Описание:** `tableau_cohort_analysis.ipynb` — 14 ячеек (markdown-нарратив + изолированные шаги): retention heatmap, кривые удержания, размеры когорт, ARPU/LTV.

**Acceptance Criteria:**
- [ ] Heatmap не рендерит `nan%` в пустых ячейках (NaN замаскированы)
- [ ] Ноутбук исполняем: `nbconvert --execute --kernl_name=cohort-py` проходит end-to-end
- [ ] Каждый график снабжён выводом-интерпретацией в markdown

**Dependencies:** REQ-001, REQ-002, REQ-003

#### REQ-006: Воспроизводимость и документация
**Описание:** среда фиксируется `pyproject.toml` + `.python-version` (Python ≥ 3.10, uv); README описывает модель, методологию, запуск и сборку Tableau-вью.

**Acceptance Criteria:**
- [ ] `uv sync --all-groups` из чистого клона восстанавливает окружение
- [ ] README содержит: модель данных, методологию, метрики, команды запуска, структуру проекта, ограничения
- [ ] В README документировано, что данные синтетические и LTV младших когорт занижен

**Dependencies:** None

### Should Have (P1) — road-map, Phase 1–2

#### REQ-010: Адаптер реального источника данных
**Описание:** источник данных выносится за `generate_data()`: чтение CSV в тот же `user_id × period`-формат, метрическая модель не меняется.

**Acceptance Criteria:**
- [ ] Функция-адаптер `load_real_data(path) -> pd.DataFrame` возвращает контракт REQ-001 (6 колонок)
- [ ] `cohort_sizes/retention_matrix/revenue_by_cohort` работают без изменений на реальных данных
- [ ] PII-поля отсутствуют или scrub'атся (GDPR)
- [ ] Документировано требование: период 0 = 100 % только если это месяц регистрации, иначе определение уточняется

**Dependencies:** REQ-001, REQ-002, REQ-003

#### REQ-011: Публикация на Tableau Public
**Описание:** workbook с вью из README публикуется на Tableau Public (Save to Tableau Public из Desktop либо Public REST API); данные встроены в workbook.

**Acceptance Criteria:**
- [ ] Workbook публикуется на Tableau Public и открывается по публичной ссылке
- [ ] Вью из README (heatmap, размеры, кривые, LTV) присутствуют в опубликованном дашборде
- [ ] Данные встроены в workbook (embedded .hyper/CSV) — дашборд не зависит от локальных файлов
- [ ] Учётные данные Tableau Public не хранятся в коде (Desktop-сессия / env)
- [ ] README дополнен ссылкой на опубликованный дашборд

**Dependencies:** REQ-004; внешний сервис (бесплатный Tableau Public, данные публичны)

### Nice to Have (P2) — road-map, Phase 3

#### REQ-020: Автоматизация регенерации отчётов
**Описание:** генерация данных → расчёт метрик → export → публикация по расписанию (scheduler/GitHub Actions).

**Acceptance Criteria:**
- [ ] Job запускается по cron без ручных шагов
- [ ] При ошибке любого шага пайплайн останавливается с понятным логом, дашборд не частично обновляется
- [ ] Артефакты версионируются (дата в имени/метке)

**Dependencies:** REQ-010, REQ-011

#### REQ-021: Готовый workbook-дашборд
**Описание:** workbook с каноническими вью и параметрами (переключатель когорт/периодов), данные из .hyper/CSV.

**Acceptance Criteria:**
- [ ] Workbook открывается в Tableau Desktop/Public с подключением к .hyper/CSV
- [ ] Минимум 4 вью: heatmap удержания, размеры когорт, кривые удержания, LTV
- [ ] Параметры дашборда (порог периодов, диапазон когорт) изменяются в UI Tableau
- [ ] Workbook публикуется на Tableau Public (связка с REQ-011)

**Dependencies:** REQ-004, REQ-010, REQ-011

## 6. Non-Functional Requirements

### Performance
- Генерация 1000 users × 10 когорт × ≤12 периодов: < 5 с
- Export (CSV + .hyper): < 10 с
- Размер данных: < 10 MB (память < 500 MB)

### Security
- Политика данных: синтетика, PII отсутствует по определению
- При подключении реальных данных (REQ-010): PII scrub, секреты только через env
- Compliance: GDPR-совместимый подход к пользовательским данным

### Scalability
- Конфигурируемое число users/когорт через `DataConfig` (без оверхеда до ~100k rows)
- Векторизованные операции на `datetime64[M]` (без per-row DateOffset для export)

### Reliability
- Детерминизм: `seed=42` ⇒ идентичный датасет
- Методология: retention периода 0 = 1.0; NaN маскируются
- Graceful degradation: отсутствие `tableauhyperapi` не ломает CSV-ветку
- Версионирование окружения: `uv.lock` + `pyproject.toml`

## 7. Technical Considerations

### Архитектура
```
pyproject.toml (.venv, uv)
      │
      ▼
cohort_analysis.py ──► generate_data() ──► метрики (sizes/retention/revenue)
      │                                              │
      ▼                                              ▼
tableau_export.py                           tableau_cohort_analysis.ipynb
      │                                    (heatmap + кривые + выводы)
      ▼
tableau/cohort_export.csv ──► Tableau Desktop/Cloud (heatmap, LTV)
tableau/cohort_extract.hyper
```

### Технологический стек
- **Backend (аналитика):** Python ≥ 3.10, pandas ≥ 2.0, numpy, matplotlib, seaborn
- **Data:** синтетика (seed=42); road-map — CSV/Postgres (REQ-010)
- **Export:** tableauhyperapi (Hyper Extract); road-map — публикация на Tableau Public (REQ-011)
- **Infrastructure:** uv + pyproject.toml + .python-version; road-map — GitHub Actions scheduler (REQ-020)
- **Notebook:** jupyter + ipykernel (kernel_name=cohort-py)

### Внешние зависимости
1. **Tableau Hyper API (`tableauhyperapi`):** сборка `.hyper`. Rate limit — нет (локально). Fallback: только CSV (уже реализован).
2. **Tableau Public (road-map):** публикация workbook с встроенными данными. Бесплатно, данные публичны. Публикация через Desktop «Save to Tableau Public» или Public REST API.

### Миграция
N/A — standalone-проект (не существующая продакшн-система). Для road-map: расширение пайплайна обратимо (адаптер не трогает метрики).

### Тестирование
- Unit: `cohort_analysis.py` — детерминизм, период 0 = 1.0, треугольность (добавить `tests/`)
- Integration: полный прогон `cohort_analysis.py` + `tableau_export.py` end-to-end
- Manual: загрузка `.hyper`/CSV в Tableau и сборка heatmap по инструкции README

## 8. Implementation Roadmap

### Phase 0: Foundation (DONE — 2026-08)
**Goal:** верифицированный текущий scope.
**Tasks:**
- [x] Data-генерация + метрики (REQ-001, REQ-002, REQ-003)
- [x] Tableau export CSV + .hyper (REQ-004)
- [x] Ноутбук-нарратив (REQ-005)
- [x] uv-среда + README (REQ-006)
**Validation Checkpoint:** `uv run python cohort_analysis.py` и `uv run python tableau_export.py` проходят; heatmap собирается в Tableau. ✅

### Phase 1: Real Data Adapter (week 1–2)
**Goal:** пайплайн работает на реальном источнике.
**Tasks:**
- [ ] Task 1.1: функция `load_real_data()` + контракт 6 колонок (REQ-010) — Medium (6h)
- [ ] Task 1.2: PII-scrub и валидация формата (REQ-010) — Medium (4h)
- [ ] Task 1.3: unit-тесты на детерминизм и период 0 — Medium (4h)
**Validation Checkpoint:** реальный CSV → та же retention-матрица и LTV; метрики без изменений.

### Phase 2: Tableau Public Publish (week 3–4)
**Goal:** дашборд доступен по публичной ссылке.
**Tasks:**
- [ ] Task 2.1: сборка workbook с вью из README + встраивание данных (REQ-011) — Medium (6h)
- [ ] Task 2.2: публикация на Tableau Public, документирование URL в README (REQ-011) — Small (2h)
**Validation Checkpoint:** публичная ссылка открывается, вью соответствуют README.

### Phase 3: Automation & Dashboard Package (week 5–6)
**Goal:** self-serve дашборд с автообновлением.
**Tasks:**
- [ ] Task 3.1: scheduler/job регенерации (REQ-020) — Large (10h)
- [ ] Task 3.2: workbook-дашборд с параметрами (REQ-021) — Medium (8h)
**Validation Checkpoint:** дашборд обновляется по расписанию; .twbx открывается автономно.

### Зависимости задач
```
Phase 0 (done) → Phase 1 → Phase 2 → Phase 3
Critical Path: REQ-010 → REQ-011 → REQ-020
```

### Оценка усилий
- Phase 1: ~14h
- Phase 2: ~8h
- Phase 3: ~18h
- **Итого:** ~40h (~2 недели соло)
- **Риск-буфер:** +20%

## 9. Out of Scope

1. **Real-time / стриминг когорт** — пайплайн batch-only; стриминг требует другой архитектуры.
2. **Многопользовательский BI-портал** — публикация одного дашборда, не полноценная BI-платформа.
3. **Мобильные/узкие вью** — дашборд desktop-first.
4. **A/B-тесты и эксперименты с retention** — вне контура данного кейса.

## 10. Open Questions & Risks

### Open Questions
#### Q1: Целевая платформа публикации
- **Статус:** resolved (2026-09-04)
- **Решение:** (A) Tableau Public — бесплатно, публично
- **Влияние:** REQ-011 переписан под Tableau Public

#### Q2: Источник реальных данных
- **Статус:** resolved (2026-09-04)
- **Решение:** (A) CSV-экспорт
- **Влияние:** REQ-010 — адаптер `load_real_data(path)` для CSV

#### Q3: Формат дашборда
- **Статус:** resolved (2026-09-04)
- **Решение:** (A) отдельный workbook
- **Влияние:** REQ-021 — workbook, не .twbx

### Risks & Mitigation

| Риск | Вероятность | Влияние | Severity | Митигация | Контингенция |
|------|-------------|---------|----------|-----------|--------------|
| Tableau Public: данные публичны, лимиты (10 GB, 1.5M rows) | Medium | Medium | Medium | Синтетика/обезличенные данные; проверка перед публикацией | Держать локальные CSV/.hyper + инструкцию |
| Смена API Tableau Hyper/Server ломает export | Medium | Medium | Medium | Пин версий в uv.lock; CI-прогон export | Вернуться к CSV-only ветке |
| Реальные данные «грязные» (пропуски, дубли) | High | Medium | **High** | Валидация формата в адаптере (REQ-010) | Документированные ограничения входных данных |
| LTV младших когорт занижен из-за короткой истории | High | Low | Medium | Сравнение только равных «возрастов» (уже в README) | Фильтр «возраст когорты» в дашборде |

## 11. Validation Checkpoints

### Checkpoint 1: Конец Phase 1
**Критерии:**
- [ ] Реальный CSV проходит через `load_real_data()` без ручной правки
- [ ] `retention_matrix`/`revenue_by_cohort` дают те же типы выходов, что на синтетике
- [ ] `uv run pytest` зелёный (детерминизм, период 0 = 1.0)
**Если провален:** уточнить контракт данных; скорректировать адаптер.

### Checkpoint 2: Конец Phase 2
**Критерии:**
- [ ] Публичная ссылка Tableau Public открывается в браузере
- [ ] На дашборде видны heatmap, размеры когорт, кривые удержания, LTV
- [ ] README содержит актуальный URL
**Если провален:** проверить аккаунт/права Tableau Public; пересобрать workbook.

### Checkpoint 3: Конец Phase 3
**Критерии:**
- [ ] Автообновление срабатывает по расписанию (нет ручных шагов)
- [ ] .twbx открывается автономно (данные в пакете)
- [ ] Падение любого шага логируется и не публикует частичный дашборд
**Если провален:** диагностировать шаг; добавить ретраи/алерты.

---

**Конец PRD**

*Статус текущего scope: Verified (Phase 0 done, прогон команд + верификация в README). Road-map фазы — Inferred, требуют реализации.*
