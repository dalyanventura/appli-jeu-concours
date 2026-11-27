"""Closing date of a contest, read from French captions.

"jusqu'au 29 novembre 2026 à 23h59", "fin du concours : dimanche 29 novembre", "tirage au sort le 07/12",
"du 28 novembre au 6 décembre", "24H POUR PARTICIPER", "tirage dimanche" (next Sunday).
Priority: end of participation > draw date > earliest other future date (often the event itself).
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from collector.normalize import fold

MONTHS = {
    "janvier": 1, "janv": 1, "fevrier": 2, "fevr": 2, "fev": 2, "mars": 3, "avril": 4, "avr": 4, "mai": 5,
    "juin": 6, "juillet": 7, "juil": 7, "aout": 8, "septembre": 9, "sept": 9, "octobre": 10, "oct": 10,
    "novembre": 11, "nov": 11, "decembre": 12, "dec": 12,
}
WEEKDAYS = {"lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3, "vendredi": 4, "samedi": 5, "dimanche": 6}

WRITTEN = re.compile(r"\b(\d{1,2})(?:er)?\s+(" + "|".join(sorted(MONTHS, key=len, reverse=True))
                     + r")\.?(?![a-z])(?:\s+(20\d\d))?")
NUMERIC = re.compile(r"(?<![\d/.,])(\d{1,2})[/.](\d{1,2})(?:[/.](20\d\d|\d\d))?(?![\d/]|[.,]\d|\s?(?:€|%|euros?))")
_WEEKDAY = r"(?:(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche) )?"
END_CONTEXT = re.compile(r"jusqu|\bfin\b|termine|cloture|avant le|au plus tard|dernier jour|deadline|limite"
                         r"|\bends?\b|\bau " + _WEEKDAY + r"$")      # "du 28 novembre au (samedi) 6 décembre"
DRAW_CONTEXT = re.compile(r"tirage|tire|resultat|annonce|gagnant|designe")


def _last(rx: re.Pattern, text: str) -> int:
    return max((m.end() for m in rx.finditer(text)), default=-1)
HOURS_TO_ENTER = re.compile(r"\b(24|48|72) ?h(?:eures)? pour (?:participer|jouer|tenter)")
WEEKDAY_DRAW = re.compile(r"(?:tirage|fin|jusqu'a|resultats?)[^.\n]{0,25}?\b(" + "|".join(WEEKDAYS)
                          + r")\b(?!\s*\d)")

MAX_AHEAD = timedelta(days=120)


def _resolve(day: int, month: int, year: int | None, published: date) -> date | None:
    years = [year] if year else [published.year, published.year + 1]
    for y in years:
        try:
            candidate = date(y, month, day)
        except ValueError:
            return None
        if year or candidate >= published - timedelta(days=7):
            if published - timedelta(days=7) <= candidate <= published + MAX_AHEAD:
                return candidate
            return None
    return None


def _dates(text: str, published: date) -> list[tuple[int, date]]:
    """(position, date) of every plausible date in the text."""
    found = []
    for m in WRITTEN.finditer(text):
        d = _resolve(int(m.group(1)), MONTHS[m.group(2)], int(m.group(3)) if m.group(3) else None, published)
        if d:
            found.append((m.start(), d))
    for m in NUMERIC.finditer(text):
        day, month, year = int(m.group(1)), int(m.group(2)), m.group(3)
        if not 1 <= month <= 12:
            continue
        full_year = (2000 + int(year) if len(year) == 2 else int(year)) if year else None
        d = _resolve(day, month, full_year, published)
        if d:
            found.append((m.start(), d))
    return found


def extract_deadline(caption: str | None, published: date) -> date | None:
    text = fold(caption)
    if not text:
        return None
    ends, draws, others = [], [], []
    for pos, d in _dates(text, published):
        before = text[max(0, pos - 45):pos]
        end_at, draw_at = _last(END_CONTEXT, before), _last(DRAW_CONTEXT, before)
        if end_at >= 0 and end_at >= draw_at:      # the closest cue before the date decides
            ends.append(d)
        elif draw_at >= 0:
            draws.append(d)
        else:
            others.append(d)
    if ends:
        return max(ends)
    if draws:
        return min(draws)
    if m := HOURS_TO_ENTER.search(text):
        return published + timedelta(days=int(m.group(1)) // 24)
    if m := WEEKDAY_DRAW.search(text):
        ahead = (WEEKDAYS[m.group(1)] - published.weekday()) % 7 or 7
        return published + timedelta(days=ahead)
    future = [d for d in others if d >= published]
    return min(future) if future else None
