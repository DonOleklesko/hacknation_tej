from odw.crosscheck import get_values, run_checks

ODW = {"class_name": "odwolanie", "name": "odwolanie.pdf", "json": {
    "Odwolujacy": [{"krs": "9992397370", "nip": "9995126748", "nazwa": "Gildentia sp. z o.o.",
                    "pelnomocnik": {"imie_nazwisko": "Patrycja Furman"}}],
    "ZamowieniePubliczne": {"numer_postepowania": "ZP.447.2026"}}}
PEL = {"class_name": "pelnomocnictwo", "name": "pel.pdf", "json": {
    "mocodawca": [{"data": {"krs": "9992397370", "nip": "9995126748", "nazwa": "GILDENTIA  sp. z o.o."}}],
    "pelnomocnicy": [{"imie_nazwisko": "Patrycja Furman"}, {"imie_nazwisko": "Inny Prawnik"}]}}
PRZ = {"class_name": "przelew", "name": "prz.pdf", "json": {"przelew_bankowy": {
    "tytul": "opłata skarbowa od pełnomocnictwa dla Patrycja Furman w przetargu ZP.447.2026 CEN1"}}}


def by_name(res):
    return {r["name"]: r["status"] for r in res}


def test_get_values_expands_lists_and_skips_nulls():
    assert get_values(PEL["json"], "pelnomocnicy[].imie_nazwisko") == ["Patrycja Furman", "Inny Prawnik"]
    assert get_values(PEL["json"], "mocodawca[0].data.nazwa") == ["GILDENTIA  sp. z o.o."]
    assert get_values({"a": None}, "a") == []


ORIGINAL_CHECKS = [
    "Pełnomocnik z odwołania występuje w pełnomocnictwie",
    "KRS Odwołującego zgadza się z KRS mocodawcy",
    "NIP Odwołującego zgadza się z NIP mocodawcy",
    "Nazwa Odwołującego zgadza się z nazwą mocodawcy",
    "Numer postępowania z odwołania jest w tytule przelewu",
    "Pełnomocnik z odwołania jest w tytule przelewu (opłata skarbowa)",
]


def test_consistent_case_passes_all_checks():
    res = by_name(run_checks([ODW, PEL, PRZ]))
    assert all(res[n] == "ok" for n in ORIGINAL_CHECKS)
    assert "blad" not in res.values()


def test_mismatch_is_reported():
    bad = {**PEL, "json": {**PEL["json"], "pelnomocnicy": [{"imie_nazwisko": "Ktoś Inny"}]}}
    res = by_name(run_checks([ODW, bad, PRZ]))
    assert res["Pełnomocnik z odwołania występuje w pełnomocnictwie"] == "blad"


def test_missing_documents_are_skipped_not_failed():
    res = by_name(run_checks([ODW]))
    assert all(res[n] == "pominieto" for n in ORIGINAL_CHECKS)
    # reguły kompletności to właśnie wyłapują
    assert res["Jest pełnomocnictwo (odwołanie wnosi pełnomocnik)"] == "blad"
    assert res["Jest potwierdzenie wpisu"] == "blad"


# ---------------------------------------------------------------- reguły merytoryczne
from datetime import date

import pytest

from odw.crosscheck import deadline, easter, is_day_off, load_checks

TERMIN = "Odwołanie wniesione w terminie (art. 515 Pzp)"
WPIS = "Kwota wpisu od odwołania"
SKARB = "Opłata skarbowa od pełnomocnictwa (17 zł)"
RACHUNEK = "Wpis wpłacony na rachunek UZP"
JEST_PEL = "Jest pełnomocnictwo (odwołanie wnosi pełnomocnik)"
JEST_PRZ = "Jest potwierdzenie wpisu"


def odw(czynnosc=None, data=None, przez=1, pelnomocnik="Patrycja Furman"):
    return {"class_name": "odwolanie", "name": "odwolanie.pdf", "json": {
        "OdwolanieKIO": {"czynnosc_dzien": czynnosc, "data": data},
        "Odwolujacy": [{"przez-pelnomocnika": przez, "pelnomocnik": {"imie_nazwisko": pelnomocnik}}]}}


def prz(kwota, rachunek=None, name="prz.pdf"):
    return {"class_name": "przelew", "name": name,
            "json": {"przelew_bankowy": {"kwota": kwota, "na_rachunek": rachunek}}}


def only(name, checks=None):
    return [c for c in (checks or load_checks()) if c["name"] == name]


def status(docs, name, checks=None):
    res = run_checks(docs, only(name, checks))
    assert len(res) == 1
    return res[0]


def test_easter_and_holidays():
    assert easter(2024) == date(2024, 3, 31)
    assert easter(2025) == date(2025, 4, 20)
    assert easter(2026) == date(2026, 4, 5)
    assert is_day_off(date(2026, 4, 6))          # Poniedziałek Wielkanocny
    assert is_day_off(date(2026, 6, 4))          # Boże Ciało (Wielkanoc + 60)
    assert is_day_off(date(2026, 12, 24))        # Wigilia (od 2025)
    assert not is_day_off(date(2024, 12, 24))
    assert is_day_off(date(2026, 11, 14))        # sobota
    assert not is_day_off(date(2026, 11, 13))    # piątek


def test_deadline_saturday_moves_to_monday():
    assert deadline(date(2026, 11, 4), 10) == date(2026, 11, 16)


def test_deadline_christmas_moves_past_holidays_and_weekend():
    # 25.12.2026 piątek -> 26 sobota (św.) -> 27 niedziela -> 28 poniedziałek
    assert deadline(date(2026, 12, 15), 10) == date(2026, 12, 28)


def test_deadline_easter_monday():
    assert deadline(date(2026, 3, 27), 10) == date(2026, 4, 7)


def test_termin_ok_on_last_day():
    assert status([odw("2026-11-04", "2026-11-14")], TERMIN)["status"] == "ok"
    assert status([odw("2026-11-04", "2026-11-16")], TERMIN)["status"] == "ok"   # przesunięty


def test_termin_late():
    r = status([odw("2026-11-04", "2026-11-17")], TERMIN)
    assert r["status"] == "blad"
    assert "13 dni" in r["detail"] and "10 dni" in r["detail"]


def test_termin_easter_monday_appeal_on_tuesday_is_ok():
    assert status([odw("2026-03-27", "2026-04-07")], TERMIN)["status"] == "ok"
    assert status([odw("2026-03-27", "2026-04-08")], TERMIN)["status"] == "blad"


def test_termin_missing_or_bad_dates_skipped():
    assert status([odw(None, "2026-11-14")], TERMIN)["status"] == "pominieto"
    assert status([odw("nie-data", "2026-11-14")], TERMIN)["status"] == "pominieto"
    assert status([], TERMIN)["status"] == "pominieto"


def test_termin_appeal_before_action_is_error():
    assert status([odw("2026-11-10", "2026-11-04")], TERMIN)["status"] == "blad"


@pytest.mark.parametrize("kwota", [7500, 7500.0, "7 500,00", "7 500,00", "15000.00", 20000])
def test_wpis_accepts_amount_formats(kwota):
    assert status([odw(), prz(kwota)], WPIS)["status"] == "ok"


def test_wpis_wrong_amount_is_warning():
    r = status([odw(), prz(200.0)], WPIS)
    assert r["status"] == "ostrzezenie" and "200" in r["detail"]


def test_two_transfers_any_matches():
    docs = [odw(), PEL, prz(17.0, name="oplata.pdf"), prz(15000.0, name="wpis.pdf")]
    assert status(docs, WPIS)["status"] == "ok"
    assert status(docs, SKARB)["status"] == "ok"


def test_oplata_skarbowa_only_when_pelnomocnictwo():
    assert status([odw(), prz(7500.0)], SKARB)["status"] == "pominieto"
    assert status([odw(), PEL, prz(7500.0)], SKARB)["status"] == "ostrzezenie"


def test_wpis_no_transfer_skipped_but_completeness_fails():
    assert status([odw()], WPIS)["status"] == "pominieto"
    r = status([odw()], JEST_PRZ)
    assert r["status"] == "blad" and "przelewu" in r["detail"]
    assert status([odw(), prz(7500.0)], JEST_PRZ)["status"] == "ok"


def test_rachunek_empty_list_is_skipped():
    assert status([odw(), prz(7500.0, "12345678901234567890123456")], RACHUNEK)["status"] == "pominieto"


def test_rachunek_with_configured_list():
    checks = [{**only(RACHUNEK)[0], "values": ["PL12 3456 7890 1234 5678 9012 3456"]}]
    assert status([odw(), prz(1, "12345678901234567890123456")], RACHUNEK, checks)["status"] == "ok"
    assert status([odw(), prz(1, "99945678901234567890123456")], RACHUNEK, checks)["status"] == "blad"


def test_pelnomocnictwo_required_when_appeal_by_attorney():
    r = status([odw(przez=1)], JEST_PEL)
    assert r["status"] == "blad" and "pełnomocnictwa" in r["detail"]
    assert status([odw(przez=1), PEL], JEST_PEL)["status"] == "ok"
    assert status([odw(przez=0, pelnomocnik=None)], JEST_PEL)["status"] == "pominieto"
    assert status([odw(przez=0, pelnomocnik="Jan Kowalski")], JEST_PEL)["status"] == "blad"


def test_unknown_operator_does_not_raise():
    res = run_checks([odw()], [{"name": "x", "op": "nie_ma_takiego"}])
    assert res[0]["status"] == "pominieto"


def test_all_configured_rules_never_raise_on_garbage():
    junk = [{"class_name": "odwolanie", "name": "a", "json": {"OdwolanieKIO": "zle"}},
            {"class_name": "przelew", "name": "b", "json": {"przelew_bankowy": {"kwota": "abc"}}},
            {"class_name": "pelnomocnictwo", "name": "c", "json": {}}]
    res = run_checks(junk)
    assert len(res) >= len(load_checks())
    assert {r["status"] for r in res} <= {"ok", "blad", "ostrzezenie", "pominieto"}
