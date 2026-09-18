"""Live serial dashboard for the Nano 33 BLE Sense Rev2 badge."""

from __future__ import annotations

import csv
import math
import queue
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
import serial
from serial.tools import list_ports


FIELDS = [
    "time_ms", "sound", "ax", "ay", "az", "gx", "gy", "gz",
    "mx", "my", "mz", "temp_c", "humidity_pct", "pressure_kpa",
    "proximity", "red", "green", "blue", "gsr", "rssi",
]

PLOTS = (
    ("gsr", "GSR", "0–255"),
    ("sound", "Sound level (RMS)", "amplitude"),
    ("accel_mag", "Acceleration magnitude", "g"),
    ("temp_c", "Temperature", "°C"),
)


def parse_data_line(line: str) -> dict[str, float]:
    """Parse one firmware DATA line and calculate derived plot values."""
    if not line.startswith("DATA,"):
        raise ValueError("not a DATA line")
    parts = line.split(",")[1:]
    if len(parts) != len(FIELDS):
        raise ValueError(f"expected {len(FIELDS)} fields, received {len(parts)}")
    sample: dict[str, float] = {}
    for name, value in zip(FIELDS, parts):
        try:
            sample[name] = float(value)
        except ValueError:
            sample[name] = math.nan
    sample["accel_mag"] = math.sqrt(
        sample["ax"] ** 2 + sample["ay"] ** 2 + sample["az"] ** 2
    )
    return sample


def available_ports() -> list[str]:
    ports = list(list_ports.comports())
    ports.sort(key=lambda p: ("arduino" not in (p.description or "").lower(), p.device))
    return [f"{p.device} — {p.description}" for p in ports]


class BadgeViewer(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Nano 33 Sense Rev2 — Live Badge Data")
        self.geometry("1200x780")
        self.minsize(900, 600)

        self.serial_port: serial.Serial | None = None
        self.reader_thread: threading.Thread | None = None
        self.stop_reader = threading.Event()
        self.inbox: queue.Queue[tuple[str, object]] = queue.Queue()
        self.history: deque[dict[str, float]] = deque(maxlen=6000)
        self.lines: dict[str, object] = {}
        self.csv_file = None
        self.csv_writer = None
        self.last_draw = 0.0
        self.samples_received = 0
        self.last_sample_wall = 0.0

        self.port_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Disconnected")
        self.rate_var = tk.IntVar(value=10)
        self.refresh_var = tk.IntVar(value=10)
        self.window_var = tk.DoubleVar(value=30.0)
        self.record_var = tk.StringVar(value="Not recording")

        self._build_ui()
        self.refresh_ports()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(25, self.process_inbox)

    def _build_ui(self) -> None:
        controls = ttk.Frame(self, padding=10)
        controls.pack(fill="x")

        ttk.Label(controls, text="Serial port").grid(row=0, column=0, sticky="w")
        self.port_box = ttk.Combobox(controls, textvariable=self.port_var, width=42, state="readonly")
        self.port_box.grid(row=1, column=0, padx=(0, 5), sticky="ew")
        ttk.Button(controls, text="Refresh", command=self.refresh_ports).grid(row=1, column=1, padx=5)
        self.connect_button = ttk.Button(controls, text="Connect", command=self.toggle_connection)
        self.connect_button.grid(row=1, column=2, padx=5)

        ttk.Label(controls, text="Device send rate (Hz)").grid(row=0, column=3, padx=(20, 0), sticky="w")
        rate = ttk.Scale(controls, from_=1, to=25, variable=self.rate_var, command=self._rate_changed)
        rate.grid(row=1, column=3, padx=(20, 4), sticky="ew")
        self.rate_label = ttk.Label(controls, text="10 Hz", width=7)
        self.rate_label.grid(row=1, column=4)
        self.apply_rate_button = ttk.Button(controls, text="Apply", command=self.apply_device_rate)
        self.apply_rate_button.grid(row=1, column=5, padx=5)

        ttk.Label(controls, text="Plot refresh (Hz)").grid(row=0, column=6, padx=(20, 0), sticky="w")
        refresh = ttk.Scale(controls, from_=1, to=30, variable=self.refresh_var, command=self._refresh_changed)
        refresh.grid(row=1, column=6, padx=(20, 4), sticky="ew")
        self.refresh_label = ttk.Label(controls, text="10 Hz", width=7)
        self.refresh_label.grid(row=1, column=7)

        ttk.Label(controls, text="Visible seconds").grid(row=0, column=8, padx=(20, 0), sticky="w")
        ttk.Spinbox(controls, from_=5, to=300, increment=5, textvariable=self.window_var, width=7).grid(
            row=1, column=8, padx=(20, 5)
        )
        controls.columnconfigure(0, weight=2)
        controls.columnconfigure(3, weight=1)
        controls.columnconfigure(6, weight=1)

        actions = ttk.Frame(self, padding=(10, 0, 10, 6))
        actions.pack(fill="x")
        ttk.Button(actions, text="Start CSV recording", command=self.toggle_recording).pack(side="left")
        self.record_button = actions.winfo_children()[-1]
        ttk.Label(actions, textvariable=self.record_var).pack(side="left", padx=10)
        ttk.Button(actions, text="Clear", command=self.clear_history).pack(side="left", padx=5)
        ttk.Label(actions, textvariable=self.status_var).pack(side="right")

        self.figure = Figure(figsize=(11, 6), dpi=100, constrained_layout=True)
        axes = self.figure.subplots(2, 2)
        self.axes = list(axes.flat)
        colors = ("#8e44ad", "#2980b9", "#16a085", "#d35400")
        for axis, (field, title, units), color in zip(self.axes, PLOTS, colors):
            (line,) = axis.plot([], [], color=color, linewidth=1.5)
            self.lines[field] = line
            axis.set_title(title)
            axis.set_ylabel(units)
            axis.set_xlabel("seconds")
            axis.grid(True, alpha=0.25)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def refresh_ports(self) -> None:
        values = available_ports()
        previous_device = self.port_var.get().split(" — ", 1)[0]
        self.port_box["values"] = values
        matching = next((v for v in values if v.startswith(previous_device + " —")), None)
        if matching:
            self.port_var.set(matching)
        elif values:
            self.port_var.set(values[0])
        else:
            self.port_var.set("")
        if not values and self.serial_port is None:
            self.status_var.set("No serial ports found")

    def toggle_connection(self) -> None:
        if self.serial_port is not None:
            self.disconnect()
            return
        selection = self.port_var.get()
        if not selection:
            messagebox.showerror("No port", "Connect the Nano by USB, then click Refresh.")
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
        self.status_var.set(f"Connected to {device}; waiting for data…")
        self.after(800, self.apply_device_rate)

    def disconnect(self) -> None:
        self.stop_reader.set()
        port, self.serial_port = self.serial_port, None
        if port is not None:
            try:
                port.close()
            except serial.SerialException:
                pass
        self.connect_button.configure(text="Connect")
        self.status_var.set("Disconnected")

    def read_serial(self) -> None:
        port = self.serial_port
        while port is not None and not self.stop_reader.is_set():
            try:
                raw = port.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if line.startswith("DATA,"):
                    try:
                        sample = parse_data_line(line)
                    except ValueError as exc:
                        self.inbox.put(("message", f"Ignored malformed data line: {exc}"))
                        continue
                    self.inbox.put(("sample", sample))
                elif line:
                    self.inbox.put(("message", line))
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
                sample = payload
                self.history.append(sample)
                self.samples_received += 1
                self.last_sample_wall = time.monotonic()
                if self.csv_writer:
                    self.csv_writer.writerow({name: sample[name] for name in FIELDS})
                    self.csv_file.flush()
            elif kind == "message":
                newest_message = str(payload)
            elif kind == "error":
                newest_message = f"Serial error: {payload}"
                self.disconnect()

        now = time.monotonic()
        if newest_message:
            self.status_var.set(newest_message)
        elif self.serial_port and self.samples_received:
            age = now - self.last_sample_wall
            self.status_var.set(f"Receiving — {self.samples_received:,} samples ({age:.1f}s since last)")

        refresh_hz = max(1, int(self.refresh_var.get()))
        if now - self.last_draw >= 1.0 / refresh_hz:
            self.draw()
            self.last_draw = now
        self.after(25, self.process_inbox)

    def draw(self) -> None:
        if not self.history:
            return
        data = list(self.history)
        end_ms = data[-1]["time_ms"]
        visible_ms = max(5.0, float(self.window_var.get())) * 1000.0
        data = [sample for sample in data if end_ms - sample["time_ms"] <= visible_ms]
        x = [(sample["time_ms"] - end_ms) / 1000.0 for sample in data]

        for axis, (field, _title, _units) in zip(self.axes, PLOTS):
            y = [sample[field] for sample in data]
            self.lines[field].set_data(x, y)
            axis.set_xlim(min(x, default=-1.0), 0.0)
            finite = [value for value in y if math.isfinite(value)]
            if finite:
                low, high = min(finite), max(finite)
                margin = max((high - low) * 0.1, 0.5)
                axis.set_ylim(low - margin, high + margin)
        self.canvas.draw_idle()

    def _rate_changed(self, _value: str) -> None:
        self.rate_label.configure(text=f"{int(self.rate_var.get())} Hz")

    def _refresh_changed(self, _value: str) -> None:
        self.refresh_label.configure(text=f"{int(self.refresh_var.get())} Hz")

    def apply_device_rate(self) -> None:
        if self.serial_port is None:
            return
        try:
            self.serial_port.write(f"RATE {int(self.rate_var.get())}\n".encode("ascii"))
        except (serial.SerialException, OSError) as exc:
            self.status_var.set(f"Could not set rate: {exc}")

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
        self.samples_received = 0
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
