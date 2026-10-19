"""
Configuration for the iPad second-screen streamer.

Edit these values to tune behavior. The most important one is MONITOR_INDEX:
run `python list_monitors.py` to see the list and pick the virtual display.
"""

# Which monitor to capture and stream to the iPad.
# 1 = primary, 2 = second monitor, etc. (0 means "all monitors combined").
# After installing the Virtual Display Driver, the virtual monitor is usually
# the highest-numbered one. Run list_monitors.py to confirm.
#
# The launcher (launcher.py) can override this at runtime via the
# SECONDSCREEN_MONITOR_INDEX environment variable.
import os as _os
MONITOR_INDEX = int(_os.environ.get("SECONDSCREEN_MONITOR_INDEX", 2))

# Network
HOST = "0.0.0.0"          # listen on all interfaces so the iPad can reach it
PORT = 8000               # open http://<your-pc-ip>:8000 on the iPad

# Streaming quality / performance
#
# If it feels laggy, lower these. If you want it sharper and your WiFi is
# strong, raise them. Identical frames are skipped automatically, so a static
# screen uses almost no bandwidth regardless of these values.
TARGET_FPS = 30           # frames per second to send
JPEG_QUALITY = 55         # 1-95; lower = smaller/faster, higher = sharper
MAX_WIDTH = 1280          # downscale frames wider than this before sending.
                          # 1280 is a good balance for the iPad; set 0 to send
                          # full resolution (sharper but heavier / laggier).
