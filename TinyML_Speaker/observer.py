"""Native observer panel. No audio recording or model predictions."""
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

from ground_truth import IntervalRecorder

CHECKPOINT_MS = 200


class ObserverPanel:
    def __init__(self, root: tk.Tk, output: Path, recording_id: str, badges: list[str],
                 container: Optional[ttk.Frame] = None, on_close: Optional[Callable[[], None]] = None) -> None:
        self.root = root
        self.on_close = on_close
        self.recorder = IntervalRecorder(output, recording_id, badges, datetime.now(timezone.utc))
        self.paused = True
        self.closed = False
        self.focus_timer = None
        self.embedded = container is not None
        self.pressed: set[str] = set()
        self.badges = badges
        self.variables = {badge: tk.StringVar(value='unknown') for badge in badges}
        self.controls: list[ttk.Radiobutton] = []
        if not self.embedded:
            root.title('Speaker reference | Observer')
            root.minsize(760, 470)
            root.geometry(f'820x{max(500, 300 + 42 * len(badges))}')
        style = ttk.Style(root)
        if self.embedded:
            # The host window owns label and button styles; keep the panel compact beside the plots.
            style.configure('TRadiobutton', font=('Segoe UI', 10), padding=(2, 2))
        else:
            style.configure('TLabel', font=('Segoe UI', 11))
            style.configure('TButton', font=('Segoe UI', 11), padding=(10, 7))
            style.configure('TRadiobutton', font=('Segoe UI', 11), padding=(8, 6))
        compact = self.embedded
        body = self.body = ttk.Frame(container if container is not None else root, padding=12 if compact else 24)
        body.pack(fill='both', expand=True)
        wrapped: list[ttk.Label] = []

        def label(parent: tk.Widget, **options) -> ttk.Label:
            widget = ttk.Label(parent, wraplength=750, **options)
            wrapped.append(widget)
            return widget

        ttk.Label(body, text='Who is speaking?', font=('Segoe UI', 13 if compact else 20, 'bold')).pack(anchor='w')
        if not compact:
            ttk.Label(body, text=f'Recording: {recording_id}').pack(anchor='w', pady=(4, 12))
        self.status = tk.StringVar(value='Paused. No speech or silence labels are being assigned.')
        label(body, textvariable=self.status).pack(anchor='w', fill='x', pady=(0, 8 if compact else 16))
        table = ttk.Frame(body)
        table.pack(fill='x')
        gap = 8 if compact else 20
        ttk.Label(table, text='Badge' if compact else 'Badge / shortcut', font=('Segoe UI', 11, 'bold')).grid(
            row=0, column=0, columnspan=2, sticky='w', padx=(0, gap))
        choices = [('Speaking', 'active'), ('Quiet' if compact else 'Not speaking', 'not_active'), ('Unknown', 'unknown')]
        for i, badge in enumerate(badges, 1):
            ttk.Label(table, text=str(i)).grid(row=i, column=0, sticky='w', padx=(0, 6))
            ttk.Label(table, text=badge).grid(row=i, column=1, sticky='w', padx=(0, gap))
            for column, (text, value) in enumerate(choices, 2):
                control = ttk.Radiobutton(table, text=text, value=value, variable=self.variables[badge],
                                          command=self.changed, state='disabled')
                control.grid(row=i, column=column, sticky='w', pady=2 if compact else 3)
                self.controls.append(control)
        actions = ttk.Frame(body)
        actions.pack(fill='x', pady=(10, 6) if compact else (20, 12))
        self.start_button = ttk.Button(actions, text='Start (Enter)' if compact else 'Start observing (Enter)', command=self.start)
        pause = ttk.Button(actions, text='Pause (Space)' if compact else 'Pause / uncertain (Space)', command=self.pause)
        silence = ttk.Button(actions if compact else body, text='Silence (0)' if compact else 'Observed silence (0)', command=self.silence)
        self.start_button.pack(side='left', padx=(0, 6))
        pause.pack(side='left', padx=(0, 6))
        silence.pack(side='left') if compact else silence.pack(anchor='w')
        help_text = ('Keys: 1–9 toggle speakers, 0 silence, Space pause. Use Unknown when uncertain. '
                     'Leaving the window pauses annotation.' if compact else
                     '1–9 toggles a speaker. Multiple speakers may be selected.\n'
                     'Start means you can observe every listed badge. Use Unknown for anyone you cannot judge.\n'
                     'Switching to another window pauses annotation.')
        label(body, text=help_text).pack(anchor='w', fill='x', pady=(8, 6) if compact else (16, 12))
        footer = ttk.Frame(body)
        footer.pack(side='bottom', fill='x', pady=(4, 0))
        ttk.Button(footer, text='Finish annotations' if compact else 'Save and close', command=self.close).pack(
            side='top' if compact else 'right', anchor='w')
        label(footer, text=f'Intervals save every {CHECKPOINT_MS / 1000:g} s. Closing saves the final interval.').pack(
            side='top' if compact else 'left', anchor='w', pady=(4, 0) if compact else 0)
        if compact:
            body.bind('<Configure>', lambda event: [widget.configure(wraplength=max(160, event.width - 30))
                                                    for widget in wrapped])
        self.bindings = {sequence: root.bind(sequence, callback, add='+') for sequence, callback in [
            ('<KeyPress>', self.key_down),
            ('<KeyRelease>', lambda event: self.pressed.discard(event.keysym)),
            ('<FocusOut>', lambda _: self.queue_focus_check())]}
        if not self.embedded:
            root.protocol('WM_DELETE_WINDOW', self.close)
            root.update_idletasks()
            width = max(820, root.winfo_reqwidth())
            height = max(500, root.winfo_reqheight())
            root.minsize(width, height)
            root.geometry(f'{width}x{height}')
        self.checkpoint_timer = root.after(CHECKPOINT_MS, self.checkpoint)

    def save(self) -> None:
        try:
            self.recorder.change({badge: variable.get() for badge, variable in self.variables.items()}, datetime.now(timezone.utc))
        except (ValueError, OSError) as error:
            self.closed = True
            self.recorder.handle.close()
            self.recorder.closed = True
            messagebox.showerror('Annotation stopped', f'Could not save the next interval: {error}', parent=self.root)
            self.dispose_ui()

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
        if self.closed or isinstance(event.widget, tk.Entry):
            return None
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

    def queue_focus_check(self) -> None:
        if not self.closed:
            if self.focus_timer:
                self.root.after_cancel(self.focus_timer)
            self.focus_timer = self.root.after(100, self.check_focus)

    def checkpoint(self) -> None:
        if not self.closed:
            self.save()
            if not self.closed:
                self.checkpoint_timer = self.root.after(CHECKPOINT_MS, self.checkpoint)

    def dispose_ui(self) -> None:
        for timer in [self.focus_timer, self.checkpoint_timer]:
            if timer:
                self.root.after_cancel(timer)
        for sequence, binding in self.bindings.items():
            self.root.unbind(sequence, binding)
        if self.on_close:
            self.on_close()
        if self.embedded:
            self.body.destroy()
        else:
            self.root.destroy()

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            try:
                self.recorder.close(datetime.now(timezone.utc))
            except (ValueError, OSError) as error:
                messagebox.showerror('Final interval not saved', str(error), parent=self.root)
            self.dispose_ui()


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
