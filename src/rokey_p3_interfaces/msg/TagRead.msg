# One QR read by the hand camera: patient tag, station tag, pouch QR, canister (cn-) or module (md-) QR.
# Consumers ignore kinds they do not know (QR/DB/camera contract v1, section 1).
std_msgs/Header header       # frame_id = camera frame
uint8 kind
uint8 KIND_PATIENT=0
uint8 KIND_STATION=1
uint8 KIND_POUCH=2
uint8 KIND_CONTAINER=3       # cn-NNNN, the whole QR text is tag_id
uint8 KIND_MODULE=4          # md-NNNN, the whole QR text is tag_id
string tag_id                # patient id, station id, order id, canister id or module id
uint8 status
uint8 STATUS_OK=0
uint8 STATUS_UNREADABLE=1
