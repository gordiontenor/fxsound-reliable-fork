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

Next narrow investigation: `FxController::initConfig()` accepts `--power=1`, but `FxController::setPowerState()` forces power off if `dfx_enabled_` is false or Windows reports a remote session. A read-only session check returned `SM_REMOTESESSION=0`, making a failed virtual-device initialization worth investigating first, but not proven. Compare the fork's cold-start `sndDevicesInit` / `initOutputs` path with the upstream baseline and inspect the service-hang report if available. Then perform separately controlled acceptance of audible Focusrite output, reconnect, and stability. Do not ship before that test passes.
