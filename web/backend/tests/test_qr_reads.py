"""손 카메라 QR 판독 → snapshot.qr_reads(api.md §1.12, 재범 9/29 "QR 에 포함된 정보를 간략하게")."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.order_pool import load_pool
from app.qr_info import QrResolver
from app.state import QR_READS_MAX, WorldState

REPO = Path(__file__).resolve().parents[3]
CONFIG = REPO / "src" / "rokey_p3_orchestrator" / "config"
NOW = datetime(2026, 9, 29, 2, 0, 0, tzinfo=timezone.utc)


def resolver() -> QrResolver:
    return QrResolver(load_pool(CONFIG / "order_pool.hospital.yaml").orders, CONFIG / "pharmacy_catalog.yaml",
                      CONFIG / "dispenser.hospital-v0.yaml")


def read(kind: int, tag: str, status: int = 0) -> dict:
    return {"kind": kind, "tag_id": tag, "status": status, "stamp": 5.0}


def test_the_repository_files_turn_ids_into_short_summaries():
    r = resolver()
    assert r.info("pouch", "ord-0001") == {"order_id": "ord-0001", "patient_id": "2001", "bed": "bed_a1",
                                           "item_id": "drug-amox", "drug": "아목시실린 캡슐 500 mg"}
    assert r.info("patient", "2001") == {"patient_id": "2001", "bed": "bed_a1", "order_ids": ["ord-0001"]}
    assert r.info("station", "station_b") == {"zone": "station_b"}
    container = r.info("container", "cn-0003")
    assert (container["lot_id"], container["item_id"], container["expiry"]) == ("lot-ibu-01", "drug-ibu", "2027-05-31")
    assert container["drug"] == "이부프로펜 정 200 mg"


def test_unknown_ids_and_missing_files_leave_nulls_not_guesses():
    assert QrResolver().info("pouch", "ord-9999") == {"order_id": "ord-9999", "patient_id": None, "bed": None,
                                                      "item_id": None, "drug": None}
    assert resolver().info("container", "cn-4242")["drug"] is None


def test_repeated_frames_become_one_row_newest_first_and_unreadable_is_dropped():
    s = WorldState()
    s.qr_resolver = resolver()
    for i in range(5):
        s.note_qr_read("amr_1", read(2, "ord-0001"), NOW + timedelta(seconds=i * 0.2))
    s.note_qr_read("amr_1", read(0, "2001"), NOW + timedelta(seconds=3))
    s.note_qr_read("amr_1", read(2, "ord-0002", status=1), NOW + timedelta(seconds=4))   # 못 읽음
    s.note_qr_read("amr_1", read(9, "zzz"), NOW + timedelta(seconds=4))                  # 모르는 종류
    rows = s.qr_reads_view(NOW + timedelta(seconds=5))
    assert [(r["kind"], r["tag_id"], r["count"]) for r in rows] == [("patient", "2001", 1), ("pouch", "ord-0001", 5)]
    assert rows[1]["info"]["drug"] == "아목시실린 캡슐 500 mg"
    assert rows[0]["age_wall_s"] == 2.0


def test_m0609_container_reads_are_listed_too_and_reset_clears_the_list():
    s = WorldState()
    s.note_tag_read(read(3, "cn-0003"), NOW)
    assert [(r["robot"], r["kind"]) for r in s.qr_reads_view(NOW)] == [("m0609", "container")]
    s.note_event({"name": "RESET_BEGIN", "epoch": 2}, NOW)
    assert s.qr_reads_view(NOW) == []


def test_the_list_stays_short():
    s = WorldState()
    for i in range(QR_READS_MAX * 3):
        s.note_qr_read("amr_1", read(2, f"ord-{i:04d}"), NOW + timedelta(seconds=i))
    rows = s.qr_reads_view(NOW + timedelta(seconds=100))
    assert len(rows) == QR_READS_MAX
    assert rows[0]["tag_id"] == f"ord-{QR_READS_MAX * 3 - 1:04d}"
