#!/usr/bin/env python3
"""Собрать корпус исследований (по набору массы / сушке / поддержанию + сопутствующее)
из OpenAlex (с OA-PDF от Unpaywall) и записать research/studies.json + аннотации + PDF.

Источник: OpenAlex REST (ключ не нужен; вежливый пул через mailto). На тему делаем
title_and_abstract.search с фильтром open_access.is_oa:true,type:article и сортировкой по
цитируемости — это даёт релевантные И влиятельные работы (мета-анализы/RCT/обзоры). PDF
берём из best_oa_location.pdf_url (Unpaywall) — для OA-журналов (MDPI/Frontiers/PLOS/BMC и
т.п.) это прямой публикаторский PDF. Дедуп по DOI, объединяем темы. Идемпотентно: индекс
upsert по id, скачанные PDF не перекачиваются.

Usage:
    python3 scripts/research/fetch_studies.py --email you@example.com
    python3 scripts/research/fetch_studies.py --dry-run            # только показать план
    python3 scripts/research/fetch_studies.py --per-topic 4 --no-pdf
    python3 scripts/research/fetch_studies.py --topic creatine     # одна тема

Stdlib + httpx (уже в зависимостях backend). PDF и индекс коммитятся (по решению проекта).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
RESEARCH_DIR = REPO_ROOT / "research"
PDF_DIR = RESEARCH_DIR / "pdfs"
ABSTRACT_DIR = RESEARCH_DIR / "abstracts"
INDEX_PATH = RESEARCH_DIR / "studies.json"

OPENALEX = "https://api.openalex.org/works"
_MIN_PDF_BYTES = 25_000  # меньше — почти наверняка заглушка/HTML, не статья
SCHEMA_VERSION = 1

# Контролируемый словарь тем → поисковый запрос OpenAlex. Покрывает все 3 типа цели
# (набор массы / сушка / поддержание) + сопутствующую науку. Разносторонне по замыслу.
TOPICS: dict[str, str] = {
    # --- набор массы ---
    "hypertrophy": "resistance training skeletal muscle hypertrophy",
    "training_volume": "resistance training volume muscle hypertrophy dose response",
    "training_frequency": "resistance training frequency muscle strength hypertrophy",
    "protein_intake": "dietary protein intake muscle mass resistance training",
    "protein_timing": "nutrient timing protein intake muscle nutrients supplementation",
    "energy_surplus": "overfeeding lean body mass resistance trained athletes nutrition",
    "progressive_overload": "training load progression repetition muscle strength adaptation",
    # --- сушка / жиросжигание ---
    "energy_deficit": "caloric deficit energy restriction body composition",
    "muscle_retention_deficit": "protein energy restriction lean mass retention resistance training",
    "weight_loss_rate": "rate of weight loss body composition athletes",
    # --- поддержание / рекомпозиция / здоровье ---
    "body_recomposition": "concurrent fat loss muscle gain protein resistance training",
    "metabolic_adaptation": "adaptive thermogenesis metabolic adaptation energy restriction",
    # --- качество питания: углеводы / клетчатка ---
    "carb_quality": "carbohydrate quality whole grain glycemic metabolic health",
    "dietary_fiber": "dietary fiber satiety body weight randomized",
    "glycemic_response": "glycemic index glycemic response postprandial carbohydrate",
    "saturated_fat": "saturated fat cardiometabolic health dietary",
    # --- сопутствующее ---
    "creatine": "creatine supplementation muscle strength resistance training",
    "sleep_recovery": "sleep recovery muscle strength athletic performance",
    "meal_frequency": "meal frequency body composition protein distribution",
}


def _slug_id(doi: str | None, openalex_id: str) -> str:
    """Стабильный id: slug из DOI; нет DOI → openalex-<key>."""
    if doi:
        d = doi.lower().replace("https://doi.org/", "").strip("/")
        return re.sub(r"[^a-z0-9]+", "-", d).strip("-")
    return "openalex-" + openalex_id.rsplit("/", 1)[-1].lower()


def _reconstruct_abstract(inverted: dict | None) -> str:
    """OpenAlex отдаёт абстракт как inverted index {слово: [позиции]} — собрать обратно."""
    if not inverted:
        return ""
    positions: list[tuple[int, str]] = []
    for word, idxs in inverted.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)


def _classify(title: str, abstract: str) -> str:
    """Грубый тип исследования по тексту (для разнообразия/приоритета)."""
    t = f"{title} {abstract}".lower()
    if "meta-analysis" in t or "meta analysis" in t:
        return "meta-analysis"
    if "systematic review" in t:
        return "systematic-review"
    if "randomized" in t or "randomised" in t or "randomized controlled" in t:
        return "RCT"
    if "review" in t or "position stand" in t or "consensus" in t:
        return "review"
    return "study"


# Маркеры протоколов исследований (дизайн, а не результаты) — такие не цитируем в отчёте.
_PROTOCOL_MARKERS = ("study protocol", "protocol for", "trial protocol", "rationale and design", "rationale and study design", ": a protocol", "study design and")
# Тема-якорь: тренировка/питание/состав тела (обязан быть хоть один).
_ANCHOR_TERMS = (
    "protein", "muscle", "hypertroph", "resistance training", "strength training",
    "diet", "calorie", "caloric", "energy intake", "energy restriction", "carbohydrate",
    "fiber", "fibre", "lean mass", "creatine", "sleep", "glycemic", "glycaemic",
    "satiety", "saturated fat", "overfeeding", "macronutrient", "supplementation",
)
# Исход-якорь: работа должна РЕАЛЬНО измерять состав тела / силу / синтез / метаболизм.
_OUTCOME_TERMS = (
    "hypertroph", "lean mass", "fat mass", "fat-free mass", "fat free mass",
    "body composition", "muscle mass", "muscle strength", "1rm", "one repetition",
    "muscle protein synthesis", "protein synthesis", "satiety", "weight loss",
    "body weight", "body fat", "glycemic", "glycaemic", "muscle size",
    "cross-sectional area", "fat loss", "energy expenditure", "resting metabolic",
    "strength gain", "lean body mass", "muscle thickness",
)
# Деньлист: клинические болезни/нерелевант/хищные журналы — отсеиваем по title+journal.
_DENY_TERMS = (
    "kidney", "ckd", "dialysis", "renal", "cardiac", "cardiovascular disease", "cancer",
    "oncolog", "tumour", "tumor", "depression", "cognit", "dementia", "alzheimer",
    "menstrual", "elastography", "nursing", "dental", "periodont", "pregnan", "covid",
    "sars-cov", "editorial", "nutraceutical", "magnetic field", "pemf", "pulsed magnetic",
    "hypoxia", "kaatsu", "occlusion", "blood flow restriction", "chronotype",
    "neuro-cognition", "sympathetic", "schizophren", "rotator cuff", "shear wave",
    "asian indians", "diabetes management", "adenosine", "interesterified", "odd-chain",
)


def is_quality(study: dict) -> bool:
    """Качество-гейт: реальная аннотация, не протокол, на тему фитнеса/питания с измеримым исходом."""
    abstract = (study.get("abstract") or "").strip()
    if len(abstract) < 250:  # пустая/обрывочная аннотация — нечего цитировать
        return False
    title_l = (study.get("title") or "").lower()
    journal_l = (study.get("journal") or "").lower()
    if any(m in title_l for m in _PROTOCOL_MARKERS):
        return False
    if any(d in title_l or d in journal_l for d in _DENY_TERMS):
        return False
    text = f"{title_l} {abstract.lower()}"
    return any(a in text for a in _ANCHOR_TERMS) and any(o in text for o in _OUTCOME_TERMS)


def _authors(authorships: list[dict]) -> list[str]:
    return [
        a["author"]["display_name"]
        for a in authorships
        if a.get("author", {}).get("display_name")
    ][:12]


def fetch_topic(client: httpx.Client, query: str, per_page: int, email: str) -> list[dict]:
    """Релевантные OA-работы по теме (сорт по цитируемости). Возвращает сырые записи OpenAlex."""
    params = {
        "filter": f"title_and_abstract.search:{query},open_access.is_oa:true,type:article",
        "sort": "cited_by_count:desc",
        "per-page": str(per_page),
        "select": (
            "id,doi,title,publication_year,cited_by_count,authorships,"
            "primary_location,best_oa_location,locations,open_access,abstract_inverted_index"
        ),
        "mailto": email,
    }
    resp = client.get(OPENALEX, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("results", [])


def _pdf_candidates(raw: dict) -> list[str]:
    """Все OA-ссылки на PDF из записи (best + все locations + oa_url), без дублей, в порядке.

    Unpaywall иногда отдаёт gated/landing URL (Tandfonline ?needAccess, страница NCBI) —
    поэтому собираем ВСЕ варианты и при скачивании берём первый, что реально отдаёт %PDF."""
    urls: list[str] = []
    bo = raw.get("best_oa_location") or {}
    if bo.get("pdf_url"):
        urls.append(bo["pdf_url"])
    for loc in raw.get("locations") or []:
        if loc.get("is_oa") and loc.get("pdf_url"):
            urls.append(loc["pdf_url"])
    oa_url = (raw.get("open_access") or {}).get("oa_url") or ""
    if oa_url.lower().endswith(".pdf"):
        urls.append(oa_url)
    seen: set[str] = set()
    return [u for u in urls if not (u in seen or seen.add(u))]


def to_study(raw: dict, topic: str) -> dict:
    """Нормализовать запись OpenAlex в наш формат studies.json (+ транзиентный _pdf_urls)."""
    doi = (raw.get("doi") or "").replace("https://doi.org/", "") or None
    title = raw.get("title") or ""
    abstract = _reconstruct_abstract(raw.get("abstract_inverted_index"))
    pl = raw.get("primary_location") or {}
    candidates = _pdf_candidates(raw)
    return {
        "id": _slug_id(doi, raw["id"]),
        "title": title,
        "authors": _authors(raw.get("authorships") or []),
        "year": raw.get("publication_year"),
        "journal": (pl.get("source") or {}).get("display_name"),
        "doi": doi,
        "url": f"https://doi.org/{doi}" if doi else raw.get("id"),
        "oa_pdf_url": candidates[0] if candidates else None,
        "pdf_path": None,
        "abstract_path": None,
        "topics": [topic],
        "study_type": _classify(title, abstract),
        "abstract": abstract,
        "source_api": "openalex",
        "is_open_access": bool((raw.get("open_access") or {}).get("is_oa")),
        "cited_by_count": raw.get("cited_by_count"),
        "fetched_at": None,  # проставим при записи
        "_pdf_urls": candidates,  # транзиент: убирается перед записью индекса
    }


def collect(
    client: httpx.Client, topics: dict[str, str], email: str
) -> tuple[dict[str, dict], dict[str, list[str]]]:
    """Собрать кандидатов по темам. Возвращает (study по id, порядок id внутри темы).

    Дедуп по id: работа закрепляется за первой нашедшей темой; остальные темы добавляются
    в study['topics']. Реальный отбор (с PDF) и баланс по теме — в фазе скачивания."""
    by_id: dict[str, dict] = {}
    order: dict[str, list[str]] = {}
    for topic, query in topics.items():
        try:
            raw = fetch_topic(client, query, per_page=25, email=email)
        except httpx.HTTPError as exc:
            print(f"  ! {topic}: ошибка запроса: {exc}", file=sys.stderr)
            order[topic] = []
            continue
        ids: list[str] = []
        for r in raw:
            if not r.get("doi"):
                continue
            study = to_study(r, topic)
            if not study["_pdf_urls"] or not is_quality(study):
                continue
            existing = by_id.get(study["id"])
            if existing:
                if topic not in existing["topics"]:
                    existing["topics"].append(topic)
            else:
                by_id[study["id"]] = study
            ids.append(study["id"])
        order[topic] = ids
        print(f"  · {topic}: кандидатов {len(ids)}")
        time.sleep(0.2)
    return by_id, order


def download_pdf(client: httpx.Client, study: dict) -> bool:
    """Скачать PDF в research/pdfs/<id>.pdf, перебирая кандидатов. Проверка %PDF + размер."""
    dest = PDF_DIR / f"{study['id']}.pdf"
    if dest.exists() and dest.stat().st_size >= _MIN_PDF_BYTES:
        study["pdf_path"] = str(dest.relative_to(REPO_ROOT))
        return True
    for url in study.get("_pdf_urls", []):
        try:
            with client.stream("GET", url, timeout=60, follow_redirects=True) as resp:
                if resp.status_code != 200:
                    continue
                chunks = bytearray()
                for chunk in resp.iter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > 40_000_000:  # потолок 40 МБ
                        break
        except httpx.HTTPError:
            continue
        if bytes(chunks[:5]) == b"%PDF-" and len(chunks) >= _MIN_PDF_BYTES:
            dest.write_bytes(chunks)
            study["pdf_path"] = str(dest.relative_to(REPO_ROOT))
            study["oa_pdf_url"] = url  # тот URL, что реально сработал
            return True
    return False


def write_abstract(study: dict) -> None:
    if not study.get("abstract"):
        return
    path = ABSTRACT_DIR / f"{study['id']}.txt"
    path.write_text(study["abstract"], encoding="utf-8")
    study["abstract_path"] = str(path.relative_to(REPO_ROOT))


def load_index() -> dict[str, dict]:
    if not INDEX_PATH.exists():
        return {}
    try:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {s["id"]: s for s in data.get("studies", [])}


def write_index(studies: list[dict], now_iso: str) -> None:
    studies_sorted = sorted(studies, key=lambda s: s["id"])
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso,
        "total_studies": len(studies_sorted),
        "studies": studies_sorted,
    }
    INDEX_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--email", default="research@example.com", help="mailto для вежливого пула OpenAlex")
    p.add_argument("--per-topic", type=int, default=4, help="сколько работ с PDF брать на тему")
    p.add_argument("--topic", default=None, help="ограничиться одной темой (ключ из TOPICS)")
    p.add_argument("--query", default=None, help="переопределить поисковый запрос (с --topic)")
    p.add_argument("--no-pdf", action="store_true", help="не качать PDF (только метаданные)")
    p.add_argument("--dry-run", action="store_true", help="показать план запросов и выйти")
    p.add_argument("--prune", action="store_true", help="прогнать индекс через качество-гейт, убрать слабое")
    return p.parse_args(argv)


def prune_index() -> int:
    """Применить качество-гейт к текущему индексу: убрать слабые записи + их файлы."""
    merged = load_index()
    if not merged:
        print("Индекс пуст — нечего чистить.")
        return 0
    dropped = [s for s in merged.values() if not is_quality(s)]
    for s in dropped:
        for rel in (s.get("pdf_path"), s.get("abstract_path")):
            if rel:
                (REPO_ROOT / rel).unlink(missing_ok=True)
        print(f"  − {s['id']} | {s.get('journal')} | {(s.get('title') or '')[:60]}")
    kept = [s for s in merged.values() if is_quality(s)]
    write_index(kept, dt.datetime.now(dt.UTC).isoformat())
    print(f"Убрано {len(dropped)}, осталось {len(kept)}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.prune:
        return prune_index()
    if args.topic is not None:
        topics = {args.topic: args.query or TOPICS.get(args.topic, args.query)}
    else:
        topics = TOPICS

    if args.dry_run:
        print(f"Тем: {len(topics)}, по {args.per_topic} с PDF/тему → ориентир ~{len(topics) * args.per_topic}")
        for t, q in topics.items():
            print(f"  {t}: {q}")
        return 0

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    ABSTRACT_DIR.mkdir(parents=True, exist_ok=True)
    now_iso = dt.datetime.now(dt.UTC).isoformat()

    with httpx.Client(
        headers={"User-Agent": f"abs-research-corpus (mailto:{args.email})"},
        follow_redirects=True,
    ) as client:
        print(f"Сбор по {len(topics)} темам…")
        by_id, order = collect(client, topics, args.email)
        for study in by_id.values():
            study["fetched_at"] = now_iso

        kept: dict[str, dict] = {}
        if args.no_pdf:
            kept = by_id
        else:
            print("Скачиваю PDF (по темам, до --per-topic успехов на тему)…")
            for topic, ids in order.items():
                ok = 0
                for sid in ids:
                    if ok >= args.per_topic:
                        break
                    study = by_id[sid]
                    if study.get("pdf_path") or download_pdf(client, study):
                        kept[sid] = study
                        ok += 1
                    time.sleep(0.15)
                print(f"  · {topic}: PDF {ok}")
            print(f"С PDF: {len(kept)}")

        for study in kept.values():
            write_abstract(study)
            study.pop("_pdf_urls", None)

    merged = load_index()
    merged.update(kept)
    write_index(list(merged.values()), now_iso)
    with_pdf = sum(1 for s in merged.values() if s.get("pdf_path"))
    types: dict[str, int] = {}
    topics_count: dict[str, int] = {}
    for s in merged.values():
        types[s["study_type"]] = types.get(s["study_type"], 0) + 1
        for t in s["topics"]:
            topics_count[t] = topics_count.get(t, 0) + 1
    print(f"\nИтог: {len(merged)} исследований ({with_pdf} с PDF) → {INDEX_PATH.relative_to(REPO_ROOT)}")
    print("По типам:", dict(sorted(types.items(), key=lambda kv: -kv[1])))
    print("По темам:", dict(sorted(topics_count.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
