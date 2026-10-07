import os

os.environ["DEMO_TODAY"] = "2026-10-07"
os.environ.pop("DEMO_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402

client = TestClient(app)


def test_pob_today_excludes_person_disembarking_today():
    body = client.get("/pob").json()
    assert body["count"] == 9
    names = {p["name"] for p in body["people"]}
    assert "Emre Koç" not in names
    assert "Ali Yılmaz" in names


def test_pob_tomorrow():
    body = client.get("/pob", params={"day_offset": 1}).json()
    assert body["count"] == 10
    assert set(body["embarking_this_day"]) == {"Orhan Erdem", "Cem Polat"}
    assert body["disembarking_this_day"] == ["Ali Yılmaz"]


def test_free_beds_tomorrow_only_k104():
    body = client.get("/cabins/free", params={"day_offset": 1}).json()
    assert body["free_beds_total"] == 1
    assert [c["cabin"] for c in body["cabins_with_free_beds"]] == ["K-104"]


def test_exact_name_is_not_ambiguous():
    body = client.get("/people", params={"name": "ali yilmaz"}).json()
    assert body["match_count"] == 1
    assert body["matches"][0]["disembark"] == "8 Ekim 2026"


def test_first_name_only_is_ambiguous():
    body = client.get("/people", params={"name": "Ali"}).json()
    assert body["ambiguous"] is True
    assert {m["name"] for m in body["matches"]} == {"Ali Yılmaz", "Ali Yıldız"}


def test_unknown_person_returns_no_match():
    body = client.get("/people", params={"name": "Mert Can"}).json()
    assert body["match_count"] == 0


def test_key_enforced_when_set():
    os.environ["DEMO_KEY"] = "s3cret"
    try:
        assert client.get("/pob").status_code == 401
        assert client.get("/pob", headers={"X-Demo-Key": "s3cret"}).status_code == 200
    finally:
        os.environ.pop("DEMO_KEY")
