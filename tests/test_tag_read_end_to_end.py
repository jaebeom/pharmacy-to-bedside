"""스테이지가 내는 인식표 본문이 **어댑터를 지나 계약 값으로 나오는지** 한 번에 본다.

lap8 (9/21) 이 ⑥ 도착 뒤 ⑦ `AUTH_FAIL` 로 닫혔고, 비전이 두 자리를 의심했다:
`tag_id` 에 `pt-` 접두가 붙는가, `kind` 가 `TagRead.KIND_PATIENT` 인가.
둘 다 **이미 맞았지만** 그것을 확인하려면 두 저장소 경로를 손으로 읽어야 했다 —
`truth_sensors.patient_tag` 가 접두를 붙이고 `isaac_json._choice` 가 문자열을 uint8 로 바꾼다.

경계를 **양쪽에서 각자 맞다고 믿는 것**이 이 프로젝트에서 제일 자주 틀린 자리다. 그래서 값을
한쪽에서 만들어 다른 쪽으로 통과시키고, `TagRead.msg` 의 상수와 직접 맞댄다. ROS 런타임 없이 돈다.
"""

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sim/standalone"))
sys.path.insert(0, str(ROOT / "src/rokey_p3_bringup"))

from p3sim import bridge, truth_sensors as T  # noqa: E402
from rokey_p3_bringup import isaac_json  # noqa: E402

MSG = ROOT / "src/rokey_p3_interfaces/msg/TagRead.msg"


def constant(name):
    """`TagRead.msg` 의 `uint8 NAME=N`. **메시지 정의가 단일 출처다** — 숫자를 여기 베껴 적지 않는다."""
    match = re.search(rf"^\s*uint8\s+{name}\s*=\s*(\d+)\s*$", MSG.read_text(), re.MULTILINE)
    assert match, f"{name} 이 {MSG} 에 없다"
    return int(match.group(1))


class TagReadCrossesTheBoundary(unittest.TestCase):

    def relay(self, zone_id, tag_id, kind="patient", status="ok"):
        message = T.tag_message(12.5, 3, "amr_1/hand_camera", zone_id, tag_id, kind=kind, status=status)
        return isaac_json.parse_tag_read(bridge.encode(bridge.TAG_READS, **message))

    def test_the_patient_tag_carries_the_contract_prefix(self):
        """계약 7절: `pt-` + patient_id. 접두가 빠지면 팔은 잘 읽고 orchestrator 가 AUTH_FAIL 로 닫는다 —
        **증상이 "못 읽었다" 와 똑같아서** 회차를 한 번 더 쓰게 된다(비전 9/21)."""
        self.assertEqual(self.relay("bed_a1", T.patient_tag("1001"))["tag_id"], "pt-1001")

    def test_the_station_tag_carries_its_own_prefix(self):
        self.assertEqual(T.station_tag("dock_1"), "st-dock_1")

    def test_the_kind_arrives_as_the_message_constant_not_a_string(self):
        """`TagRead.kind` 는 uint8 이다. 팔은 `kind == KIND_PATIENT` 가 아니면 **영원히 무시**한다."""
        self.assertEqual(self.relay("bed_a1", "pt-1001")["kind"], constant("KIND_PATIENT"))
        self.assertEqual(self.relay("dock_1", "st-dock_1", kind="station")["kind"], constant("KIND_STATION"))

    def test_the_status_arrives_as_the_message_constant(self):
        self.assertEqual(self.relay("bed_a1", "pt-1001")["status"], constant("STATUS_OK"))
        self.assertEqual(self.relay("bed_a1", "pt-1001", status="unreadable")["status"],
                         constant("STATUS_UNREADABLE"))

    def test_an_empty_tag_id_never_leaves_the_stage(self):
        """빈 `tag_id` 는 orchestrator 가 스텁 태그로 비교해 인증을 **거짓 통과**시킨다(비전 #417 4절).

        막는 쪽이 **내는 쪽**이라는 것까지 본다 — 어댑터가 막아 주기를 기대하면, 어댑터를 안 거치는
        경로가 하나만 생겨도 구멍이 난다.
        """
        with self.assertRaises(ValueError) as caught:
            self.relay("bed_a1", "")
        self.assertIn("tag_id is empty", str(caught.exception))

    def test_an_unknown_kind_is_dropped_not_defaulted(self):
        """모르는 값에 기본값을 조용히 넣으면 환자 인식표가 아닌 것이 환자(0)로 통과한다."""
        message = T.tag_message(12.5, 3, "amr_1/hand_camera", "bed_a1", "pt-1001")
        message["kind"] = "nurse"
        with self.assertRaises(isaac_json.IsaacJsonError):
            isaac_json.parse_tag_read(json.dumps(message))


if __name__ == "__main__":
    unittest.main()
