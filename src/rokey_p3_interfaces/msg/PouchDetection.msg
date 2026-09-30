# One pouch detected by YOLO plus its QR read. Grasp pose conversion is done by manipulation.
std_msgs/Header header       # frame_id = camera frame, stamp = image time
string order_id              # QR payload; empty when unreadable
float32 confidence           # detection confidence 0..1
geometry_msgs/Pose pose      # pouch pose estimate in the camera frame
int32 slot_index             # deck slot index; -1 when on the belt
