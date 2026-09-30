# 병원 M0609 통합 회차 integrated-09 입력 — 2026-09-22 16:32

**master02 `m2-hospital-integrated-09`의 입력 사본이다. 9/22 16:32 당시 마지막으로 연결된 병원 M0609 보충 회차다. 공용 preset/default가 아니다.**
18칸 배치다. 1350개 혼합 진열이 아니다. `workcell.json`은 실습37 `m2-pr490-l3-10/workcell.local.json`과 바이트가 같다.

| 파일 | 용도 |
| --- | --- |
| `workcell.json` | 워크셀 실측 배치(18칸). `--workcell-layout` 입력 |
| `arm-parameters.yaml` | 당시 `m0609_arm` 파라미터 |
| `base.usda` | 당시 병원 루트 레이어. 외부 참조 자산은 별도 필요 |
| `launch-stage.sh` | 스테이지 실행 원문(`--preset demo-ros-refill-v2`, 도메인 151) |
| `launch-arm.sh` | 팔 실행 원문이다. `m0609_arm`이다. `v2_seed:=835258728`이다. `v2_guarded_module_path:=false`다. `v2_rail_select:=preferred_first`다 |
| `deployment.json` | 스테이지 코드는 `fea9b1fb9462f7b29302210adc63a041badea0db`다. 팔 install은 `20260922-practice31-321c069`다. 소스 해시도 있다 |
| `manifest.json` | 사본별 원본 경로·크기·SHA-256. 원본과 바이트 동일 |

`v1.0.0` master01 리허설 회차(9/29)의 `workcell.json` 은 이 사본과 다르다(둥근 수납통 자리·충돌 설정 등). 차이는 [9/29 대조 기록](../../../docs/analysis/2026-09-29-master01-workcell-fixture-diff.md) 에 있다.

경로는 master02 당시 출처다. 그대로 재실행하지 않는다. 저장소·자산 위치만 바꾼다. 그 회차의 결과·영상은 master02 원본 폴더에 있다. 여기로 옮기지 않았다.
