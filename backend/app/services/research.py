"""Корпус исследований для доказательного отчёта (S4.x).

Грузит `research/studies.json` (см. scripts/research/fetch_studies.py) и готовит две вещи
для генерации рекомендации:
- `build_evidence_pack` — компактный текст-блок резюме работ для вставки в промпт (модель
  пишет отчёт и цитирует работы по их `id` в квадратных скобках);
- `valid_citation_ids` — множество допустимых id, по которому валидатор схемы отбраковывает
  выдуманные ссылки (цитировать можно ТОЛЬКО то, что реально есть в корпусе).

Загрузка устойчива: нет файла / битый JSON → пустой корпус (fail-open). Тогда отчёт всё ещё
генерируется, но без проверки цитат — это осознанный компромисс, не падение.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings

# Сколько слов резюме на работу кладём в evidence-pack (баланс информативность/токены).
_SUMMARY_WORDS = 55
# Потолок числа работ в паке (весь корпус ~70 влезает; кап — страховка от разрастания).
_PACK_LIMIT = 80


@dataclass(frozen=True)
class Study:
    """Одна работа корпуса (подмножество полей studies.json, нужное для отчёта)."""

    id: str
    title: str
    authors: tuple[str, ...]
    year: int | None
    journal: str | None
    doi: str | None
    url: str | None
    topics: tuple[str, ...]
    study_type: str
    summary: str  # аннотация
    pdf_path: str | None


def load_corpus(path: Path | None = None) -> tuple[Study, ...]:
    """Загрузить корпус из studies.json. Нет файла / битый JSON → () (fail-open)."""
    src = Path(path) if path is not None else settings.research_dir / "studies.json"
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    out: list[Study] = []
    for s in data.get("studies", []):
        sid = s.get("id")
        if not sid:
            continue
        out.append(
            Study(
                id=sid,
                title=s.get("title") or "",
                authors=tuple(s.get("authors") or ()),
                year=s.get("year"),
                journal=s.get("journal"),
                doi=s.get("doi"),
                url=s.get("url"),
                topics=tuple(s.get("topics") or ()),
                study_type=s.get("study_type") or "study",
                summary=(s.get("abstract") or "").strip(),
                pdf_path=s.get("pdf_path"),
            )
        )
    return tuple(out)


def valid_citation_ids(corpus: Sequence[Study]) -> frozenset[str]:
    """Множество допустимых id цитат (для валидатора схемы)."""
    return frozenset(s.id for s in corpus)


def select_studies(
    corpus: Sequence[Study], snapshot: dict[str, Any] | None = None, *, limit: int = _PACK_LIMIT
) -> tuple[Study, ...]:
    """Отобрать работы под отчёт. v1: весь корпус (он небольшой), кап `limit`.

    `snapshot` пока не используется (оставлен под будущий тематический отбор под цель —
    snapshot несёт goal.targets/why_notes/training.by_sport для взвешивания тем)."""
    return tuple(corpus[:limit])


def _author_label(authors: tuple[str, ...]) -> str:
    if not authors:
        return "—"
    return authors[0] + (" et al." if len(authors) > 1 else "")


def _truncate_words(text: str, words: int) -> str:
    parts = text.split()
    return " ".join(parts[:words]) + ("…" if len(parts) > words else "")


def build_evidence_pack(studies: Sequence[Study]) -> str:
    """Компактный блок резюме работ для промпта. id первым — чтобы модель копировала дословно."""
    lines = []
    for s in studies:
        head = f"[{s.id}] {_author_label(s.authors)} {s.year or '?'}"
        meta = f"{s.journal or '—'} ({s.study_type})"
        lines.append(f"{head}. {meta}. {_truncate_words(s.summary, _SUMMARY_WORDS)}")
    return "\n".join(lines)
