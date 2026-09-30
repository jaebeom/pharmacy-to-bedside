# 병원 navigation v1 장면 갱신 (2026-09-23)

> **상태: 지난 기록 (2026-09-23 기준).** 지금은 [sim README 현행 절](../README.md#지금-무엇이-현행인가-v110-병원-한-바퀴)을 따른다.
> 이 씬은 v1.1.0 병원 한 바퀴의 씬이다. 마지막 절의 지도·앵커·zones·routes 재생성은 #523 에서 했다(`b1f8cef5`, `a05767db`).

## 출처와 파일

- 작성 원본: `/home/rokey/hospital_custome/hopital_custome/hospital_navigationv1.usd` (SHA-256 `7b725f010f961faf44c510bfd86238af0c6a4bbe83d7151a99e737f6b982481a`). 경로의 `hopital_custome` 철자는 원본 그대로다.
- 저장소에는 읽고 비교하기 쉬운 `hospital_navigationv1.usda`만 남긴다. 같은 장면을 중복 저장하던 `.usdc`와 오래된 부분 장면 `.usd`는 제거했다. `omni_layer.authoring_layer`는 남긴 `.usda`를 가리킨다.
- 장면에서 `/World/Graph`의 ROS 그래프 네 개, 내장 `/World/ridgeback_ur5`, 외부 참조가 끊긴 `/World/gripper`, 이 센서들에 연결된 `/Render` 설정을 제거했다. ROS 배선과 주행 로봇은 실행 스테이지가 구성한다.
- 컨베이어 자체의 `ConveyorBeltGraph`, `machine`, `PouchPool`, `PouchTemplate`과 병원 환경 배치는 유지했다.

## 배치 변경 이유

작성자가 침대와 선반의 위치를 navigation 이동 경로와 정차 공간에 맞춰 확인하고 조정한 배치를 반영했다. 컨베이어 끝의 선반은 상면 높이를 맞춰 파우치가 적절한 높이에 올라오도록 확인하고 조정한 것이다. 이 설명은 작성자의 배치 확인 내용이며, 이 PR에서 새 지도나 주행 L3를 통과했다는 뜻은 아니다.

## 기하 변경

- **C1 북쪽**(복도와 병실 사이 문 자리): `SM_Door_02b2_01`을 제거했다. `Geo_M1_DoorWall24`의 Y 배율은 1.5이고 남쪽으로 옮겼다. 벽 메시의 높이 1 m 수평 개구부는 약 **1.976 m**다(이전 1.317 m). 이는 메시 치수이지 로봇의 통과 여유 실측이 아니다.
- **C1 남쪽**: `Geo_M_DoorFloor22`를 비활성화하고 `Geo_M1_WallClose_1033`을 제거했다. 기존 두 출입구 앵커는 새 벽 배치에서 다시 확인해야 한다.
- **C2**: `SM_Door_02b2`와 문턱 `Geo_M_DoorFloor23`을 비활성화했다. `Geo_O_DoorWall_918`의 Y 배율은 1.5이고 남쪽으로 옮겼다. 높이 1 m에서 메시 개구부는 약 **1.973 m**다(이전 1.315 m).
- `Geo_M_DoorFloor11`, `Geo_M_DoorFloor22`, `Geo_M_DoorFloor23` 문턱 세 개는 모두 비활성화했다. 관련 문틀과 장식도 작성 원본의 상태를 따른다.
- D1–D4 침대는 새 병실 좌표에 맞췄다. D5–D10 침대는 씬 루트 여섯 곳에서 `/World/Environment/hospital` 아래 `SM_HospitalBed_02d4_04`부터 `_09`로 옮겼다. 맞닿은 탁자와 병원 소품도 추가하거나 재배치했다. 따라서 이 침대들은 기본 `/World` 참조에 포함된다.
- 컨베이어 출구의 받침 선반을 `SM_SideTable_02a_73`, `_74`, `_77`–`_79`로 교체·재배치했다. 이전 `_75`, `_76`은 없다.

## navigation 후속 확인

이 장면만으로 navigation 이슈가 끝나지는 않는다. 현재 저장소의 `hospital.pgm`, 앵커 JSON, zones, routes는 이전 장면을 가리킨다. 앵커 추출기는 제거된 침대·출구 탁자 prim과 비활성 문턱 세 개를 아직 참조한다. 해당 파일들은 이 장면을 기준으로 다시 생성해야 한다(PR #517 마지막 댓글). 그 뒤 master02에서 6개 목표 도착과 접촉 0을 확인해야 한다. 이 PR에서는 Isaac/PhysX와 L3를 실행하지 않았다.
