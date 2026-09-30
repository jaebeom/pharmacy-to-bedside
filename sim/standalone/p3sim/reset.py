"""/sim/reset on the Isaac side: step order and fault injection. No Isaac imports.

Contract v1 6 step 2 (isaac part): remove pouch prims, stop the belt, open grippers, M0609 home, restore canisters
refilled before the reset, then ok. The timeline is NOT stopped: /clock stays monotonic (contract 4). The received
epoch is carried on later events.
"""

import math

STEPS = ("stop_belt", "remove_pouches", "open_grippers", "m0609_home", "restore_canisters", "clear_timers",
         "set_epoch")


class ResetInjection:
    """Fault injection like the bringup L2 tests: --reset-fail answers ok=false, --reset-delay-s answers late."""

    def __init__(self, fail=False, delay_s=0.0, message="injected_failure"):
        self.fail = fail
        self.delay_s = max(0.0, delay_s)
        self.message = message

    def outcome(self):
        """(ok, message) for a completed reset."""
        return (False, self.message) if self.fail else (True, "")


def epoch_note(current, requested):
    """Log note when the requested epoch does not move forward (the orchestrator owns epochs; we still accept)."""
    if requested <= current:
        return f"epoch {requested} is not greater than current {current}"
    return None


#: 리셋 뒤 자세를 재는 때(sim s). 위치를 쓴 직후 값은 쓴 값 그대로라 드라이브가 버티는지 보려면 조금 기다린다(추정).
POSE_CHECK_DELAY_S = 1.0


def max_joint_error(home, now):
    """관절마다 |now − home| 의 최댓값(rad). 어느 쪽이든 없거나 길이가 다르면 None."""
    if home is None or now is None or len(home) != len(now) or not len(home):
        return None
    return max(abs(float(b) - float(a)) for a, b in zip(home, now, strict=True))


def pose_line(epoch, amr_base, arm_errors):
    """리셋 뒤 초기 자세 대조 한 줄(#696 제안 4, 로그만 — 판정하지 않는다).

    `amr_base` 는 AMR 출발 자세 대비 (dx, dy, dyaw) 오차다. x/y 는 dummy 관절값이며,
    yaw 는 세계 방향 관절값에서 설정된 출발 yaw 를 빼서 넘긴다.
    `arm_errors` 는 {이름: 홈 대비 최대 관절 오차(rad) 또는 None}. 없는 값은 `-` 로 쓴다.
    """
    if amr_base is None:
        amr = "amr_dxy=- amr_dyaw=-"
    else:
        amr = f"amr_dxy={math.hypot(amr_base[0], amr_base[1]):.4f} amr_dyaw={abs(amr_base[2]):.4f}"
    arms = " ".join(f"{name}_max_rad={'-' if error is None else f'{error:.4f}'}"
                    for name, error in arm_errors.items())
    return f"reset pose epoch={epoch} after_s={POSE_CHECK_DELAY_S:.1f} {amr} {arms}".rstrip()
