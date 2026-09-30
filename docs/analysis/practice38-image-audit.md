# 실습38 이미지 감사와 현재 화면 문제

검색 범위: master02 `m2-original-intakes-practice-01`, `m2-hospital-conveyor-probe-*`, `m2-hospital-single-amr-01`, `pr500-l3-20260923`, `pr500-l3-shutdown-20260923`의 PNG/JPG/WEBP. **찾은 17개 모두** 아래에 보존했다. 그 밖의 폴더·모든 영상 프레임까지 전수 확보한 것은 아니다. 이전 Git에는 실습38 대표 이미지4개가 있었으나 후속 캡처/녹화 점검 이미지를 모두 포함하지 않았다.

원본/사본 해시·변환은 [manifest](images/practice38-handoff/manifest.json). 다른 앱으로 가려진 화면도 삭제하지 않고 녹화 품질 문제로 보존한다. 모든 파일이 실습 성공 증거는 아니다.

## 01 — m2-hospital-conveyor-probe-01/probe-screen.png

![캡처 01](images/practice38-handoff/01-m2-hospital-conveyor-probe-01-probe-screen.webp)

## 02 — m2-hospital-conveyor-probe-03/full-stock-belt-screen.png

![캡처 02](images/practice38-handoff/02-m2-hospital-conveyor-probe-03-full-stock-belt-screen.webp)

## 03 — m2-hospital-conveyor-probe-04/mixed-stock-screen.png

![캡처 03](images/practice38-handoff/03-m2-hospital-conveyor-probe-04-mixed-stock-screen.webp)

## 04 — m2-hospital-conveyor-probe-06/terminal-screen.png

![캡처 04](images/practice38-handoff/04-m2-hospital-conveyor-probe-06-terminal-screen.webp)

## 05 — m2-hospital-conveyor-probe-08/chute-entry-stall.png

![캡처 05](images/practice38-handoff/05-m2-hospital-conveyor-probe-08-chute-entry-stall.webp)

## 06 — m2-hospital-conveyor-probe-10/chute-stall-screen.png

![캡처 06](images/practice38-handoff/06-m2-hospital-conveyor-probe-10-chute-stall-screen.webp)

## 07 — m2-hospital-conveyor-probe-11/receiver-boundary-failure.png

![캡처 07](images/practice38-handoff/07-m2-hospital-conveyor-probe-11-receiver-boundary-failure.webp)

## 08 — m2-hospital-conveyor-probe-13/video-final-frame.png

![캡처 08](images/practice38-handoff/08-m2-hospital-conveyor-probe-13-video-final-frame.webp)

## 09 — m2-hospital-single-amr-01/amr-screen.png

![캡처 09](images/practice38-handoff/09-m2-hospital-single-amr-01-amr-screen.webp)

## 10 — m2-hospital-single-amr-01/recording-final-frame.png

![캡처 10](images/practice38-handoff/10-m2-hospital-single-amr-01-recording-final-frame.webp)

## 11 — m2-hospital-single-amr-01/recording-frame-check.png

![캡처 11](images/practice38-handoff/11-m2-hospital-single-amr-01-recording-frame-check.webp)

## 12 — m2-original-intakes-practice-01/window-recorder-check.png

![캡처 12](images/practice38-handoff/12-m2-original-intakes-practice-01-window-recorder-check.webp)

## 13 — abort/final-window.png

![캡처 13](images/practice38-handoff/13-abort-final-window.webp)

## 14 — receiver/final-window.png

![캡처 14](images/practice38-handoff/14-receiver-final-window.webp)

## 15 — terminal/final-window.png

![캡처 15](images/practice38-handoff/15-terminal-final-window.webp)

## 16 — abort/final-window.png

![캡처 16](images/practice38-handoff/16-abort-final-window.webp)

## 17 — terminal/final-window.png

![캡처 17](images/practice38-handoff/17-terminal-final-window.webp)

## 18 — tmp/codex-clipboard-fELKED.png

![캡처 18](images/practice38-handoff/18-user-camera-problem.webp)

## 현재 카메라 문제와 인계 요청

18번은 사용자 제공 9/23 17:50 표시 화면이다. 로봇·입구가 너무 작고 과노출로 판별이 어렵다. `/HospitalPracticeCamera`는 실행 트리 `bb3ac33`의 `pharmacy_stage.py`에서 workcell JSON `camera`를 읽는다. 당시 로컬 값은 eye[-3.8,8.1,4.5], target[-3.8,11.2,0.9], focal_mm7.0이다. 그 JSON은 이번 fixture의 18칸 비교 파일과 같은 해시다.

7mm 광각/전경 구도는 작은 로봇 표시의 원인이지만 밝기 문제는 별도로 조사한다. 조명·노출 자동값을 임의 변경한 뒤 해결됐다고 보고하지 않는다. 실행 담당은 실제 기동 시 투입구·그리퍼가 구분되는 작업 카메라, 조명/노출, 녹화 실제 프레임을 함께 확인해야 한다. 이 보고 작성 중 타 담당의 살아 있는 stage는 변경하지 않았다.

## 19 — 라이브 화면 설정 변경과 조제기 자산 누락 확인

9/23 기존 bb3ac33 실행은 17:55:29 정상 종료 로그를 남겼다. 이 감사 쪽에서는 종료하지 않았다. 17:56:09 시작한 다른 담당의 603dfc1 실행에서 UI만 조정했다: Stage Lights→**Default**, focal7→**10mm**, render aspect0.89:1(1024×1152)→**16:9**. eye/target은 유지했다. 물리·목표·재고는 바꾸지 않았다. 아래 실제 화면에서 로봇과 선반이 크게 보인다.

![Default 조명과 가로 화면 적용](images/practice38-handoff/19-default-light-wide-view.webp)

재기동 인계값은 [review-display-20260923.json](../../experiments/fixtures/practice38/review-display-20260923.json)에 별도 기록했다. **현재 라이브 UI에만 적용**, 기존 workcell JSON7mm는 원본 보존을 위해 바꾸지 않았다. 런타임이 이 새 파일을 자동 로드하는 기능은 없으며 다음 실행 담당이 적용·재확인해야 한다.

조제기 자리에 받침만 보이는 문제는 화면 조정과 별개다. 해당 실행 stage.log 481행(08:56:26Z)은 `/World/P3Base/Scene/machine/machine`의 `sim/material/etc/Automatic+Blister+Packing+Machine+(DPB-80)/model.usd` payload를 열 수 없다고 기록했다. 로더 기록 `dispenser_checks=[]`. 따라서 이 실행을 기준 조제기/투입구 검증 완료로 볼 수 없다. 현재 형상 누락에 직접 관련된 로그이며 모든 실습 실패의 원인으로 확대하지 않는다.

통합 담당은 기존 외부 payload 대신 기준 조제기 에셋 참조와 실제 입구 world anchor 검사를 적용하고, #565의 fixture 및 #500/실습38의 기준 형상과 대조해야 한다. 사진을 맞추기 위해 임의 모델이나 좌표로 바꾸지 않는다.
