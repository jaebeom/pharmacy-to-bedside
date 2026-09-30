# Conveyor belt state seen by the simulator. Contract v1 section 2.1, interfaces v1.1.
# Heartbeat topic (H): 5 Hz, depth 1. No message for 1.0 s wall means unknown,
# and unknown forbids both dispensing and picking.
std_msgs/Header header       # stamp = sim time
bool occupied                # a pouch is on the belt; only one at a time
bool at_end                  # the pouch reached the end stop sensor and the belt stopped
string order_id              # order id of the pouch on the belt; empty when the belt is free
