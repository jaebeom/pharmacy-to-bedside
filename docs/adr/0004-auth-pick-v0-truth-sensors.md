# ADR 0004 — 인증·집기 v0 는 참값 센서, 카메라는 v1 옵션

- 상태: proposed
- 날짜: 2026-09-25
- 결정자: 재범(9/24). 결정 댓글 #576 5795950859(①)·#576 5807716915(②)(시나리오 281행이 이 ADR 의 근거로 든다). 이 둘 중 어느 댓글이 결정 44 = A 를 담는지는 확인하지 않았다
- 승인 PR: 없음(이 ADR 의 PR 에서 검토)
- 관련 issue / RFC / evidence review: [K5 인증·전달 v0 인터페이스](../architecture/k5-delivery-interface.md)(3133609 인증 v0 = 참값, 6110473 결정 44 = A), [QR·DB·카메라 계약](../architecture/qr-db-camera-contract-v1.md) 6.2, [미결 결정](../analysis/2026-09-24-open-decisions.md) 2번, PR #414(Draft)
- 대체 관계: 없음. 비전 v1 이 들어오면 이 ADR 을 대체하는 새 ADR 을 쓴다(아래 "비전 v1 자리")

## 맥락

- 봉투 카메라 인식은 회차마다 실패했다(#240 댓글 ID):
  - 리하01 B 5794286637(3b76030): 카메라 집기 not_detected ×2.
  - 회차20 5798030004(626cb3f): grasp_failed ×2.
  - 회차31 5799937654(8e63d37): 카메라 집기 오차 0.057 m 로 한계 0.04 m 를 넘었다. grasp_failed ×2, ABORT.
  - 41725ff 에서 QR 57 px 로 not_detected ×2 였다. 그래서 9/23 결정으로 병원도 `P3_CAMERA_POUCHES=0` 이다(`tools/demo_v2.sh` 153행).
- YOLO 가중치가 없고 카메라 판독률 N/M 도 없다([스코어카드](../presentation/scorecard.md) 76행).
- 참값 센서(스테이지 `--sim-sensors`, `sim/standalone/p3sim/truth_sensors.py`)로 돈 병원 회차는 5/5 를 넘겼다. 예: 회차46 5807102321(66450ae, rtf 0.698). 10건 PASS 는 5804528593(b40e133)·5808852884(af78350)이다. **회차표에 센서 모드 칸이 없다.** 이 회차들이 참값 센서라는 것은 런북 명령과 `demo_v2.sh` 153행으로 본 추정이다.

## 대안

| 안 | 내용 | 한계·반증 |
| --- | --- | --- |
| A | 인증(ScanTag)·집기(PickPouch 위치)를 손 카메라 QR·검출로 | 위 회차의 not_detected·grasp_failed. 가중치·판독률 증거 없음 |
| B | **v0 은 스테이지 참값 센서. 카메라는 v1 옵션** | 인식 성능은 증명하지 않는다. 반증: 카메라 경로가 같은 회차 구성에서 N/M 판독률과 5/5 를 내면 v1 로 올린다 |

## 결정과 이유

**B안.**

- 인증 v0 = 참값 인증이다(`scan_tag_source: sim`, ScanTag·CabinetObservation). 카메라 인증은 v1 옵션이다([K5](../architecture/k5-delivery-interface.md) 5행).
- 결정 44(집을 칸을 어떻게 전달하나)는 **A = `PickPouch` 에 `int32 source_slot`** 로 확정했다([K5 3절](../architecture/k5-delivery-interface.md) 59–73행). 결정 44 는 인증 v0 과 따로 정한 것이다. 코드 반영은 촬영 뒤 별도 카드다. 그때까지 `_source_slot()` 은 0 을 돌려준다.
- 배선:
  - 스테이지 `/isaac/amr_1/tag_reads`·`/isaac/amr_1/pouches` → `isaac_adapter` → `/amr_1/sim/tag_reads`·`/amr_1/sim/pouches`(`isaac_adapter.py` 109–112행).
  - `sim` 이면 팔은 보기 자세로 움직이지 않고 스테이지 값을 기다린다(`arm_node.py` 1832행).
  - `tools/demo_v2.sh` 는 `P3_SIM_SENSORS=1` 일 때 `sim_pouches/sim_tag_reads:=true pouch_source:=sim scan_tag_source:=sim sim_cabinet:=true` 를 넘긴다(410행).
- 약통 QR 확인(`P3_CONTAINER_QR`, 병원 기본 1, `demo_v2.sh` 162행)은 이 결정 밖이다. 영상의 D455 는 약통 QR 확인만 보여 준다([QR 계약 6.2](../architecture/qr-db-camera-contract-v1.md) 218–220행).

## 결과

- **v0 = 참값은 런북 명령으로만 성립한다. 스크립트 기본값으로는 성립하지 않는다.**
  - `demo_v2.sh` 기본은 `P3_SIM_SENSORS=0` 이다(151행).
  - launch 기본은 `pouch_source`·`scan_tag_source` = `camera` 다(`stub_loop.launch.py` 217·221행, `arm_node.py` 320–321행). launch 값이 yaml 보다 우선한다(97행).
  - 그래서 `P3_WORLD=hospital` 만 주면 카메라로 돈다. 리하02 회차3(ae8b0b9)이 이 때문에 검출 0 이었다([리하 02](../reha/reha-02.md) 87행).
  - 병원 런북은 `P3_SIM_SENSORS=1` 을 적는다([hospital-demo](../runbooks/hospital-demo.md) 49행, [hospital-full](../runbooks/hospital-full.md) 102·222행).
- 발표·스코어카드는 인식 성능을 주장하지 않는다. "참값 센서로 인증"이라고 적는다.
- 회차표에 센서 모드 칸을 두지 않은 부채가 남는다(위 맥락의 추정).

### 비전 v1 자리

비전 v1 이 들어오면 새 ADR 로 이 ADR 을 대체한다. 이 ADR 의 상태를 `superseded` 로 바꾸고, 아래 셋을 같은 PR 에서 고친다.

| 곳 | 지금 | 바꿀 것 |
| --- | --- | --- |
| `tools/demo_v2.sh` 152–155행 | 병원 `P3_CAMERA_POUCHES=0` | v1 기본값 |
| [QR 계약 6.2](../architecture/qr-db-camera-contract-v1.md) | 봉투 카메라 집기 = v1 옵션 | 채택 여부 |
| [K5](../architecture/k5-delivery-interface.md) 5·79행 | 인증 v0 = 참값 | 카메라 인증 상태 |

비전 관련 진행은 [미결 결정](../analysis/2026-09-24-open-decisions.md) 2번(#654 계열)에 있다. 지금도 진행 중인지는 확인하지 않았다.

## 롤백

- `P3_SIM_SENSORS=0` 이면 카메라 경로다. 코드 변경은 없다. 스크립트 기본값이 이미 그쪽이다.
- 영향: 위 회차들처럼 not_detected·grasp_failed 로 주문이 `HOLD_RETURN`·`ABORT` 로 끝날 수 있다([예외 표](../architecture/exception-outcomes-v1.md) 3.4).
