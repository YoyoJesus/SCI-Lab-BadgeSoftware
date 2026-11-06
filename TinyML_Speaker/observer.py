"""Native observer panel. No audio recording or model predictions."""
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from ground_truth import IntervalRecorder


class ObserverPanel:
    def __init__(self, root: tk.Tk, output: Path, recording_id: str, badges: list[str]) -> None:
        self.root = root
        self.recorder = IntervalRecorder(output, recording_id, badges, datetime.now(timezone.utc))
        self.paused = True
        self.closed = False
        self.pressed: set[str] = set()
        self.badges = badges
        self.variables = {badge: tk.StringVar(value='unknown') for badge in badges}
        self.controls: list[ttk.Radiobutton] = []
        root.title('Speaker reference | Observer')
        root.minsize(760, 470)
        root.geometry(f'820x{max(500, 300 + 42 * len(badges))}')
        style = ttk.Style(root)
        style.configure('TLabel', font=('Segoe UI', 11))
        style.configure('TButton', font=('Segoe UI', 11), padding=(10, 7))
        style.configure('TRadiobutton', font=('Segoe UI', 11), padding=(8, 6))
        body = ttk.Frame(root, padding=24)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='Who is speaking?', font=('Segoe UI', 20, 'bold')).pack(anchor='w')
        ttk.Label(body, text=f'Recording: {recording_id}').pack(anchor='w', pady=(4, 12))
        self.status = tk.StringVar(value='Paused. No speech or silence labels are being assigned.')
        ttk.Label(body, textvariable=self.status, wraplength=750).pack(anchor='w', pady=(0, 16))
        table = ttk.Frame(body)
        table.pack(fill='x')
        ttk.Label(table, text='Badge / shortcut', font=('Segoe UI', 11, 'bold')).grid(row=0, column=0, sticky='w', padx=(0, 20))
        for i, badge in enumerate(badges, 1):
            ttk.Label(table, text=f'{i}    {badge}').grid(row=i, column=0, sticky='w', padx=(0, 20))
            for column, (text, value) in enumerate([('Speaking', 'active'), ('Not speaking', 'not_active'), ('Unknown', 'unknown')], 1):
                control = ttk.Radiobutton(table, text=text, value=value, variable=self.variables[badge],
                                          command=self.changed, state='disabled')
                control.grid(row=i, column=column, sticky='w', pady=3)
                self.controls.append(control)
        actions = ttk.Frame(body)
        actions.pack(fill='x', pady=(20, 12))
        self.start_button = ttk.Button(actions, text='Start observing (Enter)', command=self.start)
        self.start_button.pack(side='left', padx=(0, 8))
        ttk.Button(actions, text='Pause / uncertain (Space)', command=self.pause).pack(side='left')
        ttk.Button(body, text='Observed silence (0)', command=self.silence).pack(anchor='w')
        ttk.Label(body, text='1–9 toggles a speaker. Multiple speakers may be selected.\n'
                  'Start means you can observe every listed badge. Use Unknown for anyone you cannot judge.\n'
                  'Switching to another window pauses annotation.', wraplength=750).pack(anchor='w', pady=(16, 12))
        footer = ttk.Frame(body)
        footer.pack(side='bottom', fill='x', pady=(8, 0))
        ttk.Label(footer, text='Intervals save every second. Closing saves the final interval.').pack(side='left')
        ttk.Button(footer, text='Save and close', command=self.close).pack(side='right')
        root.bind('<KeyPress>', self.key_down)
        root.bind('<KeyRelease>', lambda event: self.pressed.discard(event.keysym))
        root.bind('<FocusOut>', lambda _: root.after(100, self.check_focus))
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.update_idletasks()
        width = max(820, root.winfo_reqwidth())
        height = max(500, root.winfo_reqheight())
        root.minsize(width, height)
        root.geometry(f'{width}x{height}')
        root.after(1000, self.checkpoint)

    def save(self) -> None:
        try:
            self.recorder.change({badge: variable.get() for badge, variable in self.variables.items()}, datetime.now(timezone.utc))
        except (ValueError, OSError) as error:
            self.closed = True
            self.recorder.handle.close()
            messagebox.showerror('Annotation stopped', f'Could not save the next interval: {error}', parent=self.root)
            self.root.destroy()

    def changed(self) -> None:
        self.save()

    def start(self) -> None:
        if self.closed:
            return
        self.paused = False
        for variable in self.variables.values():
            variable.set('not_active')
        for control in self.controls:
            control.configure(state='normal')
        self.start_button.configure(text='Observing', state='disabled')
        self.status.set('Observing. Mark every speaker, including overlapping speech.')
        self.save()

    def pause(self) -> None:
        if self.closed:
            return
        self.paused = True
        for variable in self.variables.values():
            variable.set('unknown')
        for control in self.controls:
            control.configure(state='disabled')
        self.start_button.configure(text='Resume observing (Enter)', state='normal')
        self.status.set('Paused. This time remains unknown and will be excluded from training.')
        self.save()

    def silence(self) -> None:
        self.start()

    def toggle(self, badge: str) -> None:
        if not self.paused:
            variable = self.variables[badge]
            variable.set('not_active' if variable.get() == 'active' else 'active')
            self.save()

    def key_down(self, event: tk.Event) -> Optional[str]:
        key = event.keysym
        if key not in ['space', 'Return', '0'] + [str(i) for i in range(1, len(self.badges) + 1)]:
            return None
        if key not in self.pressed:
            self.pressed.add(key)
            if key == 'space':
                self.pause()
            elif key == 'Return' and self.paused:
                self.start()
            elif key == '0':
                self.silence()
            elif key in [str(i) for i in range(1, len(self.badges) + 1)]:
                self.toggle(self.badges[int(key) - 1])
        return 'break'

    def check_focus(self) -> None:
        if not self.closed and self.root.focus_displayof() is None:
            self.pressed.clear()
            self.pause()

    def checkpoint(self) -> None:
        if not self.closed:
            self.save()
            if not self.closed:
                self.root.after(1000, self.checkpoint)

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            try:
                self.recorder.close(datetime.now(timezone.utc))
            except (ValueError, OSError) as error:
                messagebox.showerror('Final interval not saved', str(error), parent=self.root)
            self.root.destroy()


def launch(output: Path, recording_id: str, badges: list[str]) -> None:
    if not 1 <= len(badges) <= 9:
        raise ValueError('The observer panel supports one to nine badges')
    root = tk.Tk()
    try:
        ObserverPanel(root, output, recording_id, badges)
    except Exception:
        root.destroy()
        raise
    print(f'Observer intervals: {output}')
    root.mainloop()
