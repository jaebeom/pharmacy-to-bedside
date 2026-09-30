# One execution event. Metrics (scenario section 6) are intervals between event stamps.
std_msgs/Header header       # stamp = sim time. Link-loss watchdogs use a separate monotonic clock
string name                  # one of the constants below
string request_id            # empty when not applicable
string order_id              # empty when not applicable
string robot_id              # amr_1 .. amr_5, m0609, dispenser
uint32 epoch                 # increments on every reset; events from an older epoch are ignored
string detail                # free text; never used for pass/fail judgement

# Event names. Contract v1 section 2.6 fixes who publishes which name; the same name is
# never published by two nodes. Four names marked v1.1 were added with the contract.
string REQUEST_ACCEPTED="REQUEST_ACCEPTED"   # v1.1, orchestrator
string DISPENSED="DISPENSED"
string DISPENSER_PAUSED="DISPENSER_PAUSED"
string DISPENSER_RESUMED="DISPENSER_RESUMED"
string REFILL_REQUESTED="REFILL_REQUESTED"
string REFILL_DONE="REFILL_DONE"
string AMR_DOCKED_LOAD="AMR_DOCKED_LOAD"
string POUCH_AT_END="POUCH_AT_END"
string PICK_ATTEMPT="PICK_ATTEMPT"           # v1.1, arm. Retries are counted by event count
string POUCH_PICKED="POUCH_PICKED"
string POUCH_LOADED="POUCH_LOADED"
string LOAD_DONE="LOAD_DONE"
string ARM_HOME="ARM_HOME"                   # v1.1, arm
string DEPARTED="DEPARTED"
string ARRIVING="ARRIVING"
string ARRIVED="ARRIVED"
string AUTH_OK="AUTH_OK"
string AUTH_FAIL="AUTH_FAIL"
string POUCH_DETECTED="POUCH_DETECTED"
string POUCH_PLACED="POUCH_PLACED"
string CABINET_LOCKED="CABINET_LOCKED"
string ORDER_DONE="ORDER_DONE"
string RETURNED="RETURNED"
string DOCKED="DOCKED"
string RESET_DONE="RESET_DONE"               # v1.1, orchestrator. Carries the new epoch
string RESET_BEGIN="RESET_BEGIN"             # orchestrator. Carries the new epoch; starts the reset barrier. Control nodes stop commands until RESET_DONE
