# Whether the base is inside the docking tolerance of a zone. Contract v1 section 11.6.
# The meaning of <robot>/base/stopped does not change. The state is UNKNOWN when the zone is not ready
# (zero, NaN or unset tolerance, judged by the same readiness function the fleet uses), when the TF
# map -> base_link cannot be looked up, when odom has not arrived for 1.0 s (wall), when AMCL is stale,
# and before the first RESET_DONE has been seen. While a GoToZone goal is active the state is NOT_DOCKED.
std_msgs/Header header       # stamp = sim stamp of the TF and odom used for the judgement
uint32 epoch                 # epoch of the last RESET_DONE seen (1 before any reset), not RESET_BEGIN
uint32 seq                   # +1 only when the odom stamp used has moved forward in sim time

uint8 docking
uint8 DOCKING_UNKNOWN=0
uint8 DOCKING_DOCKED=1       # within tol_xy and tol_yaw of zone_id
uint8 DOCKING_NOT_DOCKED=2

string zone_id               # target zone of the last accepted GoToZone; cleared on RESET_DONE
float32 error_xy             # distance from the zone pose in m; NaN when unknown
float32 error_yaw            # absolute yaw error in rad; NaN when unknown
