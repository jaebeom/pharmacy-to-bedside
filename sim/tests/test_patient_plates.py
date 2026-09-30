"""협탁 환자 인식표 판(시각 소품)의 순수 부분. Isaac 쪽(판·QR 면 세우기)은 L3 미실행이다."""
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
REPO = STANDALONE.parents[1]
sys.path.insert(0, str(STANDALONE))
import make_qr_textures  # noqa: E402
from p3sim import hospital_nav, hospital_zones, patient_plates, truth_sensors  # noqa: E402

ZONES = REPO / "src" / "rokey_p3_description" / "config" / "zones.hospital.yaml"
POOL = REPO / "src" / "rokey_p3_orchestrator" / "config" / "order_pool.hospital.yaml"
ANCHORS = REPO / "sim" / "scenes" / "hospital_navigationv1.anchors.json"


class Plates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zones = hospital_zones.zones_from_yaml(ZONES)
        cls.sizes = hospital_nav.cabinet_sizes(hospital_nav.load_anchors(ANCHORS))
        cls.patients = truth_sensors.bed_patients(POOL.read_text())
        cls.stations = hospital_zones.station_tables(ZONES)
        cls.plates = patient_plates.plates(cls.zones, cls.sizes, cls.patients, cls.stations)

    def test_every_bed_gets_its_patient_plate(self):
        # 침상 10 + 테이블 셋(station_b·station_c·station_d, 풀에 ord-0011–0013). 테이블은 st-<zone> 판이다.
        self.assertEqual(len(self.plates), 13)
        by_bed = {p["bed"]: p["tag_id"] for p in self.plates}
        self.assertEqual(by_bed["bed_a1"], "pt-2001")
        self.assertEqual(by_bed["bed_b6"], "pt-2010")
        self.assertEqual((by_bed["station_b"], by_bed["station_c"], by_bed["station_d"]),
                         ("st-station_b", "st-station_c", "st-station_d"))

    def test_plate_lies_on_the_table_top_away_from_the_robot_and_the_pouch_spot(self):
        for plate in self.plates:
            bed = plate["bed"]
            cx, cy, top = self.zones[f"{bed}/cabinet"][:3]
            bx, by = self.zones[bed][:2]
            wx, wy = self.sizes[f"{bed}/cabinet"]
            x, y, _z = plate["center"]
            half = patient_plates.PLATE_SIDE / 2.0
            self.assertLessEqual(abs(x - cx) + half, wx / 2.0 + 1e-9, bed)          # 윗면 안
            self.assertLessEqual(abs(y - cy) + half, wy / 2.0 + 1e-9, bed)
            self.assertAlmostEqual(plate["top"], top + patient_plates.PLATE_THICKNESS)
            robot_to_table = (cx - bx) ** 2 + (cy - by) ** 2
            robot_to_plate = (x - bx) ** 2 + (y - by) ** 2
            if bed.startswith('bed_'):
                self.assertLess(robot_to_plate, robot_to_table, bed)
                tag = self.zones[f'{bed}/tag']
                self.assertEqual((x, y), tag[:2])
                self.assertAlmostEqual(plate['top'] + patient_plates.QR_LIFT, tag[2])
            else:
                self.assertGreater(robot_to_plate, robot_to_table, bed)
            self.assertGreater(max(abs(x - cx), abs(y - cy)), 0.15, bed)            # 가운데(봉투 자리)를 비운다

    def test_bed_with_two_patients_gets_no_plate(self):
        patients = dict(self.patients, bed_a1={"2001", "9999"})
        beds = [p["bed"] for p in patient_plates.plates(self.zones, self.sizes, patients, self.stations)]
        self.assertNotIn("bed_a1", beds)
        self.assertEqual(len(beds), 12)

    def test_qr_textures_include_patient_ids(self):
        ids = make_qr_textures.patient_ids(POOL.read_text())
        self.assertEqual(len(ids), 13)
        self.assertIn("pt-2001", ids)
        self.assertEqual({"st-station_b", "st-station_c", "st-station_d"},
                         make_qr_textures.station_ids(POOL.read_text()))


class StationBPlate(unittest.TestCase):
    """스테이션 B 테이블 주문 풀(order_pool.station_b.yaml)이면 판이 그 테이블 위, 봉투 자리 반대편에 선다."""

    def test_station_b_gets_the_plate_on_its_table(self):
        zones = hospital_zones.zones_from_yaml(ZONES)
        sizes = hospital_nav.cabinet_sizes(hospital_nav.load_anchors(ANCHORS))
        pool = REPO / "src" / "rokey_p3_orchestrator" / "config" / "order_pool.station_b.yaml"
        plates = patient_plates.plates(zones, sizes, truth_sensors.bed_patients(pool.read_text()))
        self.assertEqual([("station_b", "pt-2011")], [(p["bed"], p["tag_id"]) for p in plates])
        x, y, _z = plates[0]["center"]
        lo, hi = hospital_nav.STATION_B_TABLE["min"], hospital_nav.STATION_B_TABLE["max"]
        half = patient_plates.PLATE_SIDE / 2.0
        self.assertTrue(lo[0] + half <= x <= hi[0] - half and lo[1] + half <= y <= hi[1] - half)
        _cx, cy, _top = zones["station_b/cabinet"][:3]
        self.assertGreater(cy - y, 0.15)       # 로봇(북) 반대편, 봉투 자리에서 0.15 넘게


if __name__ == "__main__":
    unittest.main()
