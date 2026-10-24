# FxSound reliable-audio fork — first milestone

This fork is based on upstream `v1.2.16.0` at `37463e50a1ac3cda3baff8445a6070a37bf495e4` and retains the upstream AGPL-3.0 license and attribution.

## Goal and current limitation

The first goal is reliable audio from the FxSound virtual endpoint through the Audiopassthru engine to a physical Focusrite USB Audio endpoint. On the observed Windows host, the real Focusrite endpoint carries direct audio, but the upstream FxSound path can accept signal and remain silent at the physical endpoint.

This milestone does **not** establish that the end-to-end silence bug is fixed. It closes demonstrable silent-failure paths and creates a safe baseline for diagnosis. No installed FxSound binaries, default devices, FXVAD driver, or Focusrite driver have been changed.

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

## Required acceptance before testing as a replacement

1. Build an isolated full executable with a verified JUCE 6.1.6 dependency. The upstream solution currently references `C:\JUCE6\modules`, which is not installed on the observed host. No system-wide JUCE path has been created.
2. Add bounded capture/DSP/playback counters and structured HRESULT logging to identify the first silent stage.
3. Use a disposable audio test environment or explicit operator-approved, rollback-ready live test. Keep the working direct Focusrite path available.
4. Verify audible playback, device reconnect and repeated-start stability, plus handle, memory and CPU trends. No distribution or replacement of upstream FxSound before these pass.
