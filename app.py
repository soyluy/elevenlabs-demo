"""Deniz-1 crew service: a tiny stand-in for a customer's system.

Everything the agent asks about (who is on board, free beds, rotation dates)
is derived from one roster at request time. Nothing is stored as a count, so a
backdated correction to the roster fixes every answer at once.

Run:  uvicorn app:app --port 8000
"""

from __future__ import annotations

import os
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from difflib import SequenceMatcher

from fastapi import Depends, FastAPI, Header, HTTPException, Query

# --------------------------------------------------------------------------- data

CABIN_CAPACITY: dict[str, int] = {
    "K-101": 1,
    "K-102": 2,
    "K-103": 1,
    "K-104": 2,
    "K-105": 1,
    "K-106": 2,
    "K-107": 2,
}


@dataclass(frozen=True)
class Person:
    name: str
    role: str
    cabin: str
    embark: date  # counted on board from this day
    disembark: date  # leaves in the morning; not counted on this day
    relief: str | None = None
    note: str | None = None

    def on_board(self, day: date) -> bool:
        return self.embark <= day < self.disembark


D = date
ROSTER: list[Person] = [
    Person("Ali Yılmaz", "Kaptan", "K-101", D(2026, 9, 23), D(2026, 10, 8), relief="Orhan Erdem"),
    Person("Ali Yıldız", "Güverte Zabiti", "K-102", D(2026, 10, 1), D(2026, 10, 29)),
    Person(
        "Burak Öztürk", "Makine Zabiti", "K-102", D(2026, 10, 1), D(2026, 10, 29),
        note="Biniş tarihi 6 Ekim'de düzeltildi; eski kayıtta 3 Ekim yazıyordu.",
    ),
    Person("Ayşe Demir", "Sondaj Mühendisi", "K-103", D(2026, 9, 30), D(2026, 10, 14), relief="Selin Aksoy"),
    Person("Mehmet Çelik", "Telsiz Operatörü", "K-104", D(2026, 9, 25), D(2026, 10, 9), relief="Gökhan Arslan"),
    Person("Zeynep Şahin", "Sağlık Görevlisi", "K-105", D(2026, 10, 2), D(2026, 10, 16)),
    Person("Emre Koç", "Aşçı", "K-106", D(2026, 9, 20), D(2026, 10, 7), relief="Cem Polat"),
    Person("Serkan Aydın", "Aşçı Yardımcısı", "K-106", D(2026, 9, 28), D(2026, 10, 12)),
    Person("Hakan Kaya", "Elektrik Teknisyeni", "K-107", D(2026, 10, 3), D(2026, 10, 17)),
    Person("Deniz Kurt", "Vinç Operatörü", "K-107", D(2026, 10, 5), D(2026, 10, 19)),
    Person("Orhan Erdem", "Kaptan", "K-101", D(2026, 10, 8), D(2026, 11, 5)),
    Person("Cem Polat", "Aşçı", "K-106", D(2026, 10, 8), D(2026, 10, 22)),
    Person("Gökhan Arslan", "Telsiz Operatörü", "K-104", D(2026, 10, 9), D(2026, 10, 23)),
    Person("Selin Aksoy", "Sondaj Mühendisi", "K-103", D(2026, 10, 14), D(2026, 10, 28)),
]

# ------------------------------------------------------------------------ helpers

TR_MONTHS = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]


def tr_date(d: date) -> str:
    """'8 Ekim 2026': a form the voice can read aloud naturally."""
    return f"{d.day} {TR_MONTHS[d.month - 1]} {d.year}"


def today() -> date:
    """Server-side 'today'. DEMO_TODAY=2026-10-07 pins it for repeatable demos."""
    pinned = os.getenv("DEMO_TODAY")
    return date.fromisoformat(pinned) if pinned else date.today()


def resolve_day(day_offset: int, on_date: str | None) -> date:
    """The model never does date arithmetic: it passes 0 for today, 1 for tomorrow."""
    if on_date:
        try:
            return date.fromisoformat(on_date)
        except ValueError as exc:
            raise HTTPException(422, "on_date must be YYYY-MM-DD") from exc
    return today() + timedelta(days=day_offset)


_TR_FOLD = str.maketrans({"İ": "i", "I": "ı"})


def fold(text: str) -> str:
    """Turkish-aware lowercase, then strip diacritics: 'Yıldız' -> 'yildiz'."""
    lowered = text.translate(_TR_FOLD).lower().replace("ı", "i")
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).strip()


def name_score(query: str, full_name: str) -> float:
    q, n = fold(query), fold(full_name)
    if q == n:
        return 1.0
    whole = SequenceMatcher(None, q, n).ratio()
    # Per-token: every word the caller said should match some word of the name.
    q_tokens, n_tokens = q.split(), n.split()
    per_token = sum(
        max(SequenceMatcher(None, qt, nt).ratio() for nt in n_tokens) for qt in q_tokens
    ) / len(q_tokens)
    return max(whole, per_token)


def person_view(p: Person, day: date) -> dict:
    return {
        "name": p.name,
        "role": p.role,
        "cabin": p.cabin,
        "embark": tr_date(p.embark),
        "disembark": tr_date(p.disembark),
        "on_board_on_date": p.on_board(day),
        "relief": p.relief,
        "note": p.note,
    }


# --------------------------------------------------------------------------- app

app = FastAPI(title="Deniz-1 crew service (demo)")


def check_key(x_demo_key: str | None = Header(default=None)) -> None:
    """Optional shared secret, sent by the agent as a header."""
    expected = os.getenv("DEMO_KEY")
    if expected and x_demo_key != expected:
        raise HTTPException(401, "bad or missing X-Demo-Key")


@app.get("/pob", dependencies=[Depends(check_key)])
def personnel_on_board(
    day_offset: int = Query(0, ge=-30, le=60),
    on_date: str | None = None,
) -> dict:
    day = resolve_day(day_offset, on_date)
    aboard = [p for p in ROSTER if p.on_board(day)]
    return {
        "date": tr_date(day),
        "count": len(aboard),
        "people": [{"name": p.name, "role": p.role, "cabin": p.cabin} for p in aboard],
        "embarking_this_day": [p.name for p in ROSTER if p.embark == day],
        "disembarking_this_day": [p.name for p in ROSTER if p.disembark == day],
    }


@app.get("/cabins/free", dependencies=[Depends(check_key)])
def free_beds(
    day_offset: int = Query(0, ge=-30, le=60),
    on_date: str | None = None,
) -> dict:
    day = resolve_day(day_offset, on_date)
    occupied = {cabin: 0 for cabin in CABIN_CAPACITY}
    for p in ROSTER:
        if p.on_board(day):
            occupied[p.cabin] += 1
    cabins = [
        {"cabin": c, "capacity": cap, "occupied": occupied[c], "free": cap - occupied[c]}
        for c, cap in CABIN_CAPACITY.items()
        if cap - occupied[c] > 0
    ]
    return {
        "date": tr_date(day),
        "free_beds_total": sum(c["free"] for c in cabins),
        "cabins_with_free_beds": cabins,
    }


@app.get("/people", dependencies=[Depends(check_key)])
def find_person(name: str = Query(..., min_length=2)) -> dict:
    day = today()
    scored = sorted(
        ((name_score(name, p.name), p) for p in ROSTER), key=lambda sp: sp[0], reverse=True
    )
    matches = [p for score, p in scored if score >= 0.75]
    exact = [p for score, p in scored if score == 1.0]
    if exact:
        matches = exact
    return {
        "query": name,
        "match_count": len(matches),
        # More than one candidate: the agent should ask which person was meant.
        "ambiguous": len(matches) > 1,
        "matches": [person_view(p, day) for p in matches],
    }
