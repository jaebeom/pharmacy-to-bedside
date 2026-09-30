source /opt/ros/jazzy/setup.bash
source /home/rokey/Dev/cobot3_ws/release/20260922-practice31-321c069/install/setup.bash
export ROS_DOMAIN_ID=151
exec ros2 run rokey_p3_manipulation m0609_arm --ros-args -p use_sim_time:=true -p scene_version:=2 -p v2_seed:=835258728 -p v2_guarded_module_path:=false -p v2_rail_select:=preferred_first
