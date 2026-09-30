cmake_minimum_required(VERSION 3.8)
project(rokey_p3_interfaces)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(action_msgs REQUIRED)

# 파일을 추가하면 이 목록에도 추가한다. 순서는 의존 관계와 무관하다.
rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/Order.msg"
  "msg/DeliveryRequest.msg"
  "msg/OrderStatus.msg"
  "msg/Event.msg"
  "msg/BeltState.msg"
  "msg/CabinetObservation.msg"
  "msg/DispenserSlot.msg"
  "msg/DispenserStatus.msg"
  "msg/TagRead.msg"
  "msg/PouchDetection.msg"
  "msg/PouchDetectionArray.msg"
  "msg/BeltObservation.msg"
  "msg/GripperState.msg"
  "msg/GripperCommand.msg"
  "msg/ArmClearance.msg"
  "msg/DockingState.msg"
  "srv/Dispense.srv"
  "srv/Reset.srv"
  "srv/CheckContainer.srv"
  "action/Deliver.action"
  "action/PickPouch.action"
  "action/Refill.action"
  "action/GoToZone.action"
  "action/ScanTag.action"
  DEPENDENCIES std_msgs geometry_msgs builtin_interfaces action_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
