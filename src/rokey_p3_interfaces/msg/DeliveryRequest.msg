# Delivery request. One request = one trip. Scenario section 3 and step 1.
std_msgs/Header header       # stamp = issue time from the synthetic order generator (sim time)

string request_id

uint8 mode
uint8 MODE_SINGLE=0          # one pouch to one bed
uint8 MODE_URGENT=1          # one pouch to one bed, head of dispenser queue, ARRIVING alarm
uint8 MODE_BATCH_ROOM=2      # N pouches, beds of one room in sequence
uint8 MODE_BATCH_WARD=3      # N pouches, ward station cabinet

string destination_id        # zone id such as bed_a1 / room_a1 / station_a
Order[] orders               # pouches. Empty list is rejected
