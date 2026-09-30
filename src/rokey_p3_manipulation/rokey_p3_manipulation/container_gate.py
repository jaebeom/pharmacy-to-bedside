"""보충 전 약통 확인(QR·DB·카메라 계약 2.3)의 팔 쪽 판단. ROS 를 import 하지 않는다.

M0609 가 잡기 직전(`grasp_pose` 에 도착한 뒤, `grasp` 로 닫기 전) 손 카메라의 약통 QR(`cn-NNNN`)을 읽고
orchestrator 의 `/orchestrator/check_container` 에 묻는다. DB 는 orchestrator 만 쓴다(계약 2.1).

- 도착 뒤 stamp 의 약통 판독만 쓴다(이전 칸의 판독을 쓰지 않는다).
- 못 읽으면 `unreadable`, 서비스가 시한 안에 답하지 않으면 `check_timeout` 으로 **거부**다(모르면 장착하지 않는다).
- 거부한 칸은 같은 epoch 에서 다시 고르지 않는다. 리셋(새 epoch)이면 잊는다.
"""

from collections import namedtuple

#: 판독 하나. stamp 는 이미지 시각(sim 초), tag_id 는 QR 내용 전체(cn-NNNN).
Read = namedtuple('Read', ('stamp', 'tag_id'))

REASON_UNREADABLE = 'unreadable'
REASON_TIMEOUT = 'check_timeout'


def latest_read(reads, since):
    """`since`(sim 초) 이후의 가장 새 약통 판독. 없으면 None."""
    fresh = [read for read in reads if read.stamp >= since and read.tag_id]
    return max(fresh, key=lambda read: read.stamp) if fresh else None


def decide(read, answer):
    """(허용, 이유, 약통 ID). `answer` 는 서비스 응답(allowed, reason) 또는 시한 초과면 None."""
    if read is None:
        return False, REASON_UNREADABLE, ''
    if answer is None:
        return False, REASON_TIMEOUT, read.tag_id
    allowed, reason = answer
    return bool(allowed), str(reason), read.tag_id


class RefusedCells:
    """거부한 칸. epoch 마다 따로 센다."""

    def __init__(self):
        self._epoch = None
        self._cells = []

    def add(self, epoch, cell_id):
        if epoch != self._epoch:
            self._epoch, self._cells = epoch, []
        if cell_id and cell_id not in self._cells:
            self._cells.append(cell_id)

    def of(self, epoch):
        """이 epoch 에서 거부한 칸. 다른 epoch 면 빈 목록."""
        return list(self._cells) if epoch == self._epoch else []
