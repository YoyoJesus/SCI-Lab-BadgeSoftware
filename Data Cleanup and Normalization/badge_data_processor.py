#!/usr/bin/env python3
"""
Badge Data Processing Tool

This script processes badge data files and:
1. Allows user to label time periods as 'active' or 'not active'
2. Splits data by badge name
3. Calculates statistics (min, max, avg, std) over 20-second windows
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
from tkinter import ttk, messagebox, filedialog
import matplotlib.dates as mdates
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.patches import Rectangle
import json

class BadgeDataProcessor:
    def __init__(self):
        self.data = None
        self.processed_data = []
        self.labels = []  # Store time periods and their labels
        self.window_size = 20  # 20 seconds
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
        instructions = ttk.Label(main_frame, 
                                text="Instructions: Click and drag on the graph to select time periods, then label them as 'Active' or 'Not Active'",
                                font=('Arial', 12))
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
        badge_combo = ttk.Combobox(button_frame, textvariable=self.badge_var, 
                                  values=sorted(self.data['Badge_Name'].unique()))
        badge_combo.pack(side=tk.LEFT, padx=5)
        badge_combo.bind('<<ComboboxSelected>>', self.update_plot)
        badge_combo.set(sorted(self.data['Badge_Name'].unique())[0])
        
        # Metric selection
        ttk.Label(button_frame, text="Metric:").pack(side=tk.LEFT, padx=5)
        self.metric_var = tk.StringVar(value="Sound_Level")
        metric_combo = ttk.Combobox(button_frame, textvariable=self.metric_var,
                                   values=["Sound_Level", "RSSI", "Acceleration"])
        metric_combo.pack(side=tk.LEFT, padx=5)
        metric_combo.bind('<<ComboboxSelected>>', self.update_plot)
        
        # Label buttons
        ttk.Button(button_frame, text="Label as Active", 
                  command=lambda: self.label_selection("active")).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Label as Not Active", 
                  command=lambda: self.label_selection("not_active")).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear Selection", 
                  command=self.clear_selection).pack(side=tk.LEFT, padx=5)
        
        # Process button
        ttk.Button(button_frame, text="Process Data", 
                  command=self.process_and_export).pack(side=tk.RIGHT, padx=5)
        
        # Status label
        self.status_label = ttk.Label(main_frame, text="Ready to label data")
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
        self.selection_start = event.xdata
        
    def on_motion(self, event):
        """Handle mouse motion for selection"""
        if self.selection_start is None or event.inaxes != self.ax:
            return
            
        # Remove previous selection rectangle
        if self.selection_rect is not None:
            self.selection_rect.remove()
            
        # Draw new selection rectangle
        start_x = min(self.selection_start, event.xdata)
        width = abs(event.xdata - self.selection_start)
        self.selection_rect = Rectangle((start_x, self.ax.get_ylim()[0]),
                                       width,
                                       self.ax.get_ylim()[1] - self.ax.get_ylim()[0],
                                       alpha=0.2, facecolor='blue')
        self.ax.add_patch(self.selection_rect)
        self.canvas.draw()
    
    def on_release(self, event):
        """Handle mouse release for selection"""
        if self.selection_start is None or event.inaxes != self.ax:
            return
            
        self.selection_end = event.xdata
        
        # Convert from matplotlib dates to datetime and make timezone-naive
        start_time = mdates.num2date(min(self.selection_start, self.selection_end)).replace(tzinfo=None)
        end_time = mdates.num2date(max(self.selection_start, self.selection_end)).replace(tzinfo=None)
        
        self.status_label.config(text=f"Selected: {start_time.strftime('%H:%M:%S')} to {end_time.strftime('%H:%M:%S')}")
    
    def label_selection(self, label):
        """Label the current selection"""
        if self.selection_start is None or self.selection_end is None:
            messagebox.showwarning("Warning", "Please select a time period first")
            return
        
        # Convert from matplotlib dates to datetime and make timezone-naive
        start_time = mdates.num2date(min(self.selection_start, self.selection_end)).replace(tzinfo=None)
        end_time = mdates.num2date(max(self.selection_start, self.selection_end)).replace(tzinfo=None)
        
        # Add label
        self.labels.append({
            'badge': self.badge_var.get(),
            'start': start_time,
            'end': end_time,
            'label': label
        })
        
        self.status_label.config(text=f"Labeled {len(self.labels)} segments")
        self.clear_selection()
        self.update_plot()
    
    def clear_selection(self):
        """Clear current selection"""
        if self.selection_rect is not None:
            self.selection_rect.remove()
            self.selection_rect = None
        self.selection_start = None
        self.selection_end = None
        self.canvas.draw()
    
    def calculate_window_statistics(self, badge_data, window_size_seconds=20):
        """Calculate statistics over sliding windows"""
        badge_data = badge_data.sort_values('Timestamp')
        
        # Create time windows
        start_time = badge_data['Timestamp'].min()
        end_time = badge_data['Timestamp'].max()
        
        windows = []
        current_time = start_time
        
        while current_time < end_time:
            window_end = current_time + timedelta(seconds=window_size_seconds)
            
            # Get data in this window
            window_data = badge_data[
                (badge_data['Timestamp'] >= current_time) & 
                (badge_data['Timestamp'] < window_end)
            ]
            
            if len(window_data) > 0:
                # Calculate statistics
                stats = {
                    'window_start': current_time,
                    'window_end': window_end,
                    'window_center': current_time + timedelta(seconds=window_size_seconds/2),
                    'badge_name': badge_data['Badge_Name'].iloc[0],
                    'data_points': len(window_data),
                    
                    # Sound Level statistics
                    'sound_min': window_data['Sound_Level'].min(),
                    'sound_max': window_data['Sound_Level'].max(),
                    'sound_mean': window_data['Sound_Level'].mean(),
                    'sound_std': window_data['Sound_Level'].std(),
                    
                    # Acceleration statistics
                    'accel_min': window_data['Acceleration'].min(),
                    'accel_max': window_data['Acceleration'].max(),
                    'accel_mean': window_data['Acceleration'].mean(),
                    'accel_std': window_data['Acceleration'].std(),
                }
                
                # Find label for this window
                window_label = 'unknown'
                for label in self.labels:
                    if label['badge'] == stats['badge_name']:
                        # Normalize all datetime objects for safe comparison
                        label_start = self.normalize_datetime(label['start'])
                        label_end = self.normalize_datetime(label['end'])
                        window_time = self.normalize_datetime(current_time)
                        
                        if label_start <= window_time <= label_end:
                            window_label = label['label']
                            break
                
                stats['activity_label'] = window_label
                windows.append(stats)
            
            current_time += timedelta(seconds=window_size_seconds)
        
        return windows
    
    def process_and_export(self):
        """Process all badge data and export to CSV"""
        if len(self.labels) == 0:
            response = messagebox.askyesno("Warning", 
                                         "No labels have been created. Do you want to continue anyway? "
                                         "All data will be labeled as 'unknown'.")
            if not response:
                return
        
        print("Processing badge data...")
        
        all_windows = []
        badges = self.data['Badge_Name'].unique()
        
        for badge in badges:
            print(f"Processing {badge}...")
            badge_data = self.data[self.data['Badge_Name'] == badge]
            
            # Calculate windowed statistics
            windows = self.calculate_window_statistics(badge_data, self.window_size)
            all_windows.extend(windows)
        
        # Convert to DataFrame
        processed_df = pd.DataFrame(all_windows)
        
        # Generate timestamp and create session folder
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        session_folder = self.output_folder / f"session_{timestamp}"
        session_folder.mkdir(exist_ok=True)
        
        # Generate output files in session folder
        output_file = session_folder / f"processed_badge_data_{timestamp}.csv"
        labels_file = session_folder / f"data_labels_{timestamp}.json"
        summary_file = session_folder / f"processing_summary_{timestamp}.txt"
        
        # Export to CSV
        processed_df.to_csv(output_file, index=False)
        
        # Also save labels for reference
        with open(labels_file, 'w') as f:
            json.dump([{
                'badge': label['badge'],
                'start': label['start'].isoformat(),
                'end': label['end'].isoformat(),
                'label': label['label']
            } for label in self.labels], f, indent=2)
        
        # Create detailed summary
        activity_counts = processed_df['activity_label'].value_counts()
        summary_text = f"""Badge Data Processing Summary
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Processing Configuration:
- Total windows processed: {len(processed_df)}
- Badges processed: {len(badges)}
- Badge names: {', '.join(sorted(badges))}
- Labels created: {len(self.labels)}

Activity Distribution:
{activity_counts.to_string()}

Data Quality:
- Data points per badge: {processed_df.groupby('badge_name')['data_points'].sum().to_dict()}
- Average data points per window: {processed_df['data_points'].mean():.1f}

Output Files:
- Processed data: {output_file.name}
- Activity labels: {labels_file.name}
- This summary: {summary_file.name}

Statistics Calculated:
For each time window, the following statistics were calculated:
- Sound Level: min, max, mean, standard deviation
- Acceleration: min, max, mean, standard deviation
- Activity Label: active, not_active, or unknown
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
- Total windows: {len(processed_df)}
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