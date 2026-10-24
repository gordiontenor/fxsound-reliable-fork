"""Isolated test of the *production* default-endpoint switch branch.

Extracts the SND_DEVICES_DEFAULT case verbatim from sndDevicesSet.cpp, replacing
only CoCreateInstance with a fake factory. No Windows audio interfaces are opened.
Run: python tests/test_startup_endpoint.py
"""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "audiopassthru/src/sndDevices/sndDevicesSet.cpp"
source = SOURCE.read_text(encoding="utf-8")
start = source.index("\tcase SND_DEVICES_DEFAULT :")
stop = source.index("\n\tdefault:", start)
branch = source[start:stop]
branch, substitutions = re.subn(
    r"CoCreateInstance\(__uuidof\(CPolicyConfigVistaClient\), NULL, CLSCTX_ALL,\s*"
    r"__uuidof\(IPolicyConfigVista\), \(LPVOID \*\)&pPolicyConfig\)",
    "MockCreate(&pPolicyConfig)", branch
)
assert substitutions == 1, "unexpected production branch shape"

# Separate source contract: GetId's HRESULT must be assigned before testing it.
get_all = (ROOT / "audiopassthru/src/sndDevices/sndDevices_GetAll.cpp").read_text(encoding="utf-8")
assert re.search(r"hr\s*=\s*pDefaultDevice->GetId\(&pwszIDdefault\);\s*if\s*\(FAILED\(hr\)\)", get_all), (
    "default endpoint GetId must check its own HRESULT, not an earlier COM result"
)

test_source = r"""
#include <windows.h>
#include <cstdio>
#define OKAY 0
#define NOT_OKAY_NO_BREAK 1
#define SND_DEVICES_DEFAULT 1
#define SND_DEVICES_DEVICE_OPERATION_COMPLETED 0
#define SND_DEVICES_DEVICE_NOT_PRESENT -2
#define SND_DEVICES_PROPERTY_SET_FAILED -3
#define SND_DEVICES_INSTANCE_CREATE_FAILED -16
#define SND_DEVICES_SET_STATUS_AND_RETURN_OK(status) {cast_handle->function_status = status;return OKAY;}
struct FakePolicy {
    HRESULT result = S_OK;
    int calls = 0, releases = 0;
    HRESULT SetDefaultEndpoint(const wchar_t*, int) { ++calls; return result; }
    unsigned long Release() { ++releases; return 0; }
};
struct Handle {
    wchar_t pwszID[2][40] = {L"previous", L"new"};
    int priorDefaultDeviceNum = -1, defaultDeviceNum = 0, function_status = 0;
};
FakePolicy g_policy;
HRESULT g_createResult = S_OK;
HRESULT MockCreate(FakePolicy** policy) {
    if (SUCCEEDED(g_createResult)) *policy = &g_policy;
    return g_createResult;
}
int TestSwitch(Handle& handle, int& status) {
    Handle* cast_handle = &handle;
    FakePolicy* pPolicyConfig = nullptr;
    HRESULT hr = S_OK;
    int* ip_resultFlag = &status;
    int device_index_num = 1, reserved = 0;
    switch (SND_DEVICES_DEFAULT) {
""" + branch + r"""
    default: return -99;
    }
    return -98;
}
#define CHECK(x) if (!(x)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); return 1; }
int main() {
  {
    Handle h; int status = 0; g_createResult = S_OK; g_policy = FakePolicy{};
    int r = TestSwitch(h, status);
    CHECK(r == OKAY && status == 0 && h.defaultDeviceNum == 1 && h.priorDefaultDeviceNum == 0);
    CHECK(g_policy.calls == 1 && g_policy.releases == 1);
  }
  {
    Handle h; int status = 0; g_createResult = S_OK; g_policy = FakePolicy{}; g_policy.result = E_FAIL;
    int r = TestSwitch(h, status);
    CHECK(r != OKAY && status != 0);
    CHECK(h.defaultDeviceNum == 0 && h.priorDefaultDeviceNum == -1);
    CHECK(g_policy.calls == 1 && g_policy.releases == 1);
  }
  {
    Handle h; int status = 0; g_createResult = E_FAIL; g_policy = FakePolicy{};
    int r = TestSwitch(h, status);
    CHECK(r != OKAY && status != 0);
    CHECK(h.defaultDeviceNum == 0 && h.priorDefaultDeviceNum == -1);
    CHECK(g_policy.calls == 0);
  }
  std::puts("PASS: 3 isolated endpoint switch scenarios (production branch, fake policy)");
}
"""
vcvars = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat")
with tempfile.TemporaryDirectory(prefix="fxsound-endpoint-test-") as folder:
    folder = Path(folder)
    cpp, exe, log, bat = (folder / name for name in ("test.cpp", "test.exe", "compiler.log", "run.cmd"))
    cpp.write_text(test_source, encoding="utf-8")
    bat.write_text(
        "@echo off\n"
        f'call "{vcvars}" >nul\n'
        "if errorlevel 1 exit /b 1\n"
        f'cl /nologo /MT /EHsc /std:c++17 /W4 /utf-8 /Fe:"{exe}" "{cpp}" >"{log}" 2>&1\n'
        "if errorlevel 1 exit /b 1\n"
        f'"{exe}"\n',
        encoding="ascii",
    )
    result = subprocess.run(["cmd.exe", "/d", "/c", "run.cmd"], cwd=folder,
                            capture_output=True, text=True, errors="replace", timeout=90)
    print(result.stdout.strip())
    if result.returncode:
        print(result.stderr.strip())
        if log.exists():
            print(log.read_text(errors="replace")[-2200:].encode("ascii", "backslashreplace").decode("ascii"))
    if result.returncode == 0:
        import os, shutil
        target = os.environ.get("FXSOUND_EXPORT_TESTS")
        if target:
            Path(target).mkdir(parents=True, exist_ok=True)
            shutil.copy2(exe, Path(target) / "endpoint-test.exe")
    raise SystemExit(result.returncode)
