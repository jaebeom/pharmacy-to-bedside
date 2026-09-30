# One dispenser slot = one canister. Two slots (A, B) per drug. Scenario step 1 "stock and refill".
string item_id
uint8 slot
uint8 SLOT_A=0
uint8 SLOT_B=1
string lot_id
string expiry                # ISO 8601 date; data only, no physics
uint32 count                 # pouches left; 0 means empty slot
bool active                  # slot currently dispensing (earliest expiry lot)
