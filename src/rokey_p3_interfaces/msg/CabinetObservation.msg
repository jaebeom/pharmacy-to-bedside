# Evaluator-only observation of a destination cabinet. Contract v1 section 2.1, interfaces v1.1.
# This is the ONLY basis for SUCCESS. Operating nodes (orchestrator, arm, fleet) must not
# subscribe to it; only event_logger does. The orchestrator claims DELIVERED, never SUCCESS.
std_msgs/Header header       # stamp = sim time
string cabinet_id            # cabinet frame id such as bed_a1/cabinet
string order_id              # order id observed inside that cabinet
bool present                 # true when the pouch of that order is inside the cabinet
