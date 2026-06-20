#!/usr/bin/env python3
"""TransitGate Trello Autopilot.

Watches the Trello board, picks the next actionable card, hands it to a headless
Claude Code session that runs the code-review playbook (docs/review-playbook.md)
end to end, then moves the card to "Code Review" and opens a PR. Repeats.

This automates the board's own documented dev loop:
    pick card -> "In Progress" (+comment) -> git push -> "Code Review" (+PR link)
    blocked   -> "Blocked"

Credentials are read from ~/transitgate-secrets/.env (TRELLO_API_KEY, TRELLO_TOKEN),
the same file create_trello_board.py uses. Board/list names default to the live
"TransitGate MVP — Week 1" board and can be overridden via env vars, a config file,
or CLI flags (precedence: CLI > env > config file > built-in default).

Usage:
    python3 app/scripts/autopilot/trello_autopilot.py --dry-run     # plan only, no Claude, no card moves
    python3 app/scripts/autopilot/trello_autopilot.py --once        # one card, then stop
    python3 app/scripts/autopilot/trello_autopilot.py               # loop until source lists are empty
    python3 app/scripts/autopilot/trello_autopilot.py --watch       # keep polling when empty

Stdlib only (urllib + subprocess). Python 3.10+.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.trello.com/1"
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]  # scripts/autopilot -> repo root
LOG_DIR = SCRIPT_DIR / "logs"
PLAYBOOK_PATH = REPO_ROOT / "docs" / "review-playbook.md"
INFLIGHT_PATH = LOG_DIR / ".inflight.json"  # marker for the card currently being worked (crash recovery)
QUEUE_PATH = LOG_DIR / "queue.json"  # planned execution queue (built by --plan)
# Local gitignored creds/config file next to this script (TRELLO_API_KEY / TRELLO_TOKEN).
DEFAULT_CREDS_FILE = SCRIPT_DIR / "trello.autopilot.env"
SENTINEL_RE = re.compile(r"^AUTOPILOT_RESULT:\s*(SUCCESS|FAILED)\s*(.*)$")
# Delimited blocks the agent emits in its final message; we post them as card comments.
DELIVERABLE_BLOCKS = ("EXPLANATION", "SCENARIOS", "NOTES")
TRELLO_COMMENT_LIMIT = 16384  # Trello hard cap per comment
NOTES_EMPTY = {"", "нет", "нет.", "none", "-", "(нет)", "(пусто)", "n/a", "—"}

# --- Built-in defaults for the ahillary-will-do-abs board --------------------
DEFAULTS: dict[str, str] = {
    "TRELLO_BOARD_NAME": "ahillary-will-do-abs MVP",
    "TRELLO_BOARD_ID": "O1qQWGbJ",  # shortLink; wins over board name (no members/me/boards call)
    # Lists scanned for the next card, in priority order. Cards in 📋 Backlog are already
    # ordered S0.1 -> S5.10, so plain sequential mode processes sprints top-down correctly.
    "TRELLO_SOURCE_LISTS": ",".join(
        [
            "📋 Backlog",
            "🟡 To Do",
        ]
    ),
    "TRELLO_DOING_LIST": "🔵 In Progress",
    # Personal single-user project: autopilot output goes to the normal review column.
    "TRELLO_REVIEW_LIST": "🟣 Code Review",
    "TRELLO_BLOCKED_LIST": "🟠 Blocked",
    # Only pick cards carrying this label (by name). Empty = no label filter.
    "TRELLO_PICKUP_LABEL": "",
    # Local dev ports for this project (Vite frontend / FastAPI backend).
    "WEB_BASE_URL": "http://localhost:5173",
    "API_HEALTH_URL": "http://localhost:8000/health",
    "CLAUDE_MODEL": "opus",
    "CLAUDE_MAX_TURNS": "300",
    "TASK_TIMEOUT_SECONDS": "5400",
}


# --- Errors ------------------------------------------------------------------
class TrelloError(RuntimeError):
    pass


# --- Config ------------------------------------------------------------------
def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a simple KEY=VALUE .env file. Ignores blanks, comments, `export `."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        val = val.strip().strip('"').strip("'")
        out[key.strip()] = val
    return out


@dataclass
class Config:
    file_values: dict[str, str] = field(default_factory=dict)
    cli_overrides: dict[str, str] = field(default_factory=dict)

    def get(self, key: str, default: str | None = None) -> str:
        # Precedence: CLI > process env > config file > built-in default > caller default
        if key in self.cli_overrides and self.cli_overrides[key] is not None:
            return self.cli_overrides[key]
        if os.environ.get(key):
            return os.environ[key]
        if self.file_values.get(key):
            return self.file_values[key]
        if key in DEFAULTS and DEFAULTS[key]:
            return DEFAULTS[key]
        return default if default is not None else ""

    def list(self, key: str) -> list[str]:
        return [p.strip() for p in self.get(key).split(",") if p.strip()]


def load_config(config_path: str | None, cli_overrides: dict[str, str]) -> Config:
    # Merge the dedicated config file (if any) over the shared creds file.
    merged: dict[str, str] = {}
    merged.update(parse_env_file(DEFAULT_CREDS_FILE))
    if config_path:
        p = Path(config_path).expanduser()
        if not p.is_file():
            sys.exit(f"Config file not found: {p}")
        merged.update(parse_env_file(p))
    return Config(file_values=merged, cli_overrides={k: v for k, v in cli_overrides.items() if v is not None})


# --- Trello client -----------------------------------------------------------
def trello(cfg: Config, method: str, path: str, params: dict | None = None) -> object:
    key = cfg.get("TRELLO_API_KEY")
    token = cfg.get("TRELLO_TOKEN")
    if not key or not token:
        sys.exit(f"Missing TRELLO_API_KEY / TRELLO_TOKEN (looked in {DEFAULT_CREDS_FILE}, env, config).")
    auth = {"key": key, "token": token}
    params = params or {}
    if method == "GET":
        url = f"{API}{path}?{urllib.parse.urlencode({**auth, **params})}"
        data = None
    else:
        url = f"{API}{path}?{urllib.parse.urlencode(auth)}"
        data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise TrelloError(f"Trello {method} {path} -> HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise TrelloError(f"Trello {method} {path} -> network error: {e.reason}") from e


def resolve_board(cfg: Config) -> dict:
    board_id = cfg.get("TRELLO_BOARD_ID")
    if board_id:
        b = trello(cfg, "GET", f"/boards/{board_id}", {"fields": "id,name"})
        return b  # type: ignore[return-value]
    name = cfg.get("TRELLO_BOARD_NAME")
    boards = trello(cfg, "GET", "/members/me/boards", {"fields": "id,name,closed"})
    matches = [b for b in boards if b.get("name") == name and not b.get("closed")]  # type: ignore[union-attr]
    if not matches:
        names = ", ".join(repr(b["name"]) for b in boards if not b.get("closed"))  # type: ignore[union-attr]
        raise TrelloError(f"Board {name!r} not found. Open boards: {names}")
    return matches[0]


def board_lists(cfg: Config, board_id: str) -> dict[str, str]:
    lists = trello(cfg, "GET", f"/boards/{board_id}/lists", {"fields": "id,name"})
    return {lst["name"]: lst["id"] for lst in lists}  # type: ignore[union-attr]


def list_cards(cfg: Config, list_id: str) -> list[dict]:
    cards = trello(
        cfg, "GET", f"/lists/{list_id}/cards", {"fields": "id,name,desc,shortUrl,idShort,labels"}
    )
    return cards  # type: ignore[return-value]


def move_card(cfg: Config, card_id: str, list_id: str) -> None:
    trello(cfg, "PUT", f"/cards/{card_id}", {"idList": list_id})


def comment_card(cfg: Config, card_id: str, text: str) -> None:
    trello(cfg, "POST", f"/cards/{card_id}/actions/comments", {"text": text})


def _chunk(text: str, size: int) -> list[str]:
    """Split text into <= size pieces, preferring line boundaries."""
    out: list[str] = []
    cur = ""
    for line in text.splitlines(keepends=True):
        while len(line) > size:  # a single huge line: hard-slice it
            if cur:
                out.append(cur)
                cur = ""
            out.append(line[:size])
            line = line[size:]
        if len(cur) + len(line) > size:
            out.append(cur)
            cur = ""
        cur += line
    if cur:
        out.append(cur)
    return out or [""]


def comment_card_chunked(cfg: Config, card_id: str, header: str, body: str) -> None:
    """Post a headed comment, splitting across several comments if over Trello's cap."""
    body = (body or "").strip()
    if not body:
        return
    chunks = _chunk(body, TRELLO_COMMENT_LIMIT - len(header) - 40)
    n = len(chunks)
    for i, chunk in enumerate(chunks, 1):
        tag = f"{header} (часть {i}/{n})" if n > 1 else header
        comment_card(cfg, card_id, f"{tag}\n\n{chunk}")


# --- Task selection ----------------------------------------------------------
def has_label(card: dict, label_name: str) -> bool:
    return any((lab.get("name") or "") == label_name for lab in card.get("labels", []))


def pick_next_card(
    cfg: Config, lists_by_name: dict[str, str], skip_ids: set[str]
) -> tuple[dict, str] | None:
    """Return (card, source_list_name) for the first actionable card, or None."""
    pickup = cfg.get("TRELLO_PICKUP_LABEL")
    for name in cfg.list("TRELLO_SOURCE_LISTS"):
        list_id = lists_by_name.get(name)
        if not list_id:
            continue
        for card in list_cards(cfg, list_id):
            if card["id"] in skip_ids:
                continue
            if pickup and not has_label(card, pickup):
                continue
            return card, name
    return None


# --- Prompt builder ----------------------------------------------------------
def slugify(text: str, fallback: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    s = re.sub(r"-{2,}", "-", s)[:40].strip("-")
    return s or fallback


def build_prompt(cards: list[dict], branch_hint: str, cfg: Config, pw_mode: str, done_mode: str, ui_verify_via: str = "") -> str:
    is_bundle = len(cards) > 1
    web = cfg.get("WEB_BASE_URL")
    health = cfg.get("API_HEALTH_URL")
    creds = (
        "вход в приложение — единственный сид-аккаунт из backend/.env "
        "(SEED_USER_EMAIL / SEED_USER_PASSWORD); регистрации нет"
    )

    if is_bundle:
        head = (
            f"# Бандл из {len(cards)} карточек — ОДНА ветка, ОДИН общий PR\n"
            f"Эти карточки объединены в один юнит: реализуй ВСЕ на одной ветке и оформи ОДИН общий PR.\n"
        )
        if ui_verify_via:
            head += (
                f"Через UI весь результат бандла проверяется так: {ui_verify_via}. Именно через это "
                "верифицируй ВЕСЬ юнит (в т.ч. бэкенд-карточки, которые сами по себе в UI не видны).\n"
            )
        body = "\n".join(
            f"\n--- Карточка #{c.get('idShort')}: {c['name']} ---\n{c.get('desc') or '(нет описания)'}"
            for c in cards
        )
        task_block = head + body
        intro_task = "этот юнит задач (бандл карточек ниже)"
        task_ref = "карточки ниже"
    else:
        c = cards[0]
        task_block = (
            f"# Задача (карточка Trello «{c['name']}»)\n"
            f"ЗАГОЛОВОК: {c['name']}\n\n"
            f"ОПИСАНИЕ / ACCEPTANCE:\n{c.get('desc') or '(на карточке нет описания)'}"
        )
        intro_task = "ОДНУ задачу из Trello"
        task_ref = "карточка ниже"

    if pw_mode == "full":
        verify = (
            f"Шаг 3 (проверка) — как в плейбуке, ПЛЮС живой UI-прогон: если у карточки есть видимый "
            f"результат и фронт поднят на {web}, прогони сценарии через Playwright MCP (browser_navigate "
            "только на этот адрес, дальше клики; browser_close НЕ вызывай). Обязательный гейт всё равно — "
            "ruff/pytest для backend и tsc/eslint(/vitest) для frontend. Максимум 3 цикла фиксов; если после "
            "3 циклов всё ещё FAIL — стоп и FAILED."
        )
    else:
        verify = (
            "Шаг 3 (проверка): положись на гейт качества — ruff + pytest (backend) и "
            "tsc --noEmit + eslint (+ vitest если есть) (frontend). Живой Playwright ПРОПУСТИ; для "
            "наблюдаемых через HTTP карточек при поднятых серверах можно один curl-смоук. Сделай результат "
            "наблюдаемым. Шаг 5 (сценарии для ручной проверки) всё равно собери. Максимум 3 цикла фиксов."
        )

    if done_mode == "pr":
        finalize = (
            "закоммить логическими единицами на ветке; `git push -u origin <branch>`; открой PR в `main` "
            "через `gh pr create` (тело: суть задачи + тест-план + матрица ожиданий из Шага 5). PR НЕ мержить."
        )
        sentinel_ok = "AUTOPILOT_RESULT: SUCCESS | branch=<branch> | pr=<pr_url> | summary=<одна строка>"
        ok_rule = "SUCCESS — только если все проверки прошли И PR открыт (есть pr_url)."
    elif done_mode == "commit":
        finalize = "закоммить логическими единицами на ветке. НЕ пушить и PR не открывать."
        sentinel_ok = "AUTOPILOT_RESULT: SUCCESS | branch=<branch> | summary=<одна строка>"
        ok_rule = "SUCCESS — только если все проверки прошли и работа закоммичена на ветке."
    else:
        finalize = "оставь изменения в рабочем дереве на ветке (не коммить, не пушь)."
        sentinel_ok = "AUTOPILOT_RESULT: SUCCESS | branch=<branch> | summary=<одна строка>"
        ok_rule = "SUCCESS — только если все проверки прошли."

    return f"""Ты — АВТОНОМНЫЙ агент, рядом нет человека. Выполни {intro_task} по плейбуку
от начала до конца и остановись. Никаких вопросов и ожидания подтверждения: где нужен выбор —
бери самый разумный дефолт и продолжай.

# Источник процедуры — ЖИВОЙ файл docs/review-playbook.md
Сначала прочитай `docs/review-playbook.md` ЦЕЛИКОМ и следуй ему как ЕДИНСТВЕННОМУ источнику
процедуры, правил и форматов: шаги 0→5, правила написания сценариев, строгость проверки,
определение «бага», гейты качества, форматы вывода. Файл часто редактируют — всегда опирайся
на его ТЕКУЩЕЕ содержимое (ты только что его прочитал), а не на память. Появились новые правила —
выполняй их.

# Адаптация под автономный режим (ЕДИНСТВЕННОЕ, что приоритетнее плейбука)
Плейбук написан для работы с человеком; ты работаешь без него. Поэтому ПОВЕРХ плейбука:
1. Не задавай вопросов и не жди отмашки.
2. Значения плейсхолдеров плейбука для этого прогона:
   - {{{{BASE_URL}}}} = {web}
   - {{{{API_HEALTH_URL}}}} = {health}
   - {{{{CREDS}}}} = {creds}
   - {{{{BRANCH_NAME}}}} = {branch_hint}  (можно переименовать осмысленнее; префикс feat/ или fix/)
   - {{{{TASK}}}} / {{{{ACCEPTANCE}}}} = {task_ref}
   Проект греонфилд и локальный (FastAPI + SQLite + React/Vite). Ранние карточки (Sprint 0) — скелет: серверов/UI ещё нет, это нормально, проверяй гейтом качества.
3. {verify}
4. Вместо правила плейбука «не пушить без отмашки» финализируй так: {finalize}
5. Карточки Trello НЕ двигай и комментарии в них не пиши — это делает оркестратор.

# Жёсткие guardrails (не нарушать)
- Стек: backend — Python (venv) + FastAPI + SQLModel; frontend — npm + Vite. НЕ вводи pnpm/yarn. Прод-сборку (`npm run build`) гонять не нужно — для проверки фронта хватает `tsc --noEmit` + eslint.
- В Playwright MCP НИКОГДА не вызывай browser_close — это рвёт мост к Chrome пользователя. Вкладки не закрывай.
- Ветка от свежего `main`; на `main` не коммить. Если одноимённая ветка уже существует (повторный прогон после паузы по лимиту) — удали её (`git branch -D <ветка>`) и создай заново от main. Минимальный диф — не давай ruff/prettier/eslint трогать чужие строки. Не ломай существующие тесты и общие хелперы.
- Не хардкодь секреты (ключи Anthropic/Trello) — только из .env. Видео/скрины — на диск, в БД только пути.

{task_block}

# ОБЯЗАТЕЛЬНЫЙ ВЫВОД В САМОМ КОНЦЕ ОТВЕТА
Выведи РОВНО эти три блока (маркеры дословно), затем финальную строку-вердикт. Содержимое блоков —
готовый текст для комментариев в карточку Trello (без отсылок «см. выше», самодостаточно):

===AUTOPILOT_EXPLANATION_START===
<Человеческое описание задачи из Шага 1: ровно 2 абзаца — о чём задача, что добавляет/улучшает.>
===AUTOPILOT_EXPLANATION_END===
===AUTOPILOT_SCENARIOS_START===
<Финальный документ Шага 5: сценарии для ручной проверки + матрица ожиданий, ярлыки UI точные.>
===AUTOPILOT_SCENARIOS_END===
===AUTOPILOT_NOTES_START===
<Найденные, но НЕ исправленные/отложенные баги и прочее, что важно ревьюеру. Нечего — напиши «нет».>
===AUTOPILOT_NOTES_END===
{sentinel_ok}
AUTOPILOT_RESULT: FAILED | stage=<step0|step1|step2|step3|finalize> | reason=<одна строка>

{ok_rule} При FAILED всё равно выведи блоки EXPLANATION и NOTES (в NOTES — что именно заблокировало).
Финальная строка AUTOPILOT_RESULT парсится автоматикой — после неё не пиши ничего."""


# --- Claude runner -----------------------------------------------------------
@dataclass
class ClaudeResult:
    ok: bool
    reason: str = ""
    branch: str = ""
    pr: str = ""
    summary: str = ""
    cost_usd: float = 0.0
    turns: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_cache: int = 0
    duration_s: float = 0.0
    log_path: str = ""
    final_text: str = ""
    limit_reached: bool = False
    reset_at: float | None = None


def _fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", " ")  # 1 234 567


def format_metrics(res: "ClaudeResult") -> str:
    total = res.tokens_in + res.tokens_out + res.tokens_cache
    return (
        f"⏱ {res.duration_s / 60:.1f} мин · 🔢 {_fmt_int(total)} токенов "
        f"(вход {_fmt_int(res.tokens_in)} / выход {_fmt_int(res.tokens_out)} / кэш {_fmt_int(res.tokens_cache)}) "
        f"· 💲 ${res.cost_usd:.2f} · {res.turns} ходов"
    )


# Claude Code's own usage-limit notice — tight phrases so a task that merely *mentions*
# rate limiting (this app has DRF throttling) is not mistaken for a real limit hit.
LIMIT_RE = re.compile(
    r"usage limit reached|approaching your usage limit|limit will reset|"
    r"reached your usage limit|you've hit your|out of (?:credits|usage)|"
    r"claude usage limit",
    re.IGNORECASE,
)


def tail_text(path: Path, max_bytes: int = 16384) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - max_bytes))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def detect_limit(text: str) -> tuple[bool, float | None]:
    """Return (limit_hit, reset_epoch|None). reset epoch parsed if present."""
    if not text or not LIMIT_RE.search(text):
        return (False, None)
    m = re.search(r"\b(1[6-9]\d{8})\b", text)  # plausible unix ts (2020s+), if Claude included one
    return (True, float(m.group(1)) if m else None)


def extract_block(text: str, name: str) -> str:
    """Pull content between ===AUTOPILOT_<name>_START=== / _END=== markers."""
    if not text:
        return ""
    start, end = f"===AUTOPILOT_{name}_START===", f"===AUTOPILOT_{name}_END==="
    i = text.find(start)
    if i == -1:
        return ""
    j = text.find(end, i + len(start))
    if j == -1:
        return ""
    return text[i + len(start) : j].strip()


def parse_sentinel(text: str | None) -> tuple[str, dict[str, str]] | None:
    if not text:
        return None
    for line in reversed(text.splitlines()):
        m = SENTINEL_RE.match(line.strip())
        if not m:
            continue
        status, rest = m.group(1), m.group(2)
        fields: dict[str, str] = {}
        for part in rest.split("|"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                fields[k.strip()] = v.strip()
        return status, fields
    return None


def _print_progress(obj: dict) -> None:
    typ = obj.get("type")
    if typ == "system" and obj.get("subtype") == "init":
        print(f"    · session {obj.get('session_id', '?')[:8]} model={obj.get('model', '?')}")
    elif typ == "assistant":
        for block in obj.get("message", {}).get("content", []):
            if block.get("type") == "tool_use":
                print(f"    · tool: {block.get('name')}")
            elif block.get("type") == "text":
                txt = (block.get("text") or "").strip().replace("\n", " ")
                if txt:
                    print(f"    · {txt[:140]}")
    elif typ == "result":
        u = obj.get("usage") or {}
        tok = sum(int(u.get(k) or 0) for k in
                  ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        print(
            f"    · done: subtype={obj.get('subtype')} turns={obj.get('num_turns')} "
            f"tokens={tok:,} cost=${obj.get('total_cost_usd', 0):.3f}"
        )


def run_claude(prompt: str, cfg: Config, max_turns: int, timeout_s: int, log_path: Path) -> ClaudeResult:
    cmd = [
        "claude", "-p",
        "--output-format", "stream-json",
        "--verbose",
        "--dangerously-skip-permissions",
        "--max-turns", str(max_turns),
    ]
    model = cfg.get("CLAUDE_MODEL")
    if model:
        cmd += ["--model", model]

    started = time.monotonic()
    proc = subprocess.Popen(
        cmd, cwd=str(REPO_ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    assert proc.stdin and proc.stdout
    try:
        proc.stdin.write(prompt)
        proc.stdin.close()
    except BrokenPipeError:
        pass

    killed = {"v": False}

    def watchdog() -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                return
            time.sleep(2)
        if proc.poll() is None:
            killed["v"] = True
            proc.kill()

    t = threading.Thread(target=watchdog, daemon=True)
    t.start()

    final: dict | None = None
    with log_path.open("w", encoding="utf-8") as log:
        for line in proc.stdout:
            log.write(line)
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            _print_progress(obj)
            if obj.get("type") == "result":
                final = obj
    proc.wait()
    duration = time.monotonic() - started

    base = ClaudeResult(ok=False, duration_s=duration, log_path=str(log_path))
    if killed["v"]:
        base.reason = f"timeout after {timeout_s}s"
        return base

    final_text = (final.get("result") or "") if final else ""
    base.final_text = final_text
    if final:
        base.cost_usd = float(final.get("total_cost_usd") or 0.0)
        base.turns = int(final.get("num_turns") or 0)
        usage = final.get("usage") or {}
        base.tokens_in = int(usage.get("input_tokens") or 0)
        base.tokens_out = int(usage.get("output_tokens") or 0)
        base.tokens_cache = int((usage.get("cache_creation_input_tokens") or 0) + (usage.get("cache_read_input_tokens") or 0))
    sentinel = parse_sentinel(final_text)
    is_error = bool(final.get("is_error")) if final else True

    # 1) A clean success wins — even if the text happens to mention limits.
    if sentinel and sentinel[0] == "SUCCESS" and not is_error:
        f = sentinel[1]
        return ClaudeResult(
            ok=True, branch=f.get("branch", ""), pr=f.get("pr", ""), summary=f.get("summary", ""),
            cost_usd=base.cost_usd, turns=base.turns, tokens_in=base.tokens_in, tokens_out=base.tokens_out,
            tokens_cache=base.tokens_cache, duration_s=duration, log_path=str(log_path), final_text=final_text,
        )

    # 2) Claude usage limit hit -> signal a pause (do NOT fail the card).
    limit, reset_at = detect_limit(final_text + "\n" + tail_text(log_path))
    if limit:
        base.limit_reached = True
        base.reset_at = reset_at
        base.reason = "Claude usage limit reached"
        return base

    # 3) Real failure / crash / missing sentinel.
    if final is None:
        base.reason = "claude produced no result event (crash?)"
        return base
    if sentinel and sentinel[0] == "FAILED":
        f = sentinel[1]
        base.reason = f"agent reported FAILED at {f.get('stage', '?')}: {f.get('reason', '(no reason)')}"
        return base
    base.reason = "missing/invalid AUTOPILOT_RESULT sentinel (see log)" + (" [is_error]" if is_error else "")
    return base


# --- Git preflight -----------------------------------------------------------
def git_dirty() -> str:
    out = subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(REPO_ROOT), capture_output=True, text=True
    )
    return out.stdout.strip()


class GitError(RuntimeError):
    pass


def _has_upstream() -> bool:
    """True if the current branch has a configured upstream (i.e. there's a remote to pull)."""
    r = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    return r.returncode == 0


def sync_main() -> None:
    """Always start each task from a fresh main (checkout main + ff-only pull if a remote exists)."""
    co = subprocess.run(["git", "checkout", "main"], cwd=str(REPO_ROOT), capture_output=True, text=True)
    if co.returncode != 0:
        raise GitError(f"git checkout main failed: {(co.stderr or co.stdout).strip()}")
    if not _has_upstream():  # local-only repo (no GitHub remote) — nothing to pull
        print("    · main checked out (no upstream — local-only repo, skipping pull)")
        return
    pull = subprocess.run(["git", "pull", "--ff-only"], cwd=str(REPO_ROOT), capture_output=True, text=True)
    if pull.returncode != 0:
        raise GitError(f"git pull --ff-only failed: {(pull.stderr or pull.stdout).strip()}")
    print(f"    · main synced: {pull.stdout.strip().splitlines()[-1] if pull.stdout.strip() else 'up to date'}")


def reset_to_main(branch_hint: str) -> None:
    """Best-effort clean reset to fresh main before a limit-retry (discards the interrupted attempt)."""
    subprocess.run(["git", "checkout", "-f", "main"], cwd=str(REPO_ROOT), capture_output=True, text=True)
    subprocess.run(["git", "pull", "--ff-only"], cwd=str(REPO_ROOT), capture_output=True, text=True)
    subprocess.run(["git", "branch", "-D", branch_hint], cwd=str(REPO_ROOT), capture_output=True, text=True)


def stash_and_main(label: str) -> str | None:
    """Get back to a clean main WITHOUT losing work: stash any WIP (labelled), then checkout+pull main.
    Returns the stash label if something was stashed, else None. skip-worktree files are untouched."""
    stashed = None
    if git_dirty():
        r = subprocess.run(
            ["git", "stash", "push", "-u", "-m", label], cwd=str(REPO_ROOT), capture_output=True, text=True
        )
        if r.returncode == 0 and "No local changes" not in (r.stdout + r.stderr):
            stashed = label
    subprocess.run(["git", "checkout", "main"], cwd=str(REPO_ROOT), capture_output=True, text=True)
    subprocess.run(["git", "pull", "--ff-only"], cwd=str(REPO_ROOT), capture_output=True, text=True)
    return stashed


def integrate_branch_to_main(branch: str) -> bool:
    """Fast-forward a finished card's branch into main so later cards build on top of it.
    Used by --integrate-main for fully autonomous multi-card runs (commit done-mode)."""
    if not branch:
        return False
    co = subprocess.run(["git", "checkout", "main"], cwd=str(REPO_ROOT), capture_output=True, text=True)
    if co.returncode != 0:
        print(f"    ⚠ integrate: checkout main failed: {(co.stderr or co.stdout).strip()[:200]}")
        return False
    m = subprocess.run(["git", "merge", "--ff-only", branch], cwd=str(REPO_ROOT), capture_output=True, text=True)
    if m.returncode == 0:
        print(f"    🔀 merged {branch} -> main (fast-forward)")
        return True
    print(f"    ⚠ integrate: ff-merge {branch} -> main failed: {(m.stderr or m.stdout).strip()[:200]}")
    return False


def compute_wait(reset_at: float | None, fallback: int) -> int:
    """Seconds to pause on a limit hit: until reset (+buffer) if known & sane, else fallback."""
    if reset_at:
        delta = reset_at - time.time() + 60
        if 60 <= delta <= 6 * 3600:
            return int(delta)
    return fallback


def url_reachable(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5):
            return True
    except Exception:
        return False


# --- Orchestration loop ------------------------------------------------------
def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


# --- Crash recovery: an "in-flight" marker tracks the card being worked right now -----
def write_inflight(cards: list[dict], branch_hint: str) -> None:
    try:
        INFLIGHT_PATH.write_text(
            json.dumps({
                "cards": [{"id": c["id"], "short": str(c.get("idShort") or "")} for c in cards],
                "branch_hint": branch_hint, "started_at": now_stamp(),
            }),
            encoding="utf-8",
        )
    except OSError:
        pass


def read_inflight() -> dict | None:
    try:
        return json.loads(INFLIGHT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def clear_inflight() -> None:
    try:
        INFLIGHT_PATH.unlink()
    except OSError:
        pass


def recover_if_interrupted(cfg: Config, lists_by_name: dict[str, str]) -> None:
    """If a previous run was cut off mid-card (crash/shutdown), park that card in Blocked
    (unless already there) and reset to a clean main. The user reviews Blocked manually."""
    info = read_inflight()
    if not info:
        return  # clean previous run — nothing to recover
    # Don't yank a card from another autopilot that is currently running.
    pg = subprocess.run(["pgrep", "-f", "trello_autopilot.py"], capture_output=True, text=True)
    if len([p for p in pg.stdout.split() if p.strip()]) > 1:
        print("⚠ Найден маркер прерванной задачи, но запущен ещё один экземпляр автопилота — пропускаю восстановление.")
        return

    cards = info.get("cards")
    if cards is None and info.get("card_id"):  # back-compat with the old single-card marker
        cards = [{"id": info["card_id"], "short": info.get("short", "?")}]
    cards = cards or []
    shorts = "+".join(c.get("short", "?") for c in cards) or "?"
    print(f"⚠ Восстановление: прошлый прогон прерван на #{shorts}.")
    blocked = lists_by_name.get(cfg.get("TRELLO_BLOCKED_LIST"))
    if blocked:
        for c in cards:
            cid = c.get("id")
            if not cid:
                continue
            try:
                cur = trello(cfg, "GET", f"/cards/{cid}", {"fields": "idList"})
                if cur.get("idList") != blocked:
                    comment_card(cfg, cid, "🔧 Задача была прервана (краш/выключение машины) и не завершена. Перемещаю в Blocked для ручного разбора.")
                    move_card(cfg, cid, blocked)
                    print(f"    · #{c.get('short')} -> Blocked")
                else:
                    print(f"    · #{c.get('short')} уже в Blocked")
            except TrelloError as e:
                print(f"    · #{c.get('short')} переместить не удалось: {e}")

    stash = stash_and_main(f"autopilot-recovery-{shorts}-{now_stamp()}")
    clear_inflight()
    print(f"    · дерево очищено{f' (WIP сохранён в stash: {stash})' if stash else ''}; на main. Прерванную задачу разбери вручную в Blocked.")


def playbook_meta() -> tuple[str, str] | None:
    """(version, mtime) of the live playbook, so each card records what it ran against."""
    if not PLAYBOOK_PATH.is_file():
        return None
    version = "?"
    for line in PLAYBOOK_PATH.read_text(encoding="utf-8").splitlines()[:12]:
        m = re.search(r"Верси[яи]:\*\*\s*(\S+)", line)
        if m:
            version = m.group(1)
            break
    mtime = datetime.fromtimestamp(PLAYBOOK_PATH.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return version, mtime


def post_deliverables(cfg: Config, card_id: str, final_text: str, include_scenarios: bool) -> None:
    """Post the agent's human-facing blocks (description / scenarios / notes) as comments."""
    explanation = extract_block(final_text, "EXPLANATION")
    scenarios = extract_block(final_text, "SCENARIOS")
    notes = extract_block(final_text, "NOTES")
    if explanation:
        comment_card_chunked(cfg, card_id, "📋 Описание задачи (автопилот)", explanation)
    if include_scenarios and scenarios:
        comment_card_chunked(cfg, card_id, "✅ Сценарии для ручной проверки + матрица ожиданий", scenarios)
    if notes and notes.strip().lower() not in NOTES_EMPTY:
        comment_card_chunked(cfg, card_id, "🧐 Заметки автопилота (отложенные баги и пр.)", notes)


def append_report(title: str, short: str, ok: bool, res: "ClaudeResult") -> None:
    """Append a per-card section to report.md on main and commit it — a running log of what
    was built and how it affects the project. Best-effort: never raises, never blocks the run."""
    try:
        subprocess.run(["git", "checkout", "main"], cwd=str(REPO_ROOT), capture_output=True, text=True)
        expl = extract_block(res.final_text, "EXPLANATION") or "_(агент не вернул блок с описанием)_"
        status = "✅ Готово" if ok else f"❌ Провал — {res.reason}"
        lines = [f"\n## {now_stamp()} UTC · #{short} — {title}", "", f"**Статус:** {status}"]
        if res.branch:
            lines.append(f"**Ветка:** `{res.branch}`" + (f" · PR: {res.pr}" if res.pr else ""))
        if res.duration_s or res.cost_usd or res.turns:
            lines.append(f"**Прогон:** {format_metrics(res)}")
        lines += ["", "### Что сделано и как влияет на проект", "", expl, ""]
        path = REPO_ROOT / "report.md"
        if not path.exists():
            path.write_text(
                "# Отчёт автопилота\n\nЧто сделано по каждой карточке и как это влияет на проект.\n",
                encoding="utf-8",
            )
        with path.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        subprocess.run(["git", "add", "report.md"], cwd=str(REPO_ROOT), capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", f"docs(report): #{short} {title}"], cwd=str(REPO_ROOT), capture_output=True, text=True)
        print(f"    📝 report.md дополнён (#{short})")
    except Exception as e:  # reporting must never break the pipeline
        print(f"    ⚠ не удалось обновить report.md: {e}")


def single_unit(card: dict) -> dict:
    """Wrap one card as a unit (the non-planned, one-card-at-a-time path)."""
    return {"cards": [card], "primary_short": str(card.get("idShort") or ""), "ui_verify_via": "", "title": card.get("name", "")}


def _primary_card(unit: dict) -> dict:
    ps = str(unit.get("primary_short") or "")
    for c in unit["cards"]:
        if str(c.get("idShort")) == ps:
            return c
    return unit["cards"][0]


def process_unit(unit: dict, cfg: Config, lists_by_name: dict[str, str], args) -> bool:
    """Run one unit (1 card, or a bundle of cards on a single branch/PR). Returns True on success."""
    cards = unit["cards"]
    primary = _primary_card(unit)
    title = unit.get("title") or primary["name"]
    pshort = str(primary.get("idShort") or primary["id"][:6])
    unit_short = "+".join(str(c.get("idShort") or c["id"][:6]) for c in cards)
    is_bundle = len(cards) > 1
    branch_hint = f"{'fix' if title.lower().startswith(('fix', 'багфикс', 'баг')) else 'feat'}/{slugify(title, f'task-{pshort}')}"

    print(f"\n=== {'Бандл' if is_bundle else 'Card'} #{unit_short}: {title!r} ===")
    for c in cards:
        print(f"    #{c.get('idShort')}: {c.get('shortUrl', '?')}")
    if is_bundle and unit.get("ui_verify_via"):
        print(f"    UI-проверка через: {unit['ui_verify_via']}")

    if args.dry_run:
        print(f"    [dry-run] branch≈{branch_hint}; {len(cards)} карточк(и) -> Doing, run Claude, -> Review/Blocked")
        return True

    doing = lists_by_name.get(cfg.get("TRELLO_DOING_LIST"))
    review = lists_by_name.get(cfg.get("TRELLO_REVIEW_LIST"))
    blocked = lists_by_name.get(cfg.get("TRELLO_BLOCKED_LIST"))
    meta = playbook_meta()
    meta_note = f" Плейбук: версия {meta[0]}, изменён {meta[1]}." if meta else ""
    bundle_note = f" (бандл #{unit_short})" if is_bundle else ""
    for c in cards:
        if doing:
            move_card(cfg, c["id"], doing)
        comment_card(cfg, c["id"], f"🤖 Автопилот взял в работу {now_stamp()} UTC. Ветка ≈ `{branch_hint}`{bundle_note}.{meta_note}")
    write_inflight(cards, branch_hint)  # mark in-flight so a crash here is recoverable on next start

    prompt = build_prompt(cards, branch_hint, cfg, args.pw_mode, args.done_mode, unit.get("ui_verify_via", ""))
    max_turns = int(cfg.get("CLAUDE_MAX_TURNS"))
    timeout_s = int(cfg.get("TASK_TIMEOUT_SECONDS"))

    # Run, and pause-then-retry the same unit if Claude's usage limit is hit.
    attempt = 0
    while True:
        if attempt > 0:
            reset_to_main(branch_hint)  # clean slate before a limit-retry
        suffix = "" if attempt == 0 else f"-retry{attempt}"
        log_path = LOG_DIR / f"{now_stamp()}-unit{unit_short}{suffix}.jsonl"
        print(f"    log: {log_path}")
        res = run_claude(prompt, cfg, max_turns, timeout_s, log_path)
        if not res.limit_reached:
            break
        attempt += 1
        if args.limit_max_waits and attempt > args.limit_max_waits:
            res.reason = f"лимит Claude — превышен потолок пауз (--limit-max-waits={args.limit_max_waits})"
            break
        wait_s = compute_wait(res.reset_at, args.limit_wait)
        mins = max(1, round(wait_s / 60))
        until = time.strftime("%H:%M", time.localtime(time.time() + wait_s))
        comment_card(cfg, primary["id"], f"⏸ Лимит Claude достигнут. Пауза ~{mins} мин (до ~{until}), попытка {attempt}. Возобновлю автоматически.")
        print(f"    ⏸ Лимит Claude — пауза ~{mins} мин (до ~{until}), попытка {attempt}…")
        time.sleep(wait_s)

    if res.ok:
        # Description + scenarios + notes go on the primary (UI-verifiable) card.
        post_deliverables(cfg, primary["id"], res.final_text, include_scenarios=True)
        parts = [f"✅ Автопилот завершил.\n{format_metrics(res)}"]
        if res.branch:
            parts.append(f"\nВетка: `{res.branch}`.")
        if res.pr:
            parts.append(f"PR: {res.pr}")
        if res.summary:
            parts.append(f"\n{res.summary}")
        comment_card(cfg, primary["id"], " ".join(parts))
        for c in cards:
            if c["id"] != primary["id"]:
                comment_card(cfg, c["id"], f"✅ Сделано в составе бандла с #{pshort} (PR {res.pr or res.branch}). Детали — в карточке #{pshort}.")
            if review:
                move_card(cfg, c["id"], review)
        if getattr(args, "integrate_main", False) and res.branch:
            if integrate_branch_to_main(res.branch):
                comment_card(cfg, primary["id"], f"🔀 Влито в `main` (fast-forward): `{res.branch}`. Следующие карточки строятся поверх этой работы.")
            else:
                comment_card(cfg, primary["id"], f"⚠ Не удалось автоматически влить `{res.branch}` в `main` — влей вручную, иначе зависимые карточки не увидят эту работу.")
        append_report(title, pshort, True, res)
        print(f"    ✅ SUCCESS -> Review. {res.pr or res.branch}")
        clear_inflight()
        return True

    # Failure: surface description + notes (what blocked it) on the primary, route all to Blocked.
    post_deliverables(cfg, primary["id"], res.final_text, include_scenarios=False)
    metrics = f"\n{format_metrics(res)}" if (res.duration_s or res.cost_usd or res.tokens_out) else ""
    for c in cards:
        tail = metrics if c["id"] == primary["id"] else ""
        comment_card(cfg, c["id"], f"❌ Автопилот не справился {now_stamp()} UTC: {res.reason}\nЛог: `{res.log_path}`{tail}")
        if blocked:
            move_card(cfg, c["id"], blocked)
    print(f"    ❌ FAILED ({res.reason}){' -> Blocked' if blocked else ''}.")
    stash_and_main(f"autopilot-failed-{unit_short}-{now_stamp()}")  # leave a clean main for the next unit/run
    append_report(title, pshort, False, res)
    clear_inflight()
    return False


# --- Planner: build the execution queue before running -----------------------
def gather_candidates(cfg: Config, lists_by_name: dict[str, str]) -> list[dict]:
    """All candidate cards across source lists, in list-priority order (label filter applied)."""
    pickup = cfg.get("TRELLO_PICKUP_LABEL")
    out: list[dict] = []
    seen: set[str] = set()
    for name in cfg.list("TRELLO_SOURCE_LISTS"):
        list_id = lists_by_name.get(name)
        if not list_id:
            continue
        for card in list_cards(cfg, list_id):
            if card["id"] in seen:
                continue
            if pickup and not has_label(card, pickup):
                continue
            seen.add(card["id"])
            out.append(card)
    return out


def build_planner_prompt(candidates: list[dict], cfg: Config) -> str:
    web = cfg.get("WEB_BASE_URL")
    cards_block = "\n\n".join(
        f"[#{c.get('idShort')}] {c['name']}\n{(c.get('desc') or '(нет описания)').strip()}" for c in candidates
    )
    head = f"""Ты — ПЛАНИРОВЩИК очереди для автопилота. Тебе дан список карточек Trello с доски проекта.
Построй ОЧЕРЕДЬ юнитов на исполнение. Можешь читать репозиторий (модели, фронт-блоки, services,
docs/), чтобы судить о зависимостях и UI-проверяемости — это важно.

КАРТОЧКИ:
{cards_block}

ПРАВИЛА ПОСТРОЕНИЯ ОЧЕРЕДИ:
1. ТОЛЬКО технические задачи (код / миграции / тесты / UI). Менеджерские (Sprint Info, DoD,
   планирование, договорённости, организационные, не-кодовые) — ИСКЛЮЧИ (в "excluded").
2. Каждый юнит ДОЛЖЕН быть проверяем через UI на {web} (человек открывает интерфейс и видит
   результат). Если карточка сама по себе в UI не видна (только модель/миграция/бэкенд-сервис/хук)
   — ОБЪЕДИНИ её в ОДИН юнит с карточкой, через которую результат становится виден в UI (обычно
   соответствующий фронт-блок). Бандл = один юнит = один PR. Если для карточки нет подходящего
   UI-верификатора среди карточек — исключи её с пояснением.
3. ПРИОРИТЕТ — независимые юниты (которые не влияют на последующие): ставь их раньше. Если юнит B
   зависит от A — A раньше B.
4. primary_short — карточка, через которую проверяется UI (для бандла — фронтовая/UI). Используй
   ТОЛЬКО shorts из списка выше; ничего не выдумывай, карточки не дроби.

ВЫВОД — РОВНО блок ниже (маркеры дословно), внутри ВАЛИДНЫЙ JSON без комментариев и без текста после.
"""
    schema = (
        "===AUTOPILOT_QUEUE_START===\n"
        '{"queue": ['
        '{"unit": 1, "card_shorts": [25, 26], "primary_short": 26, "title": "кратко", '
        '"ui_verify_via": "как проверить результат в UI", "independent": true, '
        '"rationale": "почему так сгруппировано и где в порядке"}'
        '], "excluded": [{"short": 7, "reason": "менеджерская: ..."}]}\n'
        "===AUTOPILOT_QUEUE_END==="
    )
    return head + "\n" + schema


def run_planner(cfg: Config, candidates: list[dict], args) -> dict | None:
    """Run the planner agent; return parsed queue dict, or None on failure."""
    prompt = build_planner_prompt(candidates, cfg)
    max_turns = int(cfg.get("CLAUDE_MAX_TURNS"))
    timeout_s = int(cfg.get("TASK_TIMEOUT_SECONDS"))
    attempt = 0
    while True:
        suffix = "" if attempt == 0 else f"-retry{attempt}"
        log_path = LOG_DIR / f"{now_stamp()}-planner{suffix}.jsonl"
        print(f"    log: {log_path}")
        res = run_claude(prompt, cfg, max_turns, timeout_s, log_path)
        if not res.limit_reached:
            break
        attempt += 1
        if args.limit_max_waits and attempt > args.limit_max_waits:
            break
        wait_s = compute_wait(res.reset_at, args.limit_wait)
        print(f"    ⏸ Лимит Claude (планировщик) — пауза ~{max(1, round(wait_s / 60))} мин…")
        time.sleep(wait_s)
    block = extract_block(res.final_text, "QUEUE")
    if not block:
        print("⚠ Планировщик не вернул блок QUEUE (см. лог).")
        return None
    try:
        return json.loads(block)
    except json.JSONDecodeError as e:
        print(f"⚠ Не удалось распарсить JSON очереди: {e}")
        return None


def print_queue(queue_data: dict) -> None:
    q = queue_data.get("queue", [])
    print(f"\n=== ОЧЕРЕДЬ ({len(q)} юнитов) ===")
    for item in q:
        names = " + ".join(f"#{s}" for s in item.get("card_shorts", []))
        flag = "независимый" if item.get("independent") else "зависимый"
        print(f"  {item.get('unit', '?')}. {names} [{flag}] — {item.get('title', '')}")
        if item.get("ui_verify_via"):
            print(f"       UI: {item['ui_verify_via']}")
        if item.get("rationale"):
            print(f"       ↳ {item['rationale']}")
    excl = queue_data.get("excluded", [])
    if excl:
        print(f"  Исключено ({len(excl)}):")
        for e in excl:
            print(f"    #{e.get('short')}: {e.get('reason', '')}")


def units_from_queue(queue_data: dict, candidates: list[dict]) -> list[dict]:
    by_short = {str(c.get("idShort")): c for c in candidates}
    units: list[dict] = []
    for item in queue_data.get("queue", []):
        ucards = [by_short[str(s)] for s in item.get("card_shorts", []) if str(s) in by_short]
        if not ucards:
            continue
        units.append({
            "cards": ucards, "primary_short": item.get("primary_short"),
            "ui_verify_via": item.get("ui_verify_via", ""), "title": item.get("title", ""),
        })
    return units


def run_loop(cfg: Config, args) -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    if not PLAYBOOK_PATH.is_file():
        print(f"Playbook not found at {PLAYBOOK_PATH} — the agent would have no procedure to follow.")
        return 2
    meta = playbook_meta()
    if meta:
        print(f"Playbook: {PLAYBOOK_PATH.relative_to(REPO_ROOT)} (версия {meta[0]}, изменён {meta[1]}) — читается заново на каждой задаче")

    board = resolve_board(cfg)
    print(f"Board: {board['name']} ({board['id']})")
    lists_by_name = board_lists(cfg, board["id"])
    for role in ("TRELLO_REVIEW_LIST", "TRELLO_DOING_LIST", "TRELLO_BLOCKED_LIST"):
        name = cfg.get(role)
        if name and name not in lists_by_name:
            print(f"⚠ List {name!r} ({role}) not found on board — that step will be skipped.")

    if not args.dry_run:
        # Recover from a prior interrupted run BEFORE the clean-tree guard (it cleans the tree).
        recover_if_interrupted(cfg, lists_by_name)
        if not args.allow_dirty:
            dirty = git_dirty()
            if dirty:
                print("Working tree is dirty — refusing to start (protects your uncommitted work).")
                print("Commit/stash first, or pass --allow-dirty if you know what you're doing.\n" + dirty)
                return 2
        if not url_reachable(cfg.get("API_HEALTH_URL")):
            print(f"⚠ API health URL {cfg.get('API_HEALTH_URL')} not reachable — Step 0 may fail until dev servers are up.")

    # --- Planned mode: build a queue (planner LLM) then execute it unit by unit ---
    if args.plan:
        candidates = gather_candidates(cfg, lists_by_name)
        if not candidates:
            print("\nНет карточек-кандидатов для планирования.")
            return 0
        print(f"\nПланировщик анализирует {len(candidates)} карточек (с чтением кода)…")
        queue_data = run_planner(cfg, candidates, args)
        if not queue_data or not queue_data.get("queue"):
            print("Планировщик не построил очередь. Останов.")
            return 2
        try:
            QUEUE_PATH.write_text(json.dumps(queue_data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Очередь сохранена: {QUEUE_PATH}")
        except OSError:
            pass
        print_queue(queue_data)
        units = units_from_queue(queue_data, candidates)
        if args.dry_run:
            print(f"\n[dry-run] Очередь построена ({len(units)} юнитов), исполнение пропущено.")
            return 0
        processed = failures = 0
        for unit in units:
            if args.max_tasks and processed >= args.max_tasks:
                print(f"\nReached --count={args.max_tasks}. Stopping.")
                break
            try:
                sync_main()  # always branch each unit off fresh main
            except GitError as e:
                print(f"\nmain sync failed: {e}\nStopping.")
                break
            ok = process_unit(unit, cfg, lists_by_name, args)
            processed += 1
            if not ok:
                failures += 1
                if args.on_fail == "stop":
                    print("\n--on-fail=stop: halting after failure.")
                    break
            if args.once:
                break
        print(f"\nSummary (planned): units={processed}, failures={failures}.")
        return 1 if failures else 0

    skip_ids: set[str] = set()
    processed = 0
    failures = 0
    total = len(gather_candidates(cfg, lists_by_name))  # snapshot of cards to do, for X/N progress
    print(f"\nК исполнению по спискам-источникам: {total} карточк(и).")
    while True:
        if args.max_tasks and processed >= args.max_tasks:
            print(f"\nReached --max-tasks={args.max_tasks}. Stopping.")
            break
        picked = pick_next_card(cfg, lists_by_name, skip_ids)
        if not picked:
            if args.watch and not args.once:
                print(f"No actionable cards. Sleeping {args.poll_interval}s (--watch)...")
                time.sleep(args.poll_interval)
                continue
            print("\nNo actionable cards left. Stopping.")
            break

        card, source_list = picked
        skip_ids.add(card["id"])  # never reprocess the same card within this run
        print(f"\n──► [{processed + 1}/{total}] следующая карточка (готово: {processed}, в Blocked: {failures})")
        if not args.dry_run:
            try:
                sync_main()  # user rule: always branch each task off fresh main
            except GitError as e:
                print(f"\nmain sync failed: {e}\nStopping (resolve git state, then re-run).")
                break
        ok = process_unit(single_unit(card), cfg, lists_by_name, args)
        processed += 1
        if not ok:
            failures += 1
            if args.on_fail == "stop":
                print("\n--on-fail=stop: halting after failure.")
                break
            # on_fail == "continue": card is in Blocked (or stays put); skip_ids prevents re-pick.
        if args.once or args.dry_run:
            break

    print(f"\nSummary: processed={processed}, failures={failures}.")
    return 1 if failures and not args.dry_run else 0


# --- CLI ---------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Drive Trello cards through the Claude review playbook.")
    p.add_argument("--config", help="Extra KEY=VALUE config file (merged over ~/transitgate-secrets/.env).")
    p.add_argument("--plan", action="store_true",
                   help="Build an execution queue first (planner LLM: keep only technical cards, order independent-first, "
                        "bundle non-UI cards with their UI verifier into one PR), then run it. With --dry-run: just print the queue.")
    p.add_argument("--once", action="store_true", help="Process a single card/unit, then exit.")
    p.add_argument("-n", "--count", "--max-tasks", dest="max_tasks", type=int, default=0,
                   help="How many cards/units to process sequentially this run (0 = until source lists empty). E.g. -n 5.")
    p.add_argument("--watch", action="store_true", help="When source lists are empty, poll instead of exiting.")
    p.add_argument("--poll-interval", type=int, default=120, help="Seconds between polls in --watch mode.")
    p.add_argument("--limit-wait", dest="limit_wait", type=int, default=1800,
                   help="Pause seconds on a Claude usage-limit hit when no reset time is known (default 1800).")
    p.add_argument("--limit-max-waits", dest="limit_max_waits", type=int, default=0,
                   help="Max pauses per card on usage limits (0 = unlimited — wait as long as needed).")
    p.add_argument("--dry-run", action="store_true", help="Resolve board + pick card and print the plan; no Claude, no moves.")
    p.add_argument("--allow-dirty", action="store_true", help="Start even if the git working tree is dirty.")
    p.add_argument("--on-fail", choices=["stop", "continue"], default="stop", help="What to do after a card fails.")
    p.add_argument("--pw-mode", choices=["full", "light"], default="light", help="light = quality gate only (default; no live UI early in a greenfield build); full = also live Playwright once a UI exists.")
    p.add_argument("--done-mode", choices=["pr", "commit", "branch"], default="commit", help="commit = commit on branch only (default; repo has no remote); pr = commit+push+PR (needs a GitHub remote); branch = leave uncommitted.")
    p.add_argument("--integrate-main", dest="integrate_main", action="store_true",
                   help="After each successful card, fast-forward its branch into main so later cards build on it. Needed for a full autonomous run (commit done-mode); autopilot writes to main unattended.")
    # Optional overrides (else env / config file / built-in defaults apply):
    p.add_argument("--board", dest="TRELLO_BOARD_NAME", help="Board name override.")
    p.add_argument("--board-id", dest="TRELLO_BOARD_ID", help="Board id/shortLink override.")
    p.add_argument("--review-list", dest="TRELLO_REVIEW_LIST", help="Target 'Review' list name.")
    p.add_argument("--doing-list", dest="TRELLO_DOING_LIST", help="'In Progress' list name.")
    p.add_argument("--blocked-list", dest="TRELLO_BLOCKED_LIST", help="'Blocked' list name.")
    p.add_argument("--source-lists", dest="TRELLO_SOURCE_LISTS", help="Comma-separated source list names (priority order).")
    p.add_argument("--label", dest="TRELLO_PICKUP_LABEL", help="Only pick cards with this label name.")
    p.add_argument("--model", dest="CLAUDE_MODEL", help="Claude model (e.g. opus, sonnet).")
    p.add_argument("--max-turns", dest="CLAUDE_MAX_TURNS", help="Max agent turns per task.")
    p.add_argument("--task-timeout", dest="TASK_TIMEOUT_SECONDS", help="Per-task timeout in seconds.")
    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    override_keys = [
        "TRELLO_BOARD_NAME", "TRELLO_BOARD_ID", "TRELLO_REVIEW_LIST", "TRELLO_DOING_LIST",
        "TRELLO_BLOCKED_LIST", "TRELLO_SOURCE_LISTS", "TRELLO_PICKUP_LABEL",
        "CLAUDE_MODEL", "CLAUDE_MAX_TURNS", "TASK_TIMEOUT_SECONDS",
    ]
    cli_overrides = {k: getattr(args, k) for k in override_keys}
    cfg = load_config(args.config, cli_overrides)
    try:
        return run_loop(cfg, args)
    except TrelloError as e:
        print(f"Trello error: {e}", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
