# 조제기·병원 씬 정합 진단 — 2026-09-22

수신: 임재범, simulation 담당 박세준, 조제실 통합 담당
상태: unreviewed. #483 측정 요청이 병합되고 #486 되돌림도 병합된 뒤, 사용자가 요청한 실제 저장소 기록이다. #486 댓글만 작성했던 미완료 대응을 보완한다. 합성 측정 자체는 여전히 미완료다.

기록 출처: #486 진단 댓글. 문서 작성 기준 main: bc350ff. 원본 run 또는 frozen protocol을 수정하지 않는다.
기준: 기존 측정 321c069e6eb7d842c0d8dee031e62e95297c378e, 새 병원 배치 #484 db9d9ada454f9345892a8a488d4704fc22b8864b, 조제기 에셋 #485 fc8a71ec3f80fbb29f5838b1037185e8084eedd2.
환경: master02, hostname IsaacSim07, Isaac Sim 5.1. 정식 protocol/run ID 없음; 아래는 진단·정지 화면/명목 IK 확인이며 acceptance run이 아님.

## 1. #483 표준 측정 절차의 실패

`prepare_hospital_scene.py`가 `unexpected asset references in hospital scene template`로 실패했다. 코드가 Isaac 자산 토큰 39개를 요구하지만 321c069의 hospital_layout.usda에는 41개가 있다(사용자 자산 토큰은 1개). 2026-09-22 재실행에서도 동일 오류를 확인했다.

명령:
```bash
python3 sim/standalone/prepare_hospital_scene.py \
  --custom-assets /home/rokey/assets-from-master01/hospital_custome-20260921 \
  --isaac-assets-root /home/rokey/assets-from-master01/hospital_custome-20260921/hopital_custome/Collected_hopital_custome/omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1 \
  --output /tmp/p3-pr486-standard-prepared.usda
```

따라서 RC-4 점검 이후 hospital-v2 합성 기동·두 프레임 동시 측정은 **미실행**이다. 합성 map의 투입구→병원 조제기 벡터와 레일→−Y면 거리를 아직 제공할 수 없다. 아래 병원 단독 수치에 원점 A를 산술 가감해 합성 실측으로 바꾸지 않았다. 원점·zones.yaml·합격선도 변경하지 않았다.

## 2. 별도 단독 미리보기에서 관측한 원본 병원 좌표

사용자가 화면 검토를 요청해, 표준 준비 절차와 별도로 외부 파일에서 자산 루트 토큰만 치환했다. prim·transform은 바꾸지 않았다. 이는 표준 hospital-v2 실행 성공을 뜻하지 않는다.

- 원본 hospital_layout.usda SHA-256: `6661f85f2e72556c66f2db91b1952f8078142987acfb20b0c224d9c13c80eade`
- 표시용 파일 SHA-256: `f013ef0cc5c0074269b1267c9c40c18c075cf74f057a2ce06448e6804772936b`
- DPB-80 원본 model.usd SHA-256: `731307e2c6ca2e3e9ea790112fba1bbd6e399023cf4ca84b818c1a5b631cb3ef`

USD world bound 관측, 미터:
| 대상 | 값 |
| --- | --- |
| /World/machine min | (−10.299363, 10.923905, 0.000000) |
| /World/machine max | (−6.855663, 12.185466, 2.295576) |
| +X bound 면 중앙 (위 bound에서 계산) | (−6.855663, 11.554686, 1.147788) |
| 실제 정면 외판 Y (메시 관측) | 약 11.265465 |

전체 bound의 −Y는 돌출된 중앙 트레이를 포함하므로 외판 Y와 다르다. 이것이 앞선 임시 투입기가 외판에서 떠 있던 원인이다.

선반 translate는 아래 **씬 authored 값**이며, 합성 map 실측이 아니다. /World zero-root와 병원 부모 transform 조건을 별도로 구분한다.
| 선반 | authored translate, m |
| --- | --- |
| SM_MedShelf_01d_67 | (−4.994185542, 11.746113273, 0.000040527) |
| SM_MedShelf_01d_68 | (−4.112901168, 11.736308698, 0.000040527) |
| SM_MedShelf_01d_69 | (−3.216840107, 11.726658714, 0.000040527) |

원본 조제기에는 이 작업에서 추가한 의미상의 투입구 prim이 없었다. 없는 투입구 위치를 0으로 기록하지 않는다.

## 3. 사용자 결정과 #485 에셋

사용자가 화면에서 지정·확인한 변경:
- 조제기 양쪽 돌출부 절단.
- 왼쪽 정면의 실제 컨베이어 위치에 개구부와 내부 테두리 추가.
- 투입기는 +X 측면이 아니라 **−Y 정면, 유리창 아래 오른쪽 금속 패널**에 밀착.
- 색상·데코는 후속 작업.

이 변경은 별도 Draft PR **#485**에 커밋·push했다. `src/rokey_p3_description/models/dispenser/dispenser.usdc`, defaultPrim /Dispenser, Z-up, 미터, root identity, 외부 자산 참조 없음.
- 최종 파일: 336026 B, SHA-256 `cd2591a821d96e44e3a0a90ef66ee33e6fd1b432582618163094bb22242ddaf2`
- 병원 배치 원점: (−8.78522324, 11.7254655, 0).
- 알약 입구 중심: (−8.05, 11.115, 0.98).
- 모듈 입구 중심: (−7.70, 11.11546546, 1.02).
- 로컬 앵커와 원본 해시는 #485 asset.json에 기록.
- 알약 내경 0.12 m, 모듈 입구 0.08×0.16 m/깊이 0.15 m는 기존 빈월드 임시 규격. 병원 실제 약통 크기 적합성은 미검증.
- 에셋에는 물리 collision이 없다. 단독 재개방/화면 확인과 구조 검사는 했지만 삽입·물리 검증 완료가 아니다.

## 4. #484와 레일/M0609 도달 검토

#484는 hospital_navigationv1.usda/usd를 갱신했다. 기존 조제기·선반 67–69 transform은 유지, 선반 70–75 여섯 개를 오른쪽에 추가하고 문·문틀을 비활성화했다. 실행 기본 템플릿은 여전히 hospital_layout.usda라 자동 적용된 것으로 보면 안 된다.

앞선 6.4 m X 이동폭 레일은 기존 세 선반까지만 고려한 **임시 배치**다. #484의 늘어난 선반 전체를 커버하는 최종 레일 길이로 확정하지 않았다.

빈월드 로그 기준: rail origin (0,0.30,0), carriage 0.25 m, Y 한계 −0.10..0.33 m, Z 0..1.10 m, TCP offset 0.19671 m.
- 첫 미리보기 rail Y=10.25에서는 기존 작업 자세 후보가 레일 한계 밖이었다. '절대 도달 불가'가 아니라 기존 후보/범위로 계획되지 않았다는 뜻이다.
- Y=10.75로 0.50 m 전진하고 Y/Z 한계를 빈월드와 맞춘 정지 배치에서, 기존 기구학과 투입 절차로 알약/모듈 각각 접근·삽입·후퇴 IK 해를 구했다.
- 알약 작업 base: (−8.332843, 10.832157, 0.660), 레일 한계 최소 여유 0.182157 m.
- 모듈 작업 base: (−7.550000, 10.745465, 0.720), 레일 한계 최소 여유 0.095465 m.
- 명목 FK 위치 잔차: 알약 약 1.54e−7 m, 모듈 약 1.36e−6 m.
- 모듈 해를 USD 관절 프레임으로 정지 배치해 link_6 + TCP offset을 읽은 잔차 약 1.42e−6 m. 이는 수학/프레임 일치이며 실제 로봇 정확도가 아니다.
- 모든 선반의 파지, 충돌 여유, 레일 이동 경로, 실제 physics 보충은 **미실행**. 미리보기 중 PhysX/CUDA 오류가 발생해 physics를 중지하고 별도 에셋 뷰어로 재개방했다. 이를 L3 성공으로 처리하지 않는다.

## 5. 원본 산출물과 캡처

호스트 내부 경로: `/home/rokey/markle_tmp/m2-pr486-diagnostic/`. `artifacts.json`에 파일별 크기와 전체 SHA-256을 기록했다. 외부 공유 URL이나 정식 evidence manifest가 아니며 원본을 git에 넣지 않았다.

| 파일 | 크기 B | SHA-256 |
| --- | ---: | --- |
| p3-pr486-prepare.log | 277 | 77aaf9f01e175bdc724d18c322b17822cb5577c86d939ed04757dd1c078f0aee |
| hospital-v2-screen.png | 254190 | 61db72cada5ced5f46651d46e387e04f80f9eef0830b9f6e769f0a0906b06503 |
| p3-asset-pr-preview.png | 376678 | 3e86e2fef859d9ab7929160a07b28d73660f499cc1e347985646e4a839db9aec |
| rail-reach-validation.json | 4354 | 544aa3d97ea7eb1c16e4381e735cb514564445e9043515ecccead8b07a40d896 |

첫 캡처는 병원 단독, 두 번째는 #485 최종 단독 에셋이다. 요청한 '병원+절차 조제실 합성 동시 화면'은 아니다.

## 6. 남은 작업

1. 표준 씬 준비기의 39/41 불일치를 별도 코드 변경으로 해결하고 정식 합성 좌표 측정을 수행.
2. #484 병원 배치와 #485 조제기를 별도 합성 레이어로 연결해 기존 조제기 중복을 제거.
3. 새 선반 9개 전체의 실제 슬롯·약통 치수 측정 후 레일 X 길이, 작업 위치, Y/Z 범위를 확정. 빈월드 상대 접근 자세를 출발점으로 전체 경로·충돌을 검증.
4. 원본 모델 출처/라이선스 추가 확인과 물리 collision 설계는 미완료.

이 문서는 현재 얻은 관측·실패·사용자 결정의 인계다. #483의 합성 측정이나 #484 기반 1:1 통합을 완료했다고 주장하지 않는다.



## #483 요구 항목 대조표

| 요청 항목 | 반영 상태 / 근거 |
| --- | --- |
| 호스트·HEAD·Isaac·자산 경로와 해시 | 본문 환경 및 1–2절. ZIP 전체 해시는 미수집이며 model.usd 해시와 혼동하지 않음 |
| /World 원점과 #480 포함 여부 | 321c069 기준 단독 씬. #484에서 조제기 transform 유지 확인. 다른 HEAD 합성 재측정은 미실행 |
| 병원 단독 조제기 min/max/+X 면 중앙 | 2절. 면 중앙은 관측 bbox에서 계산 |
| 선반 67–69 world translate | authored translate와 world bbox 자료만 확보. 합성 world translate 미측정; authored 값을 실측으로 승격하지 않음 |
| 합성 기동 pharmacy_origin | 미실행. HOSPITAL_ORIGIN_A `(0.25, 10.52854210179955, 0, 0)`는 코드 기본값일 뿐 이번 기동 로그가 아님 |
| 합성 보충구·레일·병원 조제기 좌표 | 미실행. 준비기 실패로 합성 기동 단계에 진입하지 않음 |
| 합성 보충구→+X 면 벡터 / 레일→−Y 면 거리 | 미측정. 다른 프레임의 값을 섞어 채우지 않음 |
| 의미 슬롯 prim / collision 유무 | 원본 의미 투입구 없음. #485에서 앵커를 새로 추가했으나 물리 collision은 없음 |
| 병원+절차 조제실 동시 화면 및 해시 | 미실행. 병원 단독/수정 에셋 캡처는 5절에 별도로 기록 |
| 실패·개입·미실행·클라우드 요청 | 1·3·4·6절. 준비기 코드 수정, 최종 통합과 L3는 남은 작업 |

요구 항목의 기록은 모두 채웠으나 요구된 측정이 모두 완료된 것은 아니다. 작업 경과와 사용자가 화면에서 확인한 내용은 [실습32](../practice/practice-32.md)에 기록했다.
