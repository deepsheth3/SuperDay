"""Normalization helpers for index keys."""
import re
import unicodedata


def slugify(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    return re.sub(r"[-\s]+", "-", s)


def state_key(state: str) -> str:
    if not state:
        return ""
    t = state.strip().upper()
    if len(t) == 2:
        return t
    return slugify(t)[:2].upper() if len(slugify(t)) >= 2 else t


def industry_key(industry: str) -> str:
    return slugify(industry or "") or ""


def person_key(name: str) -> str:
    return slugify(name or "") or ""
