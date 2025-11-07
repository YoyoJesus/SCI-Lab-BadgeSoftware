#!/usr/bin/env python3
"""
Badge Data Processing Tool

This script processes badge data files and:
1. Allows user to label time periods as 'active' or 'not active'
2. Splits data by badge name
3. Labels individual data points based on time period selections
4. Exports processed data to CSV for AI tools

Author: Badge Data Processing Tool
Date: October 2025
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
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.patches import Rectangle
import json

# Default sound level threshold (can be overridden in the UI prompt).
# Values >= this threshold will be labeled 'active', below -> 'not_active'.
SOUND_LEVEL_THRESHOLD = 65

class BadgeDataProcessor:
    def __init__(self):
        self.data = None
        self.processed_data = []
        self.labels = []  # Store time periods and their labels
        self.output_folder = Path("processed_data")
        self.output_folder.mkdir(exist_ok=True)
        
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
            
            print(f"Loaded {len(self.data)} data points ({removed_count} duplicates removed)")
            print(f"Time range: {self.data['Timestamp'].min()} to {self.data['Timestamp'].max()}")
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

        # Control buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10)

        # Badge selection
        ttk.Label(button_frame, text="Select Badge:").pack(side=tk.LEFT, padx=5)
        self.badge_var = tk.StringVar()
        badge_combo = ttk.Combobox(
            button_frame,
            textvariable=self.badge_var,
            values=sorted(self.data['Badge_Name'].unique())
        )
        badge_combo.pack(side=tk.LEFT, padx=5)
        badge_combo.bind('<<ComboboxSelected>>', self.update_plot)
        badge_combo.set(sorted(self.data['Badge_Name'].unique())[0])

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

        # Auto-label button
        ttk.Button(
            button_frame,
            text="Auto-label by Sound",
            command=self.prompt_auto_label_sound
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
            text="Ready to select - click and drag on the graph to select a time period"
        )
        self.status_label.pack(pady=5)

        # Selection variables
        self.selection_start = None
        self.selection_end = None
        self.selection_rect = None

        # Bind mouse events
        self.canvas.mpl_connect('button_press_event', self.on_press)
        self.canvas.mpl_connect('button_release_event', self.on_release)
        self.canvas.mpl_connect('motion_notify_event', self.on_motion)

        # Initial plot
        self.update_plot()

        return self.root
    
    def update_plot(self, event=None):
        """Update the plot based on selected badge and metric"""
        badge_name = self.badge_var.get()
        metric = self.metric_var.get()
        
        if not badge_name or not metric:
            return
        
        # Filter data for selected badge
        badge_data = self.data[self.data['Badge_Name'] == badge_name].copy()
        badge_data = badge_data.sort_values('Timestamp')
        
        # Clear and plot
        self.ax.clear()
        self.ax.plot(badge_data['Timestamp'], badge_data[metric], 'b-', alpha=0.7, linewidth=1)
        
        # Draw existing labels
        self.draw_existing_labels()
        
        self.ax.set_xlabel('Time')
        self.ax.set_ylabel(metric)
        self.ax.set_title(f'{badge_name} - {metric}')
        self.ax.grid(True, alpha=0.3)
        
        # Format x-axis
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        self.ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=1))
        plt.setp(self.ax.xaxis.get_majorticklabels(), rotation=45)
        
        self.fig.tight_layout()
        self.canvas.draw()
    
    def draw_existing_labels(self):
        """Draw existing labels on the plot"""
        for label in self.labels:
            if label['badge'] == self.badge_var.get():
                color = 'green' if label['label'] == 'active' else 'red'
                rect = Rectangle((mdates.date2num(label['start']), self.ax.get_ylim()[0]),
                               mdates.date2num(label['end']) - mdates.date2num(label['start']),
                               self.ax.get_ylim()[1] - self.ax.get_ylim()[0],
                               alpha=0.3, facecolor=color)
                self.ax.add_patch(rect)
    
    def on_press(self, event):
        """Handle mouse press for selection"""
        if event.inaxes != self.ax:
            return
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
        badge_name = self.badge_var.get()
        metric = self.metric_var.get()
        
        if not badge_name or not metric:
            return
        
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
        
        self.ax.set_xlabel('Time')
        self.ax.set_ylabel(metric)
        self.ax.set_title(f'{badge_name} - {metric}')
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
        
        # Check if we have a valid selection (minimum width)
        if abs(self.selection_end - self.selection_start) < 0.001:  # Very small selection
            self.clear_selection()
            self.status_label.config(text="Selection too small - please drag to select a time range")
            return
        
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
            
            # Add label
            self.labels.append({
                'badge': self.badge_var.get(),
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
            self.status_label.config(text="Ready to select - click and drag on the graph to select a time period")

    def prompt_auto_label_sound(self):
        """Ask user for auto-label parameters and run auto-labeling"""
        if self.data is None:
            messagebox.showwarning("Warning", "No data loaded to auto-label")
            return
        # Ask for threshold (use default constant as initial value)
        threshold = simpledialog.askinteger(
            "Auto-label by Sound",
            f"Sound level threshold to mark 'active' (>= threshold = active).\nDefault: {SOUND_LEVEL_THRESHOLD}",
            initialvalue=SOUND_LEVEL_THRESHOLD,
            minvalue=0,
            maxvalue=1000
        )
        if threshold is None:
            return

        min_dur = simpledialog.askinteger(
            "Auto-label by Sound",
            "Minimum contiguous duration (seconds) to consider (e.g. 2):",
            initialvalue=2,
            minvalue=1
        )
        if min_dur is None:
            return

        # Remove any previously auto-generated labels so repeated runs replace them
        self.labels = [lbl for lbl in self.labels if lbl.get('source') != 'auto']

        counts = self.auto_label_by_sound(level_threshold=threshold, min_duration_seconds=min_dur)
        messagebox.showinfo("Auto-label Complete", f"Created {counts.get('active',0)} 'active' and {counts.get('not_active',0)} 'not_active' labels using threshold {threshold}.")
        self.update_plot()

    def auto_label_by_sound(self, level_threshold=None, min_duration_seconds=2):
        """Auto-label contiguous periods as 'active' or 'not_active' using a fixed level threshold.

        - level_threshold: numeric threshold; values >= threshold -> 'active', else 'not_active'
        - min_duration_seconds: minimum contiguous run length to create a label

        Returns a dict with counts: {'active': n, 'not_active': m}
        """
        if level_threshold is None:
            level_threshold = SOUND_LEVEL_THRESHOLD

        counts = {'active': 0, 'not_active': 0}

        for badge in self.data['Badge_Name'].unique():
            badge_data = self.data[self.data['Badge_Name'] == badge].sort_values('Timestamp').copy()
            if badge_data.empty:
                continue

            # Create mask: True=active, False=not_active. Treat NaN as False.
            mask = (badge_data['Sound_Level'].fillna(-np.inf) >= level_threshold)
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
        
        summary_text = f"""Badge Data Processing Summary
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Processing Configuration:
- Total data points processed: {len(processed_data)}
- Badges processed: {len(badges)}
- Badge names: {', '.join(sorted(badges))}
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
- Badge_Name: Name of the badge
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