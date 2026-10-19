"""
Screen capture for a single monitor, encoded to JPEG for streaming.

Prefers the Windows Desktop Duplication API via `dxcam` (fast, GPU-assisted,
and only produces a new frame when the screen actually changes). Falls back to
`mss` if dxcam can't initialize for the requested monitor.

Neither backend captures the mouse cursor, so we draw a synthetic pointer at
the real cursor position (from the Windows API) when it's on this monitor.

A ScreenCapturer instance is NOT thread-safe: create one per thread/task.
"""

import ctypes
import io

import mss
from PIL import Image, ImageDraw

try:
    import dxcam
except Exception:  # dxcam is Windows-only / optional
    dxcam = None


def _get_cursor_pos():
    """Return the global (x, y) cursor position in virtual-screen pixels."""
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    pt = POINT()
    if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
        return pt.x, pt.y
    return None


def _draw_cursor(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0):
    """Draw a simple arrow cursor with (x, y) as its tip (hotspot)."""
    s = max(1.0, 18 * scale)
    pts = [
        (0, 0), (0, s), (0.28 * s, 0.72 * s), (0.45 * s, 1.05 * s),
        (0.62 * s, 0.98 * s), (0.45 * s, 0.66 * s), (0.72 * s, 0.66 * s),
    ]
    poly = [(x + px, y + py) for px, py in pts]
    draw.polygon(poly, fill=(255, 255, 255), outline=(0, 0, 0))


def _dxcam_output_for_monitor(monitor):
    """Map an mss monitor dict to a dxcam (device_idx, output_idx), or None.

    Matches on the monitor's top-left position, which is stable across the two
    libraries' coordinate systems.
    """
    if dxcam is None:
        return None
    try:
        info = dxcam.output_info()
    except Exception:
        return None
    # output_info() is a human string; instead probe outputs directly.
    # dxcam exposes outputs per device; we try device 0 (typical single-GPU).
    # We match by resolution as a robust-enough heuristic.
    target_w, target_h = monitor["width"], monitor["height"]
    for line in info.splitlines():
        # Format: "Device[0] Output[1] Res:(1770, 1180) Rot:0 Primary:False"
        if "Res:" in line and f"({target_w}, {target_h})" in line:
            try:
                dev = int(line.split("Device[")[1].split("]")[0])
                out = int(line.split("Output[")[1].split("]")[0])
                return dev, out
            except Exception:
                continue
    return None


class ScreenCapturer:
    def __init__(self, monitor_index: int, jpeg_quality: int = 60,
                 max_width: int = 1920, draw_cursor: bool = True,
                 target_fps: int = 30):
        self.monitor_index = monitor_index
        self.jpeg_quality = jpeg_quality
        self.max_width = max_width
        self.draw_cursor = draw_cursor

        self._sct = mss.MSS()
        monitors = self._sct.monitors
        if monitor_index < 0 or monitor_index >= len(monitors):
            raise ValueError(
                f"MONITOR_INDEX {monitor_index} is out of range. "
                f"Detected {len(monitors) - 1} monitor(s). "
                f"Run `python list_monitors.py` to see valid choices."
            )
        self.monitor = monitors[monitor_index]

        # Try to set up the fast dxcam backend for this monitor.
        self._cam = None
        mapping = _dxcam_output_for_monitor(self.monitor)
        if mapping is not None:
            dev, out = mapping
            try:
                self._cam = dxcam.create(
                    device_idx=dev, output_idx=out,
                    output_color="RGB", processor_backend="numpy",
                )
                self._cam.start(target_fps=target_fps, video_mode=True)
                self._backend = "dxcam"
            except Exception:
                self._cam = None
        if self._cam is None:
            self._backend = "mss"

    @property
    def backend(self):
        return self._backend

    @property
    def size(self):
        return self.monitor["width"], self.monitor["height"]

    # -- frame acquisition ---------------------------------------------------
    def _grab_image(self):
        """Return a PIL RGB Image of the current monitor, or None if unchanged.

        With dxcam in video_mode, get_latest_frame() blocks until a NEW frame
        is available, so callers naturally only get frames when the screen
        changes. mss always returns a frame.
        """
        if self._cam is not None:
            frame = self._cam.get_latest_frame()  # numpy HxWx3, RGB
            if frame is None:
                return None
            h, w = frame.shape[0], frame.shape[1]
            return Image.frombytes("RGB", (w, h), frame.tobytes())
        # mss fallback
        raw = self._sct.grab(self.monitor)
        return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    def grab_jpeg(self, skip_unchanged: bool = False):
        """Grab the current frame as JPEG bytes (or None if no new frame)."""
        img = self._grab_image()
        if img is None:
            return None

        scale = 1.0
        if self.max_width and img.width > self.max_width:
            scale = self.max_width / img.width
            new_size = (self.max_width, int(img.height * scale))
            img = img.resize(new_size, Image.BILINEAR)

        if self.draw_cursor:
            self._overlay_cursor(img, scale)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=self.jpeg_quality)
        return buf.getvalue()

    def _overlay_cursor(self, img: Image.Image, scale: float):
        pos = _get_cursor_pos()
        if pos is None:
            return
        gx, gy = pos
        left, top = self.monitor["left"], self.monitor["top"]
        w, h = self.monitor["width"], self.monitor["height"]
        if not (left <= gx < left + w and top <= gy < top + h):
            return
        local_x = (gx - left) * scale
        local_y = (gy - top) * scale
        _draw_cursor(ImageDraw.Draw(img), int(local_x), int(local_y), scale)

    def close(self):
        if self._cam is not None:
            try:
                self._cam.stop()
            except Exception:
                pass
            self._cam = None
        try:
            self._sct.close()
        except Exception:
            pass
