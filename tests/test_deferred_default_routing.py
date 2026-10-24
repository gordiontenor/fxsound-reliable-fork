"""Guard the order of startup routing without opening any sound device."""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1] / "audiopassthru/src/sndDevices"
rules = (root / "sndDevicesImplementDeviceRules.cpp").read_text(encoding="utf-8")
reinit = (root / "sndDevicesReInit.cpp").read_text(encoding="utf-8")
reinit = reinit[reinit.index("int PT_DECLSPEC sndDevicesReInit("):reinit.index("int PT_DECLSPEC sndCheckDeviceChanges(")]

assert not re.search(r"\bsndDevicesSetDeviceType\s*\(", rules), "device rules must not switch the system default early"
capture = reinit.index("if (sndDevicesFinalSetupCaptureDevice(")
playback = reinit.index("if (sndDevicesFinalSetupPlaybackDevice(")
mode = reinit.index("if (sndDevicesGetDefaultDeviceSelectionMode(", playback)
commit = reinit.index("if (sndDevicesSetDeviceType(", mode)
callback_enable = reinit.index("cast_handle->ignoreDeviceCallbacks = FALSE;", commit)
assert capture < playback < mode < commit < callback_enable
# The switch follows both success-status checks, not just the setup calls themselves.
assert "resultFlag != SND_DEVICES_DEVICE_OPERATION_COMPLETED" in reinit[playback:mode]
assert "defaultSelectionAutoMode == SND_DEVICES_AUTO_SELECT_DEFAULT_DEVICE_ON" in reinit[mode:commit]
assert "*ipDfxDeviceEnabledFlag = IS_FALSE;" in reinit[commit:callback_enable]
assert "return(NOT_OKAY_NO_BREAK);" in reinit[commit:callback_enable]
print("PASS: deferred default routing (no early switch; after both setup checks; failure blocks activation)")
