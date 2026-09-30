# 배포 설정

여기는 여러 패키지를 묶는 배포 profile과 현장값 예시의 위치다.
노드별 기본 파라미터·launch 자산은 해당 ROS 패키지의 config와 share에 설치한다.
같은 값의 기준 파일을 루트와 패키지에 중복하지 않는다.

[카메라 배송 프로필](hospital-camera-delivery.sh)은 9/29 master02 성공 회차의 현장값이다.
`v1.1.0`(#797, `2c08bef`)부터 `tools/demo_v2.sh` 의 병원 카메라 기본값이 이 프로필과 같다. 그래서 이 파일은 값을 드러내 적어 둔 기록이다.
파일 머리 주석의 "v1.0.1" 은 태그가 아니다. 이 기본값이 들어간 릴리스는 `v1.1.0` 이다.
적용과 한계는 [병원 런북 7절](../docs/runbooks/hospital-full.md#7-929-카메라-배송-성공-설정)에 있다.
다른 배포의 검증된 실행 profile은 아직 없다. [호스트 목록](../docs/setup/host-inventory.md) 확인과
pilot 후 확정한다. 개별 IP/interface/절대 경로·계정은 config/local/에 두고 커밋하지 않는다.
실행에 적용된 설정의 비밀 없는 snapshot과 SHA-256을 artifact로 보존한다.
설정 변경은 새 run이다. 주소 예시를 실제 구성으로 간주하지 않는다.

프로필은 저장소 루트에서 `source config/hospital-camera-delivery.sh`로 적용한다.
프로필은 `P3_SIM_SENSORS=1`도 켠다. `demo_v2.sh` 자체 기본은 `0`이다. 카메라 모드에서도 평가용 보관함 관측에는 `1`이 필요하다.
프로필이 zones·routes·팔 설정을 고정하므로, 소싱 뒤 `P3_CAMERA_POUCHES=0`만 바꿔 참값 회차를 만들지 않는다.
서로 다른 구성은 별도 셸과 해당 회차의 전체 설정으로 실행한다. 성공 후보 SHA와 통합 릴리스 SHA도 구분한다([실습45](../docs/practice/simworld/practice-45.md)).
