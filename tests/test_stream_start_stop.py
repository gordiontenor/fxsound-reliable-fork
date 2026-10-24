"""Compile the actual sndDevicesStartStopCapture implementation with mock audio clients.

No audio device is opened. Test build artifacts are written to a temporary directory.
Run: python tests/test_stream_start_stop.py
"""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "audiopassthru/src/sndDevices/sndDevicesDoCapture.cpp"
HEADER = ROOT / "audiopassthru/include/sndDevices.h"

text = SOURCE.read_text(encoding="utf-8")
anchor = "static int sndDevicesReportStreamFailure("
assert text.count(anchor) == 1, "expected one error-reporting function"
actual_functions = text[text.index(anchor):]
assert "int PT_DECLSPEC sndDevicesStartStopCapture(" in actual_functions
assert "int PT_DECLSPEC " not in actual_functions.split("int PT_DECLSPEC sndDevicesStartStopCapture(", 1)[1], (
    "test expects start/stop to be the last exported function"
)
names = (
    "SND_DEVICES_DEVICE_OPERATION_COMPLETED", "SND_DEVICES_GENERIC_FAILURE",
    "SND_DEVICES_NULL_CAPTURE_CLIENT", "SND_DEVICES_NULL_PLAYBACK_CLIENT",
    "SND_DEVICES_START_CAPTURE", "SND_DEVICES_STOP_CAPTURE",
    "SND_DEVICES_CAPTURE_START_FAILED", "SND_DEVICES_PLAYBACK_START_FAILED",
    "SND_DEVICES_CAPTURE_STOP_FAILED", "SND_DEVICES_PLAYBACK_STOP_FAILED",
)
header = HEADER.read_text(encoding="utf-8")
codedefs = (ROOT / "audiopassthru/include/codedefs.h").read_text(encoding="utf-8")
assert re.search(r"^#define OKAY 0$", codedefs, re.M)
assert re.search(r"^#define NOT_OKAY_NO_BREAK 1\b", codedefs, re.M)
definitions = []
for name in names:
    match = re.search(r"^#define\s+" + name + r"\s+(-?\d+)\s*(?:/\*.*)?$", header, re.M)
    assert match, f"missing constant: {name}"
    definitions.append(f"#define {name} {match.group(1)}")

preamble = r"""
#include <windows.h>
#include <cwchar>
#include <cstdio>
using PT_HANDLE = void;
#define PT_DECLSPEC
#define OKAY 0
#define NOT_OKAY_NO_BREAK 1
#define FIRST_LINE 0
struct MockLog { void Message_Wide(int, const wchar_t*) {} };
struct MockClient {
    HRESULT startResult = S_OK, stopResult = S_OK;
    int starts = 0, stops = 0;
    HRESULT Start() { ++starts; return startResult; }
    HRESULT Stop() { ++stops; return stopResult; }
};
struct sndDevicesHdlType {
    MockClient* pAudioClientCapture;
    MockClient* pAudioClientPlayback;
    int stopAudioCaptureAndPlaybackLoop = 0;
    int function_status = 0;
    bool i_trace_on = false;
    MockLog* slout_hdl = nullptr;
};
#define CHECK(expr) do { if (!(expr)) { \
    std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #expr); return 1; \
} } while (false)
"""

tests = r"""
int main() {
    {
        MockClient c, p; sndDevicesHdlType h{&c, &p};
        CHECK(sndDevicesStartStopCapture(reinterpret_cast<PT_HANDLE*>(&h), SND_DEVICES_START_CAPTURE) == OKAY);
        CHECK(c.starts == 1 && p.starts == 1 && c.stops == 0);
        CHECK(h.function_status == SND_DEVICES_DEVICE_OPERATION_COMPLETED && h.stopAudioCaptureAndPlaybackLoop == 0);
        CHECK(sndDevicesStartStopCapture(reinterpret_cast<PT_HANDLE*>(&h), SND_DEVICES_STOP_CAPTURE) == OKAY);
        CHECK(c.stops == 1 && p.stops == 1 && h.stopAudioCaptureAndPlaybackLoop == 1);
    }
    {
        MockClient c, p; c.startResult = E_FAIL; sndDevicesHdlType h{&c, &p};
        CHECK(sndDevicesStartStopCapture(reinterpret_cast<PT_HANDLE*>(&h), SND_DEVICES_START_CAPTURE) == NOT_OKAY_NO_BREAK);
        CHECK(c.starts == 1 && p.starts == 0 && c.stops == 0);
        CHECK(h.function_status == SND_DEVICES_CAPTURE_START_FAILED && h.stopAudioCaptureAndPlaybackLoop == 1);
    }
    for (bool rollbackFails : {false, true}) {
        MockClient c, p; p.startResult = E_FAIL;
        if (rollbackFails) c.stopResult = E_FAIL;
        sndDevicesHdlType h{&c, &p};
        CHECK(sndDevicesStartStopCapture(reinterpret_cast<PT_HANDLE*>(&h), SND_DEVICES_START_CAPTURE) == NOT_OKAY_NO_BREAK);
        CHECK(c.starts == 1 && p.starts == 1 && c.stops == 1);
        CHECK(h.function_status == SND_DEVICES_PLAYBACK_START_FAILED && h.stopAudioCaptureAndPlaybackLoop == 1);
    }
    {
        MockClient c, p; c.stopResult = E_FAIL; sndDevicesHdlType h{&c, &p};
        CHECK(sndDevicesStartStopCapture(reinterpret_cast<PT_HANDLE*>(&h), SND_DEVICES_STOP_CAPTURE) == NOT_OKAY_NO_BREAK);
        CHECK(c.stops == 1 && p.stops == 1 && h.function_status == SND_DEVICES_CAPTURE_STOP_FAILED);
    }
    {
        MockClient c, p; p.stopResult = E_FAIL; sndDevicesHdlType h{&c, &p};
        CHECK(sndDevicesStartStopCapture(reinterpret_cast<PT_HANDLE*>(&h), SND_DEVICES_STOP_CAPTURE) == NOT_OKAY_NO_BREAK);
        CHECK(c.stops == 1 && p.stops == 1 && h.function_status == SND_DEVICES_PLAYBACK_STOP_FAILED);
    }
    {
        MockClient p; sndDevicesHdlType h{nullptr, &p};
        CHECK(sndDevicesStartStopCapture(reinterpret_cast<PT_HANDLE*>(&h), SND_DEVICES_START_CAPTURE) == NOT_OKAY_NO_BREAK);
        CHECK(h.function_status == SND_DEVICES_NULL_CAPTURE_CLIENT && p.starts == 0);
    }
    {
        MockClient c; sndDevicesHdlType h{&c, nullptr};
        CHECK(sndDevicesStartStopCapture(reinterpret_cast<PT_HANDLE*>(&h), SND_DEVICES_START_CAPTURE) == NOT_OKAY_NO_BREAK);
        CHECK(h.function_status == SND_DEVICES_NULL_PLAYBACK_CLIENT && c.starts == 0);
    }
    {
        MockClient c, p; sndDevicesHdlType h{&c, &p};
        CHECK(sndDevicesStartStopCapture(reinterpret_cast<PT_HANDLE*>(&h), 999) == NOT_OKAY_NO_BREAK);
        CHECK(h.function_status == SND_DEVICES_GENERIC_FAILURE && c.starts == 0 && p.starts == 0);
    }
    CHECK(sndDevicesStartStopCapture(nullptr, SND_DEVICES_START_CAPTURE) == NOT_OKAY_NO_BREAK);
    std::puts("PASS: 10 stream start/stop scenarios (actual production function, mocked WASAPI)");
    return 0;
}
"""

# Explicitly include initializer_list for range-for test case.
fixture = preamble.replace("#include <cstdio>", "#include <cstdio>\n#include <initializer_list>")
fixture += "\n".join(definitions) + "\n" + actual_functions + "\n" + tests

vcvars = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat")
assert vcvars.is_file(), f"MSVC x64 tooling unavailable: {vcvars}"
with tempfile.TemporaryDirectory(prefix="fxsound-start-stop-test-") as temp:
    directory = Path(temp)
    cpp, exe, log = directory / "fixture.cpp", directory / "fixture.exe", directory / "compile.log"
    cpp.write_text(fixture, encoding="utf-8")
    batch = directory / "run.cmd"
    batch.write_text(
        "@echo off\n"
        f'call "{vcvars}" >nul\n'
        "if errorlevel 1 exit /b 1\n"
        f'cl /nologo /MT /EHsc /std:c++17 /W4 /utf-8 /Fe:"{exe}" "{cpp}" >"{log}" 2>&1\n'
        "if errorlevel 1 exit /b 1\n"
        f'"{exe}"\n',
        encoding="ascii",
    )
    result = subprocess.run(["cmd.exe", "/d", "/c", "run.cmd"], cwd=directory,
                            capture_output=True, text=True, errors="replace", timeout=120)
    print(result.stdout.strip())
    if result.returncode:
        print(log.read_text(errors="replace") if log.exists() else "No compiler log")
        print(result.stderr)
    if result.returncode == 0:
        import os, shutil
        target = os.environ.get("FXSOUND_EXPORT_TESTS")
        if target:
            Path(target).mkdir(parents=True, exist_ok=True)
            shutil.copy2(exe, Path(target) / "stream-test.exe")
    raise SystemExit(result.returncode)
