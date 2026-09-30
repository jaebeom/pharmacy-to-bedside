"""QR 내용 해석. 계약 2.4·7절, QR·DB·카메라 계약 1절. ROS 를 import 하지 않는다.

- 접두로 종류를 정한다: `pt-` 환자, `st-` 스테이션, `ord-` 봉투, `cn-` 약통, `md-` 모듈(사각 알약통).
- 봉투·약통·모듈은 **QR 내용 전체가 ID** 다(`Order.msg`: order_id = 봉투 QR 내용, 약통·모듈은 DB 키).
  약통·모듈 ID 는 `cn-0000`·`md-0000` 형식만 받는다(형식이 틀리면 모르는 QR 이다).
  환자·스테이션은 접두를 뗀 뒤가 ID 다(`pt-<환자 ID>`, `st-<스테이션 zone id>`).
"""

import re

_ID = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')
_ORDER_ID = re.compile(r'^ord-[0-9]{4}$')
_CONTAINER_ID = re.compile(r'^cn-[0-9]{4}$')
_MODULE_ID = re.compile(r'^md-[0-9]{4}$')

KIND_PATIENT = 'patient'
KIND_STATION = 'station'
KIND_POUCH = 'pouch'
KIND_CONTAINER = 'container'
KIND_MODULE = 'module'

# (접두, 종류, ID 에 접두를 남기는가)
PREFIXES = (
    ('ord-', KIND_POUCH, True),
    ('pt-', KIND_PATIENT, False),
    ('st-', KIND_STATION, False),
    ('cn-', KIND_CONTAINER, True),
    ('md-', KIND_MODULE, True),
)

# 접두 뒤 형식까지 정해진 종류. 나머지는 `_ID` 만 본다.
_STRICT = {KIND_CONTAINER: _CONTAINER_ID, KIND_MODULE: _MODULE_ID}


def parse_tag_id(payload):
    """QR 문자열에서 ID 를 뽑는다. 형식이 틀리면 None."""
    text = (payload or '').strip()
    return text if _ID.match(text) else None


def parse_tag(payload):
    """QR 내용 → (종류, ID). 접두가 없거나 형식이 틀리면 (None, None).

    >>> parse_tag('ord-0001')
    ('pouch', 'ord-0001')
    >>> parse_tag('pt-p001')
    ('patient', 'p001')
    >>> parse_tag('st-station_a')
    ('station', 'station_a')
    >>> parse_tag('cn-0101')
    ('container', 'cn-0101')
    """
    text = parse_tag_id(payload)
    if text is None:
        return None, None
    for prefix, kind, keep_prefix in PREFIXES:
        if text.startswith(prefix) and len(text) > len(prefix):
            strict = _STRICT.get(kind)
            if strict is not None and not strict.match(text):
                return None, None
            return kind, (text if keep_prefix else text[len(prefix):])
    return None, None


def tag_kind(payload):
    """QR 내용의 종류만. 모르면 None."""
    return parse_tag(payload)[0]


def is_order_id(payload):
    """주문 ID 형식인가. 계약 7절의 `ord-0001`."""
    return bool(_ORDER_ID.match((payload or '').strip()))
