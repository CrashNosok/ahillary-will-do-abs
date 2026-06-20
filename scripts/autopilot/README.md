# Trello Autopilot — ahillary-will-do-abs

Берёт следующую карточку из **📋 Backlog** доски `ahillary-will-do-abs MVP`, отдаёт её
headless-сессии Claude Code, которая прогоняет [`docs/review-playbook.md`](../../docs/review-playbook.md)
от начала до конца на свежей ветке, и по кругу. Карточки в Backlog уже идут в порядке
`S0.1 → S5.10`, поэтому обычный (не `--plan`) режим исполняет спринты сверху вниз.

Адаптировано из автопилота transit_gate. Изменено под этот проект: доска/списки, `REPO_ROOT`,
локальный playbook, стек (FastAPI + Vite вместо Next/pnpm), без живого Playwright по умолчанию,
и без push/PR (у репозитория нет GitHub remote).

## Цикл одной карточки

```
взять карточку → 🔵 In Progress (+коммент) → claude -p по плейбуку (ветка feat/…)
  → успех:  🟣 Code Review (+описание, сценарии, заметки, метрики)
  → провал: 🟠 Blocked     (+причина, путь к логу)
```

Карточки автопилот двигает сам; ревью и слияние ветки — за тобой (потом двигаешь в ✅ Done).

## Настройка (один раз)

```bash
cp scripts/autopilot/trello.autopilot.env.example scripts/autopilot/trello.autopilot.env
# впиши TRELLO_API_KEY / TRELLO_TOKEN (файл gitignored)
```

Нужны: `claude` CLI, `git`. Для режима `--done-mode pr` дополнительно — GitHub remote + `gh`.

## Запуск (из корня репозитория)

```bash
# Что бы он сделал — резолвит доску, выбирает следующую карточку, печатает план. Без Claude.
python3 scripts/autopilot/trello_autopilot.py --dry-run

# Ровно одна карточка и стоп (рекомендую для первого боевого прогона — последи).
python3 scripts/autopilot/trello_autopilot.py --once

# Весь Sprint 0 подряд (11 карточек), затем стоп.
python3 scripts/autopilot/trello_autopilot.py -n 11

# ВСЕ карточки подряд (S0.1 → S5.10), на ночь — собирает приложение целиком:
caffeinate -i python3 -u scripts/autopilot/trello_autopilot.py \
  --integrate-main --on-fail continue 2>&1 | tee -a scripts/autopilot/logs/console.log
```

`--integrate-main` обязателен для полного прогона: после каждой зелёной карточки её ветка
вливается (fast-forward) в `main`, чтобы следующие строились поверх. Без него каждая карточка
ответвляется от пустого `main` и зависимые падают. Провалы уходят в 🟠 Blocked и в `main` не
вливаются — разберёшь вручную.

## Дефолты этого проекта

| Параметр | Дефолт | Почему |
|---|---|---|
| `--pw-mode` | `light` | греонфилд: UI появляется не сразу, гейт = ruff/pytest/tsc/eslint |
| `--done-mode` | `commit` | у репо нет remote — коммит на ветке, ревью/мерж локально |
| источники | `📋 Backlog, 🟡 To Do` | карточки уже в порядке спринтов |

Остальные флаги (`--watch`, `--plan`, `--limit-wait`, `--model`, `--label …` и т.д.) — как в
исходном автопилоте; `python3 scripts/autopilot/trello_autopilot.py -h`.

## Безопасность

- Запускает Claude с `--dangerously-skip-permissions` в этом репозитории — держи направленным сюда.
- Плейбук запрещает коммит в `main`, требует минимальный диф и не мержит ветки.
- Креды Trello — только в gitignored `trello.autopilot.env`, не в коде.
