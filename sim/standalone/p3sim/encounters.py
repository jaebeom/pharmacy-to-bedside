"""보행자·더미가 AMR 가까이 들어온 구간을 한 줄씩 적는다(#697 avoidance_encounters). Isaac 임포트 없음.

`encounter start who=<ped_i|dummy_i> dist_min=<m> sim=<s>` 는 AMR(amr_1 몸체 중심)과 그 소품 중심의 거리가
`RADIUS` 안으로 들어온 틱에, `encounter end who=… dist_min=<m> sim=<s>` 는 `RADIUS + EXIT_MARGIN` 밖으로 나간
틱에 한 번 나온다. end 의 dist_min 은 그 구간의 최솟값이다. 기록만 한다 — 판정하지 않는다.
"""

import math

#: 들어왔다고 보는 거리(m, 중심 사이). #697 이 정한 값이다.
RADIUS = 2.0
#: 나갔다고 보는 여유(m). 경계에서 start/end 가 틱마다 번갈아 나오지 않게 한다.
EXIT_MARGIN = 0.1


class Tracker:
    def __init__(self, radius=RADIUS, exit_margin=EXIT_MARGIN):
        self.radius = radius
        self.exit_radius = radius + exit_margin
        self._open = {}  # who → 지금까지 최소 거리

    def update(self, now_s, amr_xy, others):
        """`others` 는 {who: (x, y)}. 이번 틱에 낼 줄 목록. AMR 자리를 못 읽으면 아무 줄도 없다."""
        if amr_xy is None:
            return []
        lines = []
        for who, xy in others.items():
            dist = math.hypot(xy[0] - amr_xy[0], xy[1] - amr_xy[1])
            if who in self._open:
                self._open[who] = min(self._open[who], dist)
                if dist > self.exit_radius:
                    lines.append(f"encounter end who={who} dist_min={self._open.pop(who):.3f} sim={now_s:.2f}")
            elif dist < self.radius:
                self._open[who] = dist
                lines.append(f"encounter start who={who} dist_min={dist:.3f} sim={now_s:.2f}")
        return lines
