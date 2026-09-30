"""Shared parts for the P3 Isaac Sim standalone scripts in sim/standalone/.

Pure modules (no Isaac, importable by plain Python and the tests in sim/tests/):
    common    logging helpers, loop and exit rules, argparse types
    geometry  boxes, quaternions, poses
    bridge    JSON messages on std_msgs/String between Isaac and the system-ROS adapter
    belt      belt, end sensor and dispense rules
    pouch     seeded pouch spawn sampling and order ids
    reset     /sim/reset step order and fault injection

Isaac modules import omni/isaacsim/pxr inside their functions and only run under Isaac's python.sh.
The split exists so the simulation lane can move the same parts into the hospital scene later.
"""
