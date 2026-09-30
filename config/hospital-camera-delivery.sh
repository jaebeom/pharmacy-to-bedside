# 저장소 루트에서 source config/hospital-camera-delivery.sh 후 tools/demo_v2.sh 사용.
# v1.0.1 부터 병원 카메라 기본값이 이 프로필과 같다(demo_v2). 값을 드러내 적어 두는 기록용이다.
# PC별 자산·설치·로그 경로는 config/local/에서 지정한다.
export P3_REPO="${P3_REPO:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
export P3_WORLD=hospital P3_SIM_SENSORS=1 P3_CAMERA_POUCHES=1 P3_CAMERA_TAGS=1
export P3_ZONES="$P3_REPO/src/rokey_p3_description/config/zones.hospital-receiver.yaml"
export P3_ROUTES="$P3_REPO/src/rokey_p3_description/config/routes.hospital-receiver.yaml"
export P3_UR5_ARM_PARAMS="$P3_REPO/src/rokey_p3_manipulation/config/ur5_arm.amr-combined.camera-receiver.yaml"
export P3_AMR_START='-8.266 4.102'   # = zones.hospital-receiver 의 dock_1 = load(재범 9/29 B안)
export P3_HOSPITAL_RECEIVER_PRIM=/World/P3Base/Scene/Environment/hospital/SM_SideTable_02a_74
export P3_BELT_VIEW_OFFSET=0 P3_DISPENSE_WHILE_DISPATCHING=true
