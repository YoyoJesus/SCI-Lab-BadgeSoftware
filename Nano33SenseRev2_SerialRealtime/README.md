# Nano 33 BLE Sense Rev2 — serial badge and live viewer

This folder is self-contained: it has Rev2 firmware and a Windows live-data dashboard.

## What changed from the supplied sketch

- Uses the Rev2 sensor libraries: `Arduino_BMI270_BMM150` and `Arduino_HS300x`.
- USB serial streams continuously; a BLE connection is no longer required.
- BLE Nordic UART streaming is retained as an optional second output.
- The sample rate is adjustable at runtime from 1–25 Hz.
- The microphone calculation uses RMS without overflowing a 32-bit accumulator.
- Serial output is fixed-column CSV so the viewer can parse it reliably.

## Upload in Arduino IDE

1. Connect the Nano 33 BLE Sense Rev2 with a **data-capable** USB cable.
2. Open `firmware/Nano33SenseRev2_Badge/Nano33SenseRev2_Badge.ino`.
3. In Library Manager, install `Arduino_HS300x` if it is not already installed.
4. Select **Tools > Board > Arduino Mbed OS Nano Boards > Arduino Nano 33 BLE**.
   Arduino uses this board entry for both Sense revisions; the included sensor libraries make the sketch Rev2-specific.
5. Select the Nano's USB COM port under **Tools > Port**, then click Upload.
6. Close Arduino Serial Monitor before starting the viewer. Only one program can own the COM port at a time.

If the USB COM port does not appear, use a different data-capable cable or double-press RESET to enter the bootloader. A temporary bootloader COM port should appear; select it and upload.

## Run the live viewer

Python dependencies are `pyserial` and `matplotlib`. On this machine they are already installed.

Double-click `run_viewer.bat`, or run:

```powershell
py realtime_viewer.py
```

Then select the Arduino USB port and click **Connect**.

- **Device send rate** changes how often the board samples and transmits (1–25 Hz). Move the control, then click **Apply**.
- **Plot refresh** changes how often the computer redraws the graphs (1–30 Hz). Serial data is still drained continuously so the port does not back up.
- **Visible seconds** controls the time window.
- **Start CSV recording** saves every received sample, independent of the plot refresh speed.

The baud setting is 115200. On this board's native USB serial connection it is a compatibility value; sample rate and plot refresh are the meaningful speed controls.

## Serial protocol

Commands are newline-terminated:

```text
RATE 20
STREAM ON
STREAM OFF
STATUS
HELP
```

Samples begin with `DATA,`; startup/status lines begin with `INFO,`, `HEADER,`, `STATUS,`, `OK,`, or `ERROR,`.
