"""
Enable / disable the "Virtual Display Driver" device on Windows.

Toggling the device is what makes the extra (iPad) monitor appear or vanish.
Disabling it when the iPad isn't in use stops the phantom screen that lets the
mouse wander off the edge of the laptop display.

Changing device state requires administrator rights, so these functions write a
small PowerShell script to a temp file and launch it elevated (a UAC prompt
appears once). Writing the action to a .ps1 file avoids fragile nested-quote
escaping, which is why an inline nested command silently failed before.

Windows remembers the resolution and position you set for the display, so
re-enabling restores it.
"""

import os
import subprocess
import tempfile
import time

DEVICE_NAME = "Virtual Display Driver"


def get_state() -> str:
    """Return 'enabled', 'disabled', or 'missing'."""
    ps = (
        f"$d = Get-PnpDevice -Class Display -ErrorAction SilentlyContinue | "
        f"Where-Object {{ $_.FriendlyName -eq '{DEVICE_NAME}' }}; "
        f"if (-not $d) {{ 'missing' }} "
        f"elseif ($d.Status -eq 'OK') {{ 'enabled' }} "
        f"else {{ 'disabled' }}"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return out.stdout.strip() or "missing"
    except Exception:
        return "missing"


def _run_elevated(action: str) -> bool:
    """Enable/disable the device via an elevated PowerShell script.

    Writes a .ps1 to the temp dir, then runs it with 'runas' so Windows shows
    the UAC prompt. Confirms success via a result file the script writes.
    Returns True only if the result file contains 'OK'.
    """
    verb = "Enable-PnpDevice" if action == "enable" else "Disable-PnpDevice"

    tmpdir = tempfile.gettempdir()
    script_path = os.path.join(tmpdir, "vdd_toggle.ps1")
    result_path = os.path.join(tmpdir, "vdd_toggle_result.txt")

    # Remove any stale result so we don't read an old value.
    try:
        os.remove(result_path)
    except FileNotFoundError:
        pass

    script = f"""
try {{
    $d = Get-PnpDevice -Class Display -ErrorAction Stop |
         Where-Object {{ $_.FriendlyName -eq '{DEVICE_NAME}' }}
    if (-not $d) {{ throw 'device not found' }}
    {verb} -InstanceId $d.InstanceId -Confirm:$false -ErrorAction Stop
    Set-Content -Path '{result_path}' -Value 'OK' -Encoding ascii
}} catch {{
    Set-Content -Path '{result_path}' -Value $_.Exception.Message -Encoding ascii
}}
"""
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)

    # Launch the script elevated. -Verb RunAs triggers the UAC prompt.
    # We do NOT hide this window with CREATE_NO_WINDOW, because doing so can
    # suppress the elevation request on some systems.
    launch = (
        f"Start-Process powershell "
        f"-Verb RunAs -Wait "
        f"-ArgumentList '-NoProfile','-ExecutionPolicy','Bypass',"
        f"'-WindowStyle','Hidden','-File','{script_path}'"
    )

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", launch],
            capture_output=True, text=True, timeout=120,
        )
    except Exception:
        return False

    # Wait briefly for the result file (the elevated process is separate).
    for _ in range(20):
        try:
            with open(result_path, "r", encoding="ascii", errors="ignore") as f:
                return f.read().strip() == "OK"
        except FileNotFoundError:
            time.sleep(0.25)
    return False


def enable() -> bool:
    return _run_elevated("enable")


def disable() -> bool:
    return _run_elevated("disable")
