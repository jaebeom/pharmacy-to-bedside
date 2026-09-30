"""레일 보충 v2(scene_version 2)의 순수 계획. ROS 도 Isaac 도 import 하지 않는다.

재범 9/18: 레일 3축, 약통 2종(원통형·모듈형), 선반 칸 랜덤 파지, 잡기·넣기 자세를 teach 대신 #144 IK 로 실행 중 푼다.
해가 여럿이면 여유 거리(#168 clearance)가 가장 큰 해를 고르고, 기준보다 작으면 그 칸을 건너뛴다.

- 기하(칸·수납 자세·삽입 방향·장애물)는 여기서 정하지 않는다. 스테이지 알림·설정으로 받는다(치수가 바뀐다).
- 이 모듈은 (1) 시드 랜덤 칸 고르기, (2) 직교 목표 목록 → 관절 경로 후보(다중 시드 IK), (3) 여유로 고르기를 한다.
"""

import math
import random
from collections import namedtuple

from rokey_p3_manipulation import m0609_kinematics as kin

#: 칸 하나. kind 는 약통 종류('cylinder'·'module' 등, 스테이지가 준 이름 그대로).
Cell = namedtuple('Cell', ('cell_id', 'kind', 'item_id', 'present'))
Choice = namedtuple('Choice', ('seed', 'draw', 'cell_id', 'kind', 'item_id', 'candidates'))
#: 직교 목표 하나. rail 은 이 목표를 풀 때 베이스가 있을 레일 위치, pose 는 베이스 좌표계 TCP 자세(kin.Pose).
Target = namedtuple('Target', ('phase', 'rail', 'pose'))
Candidate = namedtuple('Candidate', ('seed_index', 'joints', 'clearance', 'worst'))
Selection = namedtuple('Selection', ('candidate', 'rejected', 'reason'))


class CellPicker:
    """요청 item 에 맞는 종류의 칸을 시드 랜덤으로 고른다. 같은 시드·같은 재고·같은 요청이면 같은 순서다.

    고를 때마다 (시드, 몇 번째 뽑기, 칸, 종류, 후보 수)를 남긴다(`history`). 건너뛴 칸은 `exclude` 로 받는다.
    """

    def __init__(self, seed):
        self.seed = int(seed)
        self._rng = random.Random(self.seed)
        self.draws = 0
        self.history = []

    def choose(self, cells, kind, item_id=None, exclude=()):
        """조건에 맞는 칸 중 하나. 없으면 None(그래도 뽑기 횟수와 기록은 남긴다)."""
        excluded = set(exclude)
        candidates = sorted((c for c in cells
                             if c.present and c.kind == kind and c.cell_id not in excluded
                             and (item_id is None or not c.item_id or c.item_id == item_id)),
                            key=lambda c: c.cell_id)
        self.draws += 1
        cell = self._rng.choice(candidates) if candidates else None
        choice = Choice(self.seed, self.draws, None if cell is None else cell.cell_id, kind, item_id, len(candidates))
        self.history.append(choice)
        return cell, choice


def default_seeds(home, count=8, spread=0.6, seed=0):
    """IK 시드 목록. 첫째는 home 그대로, 나머지는 home 둘레를 고정 시드로 흩뿌린다(재현 가능)."""
    rng = random.Random(seed)
    seeds = [tuple(home)]
    for _ in range(max(0, count - 1)):
        seeds.append(tuple(q + rng.uniform(-spread, spread) for q in home))
    return seeds


def solve_chain(model, targets, seed):
    """목표를 차례로 푼다. 각 목표는 앞 해를 시드로 쓴다(가지가 튀지 않게). 하나라도 못 풀면 None."""
    joints = []
    current = tuple(seed)
    for target in targets:
        try:
            current = model.inverse(target.pose, current)
        except kin.PlanError:
            return None
        joints.append(current)
    return joints


def wrist_safe(path):
    """이웃 자세 사이에 J5 가 kπ(손목 특이점)를 지나지 않는다."""
    for a, b in zip(path, path[1:], strict=False):
        lo, hi = sorted((a[4], b[4]))
        if math.ceil(lo / math.pi) <= math.floor(hi / math.pi):
            return False
    return True


def select(model, targets, seeds, clearance_of, minimum):
    """시드마다 목표 전체를 풀고, 경로 여유가 가장 큰 해를 고른다.

    clearance_of(joints 목록, stop_below) → (최소 여유 m, 그 자리 설명). stop_below 보다 작은 것을 찾으면 더 재지 않아도
    된다(지금까지 가장 좋은 해와 minimum 중 큰 값을 준다. 그보다 작으면 어차피 뽑히지 않는다).
    여유가 minimum 보다 작으면 고르지 않고 이유를 돌려준다. 같은 해(관절 차 1e-4 rad 안)는 한 번만 잰다.
    """
    candidates, rejected, seen = [], [], []
    for index, seed in enumerate(seeds):
        path = solve_chain(model, targets, seed)
        if path is None:
            rejected.append((index, 'ik'))
            continue
        if not wrist_safe(path):
            rejected.append((index, 'wrist'))
            continue
        if any(all(abs(a - b) < 1e-4 for p, q in zip(path, other, strict=True) for a, b in zip(p, q, strict=True))
               for other in seen):
            continue
        seen.append(path)
        floor = max([minimum] + [c.clearance for c in candidates])
        clearance, worst = clearance_of(path, floor)
        candidates.append(Candidate(index, path, clearance, worst))
    if not candidates:
        return Selection(None, rejected, 'IK 해가 없다')
    best = max(candidates, key=lambda c: c.clearance)
    if best.clearance < minimum:
        return Selection(None, rejected + [(c.seed_index, f'clearance {c.clearance:.3f}') for c in candidates],
                         f'여유 {best.clearance:.3f} m 가 기준 {minimum:.3f} m 보다 작다({best.worst})')
    return Selection(best, rejected, '')
