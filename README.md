# iPad as a Second Screen for Windows (free, self-built)

Turn your iPad into a **true extended display** for your Windows PC. Your mouse
moves onto it, you drag windows there, click things — just like a real second
monitor. The iPad shows the picture over your local WiFi; you keep using your
normal mouse and keyboard.

This is **display-only**: the iPad shows the extended desktop, and you control
everything with your PC's own mouse/keyboard (no touch control needed, because
Windows already treats the extra display as real).

## How it works

```
[Virtual Display Driver]  ->  Windows creates a real extended monitor
          |
          v  (this app captures that monitor)
[server.py]  ->  grabs frames, streams JPEG over WebSocket on your WiFi
          |
          v
[client.html in Safari on iPad]  ->  shows the live picture full screen
```

The one piece we don't build is the virtual monitor itself — that requires a
Windows display driver. We use a free, open-source, signed one for that.

---

## Step 1 — Install the Virtual Display Driver (one time)

This creates the fake monitor that Windows treats as a real extended display.

1. Go to the open-source project:
   **https://github.com/VirtualDrivers/Virtual-Display-Driver**
2. Open the **Releases** page and download the latest release.
3. Follow their install instructions (typically: unzip, then run the included
   installer, or install the driver via the provided tool). Approve the driver
   installation prompt from Windows.
4. After installing, a new virtual monitor appears. Open Windows **Settings →
   System → Display** and confirm you see an extra display.

> This is a third-party driver operating at the system level. Only install the
> official signed release from the link above. It's the single external
> component this project depends on.

If you'd rather not install a driver and you already own a spare physical
monitor or an HDMI "dummy plug," those also create a real extra display that
this app can capture — the driver is just the free software equivalent.

## Step 2 — Arrange the display

In **Settings → System → Display**:

- Set the virtual display to **Extend** (not duplicate).
- Drag its box to where you want it (e.g. to the right of your main screen) so
  the mouse crosses over naturally.
- Note its resolution — you can lower it in the driver's options for smoother
  streaming (e.g. 1280x720 or 1920x1080).

## Step 3 — Install this app's dependencies (one time)

Open PowerShell in this folder and run:

```powershell
pip install -r requirements.txt
```

## Step 4 — Pick the monitor to stream

```powershell
python list_monitors.py
```

You'll see something like:

```
index 0  =  ALL monitors combined
index 1  =  2880x1800 at (0, 0)
index 2  =  1920x1080 at (2880, 0)   <- the virtual display
```

The virtual display is usually the **highest-numbered** one and sits at an
offset (its `left` value is not 0). Open **config.py** and set:

```python
MONITOR_INDEX = 2   # use the index of your virtual display
```

## Step 5 — Run the server

```powershell
python server.py
```

It prints the address to open on the iPad, for example:

```
On the iPad, open:  http://192.168.1.42:8000
```

The first time, Windows may pop up a **Firewall** prompt — allow access on
**Private networks** so the iPad can reach the server.

## Step 6 — Connect the iPad

1. Make sure the iPad is on the **same WiFi** as the PC.
2. Open **Safari** and go to the address the server printed.
3. The extended desktop appears. Tap once to reveal the **Fill / Fit** and
   **Fullscreen** buttons.
4. Tip: use Safari's **Share → Add to Home Screen** to get a full-screen,
   app-like launcher with no browser bars.

Now move your mouse toward the side where you placed the virtual display — the
cursor crosses onto the iPad, and you can drag windows over and use them.

---

## Tuning (config.py)

| Setting        | What it does                                             |
|----------------|----------------------------------------------------------|
| `MONITOR_INDEX`| Which monitor to stream (from `list_monitors.py`).       |
| `PORT`         | HTTP port for the iPad page (WebSocket uses `PORT + 1`). |
| `TARGET_FPS`   | Frames per second. 30 is smooth; drop to 15 to save WiFi.|
| `JPEG_QUALITY` | 1–95. Lower = faster and blurrier, higher = sharper.     |
| `MAX_WIDTH`    | Downscale wide frames before sending (0 = off).          |

If it feels laggy: lower `JPEG_QUALITY` (e.g. 45), lower `TARGET_FPS` (e.g. 20),
or set the virtual display to a smaller resolution in the driver options.

## Troubleshooting

- **iPad shows "Connecting…" forever** — server not running, wrong address, or
  firewall blocking. Re-run `python server.py`, re-check the printed URL, and
  allow the app through the Windows Firewall on Private networks.
- **"MONITOR_INDEX out of range"** — run `python list_monitors.py` again and set
  a valid index in `config.py`.
- **Black screen on the iPad but connected** — the virtual monitor may have
  nothing on it yet. Drag a window onto it, or move your mouse over to it.
- **Different device / can't find PC IP** — run `ipconfig` in PowerShell and use
  the IPv4 address of your active WiFi adapter with `:8000`.
- **Cursor won't cross onto the iPad** — the display isn't set to *Extend*, or
  it's positioned on a different side than you think. Recheck Step 2.

## Sharing this project with someone else

This folder is self-contained and has nothing personal hardcoded (the PC's IP
address is detected automatically at runtime). To share it:

1. Zip the folder **without** the `.venv/` and `__pycache__/` folders — they're
   tied to one specific machine. The included `.gitignore` already excludes them
   if you share via git.
2. The person who receives it does the one-time setup on their own PC:
   - Install **Python 3** from <https://www.python.org/downloads/> and tick
     **"Add python.exe to PATH"** during install.
   - Open PowerShell in the folder and run `pip install -r requirements.txt`.
   - Install the **Virtual Display Driver** (Step 1 above).
   - Double-click `start_launcher.bat` (it finds Python automatically).

`MONITOR_INDEX` in `config.py` is machine-specific, but the launcher lets each
person pick their monitor from a list, so no editing is required.

## Scope

- **Display-only**: the iPad shows the extended desktop; you control it with the
  PC's own mouse and keyboard (no touch input sent back).
- **Windows only**, and depends on one external component, the Virtual Display
  Driver, to create the extra monitor.

## Credits

Built on the open-source
[Virtual Display Driver](https://github.com/VirtualDrivers/Virtual-Display-Driver)
by the VirtualDrivers project, which provides the virtual monitor. Everything
else in this repo (capture, streaming, client, control panel) is original.

## License

MIT, see [LICENSE](LICENSE).

## Files

| File               | Purpose                                             |
|--------------------|-----------------------------------------------------|
| `server.py`        | Runs the HTTP + WebSocket servers and capture loop. |
| `capture.py`       | Grabs a monitor and encodes frames to JPEG.         |
| `client.html`      | The iPad web page that displays the stream.         |
| `list_monitors.py` | Lists monitors so you can pick the virtual display. |
| `config.py`        | All tunable settings.                               |
| `requirements.txt` | Python dependencies.                                |
