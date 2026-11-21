"""Walidacja między dokumentami sprawy (reguły w config/case_checks.yaml).

Operatory porównujące dwa dokumenty: equals, in, contained_in, days_between.
Operatory na całej sprawie: one_of (wartość z listy w YAML-u), exists (wymagany dokument).
Każda reguła zwraca {name, status, detail}; status: ok / blad / ostrzezenie / pominieto.
Brak dokumentu albo danych to zawsze "pominieto", nigdy wyjątek.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import yaml

from . import settings
from .normalize import account, amount

CHECKS_FILE = settings.ROOT / "config" / "case_checks.yaml"


def load_checks(path: Path = CHECKS_FILE) -> list[dict]:
    if not path.exists():
        return []
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("checks", [])


def get_values(obj, path: str) -> list:
    """Wartości pod ścieżką; '[]' rozwija listę, '[0]' wybiera element. Pomija null-e."""
    cur = [obj]
    for key, idx in re.findall(r"([^.\[\]]+)|\[(\d*)\]", path):
        nxt = []
        for c in cur:
            if key:
                if isinstance(c, dict) and key in c:
                    nxt.append(c[key])
            elif isinstance(c, list):
                if idx == "":
                    nxt.extend(c)
                elif int(idx) < len(c):
                    nxt.append(c[int(idx)])
        cur = nxt
    return [v for v in cur if v not in (None, "")]


def _norm(v) -> str:
    return " ".join(str(v).split()).casefold()


# ------------------------------------------------------------------ kalendarz
def easter(year: int) -> date:
    """Niedziela Wielkanocna (algorytm Meeusa/Jonesa/Butchera, kalendarz gregoriański)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


@lru_cache(maxsize=None)
def polish_holidays(year: int) -> frozenset[date]:
    """Dni ustawowo wolne od pracy w Polsce (ustawa o dniach wolnych od pracy)."""
    fixed = [(1, 1), (1, 6), (5, 1), (5, 3), (8, 15), (11, 1), (11, 11), (12, 25), (12, 26)]
    if year >= 2025:                       # Wigilia wolna od 2025 r.
        fixed.append((12, 24))
    e = easter(year)
    moving = [e, e + timedelta(days=1),    # Wielkanoc, Poniedziałek Wielkanocny
              e + timedelta(days=49),      # Zielone Świątki
              e + timedelta(days=60)]      # Boże Ciało
    return frozenset([date(year, m, d) for m, d in fixed] + moving)


def is_day_off(d: date) -> bool:
    """Sobota, niedziela albo święto (art. 509 ust. 2 Pzp: sobota też przesuwa termin)."""
    return d.weekday() >= 5 or d in polish_holidays(d.year)


def deadline(start: date, days: int) -> date:
    """Koniec terminu liczonego w dniach od zdarzenia; dzień wolny przesuwa go na następny roboczy."""
    end = start + timedelta(days=days)
    while is_day_off(end):
        end += timedelta(days=1)
    return end


def _to_date(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


# ------------------------------------------------------------------ pomocnicze
_COMPARERS = {
    "amount": amount,
    "account": account,
    "text": _norm,
}


def _truthy(v) -> bool:
    return v not in (None, "", 0, "0", False)


def _docs(docs: list[dict], cls: str) -> list[dict]:
    return [d for d in docs if d.get("class_name") == cls]


def _result(name: str, status: str, detail: str) -> dict:
    return {"name": name, "status": status, "detail": detail}


def _condition_met(docs: list[dict], cond: dict | None) -> bool:
    """when: {doc: X} -> jest dokument X;  when: {doc: X, any: [ścieżki]} -> któraś ścieżka niepusta."""
    if not cond:
        return True
    found = _docs(docs, cond["doc"])
    if not found:
        return False
    paths = cond.get("any") or ([cond["path"]] if cond.get("path") else [])
    if not paths:
        return True
    return any(_truthy(v) for d in found for p in paths for v in get_values(d["json"], p))


# ------------------------------------------------------------------ operatory
def _pairwise(c: dict, docs: list[dict]) -> list[dict]:
    """equals / in / contained_in / days_between: lewy dokument vs prawy."""
    lefts, rights = _docs(docs, c["left"]["doc"]), _docs(docs, c["right"]["doc"])
    if not lefts or not rights:
        missing = c["left"]["doc"] if not lefts else c["right"]["doc"]
        return [_result(c["name"], "pominieto", f"brak dokumentu: {missing}")]
    same_doc = c["left"]["doc"] == c["right"]["doc"]
    out = []
    for ld in lefts:
        name = c["name"] + (f" ({ld['name']})" if len(lefts) > 1 else "")
        lv = get_values(ld["json"], c["left"]["path"])
        rsrc = [ld] if same_doc else rights
        rv = [v for d in rsrc for v in get_values(d["json"], c["right"]["path"])]
        if not lv or not rv:
            out.append(_result(name, "pominieto", "brak wartości do porównania"))
            continue
        if c["op"] == "days_between":
            out.append(_days_between(c, name, lv[0], rv[0]))
            continue
        left, rights_n = _norm(lv[0]), [_norm(v) for v in rv]
        ok = {"equals": lambda: left in rights_n,
              "in": lambda: left in rights_n,
              "contained_in": lambda: any(left in r for r in rights_n)}[c["op"]]()
        out.append(_result(name, "ok" if ok else c.get("severity", "blad"),
                           f"{lv[0]}" if ok else f"„{lv[0]}” nie pasuje do wartości z drugiego dokumentu"))
    return out


def _days_between(c: dict, name: str, start_raw, end_raw) -> dict:
    start, end = _to_date(start_raw), _to_date(end_raw)
    if not start or not end:
        return _result(name, "pominieto", "nieczytelna data")
    max_days = int(c.get("max_days", 10))
    n = (end - start).days
    limit = deadline(start, max_days)
    shifted = ", przesunięty z powodu dnia wolnego" if limit != start + timedelta(days=max_days) else ""
    info = (f"odwołanie wniesione {n} dni po czynności ({start} → {end}), "
            f"termin {max_days} dni upływa {limit}{shifted}")
    if n < 0:
        return _result(name, c.get("severity", "blad"), f"data odwołania ({end}) jest wcześniejsza niż czynność ({start})")
    return _result(name, "ok" if end <= limit else c.get("severity", "blad"), info)


def _one_of(c: dict, docs: list[dict]) -> list[dict]:
    """Wartość pod ścieżką w KTÓRYMKOLWIEK dokumencie danego typu jest na liście `values`."""
    allowed = c.get("values") or []
    if not allowed:
        return [_result(c["name"], "pominieto", "brak listy wartości w case_checks.yaml (do uzupełnienia)")]
    src = c["left"]
    found = _docs(docs, src["doc"])
    if not found:
        return [_result(c["name"], "pominieto", f"brak dokumentu: {src['doc']}")]
    conv = _COMPARERS[c.get("compare", "text")]
    allowed_n = {conv(v) for v in allowed} - {None}
    values = [v for d in found for v in get_values(d["json"], src["path"])]
    if not values:
        return [_result(c["name"], "pominieto", "brak wartości do porównania")]
    hits = [v for v in values if conv(v) in allowed_n]
    shown = ", ".join(str(v) for v in values)
    if hits:
        return [_result(c["name"], "ok", f"{hits[0]}")]
    return [_result(c["name"], c.get("severity", "blad"),
                    f"znaleziono: {shown}; oczekiwano jednej z: {', '.join(str(v) for v in allowed)}")]


def _exists(c: dict, docs: list[dict]) -> list[dict]:
    """W sprawie musi być dokument `require.doc` (opcjonalnie gdy spełniony warunek `when`)."""
    need = c["require"]["doc"]
    if _docs(docs, need):
        return [_result(c["name"], "ok", f"jest dokument: {need}")]
    return [_result(c["name"], c.get("severity", "blad"), c.get("message", f"brak dokumentu: {need}"))]


_OPS = {"equals": _pairwise, "in": _pairwise, "contained_in": _pairwise, "days_between": _pairwise,
        "one_of": _one_of, "exists": _exists}


def run_checks(docs: list[dict], checks: list[dict] | None = None) -> list[dict]:
    """docs: [{"name": plik, "class_name": typ, "json": wynik}]. Zwraca listę wyników reguł."""
    checks = load_checks() if checks is None else checks
    out = []
    for c in checks:
        op = _OPS.get(c.get("op"))
        if op is None:
            out.append(_result(c.get("name", "?"), "pominieto", f"nieznany operator: {c.get('op')}"))
            continue
        when = c.get("when")
        if when and not _docs(docs, when["doc"]):
            out.append(_result(c["name"], "pominieto", f"brak dokumentu: {when['doc']}"))
            continue
        if not _condition_met(docs, when):
            out.append(_result(c["name"], "pominieto", "nie dotyczy tej sprawy"))
            continue
        try:
            out.extend(op(c, docs))
        except Exception as exc:          # zła reguła albo dziwne dane - nie wywracamy walidacji
            out.append(_result(c["name"], "pominieto", f"nie udało się sprawdzić: {exc}"))
    return out
