"""Live USB serial and Bluetooth LE dashboard for the Nano badge."""

from __future__ import annotations

import asyncio
import csv
import math
import queue
import struct
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import matplotlib

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
import serial
from serial.tools import list_ports


FIELDS = [
    "time_ms", "sound", "ax", "ay", "az", "gx", "gy", "gz",
    "mx", "my", "mz", "temp_c", "humidity_pct", "pressure_kpa",
    "proximity", "red", "green", "blue", "ambient", "gesture", "gsr", "rssi", "seq",
]

# Firmware before the high-rate sampler did not send seq; the original
# firmware also lacked ambient and gesture.
UNSEQUENCED_FIELDS = FIELDS[:-1]
LEGACY_FIELDS = [field for field in UNSEQUENCED_FIELDS if field not in {"ambient", "gesture"}]
KNOWN_LAYOUTS = {len(layout): layout for layout in (FIELDS, UNSEQUENCED_FIELDS, LEGACY_FIELDS)}

MAX_RATE_HZ = 200
MAX_SEND_INTERVAL_MS = 5000
MAX_WINDOW_SECONDS = 300
# Lines are decimated to about this many points so drawing stays fast at high
# sample rates; CSV recording always keeps every sample.
MAX_PLOT_POINTS = 2000

NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
TRANSPORT_USB = "USB Serial"
TRANSPORT_BLE = "Bluetooth LE"

PLOT_OPTIONS = (
    ("gsr", "GSR", "0–255", True),
    ("sound", "Sound", "RMS", True),
    ("accel_mag", "Acceleration magnitude", "g", True),
    ("ax", "Acceleration X", "g", False),
    ("ay", "Acceleration Y", "g", False),
    ("az", "Acceleration Z", "g", False),
    ("gyro_mag", "Gyroscope magnitude", "dps", False),
    ("gx", "Gyroscope X", "dps", False),
    ("gy", "Gyroscope Y", "dps", False),
    ("gz", "Gyroscope Z", "dps", False),
    ("mag_mag", "Magnetic magnitude", "µT", False),
    ("mx", "Magnetic X", "µT", False),
    ("my", "Magnetic Y", "µT", False),
    ("mz", "Magnetic Z", "µT", False),
    ("temp_c", "Temperature", "°C", True),
    ("humidity_pct", "Humidity", "%", False),
    ("pressure_kpa", "Pressure", "kPa", False),
    ("altitude_m", "Estimated altitude", "m", False),
    ("proximity", "Proximity", "0–255", False),
    ("ambient", "Ambient light", "clear counts", False),
    ("red", "Red light", "counts", False),
    ("green", "Green light", "counts", False),
    ("blue", "Blue light", "counts", False),
    ("gesture", "Gesture", "direction", False),
    ("rssi", "BLE signal strength", "dBm", False),
)


def parse_data_line(line: str) -> dict[str, float]:
    """Parse one firmware DATA line and calculate derived plot values."""
    if not line.startswith("DATA,"):
        raise ValueError("not a DATA line")
    parts = line.split(",")[1:]
    field_names = KNOWN_LAYOUTS.get(len(parts))
    if field_names is None:
        expected = ", ".join(str(count) for count in sorted(KNOWN_LAYOUTS, reverse=True))
        raise ValueError(f"expected {expected} fields, received {len(parts)}")
    sample: dict[str, float] = {}
    for name, value in zip(field_names, parts):
        try:
            sample[name] = float(value)
        except ValueError:
            sample[name] = math.nan
    for name in FIELDS:
        sample.setdefault(name, math.nan)
    return add_derived_fields(sample)


def add_derived_fields(sample: dict[str, float]) -> dict[str, float]:
    sample["accel_mag"] = math.sqrt(
        sample["ax"] ** 2 + sample["ay"] ** 2 + sample["az"] ** 2
    )
    sample["gyro_mag"] = math.sqrt(
        sample["gx"] ** 2 + sample["gy"] ** 2 + sample["gz"] ** 2
    )
    sample["mag_mag"] = math.sqrt(
        sample["mx"] ** 2 + sample["my"] ** 2 + sample["mz"] ** 2
    )
    pressure = sample["pressure_kpa"]
    sample["altitude_m"] = (
        44330.0 * (1.0 - (pressure / 101.325) ** 0.1903)
        if math.isfinite(pressure) and pressure > 0
        else math.nan
    )
    return sample


BLE_PACKET_TYPE = 0x01
BLE_HEADER = struct.Struct("<BBII3hhHIB4HbBb")
BLE_SAMPLE = struct.Struct("<3H6h")


def _signed(raw: int, scale: float) -> float:
    return math.nan if raw == -0x8000 else raw / scale


def _unsigned(raw: int, scale: float, missing: int) -> float:
    return math.nan if raw == missing else raw / scale


def parse_ble_packet(data: bytes) -> list[dict[str, float]]:
    """Unpack one binary BLE notification into DATA-equivalent samples."""
    if len(data) < BLE_HEADER.size or data[0] != BLE_PACKET_TYPE:
        raise ValueError("not a binary data packet")
    (_, count, seq0, time0, mx, my, mz, temp, humidity, pressure,
     proximity, red, green, blue, ambient, gesture, gsr, rssi) = BLE_HEADER.unpack_from(data)
    if len(data) != BLE_HEADER.size + count * BLE_SAMPLE.size:
        raise ValueError(f"packet length {len(data)} does not match {count} samples")
    slow = {
        "mx": _signed(mx, 10), "my": _signed(my, 10), "mz": _signed(mz, 10),
        "temp_c": _signed(temp, 100),
        "humidity_pct": _unsigned(humidity, 100, 0xFFFF),
        "pressure_kpa": _unsigned(pressure, 1000, 0xFFFFFFFF),
        "proximity": proximity, "red": red, "green": green, "blue": blue, "ambient": ambient,
        "gesture": gesture, "gsr": gsr, "rssi": rssi,
    }
    samples = []
    for offset in range(BLE_HEADER.size, len(data), BLE_SAMPLE.size):
        dt, dseq, sound, ax, ay, az, gx, gy, gz = BLE_SAMPLE.unpack_from(data, offset)
        sample = dict(slow)
        sample.update(
            time_ms=time0 + dt, seq=seq0 + dseq, sound=sound,
            ax=_signed(ax, 1000), ay=_signed(ay, 1000), az=_signed(az, 1000),
            gx=_signed(gx, 16), gy=_signed(gy, 16), gz=_signed(gz, 16),
        )
        samples.append(add_derived_fields(sample))
        # A gesture is an event, so only the first sample in a packet carries it.
        slow["gesture"] = -1
    return samples


def available_ports() -> list[str]:
    ports = list(list_ports.comports())
    arduino_vendor_ids = {0x2341, 0x2A03}
    ports.sort(
        key=lambda p: (
            p.vid not in arduino_vendor_ids,
            "arduino" not in (p.description or "").lower(),
            p.device,
        )
    )
    return [f"{p.device} — {p.description}" for p in ports]


def first_index_at_or_after(samples: list[dict[str, float]], time_ms: float) -> int:
    """Binary search time-ordered samples for the first one at or after time_ms."""
    low, high = 0, len(samples)
    while low < high:
        middle = (low + high) // 2
        if samples[middle]["time_ms"] < time_ms:
            low = middle + 1
        else:
            high = middle
    return low


class BadgeViewer(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Nano 33 Sense Rev2 — Live Badge Data")
        self.geometry("1200x780")
        self.minsize(900, 600)

        self.serial_port: serial.Serial | None = None
        self.reader_thread: threading.Thread | None = None
        self.stop_reader = threading.Event()
        self.ble_devices: dict[str, BLEDevice] = {}
        self.ble_client: BleakClient | None = None
        self.ble_loop: asyncio.AbstractEventLoop | None = None
        self.ble_thread: threading.Thread | None = None
        self.stop_ble = threading.Event()
        self.inbox: queue.Queue[tuple[str, object]] = queue.Queue()
        self.history: deque[dict[str, float]] = deque(maxlen=MAX_RATE_HZ * MAX_WINDOW_SECONDS)
        self.recent_times: deque[float] = deque()
        self.lines: dict[str, object] = {}
        self.axes: list[object] = []
        self.plot_vars: dict[str, tk.BooleanVar] = {}
        self.csv_file = None
        self.csv_writer = None
        self.last_draw = 0.0
        self.samples_received = 0
        self.samples_dropped = 0
        self.last_seq: float | None = None
        self.last_sample_wall = 0.0

        self.transport_var = tk.StringVar(value=TRANSPORT_USB)
        self.endpoint_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Disconnected")
        self.rate_var = tk.IntVar(value=100)
        self.send_interval_var = tk.IntVar(value=50)
        self.refresh_var = tk.IntVar(value=10)
        self.window_var = tk.DoubleVar(value=30.0)
        self.record_var = tk.StringVar(value="Not recording")

        self._build_ui()
        self.refresh_devices()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(25, self.process_inbox)

    def _build_ui(self) -> None:
        controls = ttk.Frame(self, padding=10)
        controls.pack(fill="x")

        ttk.Label(controls, text="Connection").grid(row=0, column=0, sticky="w")
        self.transport_box = ttk.Combobox(
            controls,
            textvariable=self.transport_var,
            values=(TRANSPORT_USB, TRANSPORT_BLE),
            width=14,
            state="readonly",
        )
        self.transport_box.grid(row=1, column=0, padx=(0, 5), sticky="w")
        self.transport_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_devices())

        self.endpoint_label = ttk.Label(controls, text="Serial port")
        self.endpoint_label.grid(row=0, column=1, sticky="w")
        self.endpoint_box = ttk.Combobox(
            controls, textvariable=self.endpoint_var, width=38, state="readonly"
        )
        self.endpoint_box.grid(row=1, column=1, padx=(0, 5), sticky="ew")
        self.refresh_button = ttk.Button(controls, text="Refresh", command=self.refresh_devices)
        self.refresh_button.grid(row=1, column=2, padx=5)
        self.connect_button = ttk.Button(controls, text="Connect", command=self.toggle_connection)
        self.connect_button.grid(row=1, column=3, padx=5)

        ttk.Label(controls, text="Device sample rate (Hz)").grid(row=0, column=4, padx=(20, 0), sticky="w")
        rate = ttk.Scale(controls, from_=1, to=MAX_RATE_HZ, variable=self.rate_var, command=self._rate_changed)
        rate.grid(row=1, column=4, padx=(20, 4), sticky="ew")
        self.rate_label = ttk.Label(controls, text=f"{self.rate_var.get()} Hz", width=7)
        self.rate_label.grid(row=1, column=5)

        ttk.Label(controls, text="Send every (ms)").grid(row=0, column=6, padx=(10, 0), sticky="w")
        ttk.Spinbox(
            controls, from_=0, to=MAX_SEND_INTERVAL_MS, increment=10,
            textvariable=self.send_interval_var, width=7,
        ).grid(row=1, column=6, padx=(10, 4))
        self.apply_rate_button = ttk.Button(controls, text="Apply", command=self.apply_device_rate)
        self.apply_rate_button.grid(row=1, column=7, padx=5)

        ttk.Label(controls, text="Plot refresh (Hz)").grid(row=0, column=8, padx=(20, 0), sticky="w")
        refresh = ttk.Scale(controls, from_=1, to=30, variable=self.refresh_var, command=self._refresh_changed)
        refresh.grid(row=1, column=8, padx=(20, 4), sticky="ew")
        self.refresh_label = ttk.Label(controls, text="10 Hz", width=7)
        self.refresh_label.grid(row=1, column=9)

        ttk.Label(controls, text="Visible seconds").grid(row=0, column=10, padx=(20, 0), sticky="w")
        ttk.Spinbox(
            controls, from_=5, to=MAX_WINDOW_SECONDS, increment=5, textvariable=self.window_var, width=7
        ).grid(row=1, column=10, padx=(20, 5))
        controls.columnconfigure(1, weight=2)
        controls.columnconfigure(4, weight=1)
        controls.columnconfigure(8, weight=1)

        actions = ttk.Frame(self, padding=(10, 0, 10, 6))
        actions.pack(fill="x")
        ttk.Button(actions, text="Start CSV recording", command=self.toggle_recording).pack(side="left")
        self.record_button = actions.winfo_children()[-1]
        ttk.Label(actions, textvariable=self.record_var).pack(side="left", padx=10)
        ttk.Button(actions, text="Clear", command=self.clear_history).pack(side="left", padx=5)
        ttk.Label(actions, textvariable=self.status_var).pack(side="right")

        sensor_controls = ttk.LabelFrame(self, text="Visible sensor charts", padding=(8, 4))
        sensor_controls.pack(fill="x", padx=10, pady=(0, 6))
        for index, (field, title, _units, selected) in enumerate(PLOT_OPTIONS):
            variable = tk.BooleanVar(value=selected)
            self.plot_vars[field] = variable
            ttk.Checkbutton(
                sensor_controls,
                text=title,
                variable=variable,
                command=self.rebuild_plots,
            ).grid(row=index // 7, column=index % 7, sticky="w", padx=6, pady=2)
        chart_buttons = ttk.Frame(sensor_controls)
        chart_buttons.grid(row=4, column=0, columnspan=7, sticky="w", padx=4, pady=(4, 0))
        ttk.Button(
            chart_buttons, text="Default charts", command=lambda: self.set_plot_selection("default")
        ).pack(side="left", padx=2)
        ttk.Button(
            chart_buttons, text="Select all", command=lambda: self.set_plot_selection("all")
        ).pack(side="left", padx=2)
        ttk.Button(
            chart_buttons, text="Select none", command=lambda: self.set_plot_selection("none")
        ).pack(side="left", padx=2)
        for column in range(7):
            sensor_controls.columnconfigure(column, weight=1)

        self.figure = Figure(figsize=(11, 6), dpi=100, constrained_layout=True)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.rebuild_plots()

    def selected_plots(self):
        return [spec for spec in PLOT_OPTIONS if self.plot_vars[spec[0]].get()]

    def set_plot_selection(self, mode: str) -> None:
        for field, _title, _units, default in PLOT_OPTIONS:
            self.plot_vars[field].set(default if mode == "default" else mode == "all")
        self.rebuild_plots()

    def rebuild_plots(self) -> None:
        selected = self.selected_plots()
        self.figure.clear()
        self.axes = []
        self.lines = {}
        if not selected:
            axis = self.figure.add_subplot(111)
            axis.set_axis_off()
            axis.text(
                0.5, 0.5, "Select one or more sensor charts above",
                ha="center", va="center", transform=axis.transAxes,
            )
            self.canvas.draw_idle()
            return

        columns = 1 if len(selected) == 1 else 2
        rows = math.ceil(len(selected) / columns)
        colors = ("#8e44ad", "#2980b9", "#16a085", "#d35400", "#c0392b", "#2c3e50")
        for index, (field, title, units, _default) in enumerate(selected, start=1):
            axis = self.figure.add_subplot(rows, columns, index)
            (line,) = axis.plot([], [], color=colors[(index - 1) % len(colors)], linewidth=1.5)
            self.axes.append(axis)
            self.lines[field] = line
            axis.set_title(title)
            axis.set_ylabel(units)
            axis.set_xlabel("seconds")
            axis.grid(True, alpha=0.25)
            if field == "gesture":
                axis.set_yticks((-1, 0, 1, 2, 3), ("none", "up", "down", "left", "right"))
        self.canvas.draw_idle()

    def refresh_devices(self) -> None:
        if self.is_connected:
            return
        if self.transport_var.get() == TRANSPORT_BLE:
            self.endpoint_label.configure(text="BLE badge")
            self.endpoint_box["values"] = ()
            self.endpoint_var.set("")
            self.refresh_button.configure(state="disabled")
            self.status_var.set("Scanning for HM Badge devices for 5 seconds…")
            threading.Thread(target=self.scan_ble, daemon=True).start()
        else:
            self.endpoint_label.configure(text="Serial port")
            self.refresh_button.configure(state="normal")
            self.refresh_ports()

    def refresh_ports(self) -> None:
        values = available_ports()
        previous_device = self.endpoint_var.get().split(" — ", 1)[0]
        self.endpoint_box["values"] = values
        matching = next((v for v in values if v.startswith(previous_device + " —")), None)
        if matching:
            self.endpoint_var.set(matching)
        elif values:
            self.endpoint_var.set(values[0])
        else:
            self.endpoint_var.set("")
        if not values:
            self.status_var.set("No serial ports found")

    def scan_ble(self) -> None:
        try:
            devices = asyncio.run(BleakScanner.discover(timeout=5.0))
            matches = [device for device in devices if (device.name or "").startswith("HM Badge")]
            self.inbox.put(("ble_devices", matches))
        except Exception as exc:
            self.inbox.put(("ble_scan_error", str(exc)))

    @property
    def is_connected(self) -> bool:
        return self.serial_port is not None or self.ble_client is not None

    def toggle_connection(self) -> None:
        if self.is_connected:
            self.disconnect()
            return
        selection = self.endpoint_var.get()
        if not selection:
            messagebox.showerror("No device", "Select a device, or click Refresh to scan again.")
            return
        if self.transport_var.get() == TRANSPORT_BLE:
            device = self.ble_devices.get(selection)
            if device is None:
                messagebox.showerror("BLE device missing", "Refresh the BLE scan and select the badge again.")
                return
            self.stop_ble.clear()
            self.connect_button.configure(text="Connecting…", state="disabled")
            self.transport_box.configure(state="disabled")
            self.endpoint_box.configure(state="disabled")
            self.status_var.set(f"Connecting to {selection}…")
            self.ble_thread = threading.Thread(target=self.run_ble, args=(device,), daemon=True)
            self.ble_thread.start()
            return

        device = selection.split(" — ", 1)[0]
        try:
            self.serial_port = serial.Serial(device, 115200, timeout=0.2, write_timeout=1)
        except serial.SerialException as exc:
            messagebox.showerror("Connection failed", str(exc))
            return
        self.stop_reader.clear()
        self.reader_thread = threading.Thread(target=self.read_serial, daemon=True)
        self.reader_thread.start()
        self.connect_button.configure(text="Disconnect")
        self.transport_box.configure(state="disabled")
        self.endpoint_box.configure(state="disabled")
        self.status_var.set(f"Connected to {device}; waiting for data…")
        self.after(800, self.apply_device_rate)

    def disconnect(self) -> None:
        self.stop_reader.set()
        self.stop_ble.set()
        port, self.serial_port = self.serial_port, None
        if port is not None:
            try:
                port.close()
            except serial.SerialException:
                pass
        self.connect_button.configure(text="Connect", state="normal")
        self.transport_box.configure(state="readonly")
        self.endpoint_box.configure(state="readonly")
        self.status_var.set("Disconnected")

    def run_ble(self, device: BLEDevice) -> None:
        try:
            asyncio.run(self.ble_session(device))
        except Exception as exc:
            self.inbox.put(("error", f"BLE error: {exc}"))
        finally:
            self.ble_client = None
            self.ble_loop = None
            self.inbox.put(("disconnected", "BLE disconnected"))

    async def ble_session(self, device: BLEDevice) -> None:
        self.ble_loop = asyncio.get_running_loop()
        async with BleakClient(device) as client:
            self.ble_client = client
            await client.start_notify(NUS_TX_UUID, self.on_ble_notification)
            self.inbox.put(("connected", f"Connected over BLE to {device.name or device.address}"))
            while not self.stop_ble.is_set() and client.is_connected:
                await asyncio.sleep(0.1)
            if client.is_connected:
                await client.stop_notify(NUS_TX_UUID)

    def on_ble_notification(self, _characteristic, data: bytearray) -> None:
        if data and data[0] == BLE_PACKET_TYPE:
            try:
                for sample in parse_ble_packet(bytes(data)):
                    self.inbox.put(("sample", sample))
            except (ValueError, struct.error) as exc:
                self.inbox.put(("message", f"Ignored malformed BLE packet: {exc}"))
            return
        # Text notifications (replies, older firmware's DATA rows) hold one or
        # more complete newline-separated lines.
        text = bytes(data).decode("utf-8", errors="replace")
        for line in text.splitlines():
            line = line.strip("\x00 ")
            if line:
                self.handle_data_line(line)

    def handle_data_line(self, line: str) -> None:
        if line.startswith("DATA,"):
            try:
                self.inbox.put(("sample", parse_data_line(line)))
            except ValueError as exc:
                self.inbox.put(("message", f"Ignored malformed data line: {exc}"))
        else:
            self.inbox.put(("message", line))

    def read_serial(self) -> None:
        port = self.serial_port
        while port is not None and not self.stop_reader.is_set():
            try:
                raw = port.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    self.handle_data_line(line)
            except (serial.SerialException, OSError) as exc:
                self.inbox.put(("error", str(exc)))
                break

    def process_inbox(self) -> None:
        newest_message = None
        while True:
            try:
                kind, payload = self.inbox.get_nowait()
            except queue.Empty:
                break
            if kind == "sample":
                self.add_sample(payload)
            elif kind == "message":
                newest_message = str(payload)
            elif kind == "error":
                newest_message = str(payload)
                self.disconnect()
            elif kind == "connected":
                newest_message = str(payload)
                self.connect_button.configure(text="Disconnect", state="normal")
                self.transport_box.configure(state="disabled")
                self.endpoint_box.configure(state="disabled")
                self.after(300, self.apply_device_rate)
            elif kind == "disconnected":
                newest_message = str(payload)
                self.connect_button.configure(text="Connect", state="normal")
                self.transport_box.configure(state="readonly")
                self.endpoint_box.configure(state="readonly")
            elif kind == "ble_devices":
                if self.transport_var.get() != TRANSPORT_BLE:
                    continue
                devices = payload
                self.ble_devices = {
                    f"{device.name or 'Unnamed'} — {device.address}": device for device in devices
                }
                values = list(self.ble_devices)
                self.endpoint_box["values"] = values
                self.endpoint_var.set(values[0] if values else "")
                self.refresh_button.configure(state="normal")
                newest_message = (
                    f"Found {len(values)} HM Badge device(s)" if values
                    else "No HM Badge found; ensure the board is powered and not already connected"
                )
            elif kind == "ble_scan_error":
                if self.transport_var.get() != TRANSPORT_BLE:
                    continue
                self.refresh_button.configure(state="normal")
                newest_message = f"BLE scan failed: {payload}"

        if self.csv_file:
            self.csv_file.flush()

        now = time.monotonic()
        if newest_message:
            self.status_var.set(newest_message)
        elif self.is_connected and self.samples_received:
            age = now - self.last_sample_wall
            self.status_var.set(
                f"Receiving — {self.measured_rate():.1f} Hz, {self.samples_received:,} samples, "
                f"{self.samples_dropped:,} dropped ({age:.1f}s since last)"
            )

        refresh_hz = max(1, int(self.refresh_var.get()))
        if now - self.last_draw >= 1.0 / refresh_hz:
            self.draw()
            self.last_draw = now
        self.after(25, self.process_inbox)

    def add_sample(self, sample: dict[str, float]) -> None:
        # A backwards timestamp means the board restarted; start a fresh plot.
        if self.history and sample["time_ms"] < self.history[-1]["time_ms"]:
            self.history.clear()
            self.recent_times.clear()
            self.last_seq = None
        seq = sample["seq"]
        if math.isfinite(seq):
            if self.last_seq is not None and seq > self.last_seq + 1:
                self.samples_dropped += int(seq - self.last_seq - 1)
            self.last_seq = seq
        self.history.append(sample)
        self.recent_times.append(sample["time_ms"])
        while self.recent_times[-1] - self.recent_times[0] > 2000.0:
            self.recent_times.popleft()
        self.samples_received += 1
        self.last_sample_wall = time.monotonic()
        if self.csv_writer:
            self.csv_writer.writerow({name: sample[name] for name in FIELDS})

    def measured_rate(self) -> float:
        """Sample rate from the board's own timestamps over the last ~2 seconds."""
        if len(self.recent_times) < 2:
            return 0.0
        span_ms = self.recent_times[-1] - self.recent_times[0]
        return (len(self.recent_times) - 1) * 1000.0 / span_ms if span_ms > 0 else 0.0

    def draw(self) -> None:
        if not self.history:
            return
        data = list(self.history)
        end_ms = data[-1]["time_ms"]
        visible_ms = max(5.0, float(self.window_var.get())) * 1000.0
        data = data[first_index_at_or_after(data, end_ms - visible_ms):]
        data = data[:: max(1, math.ceil(len(data) / MAX_PLOT_POINTS))]
        x = [(sample["time_ms"] - end_ms) / 1000.0 for sample in data]

        for axis, (field, _title, _units, _default) in zip(self.axes, self.selected_plots()):
            y = [sample[field] for sample in data]
            self.lines[field].set_data(x, y)
            axis.set_xlim(min(x, default=-1.0), 0.0)
            finite = [value for value in y if math.isfinite(value)]
            if field == "gesture":
                axis.set_ylim(-1.4, 3.4)
            elif finite:
                low, high = min(finite), max(finite)
                margin = max((high - low) * 0.1, 0.5)
                axis.set_ylim(low - margin, high + margin)
        self.canvas.draw_idle()

    def _rate_changed(self, _value: str) -> None:
        self.rate_label.configure(text=f"{int(self.rate_var.get())} Hz")

    def _refresh_changed(self, _value: str) -> None:
        self.refresh_label.configure(text=f"{int(self.refresh_var.get())} Hz")

    def apply_device_rate(self) -> None:
        try:
            send_ms = int(self.send_interval_var.get())
        except (tk.TclError, ValueError):
            send_ms = 0
        send_ms = min(max(send_ms, 0), MAX_SEND_INTERVAL_MS)
        self.send_interval_var.set(send_ms)
        command = f"RATE {int(self.rate_var.get())}\nSEND {send_ms}\n".encode("ascii")
        if self.serial_port is not None:
            try:
                self.serial_port.write(command)
            except (serial.SerialException, OSError) as exc:
                self.status_var.set(f"Could not set rate: {exc}")
        elif self.ble_client is not None and self.ble_loop is not None:
            future = asyncio.run_coroutine_threadsafe(
                self.ble_client.write_gatt_char(NUS_RX_UUID, command, response=True),
                self.ble_loop,
            )
            future.add_done_callback(self.ble_write_done)

    def ble_write_done(self, future) -> None:
        try:
            future.result()
        except Exception as exc:
            self.inbox.put(("message", f"Could not set BLE rate: {exc}"))

    def toggle_recording(self) -> None:
        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
            self.csv_writer = None
            self.record_button.configure(text="Start CSV recording")
            self.record_var.set("Not recording")
            return
        default = f"badge_data_{datetime.now():%Y%m%d_%H%M%S}.csv"
        path = filedialog.asksaveasfilename(
            title="Save badge data", initialfile=default, defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
        )
        if not path:
            return
        self.csv_file = Path(path).open("w", newline="", encoding="utf-8")
        self.csv_writer = csv.DictWriter(self.csv_file, fieldnames=FIELDS)
        self.csv_writer.writeheader()
        self.record_button.configure(text="Stop CSV recording")
        self.record_var.set(f"Recording to {Path(path).name}")

    def clear_history(self) -> None:
        self.history.clear()
        self.recent_times.clear()
        self.samples_received = 0
        self.samples_dropped = 0
        self.last_seq = None
        for line in self.lines.values():
            line.set_data([], [])
        self.canvas.draw_idle()

    def close(self) -> None:
        self.disconnect()
        if self.csv_file:
            self.csv_file.close()
        self.destroy()


if __name__ == "__main__":
    BadgeViewer().mainloop()
