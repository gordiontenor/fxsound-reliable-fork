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

Two additional observations are intentionally **not** patched without stronger evidence:

- `Main.cpp` calls `CoInitializeEx(..., COINIT_MULTITHREADED)`, while `sndDevicesInit.cpp` subsequently calls `CoInitialize(NULL)` and ignores its return code. An audio-free COM probe confirmed the sequence on an MTA thread returns `RPC_E_CHANGED_MODE (0x80010106)` for the latter call. This does **not** prove the audio-service hang.
- `sndDevicesReInit` can return `OKAY` with `ipDfxDeviceEnabledFlag=false` after approximately one second without finding the virtual device. `initOutputs` and `setPowerState` can then leave processing disabled. This is a plausible explanation for `--power=1` not taking effect, but no live HRESULT/log has yet established the actual cause on this computer.

**No host audio test or FXVAD/Focusrite driver change was performed for this isolated inspection.** The previous live acceptance remains blocked pending controlled investigation of Windows Audio service hang. Do not interpret passing mock tests or a successful build as audible-output acceptance.
