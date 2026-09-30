"""병원 월드 — 병상을 병실·병동으로 묶어 내고, 병실 묶음(mode 2)에 다른 병실이 섞이면 미리 거부한다.

병실·병동·번호는 zones 의 bed 에 있는 `room`·`ward`·`label` 이다(생성기 `hospital_nav.py` 가 낸다.
작전 9/23: C1 = D1–D4, C2 = D5–D10, 병동은 W1 하나). 웹은 그 값을 옮길 뿐 ID 글자로 짐작하지 않는다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.zones import natural_key
from tests.test_api import make_client, request_body

REPO = Path(__file__).resolve().parents[3]
HOSPITAL_ZONES = REPO / "src" / "rokey_p3_description" / "config" / "zones.hospital.yaml"

# order_pool.hospital.yaml(#553)과 같은 모양. main 에 들어오기 전이라 여기 적는다.
HOSPITAL_POOL = "version: 1\norders:\n" + "".join(
    f'  - {{order_id: ord-{n:04d}, patient_id: "{2000 + n}", '
    f'item_id: {"drug-amox" if n % 2 else "drug-ibu"}, bed: {bed}}}\n'
    for n, bed in enumerate(["bed_a1", "bed_a2", "bed_a3", "bed_a4",
                             "bed_b1", "bed_b2", "bed_b3", "bed_b4", "bed_b5", "bed_b6"], 1))


def hospital_client(tmp_path, zones=HOSPITAL_ZONES):
    pool = tmp_path / "order_pool.hospital.yaml"
    pool.write_text(HOSPITAL_POOL, encoding="utf-8")
    return make_client(allow_commands=True, order_pool=str(pool), zones_file=str(zones))


def batch(mode, *order_ids, request_id="web-0001"):
    return request_body(request_id=request_id, mode=mode, destination_id="station_a",
                        orders=[{"order_id": o} for o in order_ids])


# ── /api/destinations ────────────────────────────────────────────────────

def test_hospital_destinations_are_grouped_by_room_with_labels(tmp_path):
    client, _ = hospital_client(tmp_path)
    with client:
        rows = client.get("/api/destinations").json()["destinations"]
    beds = [r for r in rows if r["kind"] == "bed"]
    assert [(r["destination_id"], r["group"], r["label"]) for r in beds] == [
        ("bed_a1", "C1", "D1"), ("bed_a2", "C1", "D2"), ("bed_a3", "C1", "D3"), ("bed_a4", "C1", "D4"),
        ("bed_b1", "C2", "D5"), ("bed_b2", "C2", "D6"), ("bed_b3", "C2", "D7"),
        ("bed_b4", "C2", "D8"), ("bed_b5", "C2", "D9"), ("bed_b6", "C2", "D10")]
    assert {(r["group"], r["group_label"]) for r in beds} == {("C1", "C1 병실"), ("C2", "C2 병실")}
    assert {(r["ward"], r["ward_label"]) for r in beds} == {("W1", "1병동")}
    # 스테이션: station_a(데스크 면), station_b(B 테이블, 재범 9/24), station_c·station_d(병실 C 테이블, 재범 9/25 —
    # 병실 주문은 그 방 테이블에 놓는다). 병실 테이블은 zone 의 room 으로 그 병실에 묶인다.
    stations = {r["destination_id"]: r for r in rows if r["kind"] == "station"}
    assert sorted(stations) == ["station_a", "station_b", "station_c", "station_d"]
    for name in ("station_a", "station_b"):
        assert (stations[name]["group"], stations[name]["group_label"], stations[name]["label"]) == (None, None, None)
    assert (stations["station_c"]["group"], stations["station_d"]["group"]) == ("C1", "C2")


def test_the_room_comes_from_the_file_not_from_the_id_letter(tmp_path):
    """bed_a1 을 C2 에 적으면 C2 로 낸다 — 글자 a 로 C1 을 짐작하지 않는다."""
    zones = tmp_path / "zones.yaml"
    zones.write_text("frame: map\nzones:\n"
                     "  bed_a1:\n    kind: bed\n    room: C2\n    ward: W3\n    label: X9\n"
                     "  bed_a2:\n    kind: bed\n", encoding="utf-8")
    client, _ = hospital_client(tmp_path, zones)
    with client:
        rows = client.get("/api/destinations").json()["destinations"]
    assert rows[0] == {"destination_id": "bed_a1", "kind": "bed", "group": "C2", "group_label": "C2 병실",
                       "ward": "W3", "ward_label": "3병동", "label": "X9"}
    assert (rows[1]["group"], rows[1]["ward"], rows[1]["label"]) == (None, None, None)


def test_destinations_are_in_number_order(tmp_path):
    zones = tmp_path / "zones.yaml"
    zones.write_text("frame: map\nzones:\n"
                     "  bed_a10: {kind: bed}\n  bed_a2: {kind: bed}\n  bed_a1: {kind: bed}\n"
                     "  station_a: {kind: station}\n", encoding="utf-8")
    client, _ = hospital_client(tmp_path, zones)
    with client:
        ids = [r["destination_id"] for r in client.get("/api/destinations").json()["destinations"]]
    assert ids == ["bed_a1", "bed_a2", "bed_a10", "station_a"]
    assert sorted(["bed_a10", "bed_a2"]) == ["bed_a10", "bed_a2"], "문자열 정렬이면 10 이 앞선다"
    assert sorted(["bed_a10", "bed_a2"], key=natural_key) == ["bed_a2", "bed_a10"]


# ── 병실 묶음(mode 2) ────────────────────────────────────────────────────

def test_a_room_batch_across_two_rooms_is_refused_before_sending(tmp_path):
    client, _ = hospital_client(tmp_path)
    with client:
        r = client.post("/api/requests", json=batch(2, "ord-0001", "ord-0005", "ord-0002"))
    assert r.status_code == 400, r.text
    err = r.json()["error"]
    assert err["code"] == "mixed_rooms"
    assert err["detail"] == {"mode": 2, "rooms": [
        {"room": "C1", "order_ids": ["ord-0001", "ord-0002"]},
        {"room": "C2", "order_ids": ["ord-0005"]}]}


def test_a_room_batch_inside_one_room_passes(tmp_path):
    client, _ = hospital_client(tmp_path)
    with client:
        r = client.post("/api/requests", json=batch(2, "ord-0005", "ord-0010"))
    assert r.status_code == 200, r.text


def test_a_ward_batch_may_span_rooms(tmp_path):
    """병동 묶음(mode 3)은 병동 보관함 하나로 간다 — 병실이 섞여도 된다."""
    client, _ = hospital_client(tmp_path)
    with client:
        r = client.post("/api/requests", json=batch(3, "ord-0001", "ord-0005"))
    assert r.status_code == 200, r.text


def test_without_rooms_in_the_zones_file_nothing_is_refused(tmp_path):
    """병실을 모르는 월드(빈월드·조제실 zones)는 지금 동작 그대로다 — 모르는 것으로 거부하지 않는다."""
    zones = tmp_path / "zones.yaml"
    zones.write_text("frame: map\nzones:\n  bed_a1: {kind: bed}\n  bed_b1: {kind: bed}\n", encoding="utf-8")
    client, _ = hospital_client(tmp_path, zones)
    with client:
        r = client.post("/api/requests", json=batch(2, "ord-0001", "ord-0005"))
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("known", ["ord-0001", "ord-0005"])
def test_an_order_whose_room_is_unknown_is_left_out_of_the_judgement(tmp_path, known):
    """병실을 아는 주문이 한 병실뿐이면 통과다. 모르는 병상(여기선 zones 에 없는 bed_c1)은 판단에서 뺀다."""
    pool = tmp_path / "order_pool.hospital.yaml"
    pool.write_text(HOSPITAL_POOL + '  - {order_id: ord-0011, patient_id: "2011", item_id: drug-ibu, bed: bed_c1}\n',
                    encoding="utf-8")
    client, _ = make_client(allow_commands=True, order_pool=str(pool), zones_file=str(HOSPITAL_ZONES))
    with client:
        r = client.post("/api/requests", json=batch(2, known, "ord-0011"))
    assert r.status_code == 200, r.text


def test_mixed_rooms_is_answered_before_server_state(tmp_path):
    """입력이 스스로 모순이라 기다려도 안 풀린다 — 트립이 열려 있어도 mixed_rooms 가 먼저다."""
    client, _ = hospital_client(tmp_path)
    with client:
        assert client.post("/api/requests", json=batch(2, "ord-0005", "ord-0006")).status_code == 200
        r = client.post("/api/requests", json=batch(2, "ord-0001", "ord-0007", request_id="web-0002"))
    assert r.json()["error"]["code"] == "mixed_rooms"


def test_every_hospital_table_destination_has_a_zone_id_shape_the_web_accepts():
    """회차74(50b8769): 웹이 `table_c1` 을 bad_destination 으로 거부했다. 표 목적지는 웹 정규식을 지나야 한다."""
    from app.zones import is_zone_id

    for zone in ("station_b", "station_c", "station_d"):
        assert is_zone_id(zone), zone
