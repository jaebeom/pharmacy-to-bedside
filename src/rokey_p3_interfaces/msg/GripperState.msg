# Suction gripper observation. Contract v1 section 11.6, published next to <robot>/gripper/holding (Bool).
# A grasp counts only when state is HELD and last_applied_command_seq has reached the close command.
# A release counts only when state is RELEASED and last_applied_command_seq has reached the open command.
# The arm drops messages from another epoch. After RESET_DONE the counter is 0 until the first command (seq 1).
std_msgs/Header header       # stamp = sim time the observation was made
uint32 epoch                 # epoch of the last RESET_DONE seen (1 before any reset), not RESET_BEGIN
uint32 seq                   # physics-step counter shared with BeltObservation; grows only when sim time moved
uint32 last_applied_command_seq  # last GripperCommand.command_seq processed, including a close with nothing
                                 # in reach; 0 = none yet in this epoch

uint8 state
uint8 STATE_UNKNOWN=0
uint8 STATE_RELEASED=1
uint8 STATE_HELD=2

uint8 mode
uint8 MODE_UNKNOWN=0
uint8 MODE_VIRTUAL=1         # attach by distance and teleport; not a physical grasp
uint8 MODE_PHYSICAL=2        # contact or surface-gripper physics
