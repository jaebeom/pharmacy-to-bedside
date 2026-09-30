"""주문 풀과 요청 큐. 계약 7절의 ID 규칙을 쓴다. ROS 를 import 하지 않는다.

order_generator 가 쓰는 순수 로직이다. 파일을 읽는 것은 노드가 하고, 여기는
이미 읽힌 mapping 을 검사해 주문과 요청으로 바꾸는 일만 한다.
"""

import re
from dataclasses import dataclass

# 계약 7절: 주문 ID 형식은 rokey_p3_perception/qr_payload.py 의 정규식이다.
# 패키지 경계를 넘지 않으려고 같은 규칙을 여기 다시 쓴다. 바꿀 때 두 곳을 같이 본다.
_ID = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')

# 계약 2.4절: QR 내용의 접두가 TagRead.kind 를 정한다.
ORDER_PREFIX = 'ord-'
PATIENT_PREFIX = 'pt-'
STATION_PREFIX = 'st-'
_PREFIXES = (ORDER_PREFIX, PATIENT_PREFIX, STATION_PREFIX)

# 계약 3절의 zone id 규칙 중 **보관함이 있는 목적지**: 침상과 간호스테이션(9/24 재범: 목적지 = 스테이션 B 테이블).
# 칸 이름은 `bed` 그대로다 — 스테이션도 병상과 같은 흐름(ScanTag → 내려놓기 → CabinetObservation)으로 간다.
# 병실 테이블(station_c·station_d = C1·C2 병동 입구 협탁, 재범 9/25)도 스테이션 꼴이라 그대로 받는다.
_BED = re.compile(r'^(bed_[a-z][0-9]+|station_[a-z])$')

# 값은 DeliveryRequest.msg 의 MODE_ 상수와 같아야 한다.
MODE_SINGLE = 0
MODE_URGENT = 1
MODE_BATCH_ROOM = 2
MODE_BATCH_WARD = 3
MODES = {
    'single': MODE_SINGLE,
    'urgent': MODE_URGENT,
    'batch_room': MODE_BATCH_ROOM,
    'batch_ward': MODE_BATCH_WARD,
}

# 주문 하나로 요청 하나를 만들 수 있는 유형. 묶음은 정거장이 여럿이라 풀 파일만으로 못 만든다.
POOL_MODES = ('single', 'urgent')

_REQUIRED = ('order_id', 'patient_id', 'item_id', 'bed')
_ALLOWED = _REQUIRED + ('mode',)


class PoolError(ValueError):
    """주문 풀 파일이 계약의 ID 규칙을 어겼다."""


@dataclass(frozen=True)
class PoolOrder:
    """주문 풀 한 줄. 주문 하나 = 봉투 하나."""

    order_id: str
    patient_id: str
    item_id: str
    bed: str
    mode: str = 'single'


@dataclass(frozen=True)
class PendingRequest:
    """아직 보내지 않은 Deliver 요청 하나. request_id 는 보낼 때 붙인다."""

    mode: str
    destination_id: str
    order_ids: tuple

    @property
    def urgent(self):
        """긴급 요청인가. 큐에서 일반 요청보다 앞에 선다."""
        return self.mode == 'urgent'

    @property
    def mode_value(self):
        """DeliveryRequest.mode 에 넣을 정수."""
        return MODES[self.mode]


def is_order_id(value):
    """계약 7절의 주문 ID 인가. QR 내용과 같은 문자열이다."""
    return bool(_ID.match(value or '')) and value.startswith(ORDER_PREFIX)


def is_bare_id(value):
    """접두 없는 ID 인가. 환자·약품 ID 에 쓴다."""
    return bool(_ID.match(value or '')) and not value.startswith(_PREFIXES)


def patient_tag_id(patient_id):
    """환자 인식표 QR 내용. 계약 7절 pt-<환자 ID>."""
    return PATIENT_PREFIX + patient_id


def station_tag_id(zone_id):
    """스테이션 인식표 QR 내용. 계약 7절 st-<스테이션 zone id>."""
    return STATION_PREFIX + zone_id


def request_id(epoch, seq):
    """계약 7절 request_id = r<epoch 3자리>-<seq 4자리>. 예 r001-0007."""
    if epoch < 0 or seq < 0:
        raise PoolError(f'epoch 와 seq 는 음수일 수 없다: epoch={epoch}, seq={seq}')
    return f'r{epoch:03d}-{seq:04d}'


def _require_str(value, field, order_id):
    if not isinstance(value, str):
        raise PoolError(
            f'{order_id}: {field} 는 문자열이어야 한다. 숫자로만 된 ID 는 따옴표로 감싼다 (예: "1001")')
    return value


def load_pool(document):
    """읽어 둔 mapping 을 PoolOrder 목록으로. 규칙을 어기면 PoolError."""
    if not isinstance(document, dict):
        raise PoolError('주문 풀 파일의 최상위는 mapping 이어야 한다')
    rows = document.get('orders')
    if not isinstance(rows, list) or not rows:
        raise PoolError('orders 는 비어 있지 않은 목록이어야 한다')

    orders = []
    seen = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise PoolError(f'orders[{index}] 는 mapping 이어야 한다')
        label = row.get('order_id', f'orders[{index}]')
        unknown = sorted(set(row) - set(_ALLOWED))
        if unknown:
            raise PoolError(f'{label}: 모르는 항목 {unknown}. 쓸 수 있는 것은 {list(_ALLOWED)}')
        for field in _REQUIRED:
            if field not in row:
                raise PoolError(f'{label}: {field} 가 없다')
            _require_str(row[field], field, label)

        order_id = row['order_id']
        if not is_order_id(order_id):
            raise PoolError(f'{order_id}: 주문 ID 는 ord- 로 시작하는 계약 7절 형식이어야 한다')
        if order_id in seen:
            raise PoolError(f'{order_id}: 주문 ID 가 두 번 나온다')
        seen.add(order_id)

        if not is_bare_id(row['patient_id']):
            raise PoolError(f'{order_id}: patient_id 는 접두 없는 ID 여야 한다. QR 은 pt- 를 붙여 만든다')
        if not is_bare_id(row['item_id']):
            raise PoolError(f'{order_id}: item_id 는 접두 없는 ID 여야 한다')
        if not _BED.match(row['bed']):
            raise PoolError(f'{order_id}: bed 는 bed_a1·station_b 형태의 구역 ID 여야 한다')

        mode = row.get('mode', 'single')
        if mode not in POOL_MODES:
            raise PoolError(f'{order_id}: mode 는 {list(POOL_MODES)} 중 하나여야 한다. 묶음은 풀 파일만으로 못 만든다')

        orders.append(PoolOrder(order_id=order_id, patient_id=row['patient_id'],
                                item_id=row['item_id'], bed=row['bed'], mode=mode))
    return tuple(orders)


def build_requests(orders):
    """주문 하나 = 요청 하나. 목적지는 그 주문의 침상이다. 파일 순서를 지킨다."""
    return tuple(PendingRequest(mode=order.mode, destination_id=order.bed,
                                order_ids=(order.order_id,)) for order in orders)


class RequestQueue:
    """발행기의 요청 큐. 긴급은 일반 요청보다 앞에 선다(계약 2.5절).

    긴급끼리는 FIFO 다. 먼저 들어온 긴급이 먼저 나간다.
    진행 중인 트립은 큐 밖에 있어서 이 클래스가 건드리지 않는다.
    """

    def __init__(self, requests=()):
        self._items = []
        for request in requests:
            self.push(request)

    def push(self, request):
        """큐에 넣는다. 긴급이면 마지막 긴급 뒤, 일반보다는 앞."""
        if request.urgent:
            index = 0
            while index < len(self._items) and self._items[index].urgent:
                index += 1
            self._items.insert(index, request)
        else:
            self._items.append(request)

    def pop(self):
        """맨 앞 요청을 꺼낸다. 비었으면 None."""
        return self._items.pop(0) if self._items else None

    def pending(self):
        """대기 중인 요청 순서."""
        return tuple(self._items)

    def __len__(self):
        return len(self._items)
