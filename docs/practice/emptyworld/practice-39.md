# 실습39 — pouch 윗면 QR 단독 시각 확인

| 항목 | 값 |
| --- | --- |
| 번호 | 실습39 |
| 날짜·시각 | 기동은 2026-09-22 21:00:08 KST(로그). 9/23 임재범이 종료했다고 보고. 정확한 종료 시각은 미수집 |
| 돌린 사람 | 임재범 요청. `master02` 원격 기동·캡처·해독 확인 |
| 기록 | 9/23 원본 재대조 |
| 기계 | `master02`, Isaac Sim Python 5.1.0 창 모드 |
| 환경 | 병원 USD를 로드하지 않은 독립 빈 장면, 정적 시각 확인 |
| 코드 | 기존 helper 기준 `321c069e6eb7d842c0d8dee031e62e95297c378e` + 저장소 밖 `preview.py` (아래 해시) |
| 기동·로그 | `master02:/home/rokey/markle_tmp/pouch-qr-visual-01/isaac.log` |
| 결과 | 배송·로봇 통합 검증은 미실행. pouch +Z 면 QR 표시와 원본 PNG·실제 GUI 캡처에서 `ord-9001` 해독을 확인 |

## 목적

임재범이 요청한 “놓이는 면 기준 윗면에 형식에 맞는 dummy QR 이미지가 나오는지”를 확인한다.
이전 컨베이어·AMR 통합 실습과 분리했고 기존 코드를 수정하지 않았다.
제품 pouch 생성 경로에 QR 기능을 통합한 변경은 아니다.

이번 확인은 사전 frozen protocol과 run ID를 배정한 측정이 아니다.
[공통 실습 규칙](../README.md)과 [증거 규격](../../../schemas/README.md)에 따라 실습 일지로 기록하며,
`evidence/runs`에 소급 생성한 pilot/acceptance manifest를 넣지 않는다.
원본과 해시를 보존했다는 사실은 독립 검토·제품 합격을 의미하지 않는다.

## 구성

| 항목 | 값 |
| --- | --- |
| QR 내용 | `ord-9001` (dummy), `^ord-[0-9]{4}$` 검사 통과 |
| 계약 | [배송 계약 3절·7절](../../architecture/delivery-contract-v1.md): QR 면은 pouch +Z, QR 내용 전체가 주문 ID |
| QR 생성 | 기존 `sim/standalone/make_qr_textures.py`의 `write_png`; OpenCV 4.6.0, 660×660 PNG, border 인자 4, 오류 정정 M |
| QR 부착 | 기존 `sim/standalone/p3sim/scene.py`의 `add_top_texture` 읽기 전용 호출 |
| pouch | 외부 fixture의 직육면체 100×70×10 mm, 받침대 위 정지 배치 |
| QR 면 | 52×52 mm; pouch 중심 기준 +Z 5.15 mm, 몸체 윗면보다 0.15 mm 위 |
| 계층 | 스케일 없는 pouch Xform 아래 Body와 QR을 형제로 배치 |
| 카메라 | `QrReviewCamera`, Z-up 기준 위쪽 사선 시점 |
| 캐시 | 새 Isaac 프로세스에서 `new_stage()` 호출. 셰이더·텍스처 캐시 강제 삭제는 미실행 |
| ROS·물리 | 이 fixture는 ROS 노드나 물리 이송을 기동하지 않음. `app.update()`로 정적 화면 유지 |

`git-before.json`과 `git-after.json`에는 두 작업 트리의 HEAD/status/diff가 같게 남아 있다.
주 작업 트리는 당시 `docs/practice/README.md` 수정과 미추적 `practice-31.md`가 이미 있었으므로 clean이라고 하지 않는다.
이전 통합 작업 트리 HEAD는 `435ce1d50e8cef5e6f022ad65946e22d6a8d92ca`였으며 이 테스트에 그 코드를 사용하지 않았다.
이 비교는 미추적 파일 전체의 바이트 동일성 검증은 아니다.

당시 실제 기동 명령(원본의 기계별 경로이며 공용 설정이 아님):

```bash
env -i HOME=/home/rokey USER=rokey PATH=/usr/local/bin:/usr/bin:/bin   DISPLAY=:0 XAUTHORITY=/run/user/1000/gdm/Xauthority   XDG_RUNTIME_DIR=/run/user/1000 PYTHONDONTWRITEBYTECODE=1   /home/rokey/isaacsim/python.sh   /home/rokey/markle_tmp/pouch-qr-visual-01/preview.py   > /home/rokey/markle_tmp/pouch-qr-visual-01/isaac.log 2>&1
```

이는 실행 이력이다. 같은 명령을 그대로 재실행하면 원본 로그와 산출물을 덮어쓰므로 재실행에는
새 외부 디렉토리에 fixture·QR PNG를 복사하고 별도 로그 경로를 지정해야 한다.
`preview.py`의 helper import는 위 주 작업 트리의 절대 경로를 사용한다. 재현 시 해당 helper가
실행 SHA와 일치하는지 확인하고, 새로운 fixture의 변경 사항과 해시를 따로 기록해야 한다.
이 문서화 작업에서는 Isaac을 다시 띄우지 않았다.

## 관측

### 사람이 본 것

- 임재범이 윗면 QR 단독 테스트를 요청했고 기존 코드 변경 금지를 명시했다.
- 9/23 임재범은 “내가 아까 껐는데”라고 보고했다. 정확한 종료 시각·방법은 보고되지 않았다.
- 임재범의 QR 인식 성공 판정은 보고되지 않았다. 아래 시각 확인과 해독은 캡처·로그 파일로 수행했다.

### 로그로 본 것

실행 SHA는 위 구성 기준이다. `isaac.log` 첫 UTC 타임스탬프는 `2026-09-22T12:00:08Z`이며
KST 21:00:08이다. 새 장면 생성과 캐시 범위는 위와 같다.

| 관측 | 근거 | 한계 |
| --- | --- | --- |
| 장면 준비 | `QR_VISUAL_READY ord-9001` 로그와 `READY` 파일 | 전체 로봇 스택 준비 신호가 아님 |
| QR 윗면 표시 | `isaac-qr-top-view.png` 실제 GUI 캡처를 열어 확인 | 단일 정적 시점 |
| 원본 PNG 해독 | `payload.json`: `source_png_decoded = ord-9001` | 텍스처 원본 확인 |
| GUI 캡처 해독 | `visual-check.json`: `screenshot_opencv_decoded = ord-9001` | ROS 카메라·perception 노드 경로 미실행 |
| 9/23 재대조 | 기존 manifest의 파일 7개 모두 크기·SHA-256 일치, 위 이미지 두 장을 OpenCV로 재해독해 일치 | 새 Isaac 회차가 아님 |
| 종료 상태 | 9/23 10:00 KST `ps` 조회에서 해당 preview.py/조회 대상 Isaac Python 프로세스 미검출 | 정확한 종료 시각·exit code 미수집; 당시 조회 원본 파일은 미보존, lifecycle note에만 있음 |

`isaac.log`에는 startup 경고가 있다. `[previous crash]` 업로드 방지 경고를 이번 실행의
크래시로 해석하지 않는다. GPU 부하·밤새 연속 안정성은 측정하지 않았다.

## preview.py 역할과 종료

스크립트는 장면·QR·카메라를 만들고 USD를 저장한 후,
`while app.is_running(): app.update()`로 창을 유지한다. 자동 종료 시간은 없었다.
밤새 Python은 화면을 유지하는 루프에서 실행 상태로 남아 있었다. 이 시간에 반복 실습은 수행하지 않았다.

향후 같은 시각 확인은 확인 직후 창을 닫거나 실행 터미널에서 Ctrl+C로 종료하고
대상 프로세스 종료 여부를 확인한다. 당시 스크립트에는 `KeyboardInterrupt` 처리와
`finally: app.close()`가 있다. 이번 임재범의 종료가 이 경로를 거쳤는지는 확인하지 못했다.

## 문제

이 표의 P 번호는 실습39 내부 번호다.

| 번호 | 무엇 | 고치는 쪽 | PR |
| --- | --- | --- | --- |
| P1 | 자동 종료 없는 창 유지 동작을 최초 완료 보고에 명확히 안내하지 않아 밤새 실행됨 | 운영 기록에 역할·종료 절차 보완. 기존 스크립트 변경 없음 | 이 문서 변경; 런타임 수정 PR 없음 |
| P2 | 정확한 종료 시각·exit code, 장시간 부하 미수집 | 다음 실행에서 시작·종료와 필요 지표 수집 | 미작성 |

## 캡처·녹화·원본

원본 위치: `master02:/home/rokey/markle_tmp/pouch-qr-visual-01/`.
로컬 경로이므로 GitHub에서 직접 내려받을 수 없다. 팀 공유 artifact 저장소 업로드와
다른 장비의 접근 확인은 미실행이며 필요하면 master02 원본을 따로 복사해 전달해야 한다.

- 화면: `isaac-qr-top-view.png`, 1440×900 실제 Isaac 창 캡처.
- 영상: `isaac-qr-visual.mkv`, 명령에서 75 프레임·15 fps 지정한 짧은 창 녹화. 밤새 녹화가 아니다.
- 이번 장면에는 로봇이 없다. 공통 규칙의 “로봇이 보이는 Isaac 캡처만 저장소에 올림”에 따라
  이미지는 외부 원본으로 보존하고 이 문서에 위치·해시를 남긴다.
- `pouch-qr-preview.usda`는 QR 텍스처를 로컬 절대 경로로 참조하므로 USD만 옮겨서는 재현되지 않는다.
- `manifest.json`은 외부 간이 파일 목록이며 저장소의 정식 run schema manifest가 아니다.
  기존 목록은 수정하지 않고 아래 표에 로그·종료 보충 기록까지 추가 식별했다.

2026-09-23 문서화 시 파일 크기와 SHA-256:

| 파일 | bytes | SHA-256 |
| --- | ---: | --- |
| `README.md` | 839 | `e33a0c9412c06a0c03018b468a91e3e93220dfcaa5014043feef498f82e24c86` |
| `READY` | 53 | `beb50cb8bc00349efe75aa2c5463134f6e24f0589f728f7867282c2692acca94` |
| `git-after.json` | 2,876 | `67918d5c909f47805c4daea821829e0089379ad4169497c126015b9d82fd5ee3` |
| `git-before.json` | 2,876 | `67918d5c909f47805c4daea821829e0089379ad4169497c126015b9d82fd5ee3` |
| `isaac-qr-top-view.png` | 312,143 | `1ecef02292404a1c0be68ed1701257a9b01b7f500947b48af1d8cbd30c7be762` |
| `isaac-qr-visual.mkv` | 626,916 | `36ff775c18024b37766cf7afc2d8ce0d99ed03b9aa74b25b95f1d8c27be0cc6e` |
| `isaac.log` | 42,465 | `54f20003e505ff57daa9d700864d1f17c8ed04b4a8f5cfd4c902bfe6275dcb19` |
| `lifecycle-note-20260923.md` | 1,588 | `e761bf093f6091e1d8db5787524557fe2a0ef87caca02dae7437d5bc7cc6d04f` |
| `manifest.json` | 907 | `03fd3076842c49cd856ea6afccc846d41b79a5f744669754394975477d21d300` |
| `ord-9001.png` | 8,430 | `a09553950a49cc89ca8f9928541b72c7570b3336c07e0a6840f9b68a655be5e1` |
| `payload.json` | 248 | `3a80c57e7e0cc83354916c9f1feb6965cb1e4a0d341fdcde8dfa3f641ed66b12` |
| `pouch-qr-preview.usda` | 7,351 | `0034e33fbda5197697debe542a9b954af25975a3d0e47009efd7e2e37f137cb6` |
| `preview.py` | 2,814 | `f627dd1d597748820f8c2329f5ba0d4d12d48d4415f504938041ae65faacd252` |
| `visual-check.json` | 174 | `e20299a6d4140c2ef3ddb599622d26fcabb36880eba88cb04d0619ff16de508e` |

## 미실행

- ROS 이미지 토픽·perception 노드의 QR 검출, 실제 센서 카메라 인식
- 조제기 pouch 생성 경로 통합, 컨베이어·파지·Nav2·배송 전체 루프
- 조명·각도·거리 변화와 이동 중 QR 인식, 반복 통계
- 밤새 GPU 부하 및 연속 안정성 측정, 정식 frozen protocol 기반 L3 합격 판정

## 다음 실습에서 확인할 것

- 제품 통합을 요청받으면 기존 pouch 생성·pose 갱신 경로와 QR 면 동기화를 별도 구현·검토한다.
- 인식 검증은 센서 이미지→perception 노드→payload 결과까지 범위와 조건을 실행 전에 정한다.
- 새 실행 디렉토리, 종료 조건, 캡처·녹화 범위를 먼저 정하고 종료 상태를 남긴다.
