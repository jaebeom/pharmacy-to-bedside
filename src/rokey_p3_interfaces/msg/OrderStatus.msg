# State of one order (pouch). The four terminal states match scenario section 5.
std_msgs/Header header
string request_id
string order_id

uint8 state
uint8 STATE_ACCEPTED=0
uint8 STATE_IN_PROGRESS=1
uint8 STATE_DELIVERED=2      # v1.1. Orchestrator claim: placed and CABINET_LOCKED was emitted
uint8 STATE_SUCCESS=10       # evaluator observed the pouch id inside the destination cabinet.
                             # The orchestrator never publishes this one; event_logger writes it
                             # into the run record from /evaluator/cabinet only
uint8 STATE_HOLD_RETURN=11   # auth mismatch or not detected; pouch stays in deck slot; re-dispatchable
uint8 STATE_ABORT=12         # dropped or lost; not re-dispatchable
uint8 STATE_TIMEOUT=13       # protocol time limit exceeded

string reason                # terminal reason; defined in docs/architecture/exception-outcomes-v1.md
