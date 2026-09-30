"""K4·K5 의 참값 센서: 봉투 검출과 인식표 판독. Isaac 임포트는 늦게 한다.

**스텁이 아니라 센서다.** 판정 영역 안에 실제로 있는 것만 낸다 — 없으면 빈 목록이고, 그래서 음성 사례
(`not_detected`·`UNREADABLE`)가 선다. 스텁을 고치는 대신 센서를 두는 이유가 이것이다(비전 9/21).

길: 스테이지가 JSON(`std_msgs/String`)으로 내고 → `isaac_adapter`(통합&정비)가 `PouchDetection`·`TagRead` 로
옮겨 `/{ns}/sim/*` 에 낸다. 팔은 opt-in(`pouch_source: sim`·`scan_tag_source: sim`)일 때만 구독한다.
계약 토픽 `hand_camera/*` 의 작성자는 그대로 perception 하나다.

자세 기준 프레임은 **팔 노드의 기준 프레임**이다(`arm_base_frame`, 지금 `amr_1/base_link` = 받침대 UR5 의 밑동).
v0 에서 UR5 는 AMR 위가 아니라 받침대에 월드 고정이고 벨트·상판도 고정이라, 그 변환은 항등이 아니라
**상수**다 — AMR 이 어디 있든 안 변한다. 그래서 여기서 월드 좌표를 그 프레임으로 옮기는 것은 뺄셈 하나다.

여기 함수는 전부 순수 함수다. Isaac 에서 읽은 참값을 넣으면 낼 메시지를 돌려준다.
"""

from . import bridge

#: 벨트 끝 판정 영역의 반경(m, xy). 이 안에 있는 봉투만 "벨트 끝에 있다" 로 본다. 임시값이고 실측 아님.
#:
#: **`--end-zone` 보다 커야 한다.** 봉투는 벨트 끝(x 2.95)까지 가지 않는다 — 정지 구역에 들어서는 순간
#: 벨트가 서므로 **끝에서 `end_zone` 만큼 앞에 선다**(실습25: 관측 x 2.805, 계산 2.800 + 정착 밀림 0.005).
#: 반경이 `end_zone` 보다 작으면 **벨트가 선 바로 그 순간 검출이 끊긴다** — 팔이 집으러 오는 그때다.
#: 지금 여유는 0.25 − 0.15 = 0.10 m 다.
BELT_END_RADIUS = 0.25
#: 이 속도(m/s)보다 빠른 봉투는 **검출로 내지 않는다.**
#:
#: 센서 영역(0.25)이 벨트 정지 구역(0.15)보다 넓어서, 봉투가 **아직 굴러가는 동안** 0.667 s 먼저 검출된다
#: — 그 사이에 0.10 m 를 더 간다. lap5 에서 팔이 그 자세로 풀었고, 봉투가 실제로 선 자리와 **0.0988 m**
#: 어긋났다(계산 0.1000 과 같다). 그 0.1 이 앞팔↔벨트 여유를 +0.087 에서 +0.001 로 깎아 ⑤를 닫았다.
#:
#: `PouchDetection` 에는 속도 자리가 없고 팔에는 추종 파지가 없다 — **못 잡을 목표를 주지 않는다.**
#: `--settle-speed`(0.01)와 같은 뜻이고 그보다 넉넉하게 둔다.
POUCH_STILL_SPEED = 0.02
#: 검출 신뢰도. 참값이라 1.0 이다 — 이 값이 1.0 이 아니면 참값이 아니라는 뜻이다.
TRUTH_CONFIDENCE = 1.0
#: 봉투 센서 주기(Hz). 팔의 detection_max_age_s(1 s)에 넉넉하다.
POUCHES_HZ = 10.0
#: 인식표 센서 주기(Hz). 서 있는 동안 계속 낸다 — 변할 때만 내면 놓쳤을 때 못 살아난다.
TAG_READS_HZ = 5.0
#: "이 침상 앞에 서 있다" 로 볼 반경(m, xy). **주행의 도착 공차(`tol_xy`)와 같은 값을 쓰지 않는다.**
#:
#: 실습26(9/21): 추종기가 공차 원에 **들어서는 즉시** 멈춰 여섯 번 모두 목표에서 0.1396–0.1461 m 였다.
#: 공차 0.15 를 그대로 센서 판정에 쓰면 여유가 **4–10 mm** 다 — 추종 오차가 조금만 늘면 인식표가 안 나오고
#: 인증이 `UNREADABLE` 로 닫힌다. "도착했나" 와 "인식표를 읽을 수 있나" 는 다른 질문이고 같은 숫자일 이유가 없다.
#:
#: 아래로: 주행 공차 + 여유보다 커야 한다(공차가 커지면 같이 커져야 한다 — 관계를 시험이 잡는다).
#: 위로: 자리가 다른 침상 사이 거리의 절반(2.40 / 2 = 1.20)보다 작아야 한다. 넘으면 옆 침상과 헷갈린다.
#: 0.35 는 그 사이에서 관측(0.146)에 **0.20 m 의 여유**를 둔 값이다. 임시값이고 실측 아님.
TAG_READ_RADIUS = 0.35


def to_base(world_xyz, base_xyz):
    """월드 좌표를 팔 기준 프레임으로. v0 은 회전이 없어 뺄셈이다(UR5 가 월드 축과 정렬돼 있다)."""
    return tuple(float(w) - float(b) for w, b in zip(world_xyz, base_xyz, strict=True))


def in_belt_end(world_xyz, belt_end_xy, radius=BELT_END_RADIUS):
    """벨트 끝 판정 영역 안인가. xy 만 본다 — 봉투 두께로 z 가 갈리면 안 된다."""
    dx = float(world_xyz[0]) - float(belt_end_xy[0])
    dy = float(world_xyz[1]) - float(belt_end_xy[1])
    return (dx * dx + dy * dy) ** 0.5 <= radius


def in_slot(world_xyz, slot_xyz, slot_size):
    """상판 칸 AABB 안인가. `in_slot` 참값과 **같은 판정**이다(refill.point_in_aabb 와 같은 뜻)."""
    return all(abs(float(world_xyz[i]) - float(slot_xyz[i])) <= float(slot_size[i]) / 2.0 for i in range(3))


def detection(order_id, base_xyz_pose, orientation_xyzw):
    """검출 원소 하나. `slot_index` 는 계약 319줄대로 **항상 −1** 이다."""
    x, y, z = (float(v) for v in base_xyz_pose)
    ox, oy, oz, ow = (float(v) for v in orientation_xyzw)
    return {"order_id": order_id or "",
            "confidence": TRUTH_CONFIDENCE,
            "pose": {"position": {"x": x, "y": y, "z": z},
                     "orientation": {"x": ox, "y": oy, "z": oz, "w": ow}},
            "slot_index": bridge.SLOT_INDEX_V1}


def wxyz_to_xyzw(quat):
    """Isaac 의 (w, x, y, z) -> 메시지의 (x, y, z, w). 순서를 섞으면 자세가 조용히 틀린다."""
    w, x, y, z = (float(v) for v in quat)
    return (x, y, z, w)


def pouches_message(sim_time, epoch, frame_id, detections):
    """`/isaac/amr_1/pouches` 본문. 검출이 없으면 **빈 목록으로 낸다**(안 내지 않는다)."""
    return {"v": bridge.SCHEMA_VERSION, "stamp": bridge.stamp(sim_time), "epoch": int(epoch),
            "frame_id": frame_id, "detections": list(detections)}


#: 보관함 참값을 볼 부피의 높이(m). 지금 보관함은 **속이 찬 상자**라 봉투는 윗면에 얹힌다 —
#: "안에 있다" 가 아니라 "윗면 위 이 높이 안에 있다" 다. 열린 칸으로 바꾸면 칸 부피로 바뀐다.
CABINET_VOLUME_HEIGHT = 0.12
#: 보관함 참값 주기(Hz).
CABINET_HZ = 5.0


def in_cabinet(world_xyz, cabinet_xyz, cabinet_size, height=CABINET_VOLUME_HEIGHT):
    """봉투가 그 보관함의 판정 부피 안인가. `cabinet_xyz` 는 **윗면 중심**(계약 471줄의 뜻)이다.

    상판 칸의 `in_slot` 과 **같은 AABB 판정**이다 — 이벤트나 주장에서 만들지 않고 자세로 본다.
    윗면에서 위로 `height` 까지를 본다: 놓인 직후뿐 아니라 **미끄러져 나가면 false 가 되어야** 하기 때문이다
    (#444 F04: 한 번 true 가 영구 성공이 되는 구멍).
    """
    hx, hy = float(cabinet_size[0]) / 2.0, float(cabinet_size[1]) / 2.0
    dx = abs(float(world_xyz[0]) - float(cabinet_xyz[0]))
    dy = abs(float(world_xyz[1]) - float(cabinet_xyz[1]))
    dz = float(world_xyz[2]) - float(cabinet_xyz[2])
    return dx <= hx and dy <= hy and 0.0 <= dz <= float(height)


def cabinet_updates(inside, before):
    """한 보관함의 이번 관측 → ([(order_id, present)], 들어온 주문들, 새 상태). 순수 함수.

    `inside` 는 지금 그 보관함 부피 안의 주문(순서 유지), `before` 는 지난번 안에 있던 주문 집합.
    **안에 있는 주문마다** present 를 낸다 — 한 보관함(병실 C 테이블)에 봉투 여럿이 놓인다(재범 9/25).
    9/25 campaign 1 attempt 6(#240 5824830092): 보관함마다 첫 주문 하나만 내서 station_d 3봉투 중 ord-0005 만
    present 로 남았다. 빠져나간 주문은 false 를 한 번 낸다(true→false, #444 F04). 비었으면 빈 order_id 로 false.
    """
    now = list(dict.fromkeys(inside))
    gone = sorted(set(before) - set(now))
    updates = [(order_id, True) for order_id in now] + [(order_id, False) for order_id in gone]
    if not updates:
        updates = [("", False)]
    entered = [order_id for order_id in now if order_id not in before]
    return updates, entered, set(now)


def cabinet_message(sim_time, epoch, cabinet_id, order_id, present):
    """`/isaac/evaluator/cabinet` 본문. **true→false 도 낸다** — 놓은 뒤 미끄러져 나가면 false 가 나가야
    한다(#444 F04). "해제 뒤 몇 초 유지" 판정은 받는 쪽(run 기록) 일이다."""
    return {"v": bridge.SCHEMA_VERSION, "stamp": bridge.stamp(sim_time), "epoch": int(epoch),
            "cabinet_id": cabinet_id, "order_id": order_id or "", "present": bool(present)}


def patient_tag(patient_id):
    """계약 7절: 환자 인식표는 `pt-` + patient_id."""
    return f"pt-{patient_id}"


def station_tag(zone_id):
    """계약 7절: 스테이션 인식표는 `st-` + zone id."""
    return f"st-{zone_id}"


def tag_for_zone(zone_id, stations, bed_patients):
    """정차한 구역의 인식표 (tag_id, kind). 테이블 스테이션이면 `st-<zone>`, 환자 침상이면 `pt-<환자>`, 아니면 None.

    **스테이션이 먼저다.** 테이블에는 환자 표가 아니라 스테이션 표가 붙는다(재범 9/25: 병동 → B, 병실 → C).
    station_b 는 1인 주문 풀(ord-0011)에서 환자 침상으로도 나오지만, 거기서도 `st-station_b` 를 낸다.
    """
    if zone_id in stations:
        return station_tag(zone_id), "station"
    patient = bed_patients.get(zone_id)
    if patient is None:
        return None
    return patient_tag(patient), "patient"


def tag_message(sim_time, epoch, frame_id, zone_id, tag_id, kind="patient", status="ok"):
    """`/isaac/amr_1/tag_reads` 본문. `tag_id` 를 비우면 안 된다 — 비면 orchestrator 가 스텁 태그로 비교해
    인증이 거짓 통과한다(비전 #417 4절). 그래서 부를 곳에서 없으면 **아예 안 내는** 쪽을 고른다."""
    return {"v": bridge.SCHEMA_VERSION, "stamp": bridge.stamp(sim_time), "epoch": int(epoch),
            "frame_id": frame_id, "zone_id": zone_id, "kind": kind, "tag_id": tag_id, "status": status}


def parked_zone(base_pose, zones, tol_xy, tol_yaw):
    """AMR 이 지금 서 있는 구역 id. 어디에도 안 맞으면 None.

    **yaw 를 같이 본다.** `bed_a1` 과 `bed_b1` 은 같은 (x, y) 에 yaw 만 반대라 위치만 보면 못 가른다
    (시뮬 배치: 두 줄이 통로 하나를 공유한다). 이것이 빠지면 "다른 침상에서 AUTH_FAIL" 이라는
    음성 판정이 통과해 버린다(비전 9/21).

    `tol_xy` 는 **센서의 판정 반경**(`TAG_READ_RADIUS`)이지 주행의 도착 공차가 아니다. `tol_yaw` 는
    주행 공차 그대로다 — **yaw 쪽은 넓히면 안 된다.** 넓히면 a1 과 b1 이 섞인다.
    """
    import math

    x, y, yaw = (float(v) for v in base_pose)
    best = None
    for zone_id, pose in zones.items():
        if "/" in zone_id:
            continue
        dx, dy = x - float(pose[0]), y - float(pose[1])
        distance = (dx * dx + dy * dy) ** 0.5
        if distance > tol_xy:
            continue
        error = abs((yaw - float(pose[3]) + math.pi) % (2.0 * math.pi) - math.pi)
        if error > tol_yaw:
            continue
        if best is None or distance < best[1]:
            best = (zone_id, distance)
    return best[0] if best else None


def nearest_zone_diagnosis(base_pose, zones, tol_xy, tol_yaw):
    """제일 가까운 구역과 **왜 안 맞았는지**. `(zone_id, distance, yaw_error, reason)` 또는 None.

    `parked_zone` 이 None 을 돌려주면 `tag_reads` 는 **아무것도 안 나간다** — 빈 `tag_id` 를 내면
    orchestrator 가 스텁 태그로 비교해 인증이 거짓 통과하기 때문이다(비전 #417 4절). 그 선택은 맞다.
    **그런데 조용하다.** lap8 이 ⑥ 도착까지 가고 ⑦ `AUTH_FAIL` 로 닫혔는데 스택에 스캔 줄이 없었고,
    거리가 먼 것인지 yaw 가 어긋난 것인지 환자 표가 빈 것인지 **로그만으로는 갈리지 않았다.**

    이 함수는 메시지를 만들지 않는다 — **부르는 쪽이 진단 줄을 찍는 데만** 쓴다. 참값의 뜻은 그대로다.
    """
    import math

    x, y, yaw = (float(v) for v in base_pose)
    best = None
    for zone_id, pose in zones.items():
        if "/" in zone_id:
            continue
        dx, dy = x - float(pose[0]), y - float(pose[1])
        distance = (dx * dx + dy * dy) ** 0.5
        error = abs((yaw - float(pose[3]) + math.pi) % (2.0 * math.pi) - math.pi)
        if best is None or distance < best[1]:
            best = (zone_id, distance, error)
    if best is None:
        return None
    zone_id, distance, error = best
    if distance > tol_xy:
        reason = f"거리 {distance:.4f} > {tol_xy}"
    elif error > tol_yaw:
        reason = f"yaw 오차 {error:.4f} > {tol_yaw}"
    else:
        reason = "구역은 맞는다 — 환자 표에 그 침상이 없다"
    return (zone_id, distance, error, reason)


def bed_patients(order_pool_text):
    """주문 풀 본문에서 `{침상: {환자 id}}`. PyYAML 없이 읽는다(Isaac 의 python 에 없다).

    집합으로 모으는 이유는 **한 침상에 환자가 둘 이상이면 기동을 거부**하기 때문이다 — 어느 인식표를
    낼지 모르는 채로 하나를 고르면 인증이 조용히 틀린다(fail-closed, 비전 9/21).
    """
    import re

    out = {}
    for line in order_pool_text.splitlines():
        bed = re.search(r"\bbed:\s*[\"']?([a-z_0-9]+)", line)
        patient = re.search(r"\bpatient_id:\s*[\"']?([A-Za-z0-9_-]+)", line)
        if bed and patient:
            out.setdefault(bed.group(1), set()).add(patient.group(1))
    return out


def ambiguous_beds(table):
    """환자가 둘 이상인 침상. 비어 있지 않으면 기동을 거부한다."""
    return sorted(bed for bed, patients in table.items() if len(patients) > 1)
