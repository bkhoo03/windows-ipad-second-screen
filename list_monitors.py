"""
List all monitors Windows currently reports, so you can pick which one to
stream to the iPad.

Run:  python list_monitors.py

After installing the Virtual Display Driver, run this again. The new entry
(usually the last / highest index) is your virtual display. Put its index
into MONITOR_INDEX in config.py.
"""

import mss


def main():
    with mss.MSS() as sct:
        monitors = sct.monitors
        real = monitors[1:]  # index 0 is the combined "all monitors" region

        if not real:
            print("No monitors detected.")
            return

        print(f"Detected {len(real)} monitor(s):\n")
        print(f"  index 0  =  ALL monitors combined "
              f"({monitors[0]['width']}x{monitors[0]['height']})")
        for i, m in enumerate(real, start=1):
            print(f"  index {i}  =  {m['width']}x{m['height']} "
                  f"at ({m['left']}, {m['top']})")

        print("\nSet MONITOR_INDEX in config.py to the index of your "
              "virtual display (usually the highest number).")


if __name__ == "__main__":
    main()
