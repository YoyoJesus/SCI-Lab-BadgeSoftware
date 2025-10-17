import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import csv
import time
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Global data storage
plot_data = []
badge_colors = {}  # Consistent colors for each badge
badge_toggles = {}  # Toggle states for each badge
badge_order = []  # Maintain consistent badge order for legend
root = None
canvas = None
toggle_frame = None

def read_latest_csv():
    """Read the most recent CSV file in the directory"""
    # Look for badge CSV files in the 'badge_data' subfolder
    badge_data_dir = Path('..') / 'badge_data'
    if not badge_data_dir.exists():
        badge_data_dir = Path('badge_data')  # fallback for direct run from root
    csv_files = list(badge_data_dir.glob('AllBadges_data_*.csv'))
    
    # If no real data files, try the test file
    if not csv_files:
        test_file = Path('test_badge_data.csv')
        if test_file.exists():
            csv_files = [test_file]
        else:
            return []
    
    # Get the most recent file
    latest_file = max(csv_files, key=os.path.getctime)
    
    data = []
    import traceback
    try:
        print(f"[DEBUG] Attempting to read CSV: {latest_file}")
        with open(latest_file, 'r') as file:
            reader = csv.DictReader(file)
            print(f"[DEBUG] CSV columns: {reader.fieldnames}")
            for row in reader:
                try:
                    data.append({
                        'badge_name': row['Badge_Name'],
                        'sound': float(row['Sound_Level']) if row['Sound_Level'] != 'N/A' else 0,
                        'rssi': float(row['RSSI']) if row['RSSI'] != 'N/A' else 0,
                        'acceleration': float(row['Acceleration']) if row['Acceleration'] != 'N/A' else 0
                    })
                except Exception as row_e:
                    print(f"[ERROR] Problem with row: {row}\n{row_e}")
                    traceback.print_exc()
    except Exception as e:
        print(f"[ERROR] Exception reading CSV '{latest_file}': {e}")
        traceback.print_exc()
        print(f"Available columns: {list(reader.fieldnames) if 'reader' in locals() else 'Unknown'}")
    return data

def assign_badge_color(badge_name):
    """Assign a consistent color to a badge"""
    global badge_colors, badge_order
    if badge_name not in badge_colors:
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', 
                 '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
        color_index = len(badge_colors) % len(colors)
        badge_colors[badge_name] = colors[color_index]
        # Initialize toggle state for new badge
        badge_toggles[badge_name] = True
        # Add to badge order for consistent legend positioning
        if badge_name not in badge_order:
            badge_order.append(badge_name)
    return badge_colors[badge_name]

def toggle_all_badges(state):
    """Toggle all badges on/off"""
    for badge_name in badge_colors.keys():
        badge_toggles[badge_name] = state
        # Update the checkbox variables if they exist
        var_name = f"{badge_name}_var"
        if var_name in badge_toggles:
            badge_toggles[var_name].set(state)

def create_toggle_controls():
    """Create toggle controls for each badge"""
    global toggle_frame, root
    
    # Clear existing controls
    for widget in toggle_frame.winfo_children():
        widget.destroy()
    
    # Add title with larger, more visible text
    title_label = tk.Label(toggle_frame, text="BADGE CONTROLS", 
                          font=('Arial', 14, 'bold'), 
                          bg='darkblue', fg='white', 
                          relief='raised', borderwidth=2)
    title_label.pack(fill='x', pady=5, padx=5)
    
    # Add master controls frame with high visibility
    master_frame = tk.Frame(toggle_frame, bg='lightblue', relief='raised', borderwidth=2)
    master_frame.pack(fill='x', padx=5, pady=10)
    
    master_label = tk.Label(master_frame, text="Master Controls:", 
                           font=('Arial', 11, 'bold'), bg='lightblue')
    master_label.pack(pady=5)
    
    # Master toggle buttons with better visibility
    button_frame = tk.Frame(master_frame, bg='lightblue')
    button_frame.pack(pady=5)
    
    show_all_btn = tk.Button(button_frame, text="SHOW ALL", 
                            command=lambda: toggle_all_badges(True), 
                            bg='green', fg='white', 
                            font=('Arial', 10, 'bold'),
                            relief='raised', borderwidth=3,
                            width=8, height=1)
    show_all_btn.pack(side='left', padx=5)
    
    hide_all_btn = tk.Button(button_frame, text="HIDE ALL", 
                            command=lambda: toggle_all_badges(False), 
                            bg='red', fg='white', 
                            font=('Arial', 10, 'bold'),
                            relief='raised', borderwidth=3,
                            width=8, height=1)
    hide_all_btn.pack(side='left', padx=5)
    
    # Individual badge controls label
    individual_label = tk.Label(toggle_frame, text="Individual Badge Controls:", 
                               font=('Arial', 12, 'bold'), 
                               bg='white')
    individual_label.pack(pady=(10, 5))
    
    # Show badges found message if no badges detected yet
    if not badge_order:
        waiting_label = tk.Label(toggle_frame, 
                               text="Waiting for badge data...\nCheckboxes will appear here\nwhen badges are detected", 
                               font=('Arial', 10, 'italic'), 
                               bg='lightyellow',
                               relief='sunken',
                               borderwidth=1)
        waiting_label.pack(fill='x', padx=10, pady=10)
    
    # Create toggle checkboxes for each badge in consistent order
    for badge_name in badge_order:
        if badge_name in badge_colors:
            color = badge_colors[badge_name]
            var = tk.BooleanVar(value=badge_toggles[badge_name])
            
            # Create a frame for each checkbox with high visibility
            checkbox_frame = tk.Frame(toggle_frame, 
                                    relief='raised', 
                                    borderwidth=2, 
                                    bg='lightyellow')
            checkbox_frame.pack(fill='x', padx=5, pady=3)
            
            # Color indicator (much larger and more visible)
            color_label = tk.Label(checkbox_frame, text="●", 
                                 fg=color, 
                                 font=('Arial', 24, 'bold'),
                                 bg='lightyellow')
            color_label.pack(side='left', padx=10)
            
            # Checkbox with much better styling and larger text
            checkbox = tk.Checkbutton(
                checkbox_frame, 
                text=badge_name, 
                variable=var,
                command=lambda name=badge_name, v=var: toggle_badge(name, v.get()),
                font=('Arial', 12, 'bold'),
                anchor='w',
                bg='lightyellow',
                activebackground='lightgreen',
                selectcolor='lightgreen',
                relief='flat'
            )
            checkbox.pack(side='left', fill='x', expand=True, padx=(0, 10), pady=5)
            
            # Store the variable reference
            badge_toggles[f"{badge_name}_var"] = var

def toggle_badge(badge_name, state):
    """Toggle visibility of a badge"""
    badge_toggles[badge_name] = state

def update_plot(frame):
    """Update the plot with new data"""
    global plot_data
    
    # Read fresh data from CSV
    new_data = read_latest_csv()
    if not new_data:
        return
    
    plot_data = new_data
    
    # Get last 100 points
    data_slice = plot_data[-100:] if len(plot_data) >= 100 else plot_data
    
    if not data_slice:
        return
    
    # Group data by badge and assign consistent colors
    badge_data = {}
    for entry in data_slice:
        badge_name = entry['badge_name']
        if badge_name not in badge_data:
            badge_data[badge_name] = {'sound': [], 'rssi': [], 'acceleration': []}
            # Assign consistent color for this badge
            assign_badge_color(badge_name)
        
        badge_data[badge_name]['sound'].append(entry['sound'])
        badge_data[badge_name]['rssi'].append(entry['rssi'])
        badge_data[badge_name]['acceleration'].append(entry['acceleration'])
    
    # Update toggle controls if new badges are detected
    current_badges = set(badge_order)
    new_badges = set(badge_data.keys()) - current_badges
    if new_badges:
        print(f"🔍 New badges detected: {new_badges}")
        create_toggle_controls()
    
    # Clear plots
    for ax in axs:
        ax.clear()
        ax.grid(True, alpha=0.3)
    
    # Plot data for each badge (only if toggle is enabled) in consistent order
    plotted_badges = []
    for badge_name in badge_order:
        if badge_name in badge_data and badge_toggles.get(badge_name, True):
            data = badge_data[badge_name]
            color = badge_colors[badge_name]
            
            if data['sound']:
                x = list(range(len(data['sound'])))
                axs[0].plot(x, data['sound'], color=color, label=badge_name, marker='o', markersize=1, linewidth=1.5)
                axs[1].plot(x, data['rssi'], color=color, label=badge_name, marker='o', markersize=1, linewidth=1.5)
                axs[2].plot(x, data['acceleration'], color=color, label=badge_name, marker='o', markersize=1, linewidth=1.5)
                plotted_badges.append(badge_name)
    
    # Add placeholder entries for consistent legend positioning
    for badge_name in badge_order:
        if badge_name in badge_colors and badge_name not in plotted_badges:
            color = badge_colors[badge_name]
            # Add invisible lines to maintain legend order
            axs[0].plot([], [], color=color, label=f"{badge_name} (hidden)", alpha=0.3, linestyle='--')
            axs[1].plot([], [], color=color, label=f"{badge_name} (hidden)", alpha=0.3, linestyle='--')
            axs[2].plot([], [], color=color, label=f"{badge_name} (hidden)", alpha=0.3, linestyle='--')
    
    # Set labels and titles with improved styling
    axs[0].set_ylabel('Sound Level', fontweight='bold')
    axs[0].set_title(f'Live Sound Level (Total points: {len(plot_data)})', fontweight='bold', pad=10)
    legend0 = axs[0].legend(loc='upper right', framealpha=0.9, fontsize=8, ncol=1)
    legend0.set_title("Badges", prop={'weight': 'bold'})
    
    axs[1].set_ylabel('RSSI (dBm)', fontweight='bold')
    axs[1].set_title('Live RSSI Signal Strength', fontweight='bold', pad=10)
    legend1 = axs[1].legend(loc='upper right', framealpha=0.9, fontsize=8, ncol=1)
    legend1.set_title("Badges", prop={'weight': 'bold'})
    
    axs[2].set_ylabel('Acceleration', fontweight='bold')
    axs[2].set_title('Live Acceleration', fontweight='bold', pad=10)
    axs[2].set_xlabel('Sample Index (Recent 100 points)', fontweight='bold')
    legend2 = axs[2].legend(loc='upper right', framealpha=0.9, fontsize=8, ncol=1)
    legend2.set_title("Badges", prop={'weight': 'bold'})
    
    # Improve plot appearance
    for ax in axs:
        ax.tick_params(labelsize=8)
        ax.set_facecolor('#f8f9fa')

def on_closing():
    """Handle window close event"""
    global root, ani
    try:
        if ani:
            ani.event_source.stop()
        plt.close('all')
        if root:
            root.quit()
            root.destroy()
    except:
        pass

if __name__ == "__main__":
    # Create the main window
    root = tk.Tk()
    root.title("Voice Badge Live Data Viewer")
    root.state('zoomed')  # Maximize window on Windows
    
    # Handle window close event
    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    # Create main frame
    main_frame = tk.Frame(root)
    main_frame.pack(fill='both', expand=True)
    
    # Create control panel frame (left side) - MUCH LARGER
    control_frame = tk.Frame(main_frame, width=400, bg='red', relief='solid', borderwidth=5)
    control_frame.pack(side='left', fill='y', padx=10, pady=10)
    control_frame.pack_propagate(False)  # Maintain fixed width
    
    # Create main toggle controls frame (this is where the badges will appear)
    toggle_frame = tk.Frame(control_frame, bg='yellow', relief='solid', borderwidth=3)
    toggle_frame.pack(fill='both', expand=True, padx=10, pady=10)
    
    # Create refresh rate control at the bottom
    refresh_frame = tk.Frame(control_frame, bg='lightblue', relief='solid', borderwidth=2)
    refresh_frame.pack(fill='x', pady=5)
    
    refresh_label = tk.Label(refresh_frame, text="Refresh Rate:", font=('Arial', 12, 'bold'), bg='lightblue')
    refresh_label.pack()
    
    refresh_var = tk.StringVar(value="500ms")
    refresh_options = ["250ms", "500ms", "1000ms", "2000ms"]
    refresh_menu = ttk.Combobox(refresh_frame, textvariable=refresh_var, values=refresh_options, state="readonly", font=('Arial', 11))
    refresh_menu.pack(pady=5)
    
    # Create plot frame (right side)
    plot_frame = tk.Frame(main_frame)
    plot_frame.pack(side='right', fill='both', expand=True, padx=5, pady=5)
    
    # Create figure and subplots
    fig, axs = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
    fig.patch.set_facecolor('#ffffff')
    
    # Embed plot in tkinter
    canvas = FigureCanvasTkAgg(fig, master=plot_frame)
    canvas.draw()
    canvas.get_tk_widget().pack(fill='both', expand=True)
    
    print("🎨 Starting enhanced live graph viewer...")
    print("📊 Features: Consistent colors, badge toggles, faster refresh!")
    print("🔄 Reading from CSV files in real-time...")
    
    # Check for available CSV files
    csv_files = list(Path('.').glob('Badge*_data_*.csv'))
    print(f"📋 Found {len(csv_files)} CSV files")
    if csv_files:
        latest_file = max(csv_files, key=os.path.getctime)
        print(f"📄 Latest file: {latest_file}")
    
    # Initialize toggle controls immediately (even if no badges detected yet)
    create_toggle_controls()
    
    # Function to update refresh rate
    def update_refresh_rate(*args):
        global ani
        rate_map = {"250ms": 250, "500ms": 500, "1000ms": 1000, "2000ms": 2000}
        new_interval = rate_map[refresh_var.get()]
        ani.event_source.interval = new_interval
        print(f"🔄 Refresh rate updated to {refresh_var.get()}")
    
    refresh_var.trace('w', update_refresh_rate)
    
    # Create animation with faster default refresh (500ms instead of 2000ms)
    ani = animation.FuncAnimation(fig, update_plot, interval=500, repeat=True, blit=False, cache_frame_data=False)
    
    plt.tight_layout()
    
    # Start the GUI
    root.mainloop()
