# FxSound reliable-audio fork — first milestone

This fork is based on upstream `v1.2.16.0` at `37463e50a1ac3cda3baff8445a6070a37bf495e4` and retains the upstream AGPL-3.0 license and attribution.

## Goal and current limitation

The first goal is reliable audio from the FxSound virtual endpoint through the Audiopassthru engine to a physical Focusrite USB Audio endpoint. On the observed Windows host, the real Focusrite endpoint carries direct audio, but the upstream FxSound path can accept signal and remain silent at the physical endpoint.

This milestone does **not** establish that the end-to-end silence bug is fixed. It closes demonstrable silent-failure paths and creates a safe baseline for diagnosis. The installed FxSound executable, FXVAD driver, and Focusrite driver have not been replaced. A short live test temporarily selected the FxSound endpoint, then restored all three Windows default render roles to Focusrite and verified the original FxSound settings against a backup.

## Changes in this branch

- Check capture and playback `IAudioClient::Start()` results independently. Do not overwrite or silently ignore a failed HRESULT.
- On playback-start failure, stop the capture client that was already started. Report rollback failure separately without concealing the original playback-start error.
- Check both stop operations, attempting both even if capture stop fails, and reject absent clients or invalid operation flags.
- Record distinct internal status codes and the original HRESULT in the Windows debug output. Stream errors use `NOT_OKAY_NO_BREAK` rather than the existing modal-dialog `NOT_OKAY` macro; they should not block automatic retries behind a message box.
- When a processing thread fails, use automatic bounded exponential retry delay (1, 2, 4, 8, then 16 seconds), rather than reinitializing the audio stack on every timer tick. Reset the failure count after 15 seconds of uninterrupted thread activity. The upstream no-device sentinel remains in place.

## Evidence and commands

From this repository root:

```powershell
python tests/test_stream_start_stop.py
& 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\MSBuild\Current\Bin\MSBuild.exe' audiopassthru\audiopassthru.vcxproj /t:Build /p:Configuration=Release /p:Platform=x64 /m:2 /v:minimal /nologo
& 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\MSBuild\Current\Bin\MSBuild.exe' audiopassthru\audiopassthru.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /m:2 /v:minimal /nologo
```

The test compiles the **actual production function** extracted from `sndDevicesDoCapture.cpp` with mock audio clients and checks startup, rollback, shutdown and invalid inputs. It does not open a live audio endpoint. The Audiopassthru x64 static library builds in both configurations.

## Full application build and targeted diagnostic

JUCE 6.1.6 is pinned to official tag commit `2f980209cc4091a4490bb1bafc5d530f16834e58` at `.local/JUCE-6.1.6` (gitignored). Install it with `git clone --depth 1 --branch 6.1.6 https://github.com/juce-framework/JUCE.git .local/JUCE-6.1.6`, then verify that commit hash. The fork's x64 project uses this relative path; no global `C:\JUCE6` directory or Java setting was changed. The full Release/x64 solution builds and produces `bin/x64/FxSound.exe`.

When explicitly launched with environment variable `FXSOUND_AUDIO_DIAG=1`, the processing thread records one bounded per-second summary at `%TEMP%\fxsound-fork-audio-diagnostic.log`: CAP captured frames/sample peak, DSP processed frames/sample peak/status, and PLAY queued frame count. Queueing is not proof of audible sound. Logging is disabled by default.

## Live acceptance: BLOCKED (2026-10-24)

A short host test started the isolated unsigned fork, but it never produced a CAP/DSP/PLAY diagnostic record. A tone test timed out; zero audio meter values must not be interpreted as a reliable DSP result. In a subsequent startup-only test the fork window eventually responded, but processing power was not observed to enable. Windows Event Log recorded an `Application Hang` of `svchost.exe` (Event 1002) and unexpected Windows Audio `Audiosrv` termination (System Event 7031) at **17:10:12**. The fork had started several seconds before; causality is not yet proven. Windows automatically recovered the service. The fork was stopped and all three Windows default render roles were verified back at direct Focusrite; the saved FxSound settings and installed EXE hash matched their pre-test copies.

**Stop condition:** Do not repeat the unsigned fork live on the host or replace the installed application until the startup/audio-service hang has been understood in an isolated environment. No driver changes, AV exclusions, or further DSP changes are justified from this evidence.

## Isolated startup inspection (no audio device opened)

The cold-start sequence is `Main::initialise → FxController::init → AudioPassthru::init → sndDevicesInit → sndDevicesReInit → sndDevicesImplementDeviceRules → initOutputs → setPowerState`. This sequence is **not passive**: device rules can request that Windows select the FxSound virtual endpoint before final capture/playback setup has finished.

Two concrete error-handling bugs were found and fixed on this development branch:

- `sndDevicesSetDeviceType(SND_DEVICES_DEFAULT)` previously ignored `IPolicyConfigVista::SetDefaultEndpoint`'s HRESULT and updated its internal default index even when Windows rejected the switch. It now returns failure and preserves the previous index on rejected Windows switches and policy-creation errors. `tests/test_startup_endpoint.py` compiles the **production switch case** with a fake policy object, never opens a Windows audio device, and checks success, rejected switch and policy-creation failure (3/3 passing after fix; baseline failed on rejected switch).
- `sndDevices_GetAll()` called `pDefaultDevice->GetId` without assigning its result to `hr` and then tested an earlier HRESULT. It now captures and checks the correct value. The test includes a source-level regression guard for this assignment.

## Narrow follow-up: COM and delayed virtual endpoint

- `Main.cpp` initializes its UI thread with `CoInitializeEx(..., COINIT_MULTITHREADED)`. `sndDevicesInit.cpp` previously called `CoInitialize(NULL)` on the same thread, requesting STA, ignoring `RPC_E_CHANGED_MODE (0x80010106)` and confusing COM apartment ownership. It now requires an already initialized caller-owned COM context using `CoGetContextToken`, reports an uninitialized thread as an explicit error, and never changes/unbalances the caller's apartment. `tests/test_startup_com.py` uses two independent audio-free Windows threads to verify the MTA/STA context contract (2/2).
- `sndDevicesReInit` previously gave up after about 1 second and returned `OKAY` without a distinct not-ready status. It now allows up to 60 bounded 50 ms polls (nominally 3 seconds); an endpoint appearing on the 60th poll succeeds. If absent, it sets both the output status and the handle status to `SND_DEVICES_DEVICE_NOT_PRESENT` while disabling the virtual device; the failure is explicit rather than silently reported as a successful discovery. Recovery after this timeout is **not** yet proven at the GUI level. `tests/test_startup_readiness.py` compiles the **production polling loop**, substitutes mock device responses and virtual time, and checks six success/not-ready/error cases (6/6).

All isolated tests: COM 2/2, startup readiness 6/6, endpoint switch 3/3, stream start/stop 10/10 (21/21). The full Release/x64 solution builds.

**Evidence limit:** Neither the COM mismatch nor the short wait has been proven to cause the 17:10:12 Windows Audio service hang. The fixes close two concrete startup problems; no real Focusrite audible-output acceptance has been run. No installed FxSound executable, default audio device, FXVAD/Focusrite driver or Windows Audio service was changed by these follow-up tests. Do not retry the live host fork or ship it before a separately controlled investigation/acceptance.

## Host-audio-safe next change (2026-10-24)

After the host experienced a complete speaker/microphone interruption and the user restored Windows Audio, **live host testing remains prohibited**. The startup default-device switch was previously performed in `sndDevicesImplementDeviceRules` before capture and physical playback client initialization. If either client failed later, Windows could remain pointed to a nonfunctional FxSound virtual output. The fork now defers the automatic default-output switch to the very end of the successful `sndDevicesReInit` path, after both final setup calls, their status checks, volume synchronization and buffer initialization. Automatic-selection-off continues to skip the switch; a rejected switch is reported as a failure and does not activate processing. The existing `tests/test_startup_endpoint.py` verifies actual endpoint-switch error handling, while `tests/test_deferred_default_routing.py` enforces the source ordering without opening audio devices. All previous COM, readiness and stream-start tests still pass. The full Release/x64 solution builds, but the EXE has not been launched.

This patch reduces one concrete early-routing hazard, **not** the possibility of every Windows Audio hang. The only next acceptance path is a disposable/isolated audio test environment and an explicit recovery plan; do not test against the working host's default speaker or microphone.

## Windows Sandbox acceptance evidence (2026-10-24)

The isolated test package lives locally at `H:\FxSound-Isolated-20261024`. The input share was mapped **read-only** into a disposable Windows Sandbox; the separate results folder was its only read-write host mapping. Networking, virtualized GPU, microphone, camera, clipboard and printer sharing were disabled. The guest verified that it was `WDAGUtilityAccount` and that the physical host's H: path was not visible. The test used the exact fork EXE with SHA-256 `6A33CC405A8237A434634B43E84031007494AA7D57BC9A60FB94E489EBF6752B`.

In the guest, executable fixtures compiled from production functions with fake COM/WASAPI objects all passed: readiness **6/6**, endpoint switch **3/3**, stream start/stop **10/10**. The three Python fixture-build scripts now support opt-in `FXSOUND_EXPORT_TESTS` output and compile portable `/MT` test EXEs so an isolated guest needs no compiler or source checkout.

The guest had **no FxSound virtual driver**. Launching the actual fork EXE with `--power=0` for eight seconds in that guest left its process **running and responsive**; the test stopped only that guest process afterwards. Both guest audio services remained Running, Windows default output IDs were identical before/after, and no guest audio-service termination event (7031/7034) was observed. This shows a bounded **no-driver startup safety check**, not processing success, absence of every UI error, or audible playback.

Evidence: `H:\FxSound-Isolated-20261024\results\result.json` and `progress.log`. The disposable guest shut down; `wsb list --raw` returned no running sandboxes. Host `Audiosrv` and `AudioEndpointBuilder` were Running, host FxSound process count was zero, the installed signed FxSound EXE hash was unchanged and no new host audio-service termination events were found during the test interval.

**Remaining gate:** No FXVAD or Focusrite processing acceptance has been demonstrated inside a separate guest. Do not replace/install the fork or switch the host default audio device.
