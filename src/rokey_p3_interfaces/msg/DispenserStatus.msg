# State of the dispenser black box.
std_msgs/Header header
DispenserSlot[] slots
string[] paused_item_ids     # drugs whose two slots are both empty; dispensing paused
uint32 queue_length          # requests waiting to be dispensed
bool belt_occupied           # a pouch is on the belt (one at a time)
