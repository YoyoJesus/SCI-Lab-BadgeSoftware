# Nano 33 BLE Sense Rev2 — serial badge and live viewer

This folder is self-contained: it has Rev2 firmware and a Windows live-data dashboard supporting USB serial and Bluetooth LE.

## What changed from the supplied sketch

- Uses the Rev2 sensor libraries: `Arduino_BMI270_BMM150` and `Arduino_HS300x`.
- Streams every onboard sensing function: accelerometer, gyroscope, magnetometer,
  microphone level, temperature, humidity, pressure, proximity, RGB color,
  ambient/clear light, and gesture direction, plus external GSR and BLE RSSI.
- USB serial streams continuously; a BLE connection is no longer required.
- BLE Nordic UART streaming is retained as an optional second output.
- The sample rate is adjustable at runtime from 1–200 Hz.
- Sampling and sending are independent. Samples are taken on a microsecond
  schedule into a 512-sample buffer. The buffer is sent at a chosen interval
  (0–5000 ms), or after every sample.
- Slow sensors (GSR, magnetometer, environment, light, gesture, RSSI) are polled
  in the background without blocking. Every sample carries their latest value, so
  only the accelerometer and gyroscope are read at the full sample rate.
- The I²C bus runs at 400 kHz. When the rate is above 100 Hz, the BMI270
  accelerometer/gyroscope data rate is raised from 100 Hz to 200 Hz.
- The microphone calculation uses RMS without overflowing a 32-bit accumulator.
- Serial output is fixed-column CSV so the viewer can parse it reliably. Each row
  ends with a sequence number, so dropped samples can be detected.

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

Python dependencies are `pyserial`, `matplotlib`, and `bleak`. On this machine they are already installed.

On another computer, install them once with:

```powershell
py -m pip install -r requirements.txt
```

Double-click `run_viewer.bat`, or run:

```powershell
py realtime_viewer.py
```

For USB, select **USB Serial**, choose the Arduino COM port, and click **Connect**.

For wireless use, leave the board powered by USB or a battery, select **Bluetooth LE**, and click **Refresh**. Choose `HM Badge No.01` after the five-second scan and click **Connect**. The dashboard subscribes to the Nordic UART TX characteristic and sends rate commands through its RX characteristic; Windows pairing is not required.

- **Device sample rate** sets how often the board samples (1–200 Hz).
- **Send every (ms)** sets how often the board sends its buffered samples.
  Use `0` to send each sample as soon as it is taken. Longer intervals send
  samples in bursts, which helps BLE keep up. Every sample keeps its own
  timestamp, so batching does not reduce resolution. Set both controls, then click **Apply**.
  The viewer also applies both settings when it connects.
- **Plot refresh** changes how often the computer redraws the graphs (1–30 Hz). Serial data is still drained continuously so the port does not back up.
- **Visible seconds** controls the time window. Long windows at high rates are
  thinned to about 2,000 points per chart for drawing. CSV recording keeps every sample.
- The status bar shows the measured sample rate (from the board's timestamps) and
  how many samples were dropped (from gaps in the sequence number).
- **Start CSV recording** saves every received sample, independent of the plot refresh speed.
- **Visible sensor charts** lets you independently show or hide any measurement.
  The viewer includes individual motion axes, vector magnitudes, estimated altitude
  derived from pressure, RGB/ambient light, gesture direction, and the other raw fields.

BLE notifications use the same `DATA,...` rows as USB, so graphing, chart selection,
and CSV recording behave identically on both transports. Each notification carries
as many complete newline-separated rows as fit in 220 bytes.

### Choosing high rates

- USB handles 200 Hz comfortably. Use USB for 100 Hz and faster.
- BLE throughput depends on the computer's Bluetooth adapter and radio
  conditions. If the dropped count rises, lower the rate or increase the send interval.
- GSR is sampled at about 22 Hz, and magnetometer, pressure, and light update
  at 10–50 Hz. At higher rates these columns repeat their latest value. Sound is
  RMS over roughly 8 ms blocks of microphone audio.
- The buffer holds 512 samples. At 200 Hz that is about 2.5 s, so a longer send
  interval sends early when the buffer fills.

The baud setting is 115200. On this board's native USB serial connection it is a compatibility value; sample rate and plot refresh are the meaningful speed controls.

## Serial protocol

Commands are newline-terminated:

```text
RATE 100      sample rate, 1..200 Hz
SEND 50       send interval, 0..5000 ms (0 = send every sample immediately)
STREAM ON
STREAM OFF
STATUS        includes buffered and dropped sample counts
HELP
```

Samples begin with `DATA,`; startup/status lines begin with `INFO,`, `HEADER,`, `STATUS,`, `OK,`, or `ERROR,`.

```text
DATA,time_ms,sound,ax,ay,az,gx,gy,gz,mx,my,mz,temp_c,humidity_pct,pressure_kpa,
     proximity,red,green,blue,ambient,gesture,gsr,rssi,seq
```

`time_ms` is the time the sample was taken, not when it was sent. The viewer
still reads rows from older firmware without `seq`.

Gesture values are `-1=none`, `0=up`, `1=down`, `2=left`, and `3=right`.
