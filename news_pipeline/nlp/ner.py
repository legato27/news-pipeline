"""Local spaCy NER — runs in-process on cloud/api/worker.

Used by the OSINT pipeline to extract actors (PERSON/ORG/GPE/LOC/NORP) from
translated article text.

Env:
  NEWS_PIPELINE_NER_MODEL_EN  default "en_core_web_sm" (fast, 12MB).
                              set to "en_core_web_trf" for transformer quality.

The first call loads the model (~12MB for sm, ~500MB for trf) and caches it.
If spaCy isn't installed or the model isn't downloaded, returns empty lists
gracefully so the pipeline can still persist articles.
"""
from __future__ import annotations

import logging
import os


logger = logging.getLogger(__name__)

_nlp = None
_load_failed = False


def _model_name() -> str:
    return os.getenv("NEWS_PIPELINE_NER_MODEL_EN", "en_core_web_sm")


def _load():
    global _nlp, _load_failed
    if _nlp is not None or _load_failed:
        return _nlp
    try:
        import spacy
        _nlp = spacy.load(_model_name(), disable=["parser", "tagger", "lemmatizer"])
        logger.info("ner_model_loaded name=%s", _model_name())
    except Exception as e:
        logger.warning(
            "ner_model_load_failed name=%s err=%s hint='python -m spacy download %s'",
            _model_name(), e, _model_name(),
        )
        _load_failed = True
    return _nlp


def ner_batch(texts: list[str]) -> list[list[dict]]:
    """Batched NER. Returns per-text lists of {text, label, start, end}.
    Returns empty sub-lists on any failure so callers degrade gracefully.
    """
    if not texts:
        return []
    nlp = _load()
    if nlp is None:
        return [[] for _ in texts]

    try:
        out: list[list[dict]] = []
        for doc in nlp.pipe([t[:4000] for t in texts], batch_size=min(len(texts), 32)):
            out.append([
                {"text": ent.text, "label": ent.label_, "start": ent.start_char, "end": ent.end_char}
                for ent in doc.ents
            ])
        return out
    except Exception as e:
        logger.warning("ner_batch_failed err=%s", e)
        return [[] for _ in texts]
