# Suction gripper command with a sequence number. Contract v1 section 11.6.
# The arm publishes the same close value on <robot>/gripper/command (Bool) and here. A simulator started in
# the command_seq configuration ignores the Bool command from the start. In one epoch it ignores a command
# whose command_seq is not above the last applied one (resends are idempotent).
std_msgs/Header header       # stamp = sim time of the command
uint32 epoch                 # epoch of the last RESET_DONE seen (1 before any reset), not RESET_BEGIN
uint32 command_seq           # +1 per command; restarts at 1 after each RESET_DONE
bool close                   # true = suction on, same meaning as the Bool command
