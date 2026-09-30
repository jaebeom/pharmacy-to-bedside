# Belt backend observation. Contract v1 section 11.6, published next to /pharmacy/belt by the same writer
# from the same model state. Every enum is 0 = UNKNOWN: a default message means "not known", never
# "empty" or "stopped". Receivers drop other epochs and treat a seq that does not increase as stale.
std_msgs/Header header       # stamp = sim time the observation was made (not the publish time)
uint32 epoch                 # epoch of the last RESET_DONE seen (1 before any reset), not RESET_BEGIN
uint32 seq                   # physics-step counter shared with GripperState; grows only when sim time moved
                             # forward. Gaps between messages are normal: receivers check for an increase

string request_id            # request that dispensed the pouch on the belt; empty when none
string order_id              # order of that pouch; operation = (epoch, request_id, order_id)

uint8 mode
uint8 MODE_UNKNOWN=0
uint8 MODE_STUB=1            # no physics; never counted as a physical result
uint8 MODE_SIM_SENSOR=2      # simulator pose and velocity standing in for a sensor
uint8 MODE_PERCEPTION=3      # sensor or camera detection with capture-time TF

uint8 occupancy
uint8 OCCUPANCY_UNKNOWN=0    # includes a pouch whose tracking was lost
uint8 OCCUPANCY_EMPTY=1
uint8 OCCUPANCY_OCCUPIED=2

uint8 pouch_zone
uint8 ZONE_UNKNOWN=0
uint8 ZONE_ON_BELT=1         # on the belt, outside the end zone
uint8 ZONE_END=2             # inside the end zone
uint8 ZONE_OFF_BELT=3        # outside the belt volume (dropped, lifted away)

uint8 pouch_motion           # MOTION_* below; STOPPED only after settling for the settle time without a gap;
                             # UNKNOWN when the speed is missing or the pouch is not tracked
uint8 belt_motion            # MOTION_* below; UNKNOWN until the belt surface itself is observed
uint8 MOTION_UNKNOWN=0
uint8 MOTION_MOVING=1
uint8 MOTION_STOPPED=2

uint8 belt_command_applied   # drive command read back from the belt drive attribute (not the value written);
                             # a command state, not observed motion
uint8 APPLIED_UNKNOWN=0
uint8 APPLIED_RUN=1
uint8 APPLIED_STOP=2
