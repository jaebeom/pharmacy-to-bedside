"""`rokey_p3_orchestrator.status_view` 를 **그대로 가져다 쓴다.** 복사하지 않는다.

`status_view.py` 는 ROS 를 import 하지 않으므로 여기서 그냥 쓸 수 있다. 단계표·신호 목록·
신선도 임계·이벤트 순서 키를 여기서 한 번만 정의하게 해서, 터미널 모니터와 웹이 **같은 것을
보게** 한다. 저쪽이 바뀌면 여기도 따라 바뀐다 — 두 벌로 갈라지면 화면마다 다른 말을 한다.

워크스페이스를 source 했으면 평범한 import 로 잡힌다. `--mock` 개발에서는 그게 없으므로
저장소 안의 파일 경로로 직접 읽는다. **어느 쪽이든 원문 한 벌이다.**
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_RELATIVE = Path("src/rokey_p3_orchestrator/rokey_p3_orchestrator/status_view.py")


def _load_status_view():
    try:  # 워크스페이스를 source 한 경우
        from rokey_p3_orchestrator import status_view
        return status_view
    except ImportError:
        pass
    # 저장소 안에서 직접 읽는다 (web/backend/app → 저장소 루트는 3 단계 위)
    for base in Path(__file__).resolve().parents:
        candidate = base / _REPO_RELATIVE
        if candidate.is_file():
            spec = importlib.util.spec_from_file_location(
                "rokey_p3_status_view", candidate)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            return module
    raise ImportError(
        f"status_view.py 를 못 찾았다. 저장소 안({_REPO_RELATIVE})에서 돌리거나 "
        "워크스페이스를 source 해라.")


status_view = _load_status_view()

# 원문에서 그대로 가져오는 것들 — 여기서 새로 정의하지 않는다.
event_key = status_view.event_key
StatusModel = status_view.StatusModel
TRIP_PHASES = status_view.TRIP_PHASES
SIGNAL_FRESH_S = status_view.SIGNAL_FRESH_S
CLOCK_FRESH_S = status_view.CLOCK_FRESH_S

#: 신호 키 5개. 원문은 (키, 이름표) 쌍이라 키만 뽑는다.
SIGNAL_KEYS = tuple(key for key, _label in status_view.SIGNALS)

#: 원문의 한글 라벨 → 우리 API 의 영문 phase 키. **라벨이 정본이고 이건 우리 편의다.**
#: 라벨 하나에 여러 이벤트가 붙으므로(픽, 보관함 배달) 라벨 기준으로 맵을 만든다.
PHASE_KEYS = {
    "적재 위치로 이동": "accepted",
    "배출": "docked_load",
    "벨트 이송": "dispensing",
    "벨트 끝 픽": "dispensing",
    "픽": "loading",
    "적재": "loading",
    "적재 끝": "load_done",
    "팔 홈": "arm_home",
    "병동으로 이동": "moving",
    "병동 도착 직전": "arriving",
    "인증": "arrived",
    "보관함 배달": "unloading",
    "인증 실패": "auth",
    "보관함 잠김": "locked",
    "주문 닫힘": "order_done",
    "도크로 복귀": "returning",
    "대기(도크)": "docked",
    "리셋 중": "reset",
    "리셋 끝(3 s 뒤 요청 수락)": "reset_done",
}


def phase_for(event_name: str) -> tuple[str | None, str | None]:
    """이벤트 이름 → (영문 phase, 한글 phase_label). 단계를 안 바꾸는 이벤트면 (None, None).

    조제기·M0609 이벤트는 원문 표에 없으므로 자연히 (None, None) 이 된다.
    """
    label = TRIP_PHASES.get(event_name)
    if label is None:
        return None, None
    return PHASE_KEYS.get(label, label), label
