"""관제 웹 알림 `/p3/alerts` 의 형식. ROS 를 import 하지 않는다.

관제 웹 전체 보기(재범 v1.0, 작전 9/27): 도킹 재시도·포기, 지도 개입·포기처럼 운영자가 봐야 하는 일을
계약 밖 토픽 하나로 낸다. 계약 2.6·Event.msg(보호 경로)는 건드리지 않는다. 판정에는 쓰지 않는다.

- 타입 std_msgs/String, 내용은 JSON 객체 하나: {"kind", "robot", "detail", "sim", "wall"}
- sim 은 노드 시계(use_sim_time 이면 sim s, /clock 전이면 0), wall 은 epoch s(time.time()).
- 작성자: orchestrator(DOCK_*), map_activation_guard(MAP_GUARD_*). 한 kind 는 한 노드만 낸다.
"""

import json
import math

TOPIC = '/p3/alerts'
#: 늦게 붙은 웹도 최근 알림을 받는다. 발행이 RELIABLE 이라 구독은 어느 쪽이든 붙는다.
QOS_DEPTH = 20
DOCK_RETRY = 'DOCK_RETRY'
DOCK_GIVEUP = 'DOCK_GIVEUP'
MAP_GUARD_INTERVENE = 'MAP_GUARD_INTERVENE'
MAP_GUARD_GIVEUP = 'MAP_GUARD_GIVEUP'
KINDS = (DOCK_RETRY, DOCK_GIVEUP, MAP_GUARD_INTERVENE, MAP_GUARD_GIVEUP)
FIELDS = ('kind', 'robot', 'detail', 'sim', 'wall')


def encode(kind, robot, detail, sim, wall):
    """알림 한 건 → JSON 문자열(키 정렬). 모르는 kind 나 유한하지 않은 시각이면 ValueError."""
    if kind not in KINDS:
        raise ValueError(f'alert kind must be one of {list(KINDS)}: {kind!r}')
    if not robot:
        raise ValueError('alert robot is empty')
    for name, value in (('sim', sim), ('wall', wall)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f'alert {name} must be a finite number: {value!r}')
    return json.dumps({'kind': kind, 'robot': str(robot), 'detail': str(detail), 'sim': round(float(sim), 3),
                       'wall': round(float(wall), 3)}, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
