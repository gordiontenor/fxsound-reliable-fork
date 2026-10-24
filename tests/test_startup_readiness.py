"""Compile the actual bounded readiness-polling loop with fake device responses.

No FxSound EXE is started, no audio endpoint or system service is accessed.
Run: python tests/test_startup_readiness.py
"""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "audiopassthru/src/sndDevices/sndDevicesReInit.cpp").read_text(encoding="utf-8")
header = (ROOT / "audiopassthru/include/sndDevices.h").read_text(encoding="utf-8")
limit_match = re.search(r"^#define SND_DEVICES_STARTUP_DEVICE_MAX_POLLS\s+(\d+)", header, re.M)
assert limit_match, "bounded startup polling policy missing"
limit = int(limit_match.group(1))
assert 20 < limit <= 60, "unexpected startup bound"

begin = text.index("\t\tloopCount = 0;", text.index("int PT_DECLSPEC sndDevicesReInit("))
end_marker = "while( resultFlag != SND_DEVICES_DEVICE_OPERATION_COMPLETED );"
end = text.index(end_marker, begin) + len(end_marker)
production_loop = text[begin:end]

source = r"""
#include <windows.h>
#include <cstdio>
#include <cwchar>
using PT_HANDLE = void;
#define OKAY 0
#define NOT_OKAY -1
#define IS_TRUE 1
#define IS_FALSE 0
#define SND_DEVICES_DEVICE_OPERATION_COMPLETED 0
#define SND_DEVICES_DEVICE_NOT_PRESENT -2
#define SND_DEVICES_INIT_FOR_PROCESSING 1
#define SND_DEVICES_INIT_NO_PROCESSING 2
#define SND_DEVICES_VIRTUAL_PLAYBACK_DFX 3
#define SND_DEVICES_STARTUP_DEVICE_MAX_POLLS """ + str(limit) + r"""
struct sndDevicesHdlType {
 int totalNumDevices = 0;
 int numRealDevices = 1;
 int function_status = 0;
};
int g_polls = 0;
int g_virtualReadyAt = 1;
int g_enumerateFailureAt = 0;
int g_nameFailureAt = 0;
int g_simulatedMs = 0;
#define Sleep(ms) (g_simulatedMs += (ms))
int sndDevices_GetAll(PT_HANDLE *, int *count) {
 ++g_polls;
 *count = 2;
 return g_polls == g_enumerateFailureAt ? NOT_OKAY : OKAY;
}
int sndDevicesGetFriendlyName(PT_HANDLE *, int, wchar_t *name, int *status) {
 if (g_polls == g_nameFailureAt) return NOT_OKAY;
 *status = g_polls >= g_virtualReadyAt
    ? SND_DEVICES_DEVICE_OPERATION_COMPLETED : SND_DEVICES_DEVICE_NOT_PRESENT;
 name[0] = 0;
 return OKAY;
}
int StartupPoll(PT_HANDLE *hp_sndDevices, int i_initType, int *ipNumRealDevices,
  int *ipDfxDeviceEnabledFlag, int *ip_status) {
 auto *cast_handle = (sndDevicesHdlType *)hp_sndDevices;
 int loopCount = 0, resultFlag = 0;
 wchar_t name[128] = {};
 *ipDfxDeviceEnabledFlag = IS_TRUE;
 *ip_status = SND_DEVICES_DEVICE_OPERATION_COMPLETED;
""" + production_loop + r"""
 return OKAY;
}
#define CHECK(x) do { if(!(x)) { std::fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);return 1; } } while(0)
void Reset(int ready, int enumFail=0, int nameFail=0) {
 g_polls = 0;g_virtualReadyAt=ready;g_enumerateFailureAt=enumFail;
 g_nameFailureAt=nameFail;g_simulatedMs=0;
}
int main() {
 sndDevicesHdlType h;
 int real = 0, enabled = 0, status = 0;
 PT_HANDLE *handle = reinterpret_cast<PT_HANDLE *>(&h);
 Reset(1);
 CHECK(StartupPoll(handle,SND_DEVICES_INIT_FOR_PROCESSING,&real,&enabled,&status)==OKAY);
 CHECK(g_polls==1 && enabled==IS_TRUE && status==0 && g_simulatedMs==50);
 Reset(31); h.function_status=0;
 CHECK(StartupPoll(handle,SND_DEVICES_INIT_FOR_PROCESSING,&real,&enabled,&status)==OKAY);
 CHECK(g_polls==31 && enabled==IS_TRUE && status==0 && g_simulatedMs==1550);
 Reset(SND_DEVICES_STARTUP_DEVICE_MAX_POLLS); h.function_status=0;
 CHECK(StartupPoll(handle,SND_DEVICES_INIT_FOR_PROCESSING,&real,&enabled,&status)==OKAY);
 CHECK(g_polls==SND_DEVICES_STARTUP_DEVICE_MAX_POLLS && enabled==IS_TRUE && status==0);
 Reset(SND_DEVICES_STARTUP_DEVICE_MAX_POLLS+1); h.function_status=0;
 CHECK(StartupPoll(handle,SND_DEVICES_INIT_FOR_PROCESSING,&real,&enabled,&status)==OKAY);
 CHECK(g_polls==SND_DEVICES_STARTUP_DEVICE_MAX_POLLS && g_simulatedMs==3000);
 CHECK(enabled==IS_FALSE && status==SND_DEVICES_DEVICE_NOT_PRESENT && h.function_status==status);
 Reset(2,1); h.function_status=0;
 CHECK(StartupPoll(handle,SND_DEVICES_INIT_FOR_PROCESSING,&real,&enabled,&status)==NOT_OKAY);
 CHECK(g_polls==1);
 Reset(2,0,1); h.function_status=0;
 CHECK(StartupPoll(handle,SND_DEVICES_INIT_FOR_PROCESSING,&real,&enabled,&status)==NOT_OKAY);
 CHECK(g_polls==1);
 std::puts("PASS: 6 readiness cases (production loop, mock devices and simulated time)");
 return 0;
}
"""
vcvars = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat")
assert vcvars.is_file()
with tempfile.TemporaryDirectory(prefix="fxsound-startup-readiness-") as directory:
    root = Path(directory)
    cpp, exe, log, bat = (root / name for name in ("test.cpp", "test.exe", "compiler.log", "run.cmd"))
    cpp.write_text(source, encoding="utf-8")
    bat.write_text(
        "@echo off\n"
        f'call "{vcvars}" >nul\n'
        "if errorlevel 1 exit /b 1\n"
        f'cl /nologo /EHsc /std:c++17 /W4 /utf-8 /Fe:"{exe}" "{cpp}" >"{log}" 2>&1\n'
        "if errorlevel 1 exit /b 1\n"
        f'"{exe}"\n',
        encoding="ascii",
    )
    result = subprocess.run(["cmd.exe", "/d", "/c", "run.cmd"], cwd=root,
                            capture_output=True, text=True, errors="replace", timeout=90)
    print(result.stdout.strip())
    if result.returncode:
        print(result.stderr.strip())
        if log.exists():
            print(log.read_text(errors="replace")[-3000:].encode("ascii", "backslashreplace").decode("ascii"))
    raise SystemExit(result.returncode)
