# 병원 시뮬 부하 — rtf·기동·PhysX 경고 (2026-09-23)

상태: unreviewed다. 해석은 master02 회차 로그에서 잘라 보낸 발췌로 썼다. 원본은 읽지 않았다.
원본: master02 `~/markle_tmp/` 의 `perf-extract-0923.txt`(sha256 `1a44f300bbbc54e0…`), `perf-extract-0923-b.txt`(`b51b11153faca95d…`),
`perf-39d1ce5.txt`(`d7634da12b6f682c…`), `perf-39d1ce5-c.txt`. 전체 해시는 master02 에 있다.
환경: master02(IsaacSim07), RTX 5080 Laptop 16 GB, 드라이버 580.173.02, Isaac Sim 5.1.0, 창 모드.
acceptance run 이 아니다. 판정선은 바꾸지 않는다.

## 1. 관측

### 회차별 rtf 와 `getMaterialFromInternalFaceIndex` 줄 수

| 회차 | 경고 줄 | rtf(바퀴별) |
| --- | --- | --- |
| nav-l3 | 935 | 0.818 |
| l3b | 3644, 0 | 1.002, 0.523 |
| show | 3648 | 0.818 |
| r3 / r4 / r5 / r6 | 0 / 272 / 261 / 575 | 0.55 / 0.978 / 1.002 / 0.962 |
| r7 / r8 / r9 | 0 / 0 / 0 | 1.0 / 0.491·0.543·0.978 / 0.507 |
| demo 9186933 / 694ac9b | 0 / 0 | 0.537 / 0.988·0.517·0.961 |
| f5f7657 / 0eab978 / e4ae5ab | 0 / 27 / 0 | 0.517·0.474·0.939 / 0.962·0.958·0.496 / 0.953·0.933 |
| **m2-hf-full-d448530**(hospital + workcell) | **211,176** | ready 대기 180·420 s 한도 초과 |
| **m2-hf-full-39d1ce5**(hospital + workcell) | **419,292** | **0.340**(loop_hz 20.26, sim 193.9 s / wall 569.8 s) |

병원 주행 회차의 rtf 는 0.47–0.55 와 0.93–1.0 **두 무리**로 나뉘고 가운데 값이 없다. 같은 SHA 에서도 바퀴마다 섞인다.

### 39d1ce5 (hospital preset + workcell)

- 경고는 1종(PhysX `NpShape.cpp:566`)이다. 31.9 s 에 시작해 603 s 까지 10 s 마다 5,700–10,150줄로 일정했다.
- 바로 앞 줄: 조제기 `…/IntegratedDispenser/Machine/machine/model/…/ID398/Mesh`·`ID398_1` 의 `cooking failure` → `Unable to create triangle mesh`.
  그다음 `articulation at /World/P3Pharmacy/Amr with more than 4 velocity iterations … TGS`.
- stage 로그의 contact 줄 1,764개가 **모두 선반 약통 `shelf_N_rNcN` ↔ 병원 `SM_MedShelf_01d`** 이다. 18쌍 × 98회이고 AMR·팔 쌍은 없다.
- `contact_watch on bodies=50`, `stop reason=sigint updates=11545 wall_s=569.796 loop_hz=20.26 sim_s=193.917 rtf=0.340`.
- `tag_reads` 줄이 루프 안에서 찍혔다. 스테이지 루프는 돌았다. ready 에 못 간 것이 아니다. 느린 것이다.
- gpu.csv 609행: util 0/44/87 %, SM 300/2032/2827 MHz, 전력 10.5/76.8/80.0 W(최소/중앙/최대).
  **throttle ≠ 0 이 566행이고 전부 0x4(SW power cap)** 다. 기본·현재 전력 상한 80 W(최대 175 W), 플랫폼 프로필 balanced.
- top: Isaac python %CPU 중앙 553, 최대 772.
- 창은 `--window-half left`, 렌더 해상도 2048×1152(창과 같다, `p3sim/views.py window_half`).

### 5a59776 py-spy

stage ready 뒤 60 s 다. 50 Hz 다. `--native` 다. 샘플은 2950 이다.

원본: master02 `m2-hf-full-5a59776/pyspy.txt`(sha256 `7e53faef5bccbfe2…`). 스택에 이름이 **포함된** 샘플 수다.

| 무엇 | 샘플 | 몫 |
| --- | --- | --- |
| `world.step(render=True)`(pharmacy_stage.py:2350) | 1628 | 55% |
| 그 안의 render | 430 | 15% |
| 그 안의 physx | 358 | 12% |
| QR 면 추종 `get_world_pose`+`set_world_pose`(2734-2735) | 485 | 16% |
| `amr.slots_in_world`(1588) | 467 | 16% |
| Property 창 `_on_usd_changed` | 140 | 5% |
| `spin_once` | 95 | 3% |
| `publish` | 75 | 3% |
| `time.sleep` | 0 | 0% |

부를 때마다 `SingleXFormPrim` 을 만든다.

sleep 은 0 이다. 루프는 쉬지 않는다. 물리·렌더 밖의 Python 은 약 3분의 1이다.

### 전력 상한

재범이 master02 에서 `sudo nvidia-smi -pl 175` 를 실행했다. 시각은 19:17 이다. 원문은 `Changing power management limit is not supported for GPU: 00000000:01:00.0.` 이다. 대상은 노트북 GPU 다. 80 W 를 못 올린다. `nvidia-powerd` 유닛은 없다. GPU 는 80 W 를 전제로 한다.

## 2. 해석

1. **경고 출처는 선반 약통의 접촉 보고다.** 준비기 `sim/standalone/prepare_workcell_integration.py`(9818b73 기준 60–64행)는
   선반 `SM_MedShelf_01d_67`–`75` 의 메시를 `approximation none`(삼각형 메시)으로 둔다. 약통은 `contact_watch` 대상이다(문턱 0).
   쉬는 접촉마다 매 스텝 보고가 나가고, 삼각형 메시 쪽 면 번호로 재질을 찾다 경고가 난다.
   근거: 11,545 updates × 36 = 419,620 ≈ 419,292. 36 = 18쌍 × 접촉점 2 로 맞는다.
   경고를 내는 PhysX 조건(면 번호 `0xFFFFFFFF`)은 소스 대조로 한 추정이다. **미확인.**
2. **조제기 cooking 실패는 2줄뿐이다.** 매 프레임 경고와는 별개다.
3. 39d1ce5 의 느림은 경고만으로 설명되지 않는다. 경고는 스텝당 36줄이다. 그 비용은 kit.log 를 줄마다 flush 하는 것이다.
   같은 회차에 GPU 는 93%의 시간을 80 W 상한에 걸려 있었다. util 중앙은 44% 였다. CPU 는 5.5코어였다.
   셋 중 어느 것이 20 Hz 를 만드는지는 미확인이다.
4. **주행 회차의 rtf 두 무리(0.5 / 1.0)는 프레임이 반으로 떨어지는 모양이다.** 루프는 한 번에 physics 1/60 s + 렌더 1회를 하고 60 Hz 로 맞추므로
   rtf = loop_hz / 60 이다. 한 프레임이 16.7 ms 를 넘으면 30 Hz 로 붙는 제약(vsync 류)이 있거나, 전력 상한에 따른 클럭 변동이 후보다.
   kit.log 에 vsync·rateLimit 줄이 없어 **미확인**이다. f5f7657 lap1 kit.log 는 덮어써져 없다.
5. 기동 1분 40초의 분해(자산 내려받기·cooking·첫 play)는 아직 재지 않았다(**미실행**).

## 3. 조치와 다음 측정

| # | 조치 | 어디서 | 상태 |
| --- | --- | --- | --- |
| 1 | 약통 접촉 보고 문턱 5 N(`--canister-contact-threshold-n`), 선반 `convexDecomposition`·조제기 몸통 `convexHull` | `sim/` | 396958e(feat/hospital-full) |
| 2 | 플랫폼 프로필 performance(결정 4, 재범 승인) | master02 | **실패**: `powerprofilesctl` AccessDenied, `/sys/firmware/acpi/platform_profile` 없음. 396958e 는 balanced 로 돈다 |
| 3 | 다음 한 바퀴: gpu.csv·top.txt·py-spy 1분(`--native`) | master02 | gpu·top 기록. py-spy 는 5a59776 에서 실행(위 표) |
| 4 | 같은 SHA 바퀴마다 kit.log 를 따로 남긴다(f5f7657 lap1 유실) | master02 | 요청 |
| 5 | `slots_in_world`·`world_to_arm_base` 자세 읽기를 경로마다 한 번 만든다 | `sim/` | #574(L3 미실행) |
| 6 | QR 면 추종은 쓰는 봉투만 한다. 바뀐 자세만 쓴다. `Sdf.ChangeBlock` 으로 묶는다 | `sim/` | 요청 |
| 7 | 전력 상한 `-pl 175` | 재범 | not supported, 미적용 |

다음 회차에서 볼 것:
- 경고 줄 수가 0 에 가까운지. 남으면 보고된 쌍의 힘 분포를 본다.
- 약통 18개의 기동 직후와 1 s 뒤 자세 차이. convexDecomposition 이 칸을 메우면 약통이 튄다.
- cooking 줄의 첫 시각과 끝 시각(기동 시간 몫).
- loop_hz·rtf 와 전력 상한에 걸린 초수(39d1ce5 와 대조).

## 4. 한계

- 원본 로그를 직접 읽지 않았다. 모든 수치는 master02 에서 grep·집계한 발췌다.
- 경쟁 가설: 20 Hz 가 경고와 무관하게 조제실 v2 모듈·M0609·카메라 렌더 프로덕트의 합에서 나올 수 있다. 카메라 셋(M0609 D455 960×600, 합본 D455 640×480, RTX 라이다)의 몫은 따로 재지 않았다.
