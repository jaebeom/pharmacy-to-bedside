# Whether the arm, its tool and a held pouch are clear of a corridor. Contract v1 section 11.6.
# Judged from measured joint_states forward kinematics against a corridor box supplied by simulation.
# CLEAR is not trusted before FK has been checked against the real TCP in L3.
# During the reset barrier (RESET_BEGIN to RESET_DONE) the state is UNKNOWN.
std_msgs/Header header       # stamp = sim time of the joint_states used
uint32 epoch                 # epoch of the last RESET_DONE seen (1 before any reset), not RESET_BEGIN
uint32 seq                   # +1 only when the joint_states stamp used has moved forward in sim time

uint8 clearance
uint8 CLEARANCE_UNKNOWN=0
uint8 CLEARANCE_CLEAR=1
uint8 CLEARANCE_INTRUDING=2

string region                # corridor name such as belt_corridor; for logs, not a decision key
float32 margin_m             # smallest distance from arm, tool or held pouch to the box; negative inside;
                             # NaN when unknown
string detail                # why the state is UNKNOWN, for people; never used for a decision
