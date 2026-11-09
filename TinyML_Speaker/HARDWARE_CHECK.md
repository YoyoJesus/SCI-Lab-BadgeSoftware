# Single-board hardware check

On November 9, 2026, the paper-rule firmware was uploaded to one Nano 33 BLE
Sense Rev2 and captured over BLE on Windows. The environment used Arduino
Mbed Nano core 4.6.0, ArduinoBLE 2.1.0, and Bleak 1.1.1. No trained speaker
model was flashed. Scalar recordings remain in ignored local outputs; they
are not included in the repository.

## Findings and fixes

The initial unpaced sender lost whole BLE packets and failed the capture.
Briefly yielding between data packets improved responsiveness, but short
spacing still lost samples. The tested sender now yields for 12 ms after each
data packet and metadata reply. Only the sender sleeps; high-priority acquisition
and the processing thread continue independently.

Bundled rate/send/clock configuration also timed out during physical tests.
The receiver now sends each as a separate acknowledged write, generating the
UTC anchor after rate and send configuration. USB serial is initialized so
normal upload/reset and diagnostic access remain available.

## Successful checks

Both runs used 200 Hz acquisition, five-second sending, and paper-rule detection.
They completed the STOP/final-drain handshake and disconnected normally.

The first successful 30-second run saved 7,561 rows, including samples buffered
before connection. To exclude connection startup and old backlog, the steady
interval started two seconds after the first host arrival. That interval
contained 5,614 rows over 28.065 seconds of acquisition time: 200.000 samples/s,
zero sequence gaps, and zero increase in the device drop counter.

A fresh one-minute repeat reconnected to the same board after its previous
STOP. Its complete recording contained 12,051 rows over 60.250 seconds of
acquisition time: 200.000 samples/s, zero sequence gaps, and zero new device
drops. The extra acquisition time includes configuration and final-stop latency.
The gyro/magnetometer/humidity/pressure/proximity fields had no missing-value
sentinels in either measured interval.

Rates above are `(rows - 1) / acquisition_span`, calculated from retained device
timestamps. Sequence gaps and changes in `late_samples` were checked separately;
arrival timestamps were not used to infer the acquisition rate.

## Reproduce

After uploading the firmware and selecting the board's advertised BLE address:

```powershell
.\run.bat receive --seconds 60 --recording-id bench_200_hz --rate 200 --send-seconds 5 --raw-only
```

Use `--address` when several badges advertise the service. Check `device_ms`,
`seq_gap`, and `late_samples` in the resulting raw CSV, accounting for any
preconnection backlog when selecting a measurement interval.

This checks one board/adapter combination over a short bench session. It does
not establish multi-board performance, battery life, long-term reliability,
clock accuracy, or speaker-detection accuracy. Generated-model firmware was
compile-checked; its inference behavior has not been tested on a physical board.
