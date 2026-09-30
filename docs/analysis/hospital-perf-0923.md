# 병원 전 구간 성능 — 측정과 조치 (2026-09-23)

## 결론

1. **기동 1분 52초는 대부분 팔 계획 캐시(73.6 s)였다.** Isaac 쪽 stage ready 는 32 s 다. 캐시를 파일로 저장해 다시 쓰게 했다(8fd2492, fe12f5d). 두 번째 기동의 실제 시간은 **미실행**이다.
2. **rtf 0.42 는 GPU 가 80 W 에 묶인 상태에서 한 틱이 무거워서다.** `nvidia-smi -pl` 은 노트북이라 not supported 다. 3b76030 한 틱의 시간 구성은 omni.graph 35%, physx 17%, `slots_in_world` 16% 다. `slots_in_world` 는 고쳤다(3ad7c5e).
3. **렌더 해상도·카메라·라이다·PhysX 경고는 주 원인이 아니었다.** 남은 후보는 omni.graph 의 내역(미확인)과 매 틱 USD 쓰기다.

상태: unreviewed.
원본은 master02 `~/markle_tmp/` 회차 폴더다. 수치는 master02 원본에서 뽑아 보낸 값이다. 원본은 직접 읽지 않았다.
앞 문서: [2026-09-23-hospital-sim-load.md](2026-09-23-hospital-sim-load.md)(회차별 rtf 표, 경고 출처).
환경: master02(IsaacSim07), RTX 5080 Laptop 16 GB, 드라이버 580.173.02, Isaac Sim 5.1.0. 창 모드, `--window-half left --screen-size 2048 1152`.
acceptance run 이 아니다. 판정선은 바꾸지 않는다.

## 1. 측정 순서

| 순서 | 회차(SHA) | 잰 것 | 나온 것 |
| --- | --- | --- | --- |
| 1 | 실습40 병원 주행 회차들 | rtf, PhysX 경고 줄 수 | rtf 는 0.47-0.55 와 0.93-1.0 두 무리. 경고는 0-3,648 줄 |
| 2 | 39d1ce5 | kit.log 경고 출처, gpu.csv, top | 경고 419,292 줄은 약통 18쌍과 선반의 접촉 보고. rtf 0.340, loop_hz 20.26 |
| 3 | 39d1ce5 gpu.csv | GPU 전력 | 609 s 중 566 s 가 SW power cap(0x4). util 중앙 44%. 상한 80 W |
| 4 | master02 전원 | 전력 상한 올리기 | 프로필 performance 로도 80 W 그대로. `-pl 175` not supported. `nvidia-powerd` 없음 |
| 5 | 5a59776 py-spy 60 s | 루프 시간 분해 | `world.step` 55%, QR 면 추종 16%, `slots_in_world` 16%, sleep 0 |
| 6 | 41725ff-cam0 | 기동 분해, rtf, 렌더 상한 | stage ready 32 s, 팔 캐시 73.6 s, up 1분 52초. rtf 0.422, loop_hz 25.07. 뷰포트 640×720 |
| 7 | 3b76030 py-spy 60 s | 루프 시간 분해 | `world.step` 63%(omni.graph 35%, physx 17%), `slots_in_world` 16%, reassert 6% |

py-spy 수치는 스택에 그 이름이 **포함된** 샘플의 몫이다(전체 약 2,940 샘플).
두 항목이 한 스택에 같이 있으면 겹쳐 센다.

## 2. 시도한 것

| 조치 | 커밋·PR | 효과 |
| --- | --- | --- |
| 약통 접촉 보고 문턱 5 N, 선반·조제기 충돌체 근사 | 396958e, 232931c | 41725ff 경고 0 줄. rtf 0.340 → 0.422 이지만 다른 변경과 섞여 몫을 못 가른다 |
| QR 면은 쓰는 봉투·바뀐 자세만 | 09e4de6 | 3b76030 에서 `set_world_pose` 1.7%(5a59776 은 16%) |
| 렌더 해상도 상한 1280×720 상자(창 1024×1152 → 640×720), `P3_RENDER_MAX` | #577 | 상한은 걸렸다. rtf 0.422 로 **효과 없음** |
| 전원 프로필 performance, `nvidia-smi -pl 175` | 재범 실행 | **적용 안 됨**(노트북 GPU) |
| `slots_in_world` 자세 읽기를 한 번만 만든다 | #574 → 3ad7c5e | 루프 16% 몫. 적용 뒤 회차는 **미실행** |
| 팔 계획 캐시 파일 저장·재사용 | 8fd2492, fe12f5d | 두 번째 기동 시간 **미실행** |

## 3. 효과가 없거나 원인이 아니었던 것

- **렌더 해상도.** 640×720 에서도 rtf 0.422 였다. hydra·rtx 는 3b76030 에서 16% 안팎이다.
- **카메라.** 카메라 0 회차(41725ff-cam0)도 rtf 0.422 였다. 3b76030 에서 CameraHelper 는 9 샘플이다.
- **라이다.** RtxLidar 5 샘플(0.2%)이다. 주기를 낮춰도 얻을 것이 없다.
- **PhysX 경고.** 경고가 0 이 된 41725ff 도 rtf 0.42 였다.
- **TF·시계 그래프.** PublishTransformTree·PublishClock 0 샘플이다. AMR TF 는 static 5, dynamic 8 뿐이다.
- **물리 substep.** 이미 틱당 1 스텝(1/60 s)이다. 줄일 여지가 없다.

## 4. 남은 후보

1. **omni.graph 35% 의 내역.** 이름을 붙인 노드는 합쳐 100 샘플이 안 된다. 나머지 약 900 샘플이 어느 프레임인지 집계를 요청해 두었다.
2. **매 틱 USD 쓰기.** `HospitalConveyor.reassert()` 가 6% 다(4ef1cb4). 쓰기는 fabric 동기화(약 10%)와 Property 창 `_on_usd_changed` 로도 번진다.
3. **joint_states 공백 0.67-1.13 s.** stage 루프가 벽시계 30 Hz 로 내므로 루프가 그만큼 멈춘 것이다. 셰이더 컴파일·프림 생성·GC 가 후보다. 루프 한 번이 0.25 s 를 넘으면 `trace.dump()` 를 찍게 해 달라고 요청했다.
4. **GPU 80 W.** 하드웨어 한계다. 위 셋으로 CPU 쪽을 줄여도 rtf 0.95 에 닿지 않으면 목표를 다시 정해야 한다.

## 5. 한계

- 원본 로그를 직접 읽지 않았다. 모든 수치는 master02 에서 grep·awk 로 뽑은 값이다.
- py-spy 는 60 s 표본 둘이다. 주행 구간·집기 구간을 나눠 재지 않았다.
- 3ad7c5e·fe12f5d 가 들어간 회차는 아직 없다. 그 효과는 다음 회차에서 잰다.
