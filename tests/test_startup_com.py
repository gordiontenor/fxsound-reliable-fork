"""Audio-free COM apartment contract test for FxSound's startup thread."""
from ctypes import WinDLL, byref, c_long, c_size_t, c_uint, c_void_p
from pathlib import Path
import re
import threading

ROOT = Path(__file__).resolve().parents[1]
main = (ROOT / "fxsound/Source/Main.cpp").read_text(encoding="utf-8")
init = (ROOT / "audiopassthru/src/sndDevices/sndDevicesInit.cpp").read_text(encoding="utf-8")
assert re.search(r"CoInitializeEx\s*\(\s*0\s*,\s*COINIT_MULTITHREADED\s*\)", main)
entry = init[init.index("int PT_DECLSPEC sndDevicesInit("):init.index("int PT_DECLSPEC sndDevices_FreeReuseableObjects(")]
assert "CoGetContextToken(&comContextToken)" in entry
assert not re.search(r"(?m)^\s*(?:hr\s*=\s*)?CoInitialize(?:Ex)?\s*\(", entry), "sndDevicesInit must not change the caller's apartment"

ole = WinDLL("ole32")
ole.CoInitializeEx.argtypes = [c_void_p, c_uint]
ole.CoInitializeEx.restype = c_long
ole.CoInitialize.argtypes = [c_void_p]
ole.CoInitialize.restype = c_long
ole.CoGetContextToken.argtypes = [c_void_p]
ole.CoGetContextToken.restype = c_long
ole.CoUninitialize.argtypes = []
ole.CoUninitialize.restype = None

results = []
def check(apartment):
    def run():
        hr = ole.CoInitializeEx(None, apartment)
        assert hr >= 0, f"initialization failed: {hr & 0xffffffff:08X}"
        try:
            token = c_size_t()
            assert ole.CoGetContextToken(byref(token)) == 0 and token.value != 0
            if apartment == 0:
                wrong = ole.CoInitialize(None)  # STA request after MTA
                assert (wrong & 0xffffffff) == 0x80010106
                # A failed apartment switch must not invalidate the existing context.
                after = c_size_t()
                assert ole.CoGetContextToken(byref(after)) == 0 and after.value == token.value
            results.append(apartment)
        finally:
            ole.CoUninitialize()
    t = threading.Thread(target=run)
    t.start()
    t.join(timeout=8)
    assert not t.is_alive()
    assert apartment in results, f"COM thread assertion failed for apartment {apartment}"

check(0)  # MTA from Main.cpp
check(2)  # existing STA is equally valid for checking initialized COM
print("PASS: 2 audio-free COM apartment cases (MTA and STA; no endpoint opened)")
