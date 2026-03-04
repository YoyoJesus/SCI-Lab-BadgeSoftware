#!/usr/bin/env python3
"""
Badge Data Processing Tool

This script processes badge data files and:
1. Allows user to label time periods as 'active' or 'not active'
2. Splits data by badge name  
3. Labels individual data points based on time period selections
4. Exports processed data to CSV for AI tools

Features:
- Interactive graph-based labeling with zoom/pan controls
- Batch labeling: apply same label to all badges
- Keyboard shortcuts: A=Active, N=Not Active, Delete=Remove label
- Right-click to delete labels
- Label manager to view and manage all labels
- Person name display (when available in data)
- Auto-labeling using sound + acceleration (weighted combination, sound prioritized)

Author: Badge Data Processing Tool
Date: October 2025
Updated: February 2026
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import matplotlib.dates as mdates
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.patches import Rectangle
import json

# Default thresholds for auto-labeling (can be overridden in the UI prompt).
SOUND_LEVEL_THRESHOLD = 65  # Sound level threshold for 'active' classification
ACCELERATION_THRESHOLD = 0.5 # Acceleration threshold for 'active' classification  
SOUND_WEIGHT = 0.7  # Default weight for sound (70% sound, 30% acceleration)

class BadgeDataProcessor:
    def __init__(self):
        self.data = None
        self.processed_data = []
        self.labels = []  # Store time periods and their labels
        self.output_folder = Path("processed_data")
        self.output_folder.mkdir(exist_ok=True)
        self.badge_to_person = {}  # Map Badge_Name to Person_Name
        self.has_person_names = False  # Flag if Person_Name column exists
        
        # GUI components
        self.root = None
        self.canvas = None
        self.fig = None
        self.ax = None
    
    def normalize_datetime(self, dt):
        """Convert any datetime-like object to timezone-naive python datetime"""
        if dt is None:
            return None
        
        # Handle pandas Timestamp
        if hasattr(dt, 'to_pydatetime'):
            dt = dt.to_pydatetime()
        
        # Remove timezone info if present
        if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        
        return dt
        
    def select_file(self):
        """Select badge data file to process"""
        badge_data_folder = Path("../badge_data")
        if not badge_data_folder.exists():
            badge_data_folder = Path("badge_data")
        
        if badge_data_folder.exists():
            csv_files = list(badge_data_folder.glob("*.csv"))
            if csv_files:
                print("Available badge data files:")
                for i, file in enumerate(csv_files, 1):
                    print(f"{i}. {file.name}")
                
                while True:
                    try:
                        choice = int(input(f"Select a file (1-{len(csv_files)}): "))
                        if 1 <= choice <= len(csv_files):
                            return csv_files[choice - 1]
                        else:
                            print("Invalid choice. Please try again.")
                    except ValueError:
                        print("Please enter a valid number.")
            else:
                print("No CSV files found in badge_data folder.")
                return None
        else:
            print("Badge data folder not found. Please select a file manually.")
            return self.select_file_dialog()
    
    def select_file_dialog(self):
        """Fallback file selection using file dialog"""
        root = tk.Tk()
        root.withdraw()  # Hide the main window
        file_path = filedialog.askopenfilename(
            title="Select Badge Data CSV File",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        root.destroy()
        return Path(file_path) if file_path else None
    
    def load_data(self, file_path):
        """Load and parse badge data from CSV file"""
        print(f"Loading data from {file_path}...")
        
        try:
            # Load the CSV file
            self.data = pd.read_csv(file_path)
            
            # Convert timestamp to datetime and ensure timezone-naive
            self.data['Timestamp'] = pd.to_datetime(self.data['Timestamp'], utc=False)
            # Remove timezone info if present to ensure all are timezone-naive
            if self.data['Timestamp'].dt.tz is not None:
                self.data['Timestamp'] = self.data['Timestamp'].dt.tz_localize(None)
            
            # Remove duplicate rows (common in the badge data)
            initial_count = len(self.data)
            self.data = self.data.drop_duplicates()
            removed_count = initial_count - len(self.data)
            
            # Check if Person_Name column exists and create mapping
            if 'Person_Name' in self.data.columns:
                self.has_person_names = True
                # Create mapping from Badge_Name to Person_Name
                for badge_name in self.data['Badge_Name'].unique():
                    person_name = self.data[self.data['Badge_Name'] == badge_name]['Person_Name'].iloc[0]
                    self.badge_to_person[badge_name] = person_name
            
            print(f"Loaded {len(self.data)} data points ({removed_count} duplicates removed)")
            print(f"Time range: {self.data['Timestamp'].min()} to {self.data['Timestamp'].max()}")
            
            if self.has_person_names:
                badge_info = [f"{badge} ({self.badge_to_person[badge]})" for badge in sorted(self.data['Badge_Name'].unique())]
                print(f"Badges found: {', '.join(badge_info)}")
            else:
                print(f"Badges found: {sorted(self.data['Badge_Name'].unique())}")
            
            return True
            
        except Exception as e:
            print(f"Error loading data: {e}")
            return False
    
    def create_labeling_gui(self):
        """Create GUI for labeling data segments"""
        self.root = tk.Tk()
        self.root.title("Badge Data Labeling Tool")
        self.root.geometry("1200x800")

        # Create main frame
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Instructions
        instructions = ttk.Label(
            main_frame,
            text=("Instructions: Click and drag on the graph to select time periods, "
                  "then label them as 'Active' or 'Not Active'"),
            font=("Arial", 12)
        )
        instructions.pack(pady=10)

        # Create matplotlib figure
        self.fig, self.ax = plt.subplots(figsize=(12, 6))
        self.canvas = FigureCanvasTkAgg(self.fig, main_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Add navigation toolbar for zoom/pan
        toolbar_frame = ttk.Frame(main_frame)
        toolbar_frame.pack(fill=tk.X)
        toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame)
        toolbar.update()

        # Control buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10)

        # Badge selection
        ttk.Label(button_frame, text="Select Badge:").pack(side=tk.LEFT, padx=5)
        self.badge_var = tk.StringVar()
        
        # Create badge display options with person names if available
        if self.has_person_names:
            badge_options = [f"{badge} - {self.badge_to_person[badge]}" for badge in sorted(self.data['Badge_Name'].unique())]
        else:
            badge_options = sorted(self.data['Badge_Name'].unique())
        
        badge_combo = ttk.Combobox(
            button_frame,
            textvariable=self.badge_var,
            values=badge_options,
            width=25
        )
        badge_combo.pack(side=tk.LEFT, padx=5)
        badge_combo.bind('<<ComboboxSelected>>', self.update_plot)
        badge_combo.set(badge_options[0])

        # Metric selection
        ttk.Label(button_frame, text="Metric:").pack(side=tk.LEFT, padx=5)
        self.metric_var = tk.StringVar(value="Sound_Level")
        metric_combo = ttk.Combobox(
            button_frame,
            textvariable=self.metric_var,
            values=["Sound_Level", "Acceleration"]
        )
        metric_combo.pack(side=tk.LEFT, padx=5)
        metric_combo.bind('<<ComboboxSelected>>', self.update_plot)

        # Label buttons
        ttk.Button(
            button_frame,
            text="Label as Active",
            command=lambda: self.label_selection("active")
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            button_frame,
            text="Label as Not Active",
            command=lambda: self.label_selection("not_active")
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            button_frame,
            text="Clear Selection",
            command=self.clear_selection
        ).pack(side=tk.LEFT, padx=5)
        
        # Batch labeling option
        self.apply_to_all_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            button_frame,
            text="Apply to all badges",
            variable=self.apply_to_all_var
        ).pack(side=tk.LEFT, padx=5)

        # Auto-label button
        ttk.Button(
            button_frame,
            text="Auto-label (Sound+Motion)",
            command=self.prompt_auto_label
        ).pack(side=tk.LEFT, padx=5)
        
        # View labels button
        ttk.Button(
            button_frame,
            text="View All Labels",
            command=self.show_label_manager
        ).pack(side=tk.LEFT, padx=5)

        # Process button
        ttk.Button(
            button_frame,
            text="Process Data",
            command=self.process_and_export
        ).pack(side=tk.RIGHT, padx=5)

        # Status label
        self.status_label = ttk.Label(
            main_frame,
            text="Ready to select - click and drag to select | Shortcuts: A=Active, N=Not Active, Delete=Remove label under cursor"
        )
        self.status_label.pack(pady=5)
        
        # Label count display
        self.label_count_label = ttk.Label(
            main_frame,
            text="Labels: 0",
            font=('Arial', 10, 'bold')
        )
        self.label_count_label.pack(pady=2)

        # Selection variables
        self.selection_start = None
        self.selection_end = None
        self.selection_rect = None

        # Bind mouse events
        self.canvas.mpl_connect('button_press_event', self.on_press)
        self.canvas.mpl_connect('button_release_event', self.on_release)
        self.canvas.mpl_connect('motion_notify_event', self.on_motion)
        
        # Bind keyboard shortcuts
        self.root.bind('<a>', lambda e: self.label_selection("active"))
        self.root.bind('<n>', lambda e: self.label_selection("not_active"))
        self.root.bind('<Escape>', lambda e: self.clear_selection())
        self.root.bind('<Delete>', lambda e: self.delete_label_at_cursor())
        
        # Track cursor position for label interaction
        self.canvas.mpl_connect('motion_notify_event', self.track_cursor_position)
        self.cursor_time = None

        # Initial plot
        self.update_plot()

        return self.root
    
    def update_plot(self, event=None):
        """Update the plot based on selected badge and metric"""
        badge_display = self.badge_var.get()
        metric = self.metric_var.get()
        
        if not badge_display or not metric:
            return
        
        # Extract actual badge name from display string (e.g., "Badge10 - Andrew" -> "Badge10")
        badge_name = badge_display.split(' - ')[0] if ' - ' in badge_display else badge_display
        
        # Filter data for selected badge
        badge_data = self.data[self.data['Badge_Name'] == badge_name].copy()
        badge_data = badge_data.sort_values('Timestamp')
        
        # Clear and plot
        self.ax.clear()
        self.ax.plot(badge_data['Timestamp'], badge_data[metric], 'b-', alpha=0.7, linewidth=1)
        
        # Draw existing labels
        self.draw_existing_labels()
        
        # Create title with person name if available
        if self.has_person_names and badge_name in self.badge_to_person:
            title = f'{badge_name} - {self.badge_to_person[badge_name]} - {metric}'
        else:
            title = f'{badge_name} - {metric}'
        
        self.ax.set_xlabel('Time')
        self.ax.set_ylabel(metric)
        self.ax.set_title(title)
        self.ax.grid(True, alpha=0.3)
        
        # Format x-axis
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        self.ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=1))
        plt.setp(self.ax.xaxis.get_majorticklabels(), rotation=45)
        
        self.fig.tight_layout()
        self.canvas.draw()
    
    def draw_existing_labels(self):
        """Draw existing labels on the plot"""
        # Extract actual badge name from display string
        badge_display = self.badge_var.get()
        badge_name = badge_display.split(' - ')[0] if ' - ' in badge_display else badge_display
        
        for i, label in enumerate(self.labels):
            if label['badge'] == badge_name:
                color = 'green' if label['label'] == 'active' else 'red'
                rect = Rectangle((mdates.date2num(label['start']), self.ax.get_ylim()[0]),
                               mdates.date2num(label['end']) - mdates.date2num(label['start']),
                               self.ax.get_ylim()[1] - self.ax.get_ylim()[0],
                               alpha=0.3, facecolor=color, edgecolor='darkgray', linewidth=1.5)
                rect.label_index = i  # Store label index for deletion
                self.ax.add_patch(rect)
        
        # Update label count
        if hasattr(self, 'label_count_label'):
            badge_label_count = sum(1 for lbl in self.labels if lbl['badge'] == badge_name)
            self.label_count_label.config(text=f"Labels: {len(self.labels)} total ({badge_label_count} on current badge)")
    
    def on_press(self, event):
        """Handle mouse press for selection"""
        if event.inaxes != self.ax:
            return
        
        # Right-click to delete label
        if event.button == 3:  # Right mouse button
            self.delete_label_at_position(event.xdata)
            return
        
        # Left-click for selection
        if event.button == 1:
            # Clear any existing selection first
            self.clear_selection()
            self.selection_start = event.xdata
            print(f"[DEBUG] Mouse press at {event.xdata}")
        
    def on_motion(self, event):
        """Handle mouse motion for selection"""
        if self.selection_start is None or event.inaxes != self.ax or event.xdata is None:
            return
            
        # Store the current selection end for drawing
        self.selection_end_temp = event.xdata
        
        # Redraw the plot with the current selection
        self.update_plot_with_selection()
    
    def update_plot_with_selection(self):
        """Update the plot and show current selection"""
        # Get current selections
        badge_display = self.badge_var.get()
        metric = self.metric_var.get()
        
        if not badge_display or not metric:
            return
        
        # Extract actual badge name from display string
        badge_name = badge_display.split(' - ')[0] if ' - ' in badge_display else badge_display
        
        # Filter data for selected badge
        badge_data = self.data[self.data['Badge_Name'] == badge_name].copy()
        badge_data = badge_data.sort_values('Timestamp')
        
        # Clear and plot
        self.ax.clear()
        self.ax.plot(badge_data['Timestamp'], badge_data[metric], 'b-', alpha=0.7, linewidth=1)
        
        # Draw existing labels
        self.draw_existing_labels()
        
        # Draw current selection if active
        if self.selection_start is not None and hasattr(self, 'selection_end_temp'):
            start_x = min(self.selection_start, self.selection_end_temp)
            width = abs(self.selection_end_temp - self.selection_start)
            
            if width > 0:
                rect = Rectangle((start_x, self.ax.get_ylim()[0]),
                               width,
                               self.ax.get_ylim()[1] - self.ax.get_ylim()[0],
                               alpha=0.2, facecolor='blue')
                self.ax.add_patch(rect)
        
        # Create title with person name if available
        if self.has_person_names and badge_name in self.badge_to_person:
            title = f'{badge_name} - {self.badge_to_person[badge_name]} - {metric}'
        else:
            title = f'{badge_name} - {metric}'
        
        self.ax.set_xlabel('Time')
        self.ax.set_ylabel(metric)
        self.ax.set_title(title)
        self.ax.grid(True, alpha=0.3)
        
        # Format x-axis
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        self.ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=1))
        plt.setp(self.ax.xaxis.get_majorticklabels(), rotation=45)
        
        self.fig.tight_layout()
        self.canvas.draw_idle()
    
    def on_release(self, event):
        """Handle mouse release for selection"""
        if self.selection_start is None or event.inaxes != self.ax or event.xdata is None:
            self.clear_selection()
            return
            
        self.selection_end = event.xdata
        print(f"[DEBUG] Mouse release at {event.xdata}")

        # Convert from matplotlib dates to datetime and make timezone-naive
        try:
            start_time = mdates.num2date(min(self.selection_start, self.selection_end)).replace(tzinfo=None)
            end_time = mdates.num2date(max(self.selection_start, self.selection_end)).replace(tzinfo=None)
            
            self.status_label.config(text=f"Selected: {start_time.strftime('%H:%M:%S')} to {end_time.strftime('%H:%M:%S')} - Use label buttons to classify")
            
            # Store final selection for labeling
            self.final_selection_start = self.selection_start
            self.final_selection_end = self.selection_end
            
        except Exception as e:
            print(f"[ERROR] Failed to convert selection times: {e}")
            self.clear_selection()
    
    def label_selection(self, label):
        """Label the current selection"""
        if not hasattr(self, 'final_selection_start') or not hasattr(self, 'final_selection_end'):
            messagebox.showwarning("Warning", "Please select a time period first by clicking and dragging on the graph")
            return
        
        # Convert from matplotlib dates to datetime and make timezone-naive
        try:
            start_time = mdates.num2date(min(self.final_selection_start, self.final_selection_end)).replace(tzinfo=None)
            end_time = mdates.num2date(max(self.final_selection_start, self.final_selection_end)).replace(tzinfo=None)
            
            # Extract actual badge name from display string
            badge_display = self.badge_var.get()
            badge_name = badge_display.split(' - ')[0] if ' - ' in badge_display else badge_display
            
            # Check if we should apply to all badges
            if self.apply_to_all_var.get():
                # Apply to all badges
                for badge in self.data['Badge_Name'].unique():
                    self.labels.append({
                        'badge': badge,
                        'start': start_time,
                        'end': end_time,
                        'label': label
                    })
                label_text = "Active" if label == "active" else "Not Active"
                self.status_label.config(text=f"Labeled as '{label_text}' for ALL badges - Total labels: {len(self.labels)}")
            else:
                # Apply to current badge only
                self.labels.append({
                    'badge': badge_name,
                    'start': start_time,
                    'end': end_time,
                    'label': label
                })
                label_text = "Active" if label == "active" else "Not Active"
                self.status_label.config(text=f"Labeled as '{label_text}' - Total labels: {len(self.labels)}")
            
            # Clear selection and update plot
            self.clear_selection()
            self.update_plot()
            
        except Exception as e:
            print(f"[ERROR] Failed to label selection: {e}")
            messagebox.showerror("Error", f"Failed to label selection: {e}")
            self.clear_selection()
    
    def clear_selection(self):
        """Clear current selection"""
        self.selection_start = None
        self.selection_end = None
        self.selection_rect = None
        
        # Clear temporary selection variables
        if hasattr(self, 'selection_end_temp'):
            delattr(self, 'selection_end_temp')
        if hasattr(self, 'final_selection_start'):
            delattr(self, 'final_selection_start')
        if hasattr(self, 'final_selection_end'):
            delattr(self, 'final_selection_end')
        
        # Update plot to remove selection rectangle
        self.update_plot()
        
        # Update status
        if hasattr(self, 'status_label'):
            self.status_label.config(text="Ready to select - click and drag to select | Shortcuts: A=Active, N=Not Active, Delete=Remove label")
    
    def track_cursor_position(self, event):
        """Track cursor position for label management"""
        if event.inaxes == self.ax and event.xdata is not None:
            self.cursor_time = event.xdata
    
    def delete_label_at_cursor(self):
        """Delete label at current cursor position"""
        if self.cursor_time is not None:
            self.delete_label_at_position(self.cursor_time)
    
    def delete_label_at_position(self, time_position):
        """Delete label at the given time position"""
        if time_position is None:
            return
        
        # Extract actual badge name from display string
        badge_display = self.badge_var.get()
        badge_name = badge_display.split(' - ')[0] if ' - ' in badge_display else badge_display
        
        # Convert matplotlib time to datetime
        click_time = mdates.num2date(time_position).replace(tzinfo=None)
        
        # Find label at this position
        label_to_delete = None
        for i, label in enumerate(self.labels):
            if label['badge'] == badge_name:
                label_start = self.normalize_datetime(label['start'])
                label_end = self.normalize_datetime(label['end'])
                
                if label_start <= click_time <= label_end:
                    label_to_delete = i
                    break
        
        if label_to_delete is not None:
            deleted_label = self.labels[label_to_delete]
            label_type = deleted_label['label']
            self.labels.pop(label_to_delete)
            self.status_label.config(text=f"Deleted '{label_type}' label - Total labels: {len(self.labels)}")
            self.update_plot()
            print(f"[DEBUG] Deleted label at index {label_to_delete}")
        else:
            self.status_label.config(text="No label found at cursor position")
    
    def show_label_manager(self):
        """Show a window with all current labels for review and management"""
        manager_window = tk.Toplevel(self.root)
        manager_window.title("Label Manager")
        manager_window.geometry("800x500")
        
        # Create main frame
        main_frame = ttk.Frame(manager_window, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(main_frame, text="All Labels", font=('Arial', 14, 'bold'))
        title_label.pack(pady=(0, 10))
        
        # Create scrollable frame
        canvas = tk.Canvas(main_frame)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Create header
        header_frame = ttk.Frame(scrollable_frame)
        header_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(header_frame, text="Badge", font=('Arial', 10, 'bold'), width=15).pack(side=tk.LEFT, padx=5)
        ttk.Label(header_frame, text="Start Time", font=('Arial', 10, 'bold'), width=20).pack(side=tk.LEFT, padx=5)
        ttk.Label(header_frame, text="End Time", font=('Arial', 10, 'bold'), width=20).pack(side=tk.LEFT, padx=5)
        ttk.Label(header_frame, text="Label", font=('Arial', 10, 'bold'), width=12).pack(side=tk.LEFT, padx=5)
        ttk.Label(header_frame, text="Actions", font=('Arial', 10, 'bold'), width=10).pack(side=tk.LEFT, padx=5)
        
        # Add separator
        ttk.Separator(scrollable_frame, orient='horizontal').pack(fill=tk.X, padx=5, pady=5)
        
        # Display each label
        for idx, label in enumerate(self.labels):
            label_frame = ttk.Frame(scrollable_frame)
            label_frame.pack(fill=tk.X, padx=5, pady=2)
            
            # Badge name with person if available
            if self.has_person_names and label['badge'] in self.badge_to_person:
                badge_display = f"{label['badge']} ({self.badge_to_person[label['badge']]})"
            else:
                badge_display = label['badge']
            
            ttk.Label(label_frame, text=badge_display, width=15).pack(side=tk.LEFT, padx=5)
            ttk.Label(label_frame, text=label['start'].strftime('%Y-%m-%d %H:%M:%S'), width=20).pack(side=tk.LEFT, padx=5)
            ttk.Label(label_frame, text=label['end'].strftime('%Y-%m-%d %H:%M:%S'), width=20).pack(side=tk.LEFT, padx=5)
            
            # Color-coded label type
            label_color = 'green' if label['label'] == 'active' else 'red'
            label_text = label['label'].upper()
            label_widget = tk.Label(label_frame, text=label_text, width=12, fg=label_color, font=('Arial', 9, 'bold'))
            label_widget.pack(side=tk.LEFT, padx=5)
            
            # Delete button for this label
            delete_btn = ttk.Button(
                label_frame,
                text="Delete",
                width=10,
                command=lambda i=idx: self.delete_label_by_index(i, manager_window)
            )
            delete_btn.pack(side=tk.LEFT, padx=5)
        
        # Pack canvas and scrollbar
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Summary at bottom
        summary_frame = ttk.Frame(manager_window, padding=10)
        summary_frame.pack(fill=tk.X)
        
        active_count = sum(1 for lbl in self.labels if lbl['label'] == 'active')
        not_active_count = sum(1 for lbl in self.labels if lbl['label'] == 'not_active')
        
        summary_text = f"Total: {len(self.labels)} labels | Active: {active_count} | Not Active: {not_active_count}"
        ttk.Label(summary_frame, text=summary_text, font=('Arial', 11)).pack()
        
        # Close button
        ttk.Button(summary_frame, text="Close", command=manager_window.destroy).pack(pady=10)
    
    def delete_label_by_index(self, index, window):
        """Delete a label by its index from the label manager"""
        if 0 <= index < len(self.labels):
            deleted_label = self.labels[index]
            self.labels.pop(index)
            self.update_plot()
            window.destroy()  # Close and reopen to refresh
            self.show_label_manager()  # Reopen with updated list

    def prompt_auto_label(self):
        """Ask user for auto-label parameters and run auto-labeling"""
        if self.data is None:
            messagebox.showwarning("Warning", "No data loaded to auto-label")
            return
        
        # Ask for sound threshold
        sound_threshold = simpledialog.askinteger(
            "Auto-label Settings",
            f"Sound level threshold for 'active' classification:\nDefault: {SOUND_LEVEL_THRESHOLD}",
            initialvalue=SOUND_LEVEL_THRESHOLD,
            minvalue=0,
            maxvalue=20000
        )
        if sound_threshold is None:
            return
        
        # Ask for acceleration threshold
        accel_threshold = simpledialog.askfloat(
            "Auto-label Settings",
            f"Acceleration threshold for 'active' classification:\nDefault: {ACCELERATION_THRESHOLD} (typical motion)",
            initialvalue=ACCELERATION_THRESHOLD,
            minvalue=0.0,
            maxvalue=10.0
        )
        if accel_threshold is None:
            return
        
        # Ask for sound weight (acceleration will be 1 - sound_weight)
        sound_weight = simpledialog.askfloat(
            "Auto-label Settings",
            f"Sound weight (0.0 to 1.0):\n{SOUND_WEIGHT} = {SOUND_WEIGHT*100:.0f}% sound, {(1-SOUND_WEIGHT)*100:.0f}% acceleration\nHigher = more emphasis on sound",
            initialvalue=SOUND_WEIGHT,
            minvalue=0.0,
            maxvalue=1.0
        )
        if sound_weight is None:
            return

        min_dur = simpledialog.askinteger(
            "Auto-label Settings",
            "Minimum contiguous duration (seconds) to label:\nDefault: 2",
            initialvalue=2,
            minvalue=1
        )
        if min_dur is None:
            return

        # Remove any previously auto-generated labels so repeated runs replace them
        self.labels = [lbl for lbl in self.labels if lbl.get('source') != 'auto']

        counts = self.auto_label_combined(
            sound_threshold=sound_threshold,
            accel_threshold=accel_threshold,
            sound_weight=sound_weight,
            min_duration_seconds=min_dur
        )
        
        accel_weight = 1.0 - sound_weight
        messagebox.showinfo(
            "Auto-label Complete",
            f"Created {counts.get('active',0)} 'active' and {counts.get('not_active',0)} 'not_active' labels.\n\n"
            f"Settings:\n"
            f"  Sound threshold: {sound_threshold}\n"
            f"  Acceleration threshold: {accel_threshold}\n"
            f"  Weights: {sound_weight:.0%} sound, {accel_weight:.0%} acceleration"
        )
        self.update_plot()

    def auto_label_combined(self, sound_threshold=None, accel_threshold=None, sound_weight=None, min_duration_seconds=2):
        """Auto-label contiguous periods as 'active' or 'not_active' using combined sound and acceleration.

        - sound_threshold: numeric threshold for sound level (default: SOUND_LEVEL_THRESHOLD)
        - accel_threshold: numeric threshold for acceleration (default: ACCELERATION_THRESHOLD)
        - sound_weight: weight for sound 0.0 to 1.0 (default: SOUND_WEIGHT), acceleration gets (1 - sound_weight)
        - min_duration_seconds: minimum contiguous run length to create a label

        Returns a dict with counts: {'active': n, 'not_active': m}
        """
        if sound_threshold is None:
            sound_threshold = SOUND_LEVEL_THRESHOLD
        if accel_threshold is None:
            accel_threshold = ACCELERATION_THRESHOLD
        if sound_weight is None:
            sound_weight = SOUND_WEIGHT
        
        accel_weight = 1.0 - sound_weight

        counts = {'active': 0, 'not_active': 0}

        for badge in self.data['Badge_Name'].unique():
            badge_data = self.data[self.data['Badge_Name'] == badge].sort_values('Timestamp').copy()
            if badge_data.empty:
                continue

            # Normalize sound and acceleration to 0-1 scale for comparison
            # Sound: 1 if >= threshold, 0 otherwise
            sound_active = (badge_data['Sound_Level'].fillna(0) >= sound_threshold).astype(float)
            
            # Acceleration: 1 if >= threshold, 0 otherwise
            accel_active = (badge_data['Acceleration'].fillna(0) >= accel_threshold).astype(float)
            
            # Combine with weighted average
            combined_score = (sound_weight * sound_active) + (accel_weight * accel_active)
            
            # Consider active if combined score >= 0.5 (majority vote)
            mask = combined_score >= 0.5
            badge_data = badge_data.assign(_mask=mask)

            # Identify contiguous runs where mask value is constant
            badge_data['_run'] = (badge_data['_mask'] != badge_data['_mask'].shift()).cumsum()
            grouped = badge_data.groupby('_run')

            for _, grp in grouped:
                current_mask = bool(grp['_mask'].iloc[0])
                start = grp['Timestamp'].iloc[0]
                end = grp['Timestamp'].iloc[-1]
                duration = (end - start).total_seconds()

                if duration < min_duration_seconds:
                    continue

                label_name = 'active' if current_mask else 'not_active'
                # Append label (ensure tz-naive) and mark as auto-generated
                self.labels.append({
                    'badge': badge,
                    'start': start.replace(tzinfo=None) if hasattr(start, 'tzinfo') else start,
                    'end': end.replace(tzinfo=None) if hasattr(end, 'tzinfo') else end,
                    'label': label_name,
                    'source': 'auto'
                })
                counts[label_name] = counts.get(label_name, 0) + 1

        return counts
    
    def calculate_rolling_statistics(self, badge_data, window_seconds=20):
        """Calculate rolling statistics for sound and acceleration over time windows"""
        badge_data = badge_data.sort_values('Timestamp').copy()
        
        # Set timestamp as index for rolling calculations
        badge_data_indexed = badge_data.set_index('Timestamp')
        
        # Convert window_seconds to pandas timedelta
        window_size = f'{window_seconds}s'
        
        # Calculate rolling statistics for Sound_Level
        badge_data['sound_min_20s'] = badge_data_indexed['Sound_Level'].rolling(window=window_size, min_periods=1).min().values
        badge_data['sound_max_20s'] = badge_data_indexed['Sound_Level'].rolling(window=window_size, min_periods=1).max().values
        badge_data['sound_mean_20s'] = badge_data_indexed['Sound_Level'].rolling(window=window_size, min_periods=1).mean().values
        badge_data['sound_std_20s'] = badge_data_indexed['Sound_Level'].rolling(window=window_size, min_periods=1).std().values
        
        # Calculate rolling statistics for Acceleration
        badge_data['accel_min_20s'] = badge_data_indexed['Acceleration'].rolling(window=window_size, min_periods=1).min().values
        badge_data['accel_max_20s'] = badge_data_indexed['Acceleration'].rolling(window=window_size, min_periods=1).max().values
        badge_data['accel_mean_20s'] = badge_data_indexed['Acceleration'].rolling(window=window_size, min_periods=1).mean().values
        badge_data['accel_std_20s'] = badge_data_indexed['Acceleration'].rolling(window=window_size, min_periods=1).std().values
        
        # Fill NaN values with 0 for std (happens when there's only 1 data point)
        badge_data['sound_std_20s'] = badge_data['sound_std_20s'].fillna(0)
        badge_data['accel_std_20s'] = badge_data['accel_std_20s'].fillna(0)
        
        return badge_data
    
    def process_and_export(self):
        """Process all badge data and export to CSV"""
        if len(self.labels) == 0:
            response = messagebox.askyesno("Warning", 
                                         "No labels have been created. Do you want to continue anyway? "
                                         "All data will be labeled as 'unknown'.")
            if not response:
                return
        
        print("Processing badge data...")
        
        # Create a copy of the original data
        processed_data = self.data.copy()
        
        # Calculate rolling statistics for each badge
        all_processed_data = []
        badges = processed_data['Badge_Name'].unique()
        
        for badge in badges:
            if self.has_person_names and badge in self.badge_to_person:
                print(f"Calculating statistics for {badge} ({self.badge_to_person[badge]})...")
            else:
                print(f"Calculating statistics for {badge}...")
            badge_data = processed_data[processed_data['Badge_Name'] == badge]
            
            # Calculate rolling statistics
            badge_with_stats = self.calculate_rolling_statistics(badge_data, window_seconds=20)
            all_processed_data.append(badge_with_stats)
        
        # Combine all badge data back together
        processed_data = pd.concat(all_processed_data, ignore_index=True)
        processed_data = processed_data.sort_values(['Badge_Name', 'Timestamp']).reset_index(drop=True)
        
        # Add activity labels to each data point
        processed_data['activity_label'] = 'unknown'
        
        for _, row in processed_data.iterrows():
            badge_name = row['Badge_Name']
            timestamp = self.normalize_datetime(row['Timestamp'])
            
            # Find matching label for this data point
            for label in self.labels:
                if label['badge'] == badge_name:
                    label_start = self.normalize_datetime(label['start'])
                    label_end = self.normalize_datetime(label['end'])
                    
                    if label_start <= timestamp <= label_end:
                        processed_data.loc[_, 'activity_label'] = label['label']
                        break
        
        # Generate timestamp and create session folder
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        session_folder = self.output_folder / f"session_{timestamp}"
        session_folder.mkdir(exist_ok=True)
        
        # Generate output files in session folder
        output_file = session_folder / f"processed_badge_data_{timestamp}.csv"
        labels_file = session_folder / f"data_labels_{timestamp}.json"
        summary_file = session_folder / f"processing_summary_{timestamp}.txt"
        
        # Export to CSV
        processed_data.to_csv(output_file, index=False)
        
        # Also save labels for reference
        with open(labels_file, 'w') as f:
            json.dump([{
                'badge': label['badge'],
                'start': label['start'].isoformat(),
                'end': label['end'].isoformat(),
                'label': label['label']
            } for label in self.labels], f, indent=2)
        
        # Create detailed summary
        activity_counts = processed_data['activity_label'].value_counts()
        badges = processed_data['Badge_Name'].unique()
        
        # Create badge list with person names if available
        if self.has_person_names:
            badge_list = ', '.join([f"{badge} ({self.badge_to_person[badge]})" for badge in sorted(badges)])
        else:
            badge_list = ', '.join(sorted(badges))
        
        summary_text = f"""Badge Data Processing Summary
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Processing Configuration:
- Total data points processed: {len(processed_data)}
- Badges processed: {len(badges)}
- Badge names: {badge_list}
- Labels created: {len(self.labels)}

Activity Distribution:
{activity_counts.to_string()}

Data Quality:
- Data points per badge: {processed_data.groupby('Badge_Name').size().to_dict()}
- Total labeled points: {len(processed_data[processed_data['activity_label'] != 'unknown'])}

Output Files:
- Processed data: {output_file.name}
- Activity labels: {labels_file.name}
- This summary: {summary_file.name}

Data Columns:
- Timestamp: Original timestamp of data point
- Badge_Name: Name of the badge"""
        
        if self.has_person_names:
            summary_text += """
- Person_Name: Name of the person wearing the badge"""
        
        summary_text += """
- Sound_Level: Sound level measurement
- Acceleration: Acceleration measurement  
- Raw_Data: Original raw data string
- sound_min_20s: Minimum sound level in 20-second rolling window
- sound_max_20s: Maximum sound level in 20-second rolling window
- sound_mean_20s: Mean sound level in 20-second rolling window
- sound_std_20s: Standard deviation of sound level in 20-second rolling window
- accel_min_20s: Minimum acceleration in 20-second rolling window
- accel_max_20s: Maximum acceleration in 20-second rolling window
- accel_mean_20s: Mean acceleration in 20-second rolling window
- accel_std_20s: Standard deviation of acceleration in 20-second rolling window
- activity_label: active, not_active, or unknown
"""
        
        # Save summary to file
        with open(summary_file, 'w') as f:
            f.write(summary_text)
        
        # Show completion message
        completion_msg = f"""Processing Complete!

Session folder created: {session_folder.name}

Files saved:
✓ {output_file.name}
✓ {labels_file.name} 
✓ {summary_file.name}

Summary:
- Total data points: {len(processed_data)}
- Badges processed: {len(badges)}
- Labels created: {len(self.labels)}

The application will close automatically in 3 seconds.
        """
        
        messagebox.showinfo("Processing Complete", completion_msg)
        print(summary_text)
        
        # Auto-close after processing
        self.root.after(3000, self.auto_close)  # Close after 3 seconds
    
    def auto_close(self):
        """Automatically close the application"""
        print("Auto-closing application...")
        self.root.quit()
        self.root.destroy()
    
    def run(self):
        """Main execution function"""
        print("=== Badge Data Processing Tool ===")
        print("This tool will help you process badge data for AI analysis")
        print()
        
        # Select and load data file
        file_path = self.select_file()
        if not file_path or not self.load_data(file_path):
            print("Failed to load data file. Exiting.")
            return
        
        # Create and run labeling GUI
        print("Starting labeling interface...")
        root = self.create_labeling_gui()
        root.mainloop()

if __name__ == "__main__":
    processor = BadgeDataProcessor()
    processor.run()