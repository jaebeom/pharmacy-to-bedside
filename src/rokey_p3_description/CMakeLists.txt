cmake_minimum_required(VERSION 3.8)
project(rokey_p3_description)

find_package(ament_cmake REQUIRED)

# 씬·자산·설정(zones.yaml)을 share/rokey_p3_description/ 로 설치한다.
# 설치하지 않으면 get_package_share_directory() 로 찾을 수 없다.
install(
  DIRECTORY stages models config
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
