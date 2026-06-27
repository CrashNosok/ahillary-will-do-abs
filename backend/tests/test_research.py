"""Корпус исследований (services/research.py): загрузка, валидные id, evidence-pack.

Сети нет — работаем с фикстурой studies.json в tmp_path. Закрываем: парс полей в Study,
fail-open на отсутствии/битом файле, множество id для валидатора цитат, компактный пак с id.
"""

import json
from pathlib import Path

from app.services import research

_STUDIES = {
    "schema_version": 1,
    "studies": [
        {
            "id": "10-1249-vol",
            "title": "Resistance Training Volume",
            "authors": ["Schoenfeld BJ", "Ogborn D"],
            "year": 2017,
            "journal": "J Sports Sci",
            "doi": "10.1249/vol",
            "url": "https://doi.org/10.1249/vol",
            "topics": ["training_volume", "hypertrophy"],
            "study_type": "meta-analysis",
            "abstract": "Weekly set volume is dose-dependently related to muscle hypertrophy.",
            "pdf_path": "research/pdfs/10-1249-vol.pdf",
        },
        {
            "id": "10-1079-protein",
            "title": "Protein and exercise",
            "authors": ["Williams MH"],
            "year": 1999,
            "journal": "Br J Nutr",
            "doi": "10.1079/protein",
            "url": "https://doi.org/10.1079/protein",
            "topics": ["protein_intake"],
            "study_type": "review",
            "abstract": "Adequate protein supports strength and lean mass during training.",
            "pdf_path": None,
        },
    ],
}


def _write(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_load_corpus_parses_studies(tmp_path):
    corpus = research.load_corpus(_write(tmp_path / "studies.json", _STUDIES))
    assert len(corpus) == 2
    first = corpus[0]
    assert first.id == "10-1249-vol"
    assert first.authors == ("Schoenfeld BJ", "Ogborn D")
    assert first.study_type == "meta-analysis"
    assert "hypertrophy" in first.topics


def test_load_corpus_missing_file_returns_empty(tmp_path):
    assert research.load_corpus(tmp_path / "nope.json") == ()


def test_load_corpus_broken_json_returns_empty(tmp_path):
    bad = tmp_path / "studies.json"
    bad.write_text("{не json", encoding="utf-8")
    assert research.load_corpus(bad) == ()  # fail-open, без падения


def test_valid_citation_ids(tmp_path):
    corpus = research.load_corpus(_write(tmp_path / "studies.json", _STUDIES))
    assert research.valid_citation_ids(corpus) == frozenset({"10-1249-vol", "10-1079-protein"})


def test_build_evidence_pack_contains_ids_and_summaries(tmp_path):
    corpus = research.load_corpus(_write(tmp_path / "studies.json", _STUDIES))
    pack = research.build_evidence_pack(research.select_studies(corpus))
    assert "[10-1249-vol]" in pack and "[10-1079-protein]" in pack
    assert "Schoenfeld BJ et al." in pack  # автор + et al. при нескольких
    assert "dose-dependently" in pack  # резюме попало в пак


def test_select_studies_caps_at_limit(tmp_path):
    many = {"studies": [{"id": f"s{i}", "abstract": "x"} for i in range(50)]}
    corpus = research.load_corpus(_write(tmp_path / "studies.json", many))
    assert len(research.select_studies(corpus, limit=10)) == 10
