"""Keyword rules (pure). Comparison is case-insensitive; the first-seen casing is kept."""
from dataclasses import dataclass, field
from dataclasses import replace as _replace


@dataclass(frozen=True)
class Keywords:
    generated: list[str] = field(default_factory=list)
    manual: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)


def _dedupe(words) -> list[str]:
    seen, out = set(), []
    for w in words:
        if w.strip() and w.lower() not in seen:
            seen.add(w.lower())
            out.append(w)
    return out


def _without(words, drop) -> list[str]:
    d = {w.lower() for w in drop}
    return [w for w in words if w.lower() not in d]


def effective(k: Keywords) -> list[str]:
    """(generated - rejected) U manual."""
    return _dedupe(_without(k.generated, k.rejected) + k.manual)


def remove(k: Keywords, word: str) -> Keywords:
    """Leaves manual and always enters rejected, so regeneration doesn't bring it back."""
    return _replace(k, manual=_without(k.manual, [word]), rejected=_dedupe(k.rejected + [word]))


def add(k: Keywords, word: str) -> Keywords:
    """Enters manual and leaves rejected (rehabilitation)."""
    return _replace(k, manual=_dedupe(k.manual + [word]), rejected=_without(k.rejected, [word]))


def replace(k: Keywords, words: list[str]) -> Keywords:
    """manual = words; generated absent from words become rejected (earlier rejections not in words stay)."""
    return _replace(k, manual=_dedupe(words), rejected=_without(_dedupe(k.rejected + k.generated), words))


def regenerate(k: Keywords, generated: list[str]) -> Keywords:
    """Source update: generated replaced, manual and rejected kept."""
    return _replace(k, generated=_dedupe(generated))
