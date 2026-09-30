"""L1: 관제 웹 알림 `/p3/alerts` 형식(`alerts.py`). 작성자 둘(orchestrator, map_activation_guard)이 같은 형식을 쓴다."""

import json
import math

import pytest

from rokey_p3_navigation import alerts


def test_one_alert_is_a_flat_json_object_with_five_fields():
    text = alerts.encode(alerts.DOCK_RETRY, 'amr_1', '1/3 NOT_ARRIVED, 10 s 뒤 재시도', 123.4567, 1790000000.12345)
    message = json.loads(text)
    assert set(message) == set(alerts.FIELDS)
    assert message == {'kind': 'DOCK_RETRY', 'robot': 'amr_1', 'detail': '1/3 NOT_ARRIVED, 10 s 뒤 재시도',
                       'sim': 123.457, 'wall': 1790000000.123}
    assert '재시도' in text                                       # ensure_ascii=False — 웹이 그대로 보인다


def test_the_four_kinds_agreed_with_ops():
    assert alerts.KINDS == ('DOCK_RETRY', 'DOCK_GIVEUP', 'MAP_GUARD_INTERVENE', 'MAP_GUARD_GIVEUP')
    assert alerts.TOPIC == '/p3/alerts'


@pytest.mark.parametrize('kind, robot, sim, wall', [
    ('DOCKED', 'amr_1', 0.0, 0.0), ('DOCK_RETRY', '', 0.0, 0.0),
    ('DOCK_RETRY', 'amr_1', math.nan, 0.0), ('DOCK_RETRY', 'amr_1', 0.0, True)])
def test_bad_alerts_are_refused(kind, robot, sim, wall):
    with pytest.raises(ValueError):
        alerts.encode(kind, robot, '', sim, wall)
