"""`/rosout` 에서 goal 거부 사유를 찾는다. 순수 함수 — ROS 없이 돈다.

goal REJECT 에는 사유 자리가 없다(계약 2.5절). 실습8 에서 웹이 받은 것은
`409 "orchestrator 가 요청을 거부했다 (사유 없음)"` 뿐이었고, 진짜 사유
`Deliver goal 거부: 진행 중 트립이 있거나 정거장을 만들 수 없다` 는 **스택 로그에만** 남았다.
사람은 웹만 보고 있어서 그 줄을 못 봤다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.reject_reason import LOOKBACK_S, find_reject_reason

NOW = datetime(2026, 9, 18, 9, 0, 0, tzinfo=timezone.utc)


def log(message: str, ago: float = 0.0) -> dict:
    wall = NOW - timedelta(seconds=ago)
    return {"message": message, "level": "warn", "level_value": 30,
            "node": "orchestrator",
            "wall": wall.strftime("%Y-%m-%dT%H:%M:%S.") + f"{wall.microsecond // 1000:03d}Z"}


# ── 매칭 ─────────────────────────────────────────────────────────────────

def test_the_reason_is_taken_from_the_line_with_that_request_id():
    logs = [log("Deliver goal 거부 web-0002: 진행 중 트립이 있거나 정거장을 만들 수 없다")]
    assert find_reject_reason(logs, "web-0002", NOW) == \
        "진행 중 트립이 있거나 정거장을 만들 수 없다"


def test_the_newest_matching_line_wins():
    logs = [log("Deliver goal 거부 web-1: 옛 사유", ago=5),
            log("Deliver goal 거부 web-1: 새 사유", ago=1)]
    assert find_reject_reason(logs, "web-1", NOW) == "새 사유"


def test_other_lines_in_between_do_not_disturb_it():
    logs = [log("Deliver goal 거부 web-1: 사유", ago=2),
            log("무관한 경고", ago=1)]
    assert find_reject_reason(logs, "web-1", NOW) == "사유"


# ── 안 맞으면 비운다 ─────────────────────────────────────────────────────

def test_the_current_format_without_a_request_id_does_not_match():
    """지금 orchestrator 는 `Deliver goal 거부: {reason}` 으로 id 없이 찍는다(`_refuse`).

    팔 #201 이 id 를 넣기 전까지는 사유가 비어 있는 것이 맞다. 시각만으로 맞추면
    **남의 거부 사유가 엉뚱한 요청에 붙는다** — 틀린 사유는 사유 없음보다 나쁘다.
    """
    logs = [log("Deliver goal 거부: 진행 중 트립이 있거나 정거장을 만들 수 없다")]
    assert find_reject_reason(logs, "web-0002", NOW) is None


def test_another_requests_reason_is_not_borrowed():
    logs = [log("Deliver goal 거부 web-0003: 남의 사유")]
    assert find_reject_reason(logs, "web-0002", NOW) is None


def test_a_line_older_than_the_window_is_ignored():
    logs = [log("Deliver goal 거부 web-1: 옛 사유", ago=LOOKBACK_S + 5)]
    assert find_reject_reason(logs, "web-1", NOW) is None


@pytest.mark.parametrize("logs", [[], [log("무관한 줄")], [log("Deliver goal 거부 web-1:")]])
def test_nothing_to_find_yields_none(logs):
    assert find_reject_reason(logs, "web-1", NOW) is None


def test_an_empty_request_id_never_matches():
    assert find_reject_reason([log("Deliver goal 거부 : 사유")], "", NOW) is None


def test_a_request_id_with_regex_characters_is_escaped():
    """request_id 는 사용자 입력이다. 정규식 메타문자가 들어와도 터지지 않는다."""
    logs = [log("Deliver goal 거부 web.0001: 사유")]
    assert find_reject_reason(logs, "web.0001", NOW) == "사유"
    assert find_reject_reason(logs, "webX0001", NOW) is None, "점이 임의 문자로 새면 안 된다"


def test_a_malformed_wall_time_does_not_crash():
    logs = [{"message": "Deliver goal 거부 web-1: 사유", "wall": "언제인지 모름"}]
    assert find_reject_reason(logs, "web-1", NOW) == "사유"


# ── #201 이 실제로 찍는 형식 ─────────────────────────────────────────────

def test_the_real_emitted_format_matches():
    """`orchestrator_node._refuse` (#201): `Deliver goal 거부 {request_id or "-"}: {reason}`."""
    request_id, reason = "web-0002", "진행 중 트립이 있거나 정거장을 만들 수 없다"
    line = f'Deliver goal 거부 {request_id or "-"}: {reason}'
    assert find_reject_reason([log(line)], request_id, NOW) == reason


def test_the_dash_line_belongs_to_nobody():
    """`request_id` 가 비면 `-` 가 찍힌다. 누구의 거부인지 알 수 없으므로 쓰지 않는다."""
    empty_id = ""
    line = f'Deliver goal 거부 {empty_id or "-"}: request_id 가 비었다'
    assert find_reject_reason([log(line)], "web-0002", NOW) is None


def test_a_request_id_that_is_literally_a_dash_is_not_confused():
    """누가 request_id 를 `-` 로 보내도, 그건 '주인 없는 줄' 과 구분되지 않는다.

    구분할 방법이 없으므로 **매칭되는 쪽이 맞다** — 다만 그런 id 를 쓰지 않는 편이 낫다.
    이 테스트는 동작을 못박아 두려는 것이지 권장이 아니다.
    """
    assert find_reject_reason([log("Deliver goal 거부 -: 사유")], "-", NOW) == "사유"
