# 병원 월드 연결 로직 — 교차검토 후보

> **상태: 지난 기록 (2026-09-22 기준).** 이 검토 대상 코드는 #490 으로 main 에 들어갔다(2026-09-23). 지금은 [병원 전 구간 런카드](../../docs/runbooks/hospital-full.md)를 따른다.
> 아래 "Draft"·"병합 보류"·"이 PR" 은 9/22 검토 시점의 말이다. 지금 병원 경로는 `--preset hospital --workcell-layout` 이다.

작성 당시 상태: Draft. 원통 3회 L3 미검증으로 병합 보류였다.

측정 배치를 기존 `pharmacy_stage`와 `m0609_arm`에 전달한다. #488의 시각 데모와 구분하며 기존 IK·레일 탐색·속도·파지 알고리즘은 유지한다.

## 공용 코드와 로컬 입력

| 공용 Git 변경 | 현장 전용, Git 제외 |
| --- | --- |
| JSON 입력 검사와 기존 inventory 형식 변환 | 레일 원점·행정, 선반·투입구 좌표, 장애물 실측 |
| 기존 ROS runtime의 선택형 `--workcell-layout` 연결 | 자산 절대 경로, 도메인, 설치 경로 |
| 기존 planner의 오프라인 계산 호출 | 투입구 보정량, 카메라, AMR 시작점 |
| 순차 3회 action 요청·관측·결과 대조 | 준비된 USD, 현장 생성기, 로그·영상·실제 계획 결과 |

설정은 `config/local/workcell.local.json` 또는 저장소 밖에 둔다. 기존 `.gitignore`가 `config/local/**`, `*.local.json`을 제외한다. 이 PR에는 실제 현장 설정이나 이를 하드코딩한 준비기를 포함하지 않는다. 테스트의 좌표는 합성값이며 배포 설정으로 쓰지 않는다.

`workcell_layout.load` 입력 필드는 다음과 같다. 실행 전에 현장 준비기와 검토자가 USD와 JSON이 같은 배치를 가리키는지 대조해야 한다.

- `version=1`, `frame=hospital_world_m_z_up`: m, Z-up, 현재 연결은 평행한 XYZ 축만 지원한다. 회전된 레일을 지원한다고 주장하지 않는다.
- `cells`: 9개 선반 각각 원통 칸 하나와 모듈 칸 하나(총 18칸). ID별 `shelf`, `row`, `col`, `type`, `access=front`, `surface`, `size`, `height`.
- `targets`: `round`의 `center`, `axis`, `inner_diameter`, `floor_z`, `depth`; `module`의 `entry_center`, `axis`, `opening`, `depth`.
- `obstacles`: `name`, `center`, `size`의 월드 축에 정렬된 장애물 상자(AABB) 목록. 같은 충돌 예외 분류(`RoundBin`, `DispenserFront`, 그 외 본체) 안에서만 완전 포함 상자를 뺀다. 분류가 다른 중첩은 둘 다 남긴다. 팔과 레일의 중간 이동 구간까지 충돌 모델이 포괄하는지는 별도 검토한다.
- `rail`: `origin`은 바닥의 레일 원점. `x_stroke`, `y_limits`, `z_limits`, `carriage_height`. ROS 베이스 원점은 `origin.z + carriage_height`, 각 레일 관절값은 해당 원점 기준 변위다.
- `belt`: `start`, `length`, `yaw`; `amr_start`; `camera`: `eye`, `target`, `focal_mm`; `source_sha256`: 입력 자산 식별용 필드. 런타임 inventory와 오프라인 `inventory_for_planning`의 `source`는 파일 바이트 sha256(`hospital_workcell:<hex>`)이며, 필드 값과 파일 해시를 같다고 요구하지 않는다.

현장 배치 입력만으로 팔/레일 도달·충돌·제동이 검증되는 것은 아니다. 입력 단계에서 투입구·물품 크기·벨트·카메라의 유한값과 지원 축을 검사한다. 실제 USD와의 정합성이나 도달 가능성까지 보증하는 검사는 아니다. 현재 adapter는 병원 주행을 켜지 않는다.

## 검토 순서와 담당

1. manipulation 담당 전제환: 빈월드 실습의 베이스/레일 좌표 관계, 기존 planner 호출과 이송 중 충돌 검사, 속도 설정 소유권을 검토한다.
2. simulation 담당 박세준: #484의 월드 축·단위와 선반/조제기 형상, USD와 inventory의 좌표 일치, 장애물 모델 누락 여부를 검토한다.
3. 리뷰 지적을 코드로 반영한 뒤 지정 SHA로 현장 배치를 준비한다. 레일 원점/행정을 비교하고 선반 접근→파지→이탈→접힘→레일 이송→투입→복귀를 다시 계산한다. 빈월드의 월드 절대좌표를 그대로 복사하지 않는다.
4. 사전 계획을 확인한 뒤 같은 SHA와 설정 해시로 무작위 원통 3회 L3를 실행한다. 검토 요청은 수락이나 승인으로 간주하지 않는다.

계획 호출은 `check_workcell_plans.py --layout <local-json> --seed <recorded-seed> --output <external-jsonl>`이다. 기본 `preferred_first`는 기존 planner의 선택지이며 새 알고리즘이 아니다. 실행에는 `PYTHONPATH=sim/standalone:src/rokey_p3_manipulation`과 PyYAML이 필요하다. 이 도구의 기본 범위는 원통 3개이고 전체 선반·모듈 검증을 대신하지 않는다.

현장 배포 때 `pharmacy_stage.py --workcell-layout <local-json>`에는 `--base-usd`, `--amr-combined`도 필요하다. 이 모드는 `hospital-v2` preset을 쓰지 않는다. `pharmacy-origin`은 0이고 JSON `frame`은 `hospital_world_m_z_up`이다. `--base-deactivate`와 `--base-rigid-off`를 주지 않으면 `HOSPITAL_DEACTIVATE`와 `HOSPITAL_RIGID_OFF`(씬 벨트 강체 끔)를 자동 적용한다. 나머지 자산·ROS 환경은 기존 runbook을 따른다. 입력 파일은 시작 때 한 번 읽는다. 런타임의 방·카메라·inventory source와 오프라인 계획은 같은 스냅샷 해시를 사용한다. 실행 중 파일을 고쳐도 이미 구성된 씬의 식별자가 바뀌지 않는다.

실제 ROS 노드가 난수 선택과 움직임을 소유한다. 실행 명령은 다음과 같다.

```text
run_workcell_refill_trials.py --layout <same-local-json> --output <new-external-directory>
```

기록기는 `/m0609/arm/plan_cache`의 latched JSON(`solved`, `total`, `failed`, `source`)이 현재 inventory `source`와 같고, 전체 칸 수와 계획 가능한 서로 다른 원통 선반 3개를 만족할 때까지 기다린다. inventory가 캐시 이후에 다시 나와도 source가 같으면 무효로 보지 않는다. stdout 로그의 `v2 계획 캐시:` 줄을 긁지 않는다. 단일 clock 발행자, 최근 시각 증가, 실제 inventory와 입력 기하의 일치도 확인한다. 성공 결과 뒤 `at_home`은 결과 시각 이후 표본이 있으면 그 마지막 값을 쓰고, 없으면 한 heartbeat(0.2 s) 뒤에 결과 직전 표본을 허용한다. `/m0609/arm/at_home` 구독은 노드와 같은 reliable heartbeat QoS다. goal 실행 중 clock 정지·역행이나 기하 변경을 발견하면 취소를 요청하고 후속 goal을 보내지 않는다. 취소 요청이 성공했다는 것만으로 로봇 정지를 보증하지 않는다.

`--observe-only-seconds`는 goal 없이 기록한다. 오류/중단도 외부 `error.json`과 `results.json`에 남긴다. cache 완료 대기 1200 wall s와 goal 240 wall s는 분리하며, 노드의 기존 실행 timeout은 변경하지 않는다.


## 검증 상태와 한계

기존 실험 브랜치에서는 파지 후 이동 중 충돌과 시간초과가 발생했다. 원통 3회 연속 완료는 확인되지 않았다. 최신 대기 회차는 좌표/로직 교차검토를 먼저 하라는 사용자 지시에 따라 goal 전송 전에 중지했다. 이 문서는 실패를 성공으로 대체하지 않는다.

이 검토용 브랜치의 Isaac L3는 **미실행**이다. `/m0609/arm/plan_cache`를 내기 위해 `m0609_arm_node`를 바꿨다. `colcon build/test`는 **미실행**이다. L1과 저장소 검사 결과는 PR에 정확히 기록한다. 시뮬레이터의 파지는 기존 거리 기반 attach이고 실물 마찰 파지 검증이 아니다. 이송 중 충돌이 해결됐다고 주장하지 않는다. IK·속도·`plan_refill`·timeout은 이 변경에서 건드리지 않는다.

레일의 설정 속도와 관측 속도는 별개다. 결과 도구는 실제 JointState 속도 최고값을 보존한다. action 성공만으로 통과하지 않고 같은 셀의 attach, round release, 홈 복귀를 함께 확인한다. 결과 요약 도구는 별도 PR #489로 분리했다. 한 실행의 원통 전용, 셀당 1회인 로그를 입력으로 가정하므로 재시도/여러 실행 로그를 합치면 안 된다.

이전 `feat/hospital-random-pick-practice` 브랜치의 `8bfd61e`는 검토용 PR의 부모가 아니다. 그 브랜치에는 현장값과 임시 소스가 섞여 있어 병합 대상으로 사용하지 않는다. 기존 원격 커밋 기록은 남아 있으며 이 PR로 기록을 삭제했다고 주장하지 않는다.

## 기존 현상에 대한 교차검증 요청

이하 관측은 기존 실험 브랜치의 기록이며 이 Draft head의 L3 결과가 아니다. 실행별 원본과 해시는 기존 실패 기록 커밋 `8bfd61e`에 연결되어 있다. 좌표를 소스에 승격하지 않기 위해 현장 생성기/실측 JSON은 이 PR에 넣지 않는다. 정확한 현장 재현은 해당 외부 아티팩트와 설정 해시가 필요하며, 저장소만으로 완전 재현 가능하다고 주장하지 않는다.

| 조건 | 관측 | 미확정 원인·검토 질문 |
| --- | --- | --- |
| run07, 기존 `first_feasible`, 병원 inventory | 파지·들기·꺼내기 뒤 link_2와 PillSupport 접촉, 이송/복귀 실패 | 정적 팔 자세 검사와 접힌 팔의 레일 이송 검사 범위 차이인지, USD·계획 장애물 불일치가 있는지 |
| run08, 기존 `preferred_first`, 캐시 계산 중 goal 전송 | `preferred_first HOLD: rail transfer interrupted; reset required (gripper unchanged)`, `timeout 90.0 s sim`, `rail_to_inlet_cross_xy` 실패. action status 6, success false, last_release null, home false | 계획 계산과 실행이 같은 90 sim s 제한을 소비하는 영향. 제한을 늘리지 않고 준비 완료를 어떤 인터페이스로 확인할지 |
| run09, goal 전송 전 | 캐시 완료 대기 중 좌표/로직 검토 요청에 따라 중단 | 재계획·배치 검토 후 새 SHA/설정으로 재시험 필요 |

`scene_v2.py`의 `plan_refill`, `_place_leg`, `checked_rail_moves`가 검토 시작점이다. 이 PR은 이 함수나 IK·속도·timeout을 수정하지 않는다. 빈월드의 상대 배치를 기준으로 원점·행정 후보를 정하고, 선반 파지부터 조제기 투입 및 빈손 복귀까지 다시 계산해야 한다. 특히 정적 목표 도달과 이송 중 충돌을 구분한다.

검토자가 확인할 미완료 항목: 캐시 토픽은 기존 사전계산이 끝난 뒤의 요약이며 새 계획 알고리즘이 아니다. 이후 기하가 바뀌면 진행을 중단하므로 새 기동과 재계산이 필요하다. 모듈을 포함한 모든 셀 계획, 충돌 모델 완전성, 실제 속도 상한, 재시작/복구 L3는 미완료다. 본문에 실패가 적혀 있다는 이유로 해결 완료·머지 가능으로 해석하지 않는다.
