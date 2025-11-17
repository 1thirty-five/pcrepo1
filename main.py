import tkinter as tk
from tkinter import ttk, simpledialog
import math
import multiprocessing
from multiprocessing import Process, Queue, Manager
import time
import random
import sys

DEFAULT_GRID = 32


def vehicle_movement_process(vehicle_id, path_points, speed, position_queue, traffic_light_queue, stop_event, junction_positions, grid_size):
    """
    Process function for simulating individual vehicle movement along a path.
    This runs in a separate process for parallel computation.
    
    Traffic light logic:
    - If approaching intersection (progress > 0.5) and light is green, vehicle enters junction
    - Once inside junction zone (within grid_size distance of junction center), ignore ALL lights
    - Only stops if outside junction and approaching red/yellow light
    """
    current_segment = 0
    progress = 0.0  # Progress along current segment (0.0 to 1.0)
    stopped = False
    inside_junction = False  # Track if vehicle is inside a junction zone
    
    def is_near_junction(position):
        """Check if position is within any junction zone."""
        px, py = position
        for junction_info in junction_positions:
            if isinstance(junction_info, dict):
                jx, jy = junction_info['position']
                jtype = junction_info.get('type', 'regular')
                
                # Roundabouts need larger tolerance to cover exit positions
                # Exit distance = octagon_radius + grid_size = 3*grid_size
                # Need large tolerance to ensure vehicles ignore ALL lights while inside/exiting
                if jtype == 'Roundabout':
                    tolerance = grid_size * 5.0  # Very large to cover entire roundabout + exits
                else:
                    tolerance = grid_size * 1.5
            else:
                # Legacy format: just position tuple
                jx, jy = junction_info
                tolerance = grid_size * 1.5
            
            dist = math.sqrt((px - jx)**2 + (py - jy)**2)
            if dist < tolerance:
                return True
        return False
    
    while not stop_event.is_set() and current_segment < len(path_points) - 1:
        # Get current segment
        start_point = path_points[current_segment]
        end_point = path_points[current_segment + 1]
        
        # Calculate segment length
        segment_length = math.sqrt((end_point[0] - start_point[0])**2 + 
                                   (end_point[1] - start_point[1])**2)
        
        # Calculate current position
        x = start_point[0] + (end_point[0] - start_point[0]) * progress
        y = start_point[1] + (end_point[1] - start_point[1]) * progress
        current_pos = (x, y)
        
        # Check if we're inside a junction zone
        was_inside = inside_junction
        inside_junction = is_near_junction(current_pos)
        
        # Debug: print when entering/exiting junction zone
        if inside_junction and not was_inside:
            print(f"Vehicle {vehicle_id} entered junction zone")
        elif not inside_junction and was_inside:
            print(f"Vehicle {vehicle_id} exited junction zone")
        
        # Check traffic light status only if NOT inside a junction
        if not inside_junction:
            try:
                # Non-blocking check for traffic light states
                while not traffic_light_queue.empty():
                    light_state = traffic_light_queue.get_nowait()
                    next_pos = end_point
                    
                    # Check if this light is at our destination
                    if light_state.get('position') == next_pos:
                        current_color = light_state.get('color')
                        
                        # Only stop if we're far from junction and light is red/yellow
                        if progress < 0.8:
                            if current_color in ['red', 'yellow']:
                                stopped = True
                            elif current_color == 'green':
                                stopped = False
            except:
                pass
        else:
            # Inside junction - never stop, ignore all lights
            stopped = False
        
        if not stopped:
            # Send position update to main process
            position_queue.put({
                'vehicle_id': vehicle_id,
                'position': current_pos,
                'segment': current_segment,
                'active': True
            })
            
            # Update progress based on speed and segment length
            # Speed is in pixels per frame, normalize by segment length
            if segment_length > 0:
                progress += speed / segment_length
            else:
                progress = 1.0
            
            # Move to next segment if current is complete
            if progress >= 1.0:
                progress = 0.0
                current_segment += 1
                stopped = False
        
        time.sleep(0.02)  # Update every 20ms for smoother movement
    
    # Vehicle reached end of path
    position_queue.put({
        'vehicle_id': vehicle_id,
        'position': None,
        'active': False
    })



class RoadConfigDialog(tk.Toplevel):
    """Dialog to configure road properties with auto-detected direction."""
    def __init__(self, parent, shape_type, road_points):
        super().__init__(parent)
        self.title('Road Configuration')
        self.result = None
        self.shape_type = shape_type
        self.road_points = road_points
        
        # Auto-detect road direction
        self.detected_direction = self.detect_road_direction()
        
        # Make dialog modal
        self.transient(parent)
        self.grab_set()
        
        # Center dialog
        self.geometry('400x250')
        
        # Show detected direction
        tk.Label(self, text='Road Configuration', font=('Arial', 14, 'bold')).pack(pady=(10, 5))
        
        # Display auto-detected direction
        direction_info = tk.Frame(self, bg='#e0e0e0', relief='ridge', bd=2)
        direction_info.pack(pady=10, padx=20, fill='x')
        tk.Label(direction_info, text='Auto-Detected Direction:', font=('Arial', 10, 'bold'), 
                bg='#e0e0e0').pack(pady=(5, 2))
        tk.Label(direction_info, text=self.detected_direction, font=('Arial', 12), 
                bg='#e0e0e0', fg='#0066cc').pack(pady=(2, 5))
        
        # Road type selection
        tk.Label(self, text='Road Type:', font=('Arial', 11, 'bold')).pack(pady=(10, 5))
        self.road_type_var = tk.StringVar(value='two_way')
        
        tk.Radiobutton(self, text='Two-Way Road (Bidirectional)', variable=self.road_type_var, 
                      value='two_way').pack(anchor='w', padx=40)
        tk.Radiobutton(self, text='One-Way Road', variable=self.road_type_var, 
                      value='one_way').pack(anchor='w', padx=40)
        
        # Buttons
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=20)
        ok_btn = tk.Button(btn_frame, text='OK', command=self.ok_clicked, width=10)
        ok_btn.pack(side='left', padx=5)
        tk.Button(btn_frame, text='Cancel', command=self.cancel_clicked, width=10).pack(side='left', padx=5)
        
        # Bind keyboard shortcuts
        self.bind('<Return>', lambda e: self.ok_clicked())  # Enter key
        self.bind('<space>', lambda e: self.ok_clicked())   # Space key
        self.bind('<Escape>', lambda e: self.cancel_clicked())  # Escape key
        
        # Set focus to the dialog
        self.focus_set()
        
        # Wait for dialog to close
        self.wait_window()
    
    def detect_road_direction(self):
        """Auto-detect road direction based on start and end points."""
        if len(self.road_points) < 2:
            return "Unknown"
        
        start = self.road_points[0]
        end = self.road_points[-1]
        
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        
        # Calculate angle in degrees
        angle = math.degrees(math.atan2(-dy, dx))  # Negative dy because y increases downward
        
        # Normalize to 0-360
        if angle < 0:
            angle += 360
        
        # Determine direction based on angle
        if 337.5 <= angle or angle < 22.5:
            return "East-West"
        elif 22.5 <= angle < 67.5:
            return "Northeast-Southwest"
        elif 67.5 <= angle < 112.5:
            return "North-South"
        elif 112.5 <= angle < 157.5:
            return "Northwest-Southeast"
        elif 157.5 <= angle < 202.5:
            return "East-West"
        elif 202.5 <= angle < 247.5:
            return "Northeast-Southwest"
        elif 247.5 <= angle < 292.5:
            return "North-South"
        else:  # 292.5 <= angle < 337.5
            return "Northwest-Southeast"
    
    def ok_clicked(self):
        """Store result and close dialog."""
        road_type = self.road_type_var.get()
        
        self.result = {
            'road_type': road_type,
            'detected_direction': self.detected_direction,
            'angle': self.calculate_angle()
        }
        
        self.destroy()
    
    def calculate_angle(self):
        """Calculate the actual angle of the road."""
        if len(self.road_points) < 2:
            return 0
        
        start = self.road_points[0]
        end = self.road_points[-1]
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        return math.degrees(math.atan2(-dy, dx))
    
    def cancel_clicked(self):
        """Close dialog without saving."""
        self.result = None
        self.destroy()


class TrafficLightTimingDialog(tk.Toplevel):
    """Dialog to configure traffic light timing."""
    def __init__(self, parent):
        super().__init__(parent)
        self.title('Traffic Light Timing Configuration')
        self.result = None
        
        # Make dialog modal
        self.transient(parent)
        self.grab_set()
        
        # Center dialog
        self.geometry('350x250')
        
        tk.Label(self, text='Set duration for each light color:', 
                font=('Arial', 12, 'bold')).pack(pady=(10, 15))
        
        # Green light duration
        green_frame = tk.Frame(self)
        green_frame.pack(pady=5)
        tk.Label(green_frame, text='Green Light Duration (seconds):', width=25, anchor='w').pack(side='left', padx=10)
        self.green_var = tk.StringVar(value='3')
        tk.Spinbox(green_frame, from_=1, to=30, textvariable=self.green_var, width=10).pack(side='left')
        
        # Yellow light duration
        yellow_frame = tk.Frame(self)
        yellow_frame.pack(pady=5)
        tk.Label(yellow_frame, text='Yellow Light Duration (seconds):', width=25, anchor='w').pack(side='left', padx=10)
        self.yellow_var = tk.StringVar(value='2')
        tk.Spinbox(yellow_frame, from_=1, to=30, textvariable=self.yellow_var, width=10).pack(side='left')
        
        # Red light duration
        red_frame = tk.Frame(self)
        red_frame.pack(pady=5)
        tk.Label(red_frame, text='Red Light Duration (seconds):', width=25, anchor='w').pack(side='left', padx=10)
        self.red_var = tk.StringVar(value='3')
        tk.Spinbox(red_frame, from_=1, to=30, textvariable=self.red_var, width=10).pack(side='left')
        
        # Buttons
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=20)
        tk.Button(btn_frame, text='OK', command=self.ok_clicked, width=10).pack(side='left', padx=5)
        tk.Button(btn_frame, text='Cancel', command=self.cancel_clicked, width=10).pack(side='left', padx=5)
        
        # Wait for dialog to close
        self.wait_window()
    
    def ok_clicked(self):
        """Store result and close dialog."""
        try:
            green = int(self.green_var.get())
            yellow = int(self.yellow_var.get())
            red = int(self.red_var.get())
            
            self.result = {
                'green': green,
                'yellow': yellow,
                'red': red
            }
        except ValueError:
            # Use defaults if invalid input
            self.result = {'green': 3, 'yellow': 2, 'red': 3}
        
        self.destroy()
    
    def cancel_clicked(self):
        """Close dialog without saving."""
        self.result = None
        self.destroy()


class VehicleRouteDialog(tk.Toplevel):
    """Dialog to specify vehicle route through junctions."""
    def __init__(self, parent, junction_names):
        super().__init__(parent)
        self.title('Vehicle Route Configuration')
        self.result = None
        self.junction_names = junction_names
        
        # Make dialog modal
        self.transient(parent)
        self.grab_set()
        
        # Center dialog
        self.geometry('500x300')
        
        tk.Label(self, text='Define Vehicle Route', font=('Arial', 14, 'bold')).pack(pady=(10, 5))
        
        # Instructions - compact format only
        instruction_text = ('Format: DIRECTION_JUNCTION\n'
                          '• Examples: N_A = North at Junction A | E_B = East at Junction B\n'
                          '• Direction Codes:\n'
                          '  - Compass: N, S, E, W, NE, NW, SE, SW\n'
                          '  - Relative: L (left), R (right), ST (straight)\n'
                          '• Multiple Commands: "N_A E_B S_C" or "N_A, E_B, S_C"')
        tk.Label(self, text=instruction_text, font=('Arial', 9), wraplength=450, justify='left').pack(pady=5)
        
        # Show available junctions
        if junction_names:
            junctions_text = 'Available Junctions: ' + ', '.join(junction_names)
            tk.Label(self, text=junctions_text, font=('Arial', 9), fg='#0066cc', wraplength=450).pack(pady=3)
        
        # Route text input
        tk.Label(self, text='Route Instructions:', font=('Arial', 10, 'bold')).pack(pady=(5, 5))
        
        self.route_text = tk.Text(self, width=50, height=3, wrap='word')
        self.route_text.pack(pady=5, padx=20)
        self.route_text.focus_set()
        
        # Example text with compact format
        if junction_names:
            example = f'N_{junction_names[0] if junction_names else "A"}'
            self.route_text.insert('1.0', example)
        
        # Buttons
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=15)
        tk.Button(btn_frame, text='OK', command=self.ok_clicked, width=10).pack(side='left', padx=5)
        tk.Button(btn_frame, text='Skip (Auto Route)', command=self.skip_clicked, width=15).pack(side='left', padx=5)
        tk.Button(btn_frame, text='Cancel', command=self.cancel_clicked, width=10).pack(side='left', padx=5)
        
        # Bind keyboard shortcuts
        self.bind('<Return>', lambda e: self.ok_clicked())
        self.bind('<Escape>', lambda e: self.cancel_clicked())
        
        # Wait for dialog to close
        self.wait_window()
    
    def ok_clicked(self):
        """Store result and close dialog."""
        route_instructions = self.route_text.get('1.0', 'end-1c').strip()
        self.result = {
            'instructions': route_instructions,
            'type': 'custom'
        }
        self.destroy()
    
    def skip_clicked(self):
        """Use automatic routing."""
        self.result = {
            'instructions': 'Auto-route',
            'type': 'auto'
        }
        self.destroy()
    
    def cancel_clicked(self):
        """Close dialog without saving."""
        self.result = None
        self.destroy()


class RoundaboutConfigDialog(tk.Toplevel):
    """Dialog to configure roundabout properties."""
    def __init__(self, parent):
        super().__init__(parent)
        self.title('Roundabout Configuration')
        self.result = None
        
        # Make dialog modal
        self.transient(parent)
        self.grab_set()
        
        # Center dialog
        self.geometry('300x250')
        
        tk.Label(self, text='Roundabout Settings', font=('Arial', 12, 'bold')).pack(pady=10)
        
        # Exit count selection
        tk.Label(self, text='Number of Exits:', font=('Arial', 10)).pack(pady=(10, 5))
        self.exit_count_var = tk.IntVar(value=4)
        
        exit_frame = tk.Frame(self)
        exit_frame.pack(pady=5)
        tk.Radiobutton(exit_frame, text='4 Exits (N, E, S, W)', variable=self.exit_count_var, 
                      value=4).pack(anchor='w')
        tk.Radiobutton(exit_frame, text='8 Exits (All Directions)', variable=self.exit_count_var, 
                      value=8).pack(anchor='w')
        
        # Direction selection
        tk.Label(self, text='Traffic Direction:', font=('Arial', 10)).pack(pady=(10, 5))
        self.direction_var = tk.StringVar(value='clockwise')
        
        dir_frame = tk.Frame(self)
        dir_frame.pack(pady=5)
        tk.Radiobutton(dir_frame, text='Clockwise', variable=self.direction_var, 
                      value='clockwise').pack(anchor='w')
        tk.Radiobutton(dir_frame, text='Counter-Clockwise', variable=self.direction_var, 
                      value='counterclockwise').pack(anchor='w')
        
        # Buttons
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=15)
        tk.Button(btn_frame, text='OK', command=self.ok_clicked, width=10).pack(side='left', padx=5)
        tk.Button(btn_frame, text='Cancel', command=self.cancel_clicked, width=10).pack(side='left', padx=5)
        
        # Bind keyboard shortcuts
        self.bind('<Return>', lambda e: self.ok_clicked())
        self.bind('<Escape>', lambda e: self.cancel_clicked())
        
        # Wait for dialog to close
        self.wait_window()
    
    def ok_clicked(self):
        """Save configuration and close."""
        self.result = {
            'exit_count': self.exit_count_var.get(),
            'direction': self.direction_var.get()
        }
        print(f"OK clicked - exit_count: {self.result['exit_count']}, dir: {self.result['direction']}")
        self.destroy()
    
    def cancel_clicked(self):
        """Close dialog without saving."""
        self.result = None
        self.destroy()


class ShortestRouteDialog(tk.Toplevel):
    """Dialog to configure shortest route calculation."""
    def __init__(self, parent, junction_names):
        super().__init__(parent)
        self.title('Shortest Route Calculator')
        self.result = None
        self.junction_names = junction_names
        
        # Make dialog modal
        self.transient(parent)
        self.grab_set()
        
        # Center dialog
        self.geometry('450x300')
        
        tk.Label(self, text='Calculate Shortest Route', font=('Arial', 14, 'bold')).pack(pady=(10, 5))
        
        # Instructions
        instruction_text = ('Find the fastest route between two junctions.\n'
                          'System will test all possible paths considering traffic light timing.')
        tk.Label(self, text=instruction_text, font=('Arial', 9), wraplength=400, justify='left').pack(pady=5)
        
        # Start junction frame
        start_frame = tk.Frame(self)
        start_frame.pack(pady=15, padx=20, fill='x')
        
        tk.Label(start_frame, text='Start Junction:', font=('Arial', 10, 'bold')).pack(anchor='w')
        
        self.start_var = tk.StringVar()
        if junction_names:
            self.start_var.set(junction_names[0])
        
        self.start_combo = tk.OptionMenu(start_frame, self.start_var, *junction_names)
        self.start_combo.config(width=30)
        self.start_combo.pack(pady=5, fill='x')
        
        # Destination junction frame
        dest_frame = tk.Frame(self)
        dest_frame.pack(pady=15, padx=20, fill='x')
        
        tk.Label(dest_frame, text='Destination Junction:', font=('Arial', 10, 'bold')).pack(anchor='w')
        
        self.dest_var = tk.StringVar()
        if len(junction_names) > 1:
            self.dest_var.set(junction_names[1])
        elif junction_names:
            self.dest_var.set(junction_names[0])
        
        self.dest_combo = tk.OptionMenu(dest_frame, self.dest_var, *junction_names)
        self.dest_combo.config(width=30)
        self.dest_combo.pack(pady=5, fill='x')
        
        # Buttons
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=20)
        tk.Button(btn_frame, text='Calculate', command=self.ok_clicked, width=12).pack(side='left', padx=5)
        tk.Button(btn_frame, text='Cancel', command=self.cancel_clicked, width=12).pack(side='left', padx=5)
        
        # Bind keyboard shortcuts
        self.bind('<Return>', lambda e: self.ok_clicked())
        self.bind('<Escape>', lambda e: self.cancel_clicked())
        
        # Wait for dialog to close
        self.wait_window()
    
    def ok_clicked(self):
        """Save configuration and close."""
        start = self.start_var.get().strip()
        dest = self.dest_var.get().strip()
        
        if not start or not dest:
            tk.messagebox.showwarning("Invalid Input", "Please select both start and destination junctions.")
            return
        
        if start == dest:
            tk.messagebox.showwarning("Invalid Input", "Start and destination must be different junctions.")
            return
        
        self.result = {
            'start': start,
            'destination': dest
        }
        self.destroy()
    
    def cancel_clicked(self):
        """Close dialog without saving."""
        self.result = None
        self.destroy()


class RoundaboutConfigDialog(tk.Toplevel):
    """Dialog to configure roundabout exits (4 or 8) and direction."""
    def __init__(self, parent):
        super().__init__(parent)
        self.title('Roundabout Configuration')
        self.result = None
        
        # Make dialog modal
        self.transient(parent)
        self.grab_set()
        
        # Center dialog
        self.geometry('450x350')
        
        tk.Label(self, text='Roundabout Configuration', font=('Arial', 14, 'bold')).pack(pady=(20, 10))
        
        # Description
        desc_text = 'Choose the number of exits for the roundabout:'
        tk.Label(self, text=desc_text, font=('Arial', 10)).pack(pady=10)
        
        # Exit options with timing info
        tk.Label(self, text='4 Exits: N, E, S, W (20-second cycle)', 
                font=('Arial', 9), fg='#555').pack(pady=5)
        tk.Label(self, text='8 Exits: N, NE, E, SE, S, SW, W, NW (24-second cycle)', 
                font=('Arial', 9), fg='#555').pack(pady=5)
        
        # Radio buttons for exit count
        self.exit_count = tk.IntVar(value=4)
        
        radio_frame = tk.Frame(self)
        radio_frame.pack(pady=15)
        
        tk.Radiobutton(radio_frame, text='4 Exits', variable=self.exit_count, 
                      value=4, font=('Arial', 11)).pack(side='left', padx=12)
        tk.Radiobutton(radio_frame, text='8 Exits', variable=self.exit_count, 
                      value=8, font=('Arial', 11)).pack(side='left', padx=12)
        
        # Direction options
        tk.Label(self, text='Traffic flow direction:', font=('Arial', 10)).pack(pady=(15, 5))
        
        self.direction = tk.StringVar(value='clockwise')
        
        direction_frame = tk.Frame(self)
        direction_frame.pack(pady=10)
        
        tk.Radiobutton(direction_frame, text='Clockwise (US/Right-hand traffic)', 
                      variable=self.direction, value='clockwise', 
                      font=('Arial', 10)).pack(side='left', padx=15)
        tk.Radiobutton(direction_frame, text='Counter-clockwise (UK/Left-hand traffic)', 
                      variable=self.direction, value='counterclockwise', 
                      font=('Arial', 10)).pack(side='left', padx=15)
        
        # Buttons
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=20)
        tk.Button(btn_frame, text='OK', command=self.ok_clicked, width=10).pack(side='left', padx=5)
        tk.Button(btn_frame, text='Cancel', command=self.cancel_clicked, width=10).pack(side='left', padx=5)
        
        # Bind keyboard shortcuts
        self.bind('<Return>', lambda e: self.ok_clicked())
        self.bind('<Escape>', lambda e: self.cancel_clicked())
        
        # Wait for dialog to close
        self.wait_window()
    
    def ok_clicked(self):
        """Store result and close dialog."""
        # Store both exit count and rotation direction
        print(f"OK clicked - exit_count: {self.exit_count.get()}, dir: {self.direction.get()}")
        self.result = {
            'exit_count': self.exit_count.get(),
            'direction': self.direction.get()
        }
        self.grab_release()
        self.destroy()
    
    def cancel_clicked(self):
        """Close dialog without saving."""
        print("Cancel clicked")
        self.result = None
        self.grab_release()
        self.destroy()


class GraphPaper(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Virtual Graph Paper - simplified')
        self.grid_size = DEFAULT_GRID
        self.width = 960
        self.height = 600

        self.tool = 'pen'  # pen, line, erase, move, junction, traffic_light, ped_crossing
        self.shapes = []  # list of {'type':'line'/'poly'/'junction', 'points':[(x,y)...], 'id': canvas_id, 'junction_type': ..., 'traffic_light': ..., 'ped_crossing': ...}
        self.current = None
        self.selection = None
        self.selected_junction_type = None  # stores the selected junction template
        
        # Junction naming
        self.junction_counter = 0  # Counter for naming junctions A, B, C, etc.
        self.junction_labels = {}  # {junction_name: canvas_text_id}
        
        # Config tool state
        self.config_tool = None  # 'traffic_light' or 'ped_crossing'
        self.node_markers = {}  # dict to store traffic light and crossing markers by shape/point
        
        # Traffic light animation state
        self.traffic_light_states = {}  # {unique_id: {'state': 'green'/'yellow'/'red', 'state_index': int, 'timing': {...}, 'marker_key': ...}}
        self.traffic_light_colors = ['green', 'yellow', 'red']
        self.traffic_light_next_id = 0  # Counter for unique traffic light IDs
        
        # Junction preview state
        self.junction_preview_ids = []  # canvas IDs for preview lines
        self.junction_rotation = 0  # 0, 90, 180, 270 degrees
        self.junction_flipped = False  # horizontal flip state
        self.junction_preview_pos = None  # (x, y) in world coords

        self._dragging = False
        
        # pan and zoom state
        self.offset_x = 0
        self.offset_y = 0
        self.scale = 1.0
        self._panning = False
        self._pan_start = None
        
        # toolbar state
        self.edit_roads_expanded = False
        self.view_expanded = False
        self.monitor_expanded = False
        self.config_expanded = False
        self.junctions_expanded = False  # nested subcategory
        
        # editor mode states (for future logic/flags)
        self.editor_mode = 'day'  # 'day' or 'night'
        self.mode_states = {
            'day': True,   # day mode is active by default
            'night': False  # night mode is inactive by default
        }
        
        # theme state (day/night mode)
        self.is_night_mode = False
        self.theme = {
            'day': {
                'bg': '#d1ccb3',
                'grid': '#a8a391',
                'line': 'black',
                'text': 'black'
            },
            'night': {
                'bg': '#2c2c45',
                'grid': '#4a4a6a',
                'line': '#ffed29',
                'text': 'white'
            }
        }
        
        # Parallel computing: Vehicle simulation
        self.vehicles = {}  # {vehicle_id: {'process': Process, 'canvas_id': int, 'path': [...], 'position': (x,y)}}
        self.vehicle_position_queue = Queue()
        self.traffic_light_queue = Queue()
        self.manager = Manager()
        self.stop_event = self.manager.Event()
        self.vehicle_next_id = 0
        self.simulation_running = False

        self.create_ui()
        self.draw_grid()
        self.apply_theme()
        self.update_vehicle_positions()  # Start vehicle position update loop

    def create_ui(self):
        self.toolbar = tk.Frame(self)
        self.toolbar.pack(side='top', fill='x')

        # Store button references for theme updates
        self.buttons = []
        
        # Edit Roads category button
        self.edit_roads_btn = tk.Button(self.toolbar, text='Edit Roads', command=self.toggle_edit_roads,
                                        relief='flat', bd=0, padx=12, pady=6,
                                        highlightthickness=0, borderwidth=0)
        self.edit_roads_btn.pack(side='left', padx=4, pady=4)
        self.buttons.append(self.edit_roads_btn)
        
        # Edit Roads sub-buttons (initially hidden)
        self.edit_roads_frame = tk.Frame(self.toolbar)
        self.edit_roads_buttons = []
        
        for t in ('pen', 'line', 'erase', 'move'):
            b = tk.Button(self.edit_roads_frame, text=t.capitalize(), command=lambda tt=t: self.set_tool(tt),
                         relief='flat', bd=0, padx=12, pady=6,
                         highlightthickness=0, borderwidth=0)
            b.pack(side='left', padx=2)
            self.edit_roads_buttons.append(b)
            self.buttons.append(b)
        
        clear_btn = tk.Button(self.edit_roads_frame, text='Clear', command=self.clear,
                             relief='flat', bd=0, padx=12, pady=6,
                             highlightthickness=0, borderwidth=0)
        clear_btn.pack(side='left', padx=2)
        self.edit_roads_buttons.append(clear_btn)
        self.buttons.append(clear_btn)
        
        # Junctions button (expands to show junction types)
        junctions_btn = tk.Button(self.edit_roads_frame, text='Junctions ▼', command=self.toggle_junctions,
                                 relief='flat', bd=0, padx=12, pady=6,
                                 highlightthickness=0, borderwidth=0)
        junctions_btn.pack(side='left', padx=2)
        self.edit_roads_buttons.append(junctions_btn)
        self.buttons.append(junctions_btn)
        self.junctions_btn = junctions_btn
        
        # Junctions sub-buttons (initially hidden) - nested in edit_roads_frame
        self.junctions_frame = tk.Frame(self.edit_roads_frame)
        self.junctions_buttons = []
        
        junction_types = ['T-Section', 'Crossroads', 'Y-Intersection', 'Roundabout', 'Ramp Merge', 'Landmark']
        for jtype in junction_types:
            jb = tk.Button(self.junctions_frame, text=jtype, 
                          command=lambda jt=jtype: self.select_junction(jt),
                          relief='flat', bd=0, padx=12, pady=6,
                          highlightthickness=0, borderwidth=0)
            jb.pack(side='left', padx=2)
            self.junctions_buttons.append(jb)
            self.buttons.append(jb)
        
        # View category button
        self.view_btn = tk.Button(self.toolbar, text='View', command=self.toggle_view,
                                  relief='flat', bd=0, padx=12, pady=6,
                                  highlightthickness=0, borderwidth=0)
        self.view_btn.pack(side='left', padx=4, pady=4)
        self.buttons.append(self.view_btn)
        
        # View sub-buttons (initially hidden)
        self.view_frame = tk.Frame(self.toolbar)
        self.view_buttons = []
        
        grid_btn = tk.Button(self.view_frame, text='Grid...', command=self.change_grid,
                            relief='flat', bd=0, padx=12, pady=6,
                            highlightthickness=0, borderwidth=0)
        grid_btn.pack(side='left', padx=2)
        self.view_buttons.append(grid_btn)
        self.buttons.append(grid_btn)
        
        # Monitor category button
        self.monitor_btn = tk.Button(self.toolbar, text='Monitor', command=self.toggle_monitor,
                                     relief='flat', bd=0, padx=12, pady=6,
                                     highlightthickness=0, borderwidth=0)
        self.monitor_btn.pack(side='left', padx=4, pady=4)
        self.buttons.append(self.monitor_btn)
        
        # Monitor sub-buttons (initially hidden)
        self.monitor_frame = tk.Frame(self.toolbar)
        self.monitor_buttons = []
        # Add monitor buttons here later
        
        # Config category button
        self.config_btn = tk.Button(self.toolbar, text='Config', command=self.toggle_config,
                                    relief='flat', bd=0, padx=12, pady=6,
                                    highlightthickness=0, borderwidth=0)
        self.config_btn.pack(side='left', padx=4, pady=4)
        self.buttons.append(self.config_btn)
        
        # Config sub-buttons (initially hidden)
        self.config_frame = tk.Frame(self.toolbar)
        self.config_buttons = []
        
        # Add traffic light button
        traffic_light_btn = tk.Button(self.config_frame, text='Traffic Light', 
                                      command=lambda: self.set_config_tool('traffic_light'),
                                      relief='flat', bd=0, padx=12, pady=6,
                                      highlightthickness=0, borderwidth=0)
        traffic_light_btn.pack(side='left', padx=2)
        self.config_buttons.append(traffic_light_btn)
        self.buttons.append(traffic_light_btn)
        
        # Add pedestrian crossing button
        ped_crossing_btn = tk.Button(self.config_frame, text='Pedestrian Crossing', 
                                     command=lambda: self.set_config_tool('ped_crossing'),
                                     relief='flat', bd=0, padx=12, pady=6,
                                     highlightthickness=0, borderwidth=0)
        ped_crossing_btn.pack(side='left', padx=2)
        self.config_buttons.append(ped_crossing_btn)
        self.buttons.append(ped_crossing_btn)
        
        # Simulation category button (for parallel computing demo)
        self.simulation_btn = tk.Button(self.toolbar, text='Simulation', command=self.toggle_simulation,
                                       relief='flat', bd=0, padx=12, pady=6,
                                       highlightthickness=0, borderwidth=0)
        self.simulation_btn.pack(side='left', padx=4, pady=4)
        self.buttons.append(self.simulation_btn)
        
        # Simulation sub-buttons (initially hidden)
        self.simulation_frame = tk.Frame(self.toolbar)
        self.simulation_buttons = []
        self.simulation_expanded = False
        
        # Spawn vehicle button
        spawn_vehicle_btn = tk.Button(self.simulation_frame, text='Spawn Vehicle', 
                                      command=self.spawn_vehicle,
                                      relief='flat', bd=0, padx=12, pady=6,
                                      highlightthickness=0, borderwidth=0)
        spawn_vehicle_btn.pack(side='left', padx=2)
        self.simulation_buttons.append(spawn_vehicle_btn)
        self.buttons.append(spawn_vehicle_btn)
        
        # Start/Stop simulation button
        self.sim_control_btn = tk.Button(self.simulation_frame, text='Start Simulation', 
                                         command=self.toggle_simulation_control,
                                         relief='flat', bd=0, padx=12, pady=6,
                                         highlightthickness=0, borderwidth=0)
        self.sim_control_btn.pack(side='left', padx=2)
        self.simulation_buttons.append(self.sim_control_btn)
        self.buttons.append(self.sim_control_btn)
        
        # Clear vehicles button
        clear_vehicles_btn = tk.Button(self.simulation_frame, text='Clear Vehicles', 
                                       command=self.clear_vehicles,
                                       relief='flat', bd=0, padx=12, pady=6,
                                       highlightthickness=0, borderwidth=0)
        clear_vehicles_btn.pack(side='left', padx=2)
        self.simulation_buttons.append(clear_vehicles_btn)
        self.buttons.append(clear_vehicles_btn)
        
        # Shortest Route button
        shortest_route_btn = tk.Button(self.simulation_frame, text='Shortest Route', 
                                       command=self.find_shortest_route,
                                       relief='flat', bd=0, padx=12, pady=6,
                                       highlightthickness=0, borderwidth=0)
        shortest_route_btn.pack(side='left', padx=2)
        self.simulation_buttons.append(shortest_route_btn)
        self.buttons.append(shortest_route_btn)
        
        # theme toggle button - placed on the right side
        self.theme_btn = tk.Button(self.toolbar, text='🌙', command=self.toggle_theme,
                                   relief='flat', bd=0, padx=12, pady=6,
                                   highlightthickness=0, borderwidth=0)
        self.theme_btn.pack(side='right', padx=10, pady=4)
        self.buttons.append(self.theme_btn)

        self.canvas = tk.Canvas(self, width=self.width, height=self.height, bg='white')
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<ButtonPress-1>', self.on_down)
        self.canvas.bind('<B1-Motion>', self.on_move)
        self.canvas.bind('<ButtonRelease-1>', self.on_up)
        self.canvas.bind('<Motion>', self.on_mouse_motion)  # Track mouse for preview
        # pan with middle mouse or space+left
        self.canvas.bind('<ButtonPress-2>', self.on_pan_start)
        self.canvas.bind('<B2-Motion>', self.on_pan_move)
        self.canvas.bind('<ButtonRelease-2>', self.on_pan_end)
        # zoom with mouse wheel
        self.canvas.bind('<MouseWheel>', self.on_zoom)
        self.canvas.bind('<Button-4>', self.on_zoom)  # Linux scroll up
        self.canvas.bind('<Button-5>', self.on_zoom)  # Linux scroll down
        
        # Keyboard bindings for junction manipulation
        self.bind('<space>', self.on_space_press)
        self.bind('<KeyPress-r>', self.on_rotate_press)
        self.bind('<KeyPress-R>', self.on_rotate_press)
        self.bind('<KeyPress-t>', self.on_flip_press)
        self.bind('<KeyPress-T>', self.on_flip_press)

        # status
        self.status = ttk.Label(self, text='Tool: pen | Grid: %d' % self.grid_size)
        self.status.pack(side='bottom', fill='x')

    def set_tool(self, t):
        self.tool = t
        self.status.config(text='Tool: %s | Grid: %d' % (self.tool, self.grid_size))
    
    def set_config_tool(self, config_type):
        """Set the configuration tool (traffic light or pedestrian crossing)."""
        self.config_tool = config_type
        self.tool = config_type
        if config_type == 'traffic_light':
            self.status.config(text='Tool: Add Traffic Light (click on junction/intersection) | Grid: %d' % self.grid_size)
        elif config_type == 'ped_crossing':
            self.status.config(text='Tool: Add Pedestrian Crossing (click on road) | Grid: %d' % self.grid_size)
    
    def toggle_edit_roads(self):
        """Toggle the Edit Roads submenu."""
        self.edit_roads_expanded = not self.edit_roads_expanded
        
        if self.edit_roads_expanded:
            # Collapse other categories if open
            if self.view_expanded:
                self.view_expanded = False
                self.view_frame.pack_forget()
            if self.monitor_expanded:
                self.monitor_expanded = False
                self.monitor_frame.pack_forget()
            if self.config_expanded:
                self.config_expanded = False
                self.config_frame.pack_forget()
            if self.simulation_expanded:
                self.simulation_expanded = False
                self.simulation_frame.pack_forget()
            # Hide other category buttons
            self.view_btn.pack_forget()
            self.monitor_btn.pack_forget()
            self.config_btn.pack_forget()
            self.simulation_btn.pack_forget()
            # Show Edit Roads buttons
            self.edit_roads_frame.pack(side='left', padx=4, pady=4)
        else:
            # Hide Edit Roads buttons
            self.edit_roads_frame.pack_forget()
            # Show all category buttons in order
            self.view_btn.pack(side='left', padx=4, pady=4)
            self.monitor_btn.pack(side='left', padx=4, pady=4)
            self.config_btn.pack(side='left', padx=4, pady=4)
            self.simulation_btn.pack(side='left', padx=4, pady=4)
        
        self.apply_theme()
    
    def toggle_view(self):
        """Toggle the View submenu."""
        self.view_expanded = not self.view_expanded
        
        if self.view_expanded:
            # Collapse other categories if open
            if self.edit_roads_expanded:
                self.edit_roads_expanded = False
                self.edit_roads_frame.pack_forget()
            if self.monitor_expanded:
                self.monitor_expanded = False
                self.monitor_frame.pack_forget()
            if self.config_expanded:
                self.config_expanded = False
                self.config_frame.pack_forget()
            if self.simulation_expanded:
                self.simulation_expanded = False
                self.simulation_frame.pack_forget()
            # Hide other category buttons
            self.edit_roads_btn.pack_forget()
            self.monitor_btn.pack_forget()
            self.config_btn.pack_forget()
            self.simulation_btn.pack_forget()
            # Show View buttons
            self.view_frame.pack(side='left', padx=4, pady=4)
        else:
            # Hide View buttons
            self.view_frame.pack_forget()
            # Show all category buttons in order
            self.edit_roads_btn.pack(side='left', padx=4, pady=4)
            self.monitor_btn.pack(side='left', padx=4, pady=4)
            self.config_btn.pack(side='left', padx=4, pady=4)
            self.simulation_btn.pack(side='left', padx=4, pady=4)
        
        self.apply_theme()
    
    def toggle_monitor(self):
        """Toggle the Monitor submenu."""
        self.monitor_expanded = not self.monitor_expanded
        
        if self.monitor_expanded:
            # Collapse other categories if open
            if self.edit_roads_expanded:
                self.edit_roads_expanded = False
                self.edit_roads_frame.pack_forget()
            if self.view_expanded:
                self.view_expanded = False
                self.view_frame.pack_forget()
            if self.config_expanded:
                self.config_expanded = False
                self.config_frame.pack_forget()
            if self.simulation_expanded:
                self.simulation_expanded = False
                self.simulation_frame.pack_forget()
            # Hide other category buttons
            self.edit_roads_btn.pack_forget()
            self.view_btn.pack_forget()
            self.config_btn.pack_forget()
            self.simulation_btn.pack_forget()
            # Show Monitor buttons
            self.monitor_frame.pack(side='left', padx=4, pady=4)
        else:
            # Hide Monitor buttons
            self.monitor_frame.pack_forget()
            # Show all category buttons in order
            self.edit_roads_btn.pack(side='left', padx=4, pady=4)
            self.view_btn.pack(side='left', padx=4, pady=4)
            self.config_btn.pack(side='left', padx=4, pady=4)
            self.simulation_btn.pack(side='left', padx=4, pady=4)
        
        self.apply_theme()
    
    def toggle_config(self):
        """Toggle the Config submenu."""
        self.config_expanded = not self.config_expanded
        
        if self.config_expanded:
            # Collapse other categories if open
            if self.edit_roads_expanded:
                self.edit_roads_expanded = False
                self.edit_roads_frame.pack_forget()
            if self.view_expanded:
                self.view_expanded = False
                self.view_frame.pack_forget()
            if self.monitor_expanded:
                self.monitor_expanded = False
                self.monitor_frame.pack_forget()
            if self.simulation_expanded:
                self.simulation_expanded = False
                self.simulation_frame.pack_forget()
            # Hide other category buttons
            self.edit_roads_btn.pack_forget()
            self.view_btn.pack_forget()
            self.monitor_btn.pack_forget()
            self.simulation_btn.pack_forget()
            # Show Config buttons
            self.config_frame.pack(side='left', padx=4, pady=4)
        else:
            # Hide Config buttons
            self.config_frame.pack_forget()
            # Show all category buttons in order
            self.edit_roads_btn.pack(side='left', padx=4, pady=4)
            self.view_btn.pack(side='left', padx=4, pady=4)
            self.monitor_btn.pack(side='left', padx=4, pady=4)
            self.simulation_btn.pack(side='left', padx=4, pady=4)
        
        self.apply_theme()
    
    def toggle_simulation(self):
        """Toggle the Simulation submenu."""
        self.simulation_expanded = not self.simulation_expanded
        
        if self.simulation_expanded:
            # Collapse other categories if open
            if self.edit_roads_expanded:
                self.edit_roads_expanded = False
                self.edit_roads_frame.pack_forget()
            if self.view_expanded:
                self.view_expanded = False
                self.view_frame.pack_forget()
            if self.monitor_expanded:
                self.monitor_expanded = False
                self.monitor_frame.pack_forget()
            if self.config_expanded:
                self.config_expanded = False
                self.config_frame.pack_forget()
            # Hide other category buttons
            self.edit_roads_btn.pack_forget()
            self.view_btn.pack_forget()
            self.monitor_btn.pack_forget()
            self.config_btn.pack_forget()
            # Show Simulation buttons
            self.simulation_frame.pack(side='left', padx=4, pady=4)
        else:
            # Hide Simulation buttons
            self.simulation_frame.pack_forget()
            # Show all category buttons in order
            self.edit_roads_btn.pack(side='left', padx=4, pady=4)
            self.view_btn.pack(side='left', padx=4, pady=4)
            self.monitor_btn.pack(side='left', padx=4, pady=4)
            self.config_btn.pack(side='left', padx=4, pady=4)
        
        self.apply_theme()
    
    def apply_theme(self):
        """Apply the current theme colors to all UI elements."""
        theme = self.theme['night'] if self.is_night_mode else self.theme['day']
        
        # Update main window background
        self.config(bg=theme['bg'])
        
        # In night mode: yellow toolbar and buttons with dark text
        # In day mode: normal appearance with dark text
        if self.is_night_mode:
            toolbar_bg = theme['line']  # #ffed29 yellow
            button_bg = theme['line']   # #ffed29 yellow
            button_fg = theme['bg']     # #2c2c45 dark blue
        else:
            toolbar_bg = theme['bg']    # #d1ccb3 beige
            button_bg = theme['bg']     # #d1ccb3 beige
            button_fg = theme['text']   # black
        
        # Update toolbar background
        self.toolbar.config(bg=toolbar_bg)
        
        # Update sub-menu frames background
        self.edit_roads_frame.config(bg=toolbar_bg)
        self.view_frame.config(bg=toolbar_bg)
        self.monitor_frame.config(bg=toolbar_bg)
        self.config_frame.config(bg=toolbar_bg)
        self.junctions_frame.config(bg=toolbar_bg)  # nested frame
        
        # Update all buttons
        for btn in self.buttons:
            btn.config(bg=button_bg, fg=button_fg, activebackground=button_bg, 
                      activeforeground=button_fg)
        
        # Update status bar
        self.status.config(background=theme['bg'], foreground=theme['text'])
        
        # Canvas will be updated by draw_grid()
        self.draw_grid()
    
    def toggle_theme(self):
        """Toggle between day and night mode."""
        self.is_night_mode = not self.is_night_mode
        
        # Update editor mode states
        if self.is_night_mode:
            self.editor_mode = 'night'
            self.mode_states['day'] = False
            self.mode_states['night'] = True
            self.theme_btn.config(text='☀️')
        else:
            self.editor_mode = 'day'
            self.mode_states['day'] = True
            self.mode_states['night'] = False
            self.theme_btn.config(text='🌙')
        
        # apply new theme to entire UI
        self.apply_theme()

    def change_grid(self):
        val = simpledialog.askinteger('Grid size', 'Enter grid spacing in px', initialvalue=self.grid_size, minvalue=4, maxvalue=200)
        if val:
            self.grid_size = val
            self.status.config(text='Tool: %s | Grid: %d' % (self.tool, self.grid_size))
            self.draw_grid()

    def clear(self):
        # Clear all shapes
        for s in list(self.shapes):
            if 'id' in s and s['id']:
                try:
                    self.canvas.delete(s['id'])
                except Exception:
                    pass
        self.shapes.clear()
        
        # Clear all markers (traffic lights and pedestrian crossings)
        self.canvas.delete('marker')
        self.node_markers.clear()
        self.traffic_light_states.clear()
        
        print("All structures cleared")
    
    def open_junctions(self):
        """Open junctions submenu/dialog - placeholder for future functionality."""
        # Placeholder for junctions functionality
        print("Junctions feature - to be implemented")
        pass
    
    def toggle_junctions(self):
        """Toggle the Junctions nested submenu."""
        self.junctions_expanded = not self.junctions_expanded
        
        if self.junctions_expanded:
            # Change button text to show it's expanded
            self.junctions_btn.config(text='Junctions ▲')
            # Hide other Edit Roads buttons (pen, line, erase, move, clear)
            for btn in self.edit_roads_buttons:
                if btn != self.junctions_btn:  # Don't hide the junctions button itself
                    btn.pack_forget()
            # Show junctions sub-buttons
            self.junctions_frame.pack(side='left', padx=4, pady=4)
        else:
            # Change button text back
            self.junctions_btn.config(text='Junctions ▼')
            # Hide junctions sub-buttons
            self.junctions_frame.pack_forget()
            # Show other Edit Roads buttons again
            for btn in self.edit_roads_buttons:
                if btn != self.junctions_btn:
                    btn.pack(side='left', padx=2)
        
        self.apply_theme()
    
    def add_traffic_light(self, x, y):
        """Add a traffic light marker at the nearest junction/intersection point."""
        # Find nearest point from any shape
        min_dist = float('inf')
        nearest_point = None
        nearest_shape = None
        
        thresh = self.grid_size * 1.5
        for shape in self.shapes:
            for px, py in shape['points']:
                dist = math.sqrt((px - x) ** 2 + (py - y) ** 2)
                if dist < min_dist and dist < thresh:
                    min_dist = dist
                    nearest_point = (px, py)
                    nearest_shape = shape
        
        if nearest_point:
            marker_key = (nearest_shape.get('id'), nearest_point)
            
            # Check if this is a two-way road
            road_config = nearest_shape.get('road_config', {})
            is_two_way = road_config.get('road_type') == 'two_way'
            
            # Count existing traffic lights at this point
            if marker_key not in self.node_markers:
                self.node_markers[marker_key] = {}
            
            existing_lights = [k for k in self.node_markers[marker_key].keys() if k.startswith('traffic_light_')]
            
            # Check if we can add another light
            if is_two_way and len(existing_lights) >= 2:
                print(f"Two-way road already has 2 traffic lights at {nearest_point}")
                return
            elif not is_two_way and len(existing_lights) >= 1:
                print(f"One-way road already has 1 traffic light at {nearest_point}")
                return
            
            # Show timing configuration dialog
            timing_dialog = TrafficLightTimingDialog(self)
            
            if not timing_dialog.result:
                print("Traffic light placement cancelled")
                return
            
            timing = timing_dialog.result
            
            # Calculate perpendicular offset based on road direction
            # Find the line segment this point belongs to
            point_idx = None
            for i, (px, py) in enumerate(nearest_shape['points']):
                if (px, py) == nearest_point:
                    point_idx = i
                    break
            
            # Calculate perpendicular direction
            perpendicular_offset_x = 0
            perpendicular_offset_y = 15  # Default offset distance from node
            
            if point_idx is not None and len(nearest_shape['points']) > 1:
                # Get adjacent points to determine road direction
                if point_idx > 0:
                    # Use previous point
                    prev_x, prev_y = nearest_shape['points'][point_idx - 1]
                    dx = nearest_point[0] - prev_x
                    dy = nearest_point[1] - prev_y
                elif point_idx < len(nearest_shape['points']) - 1:
                    # Use next point
                    next_x, next_y = nearest_shape['points'][point_idx + 1]
                    dx = next_x - nearest_point[0]
                    dy = next_y - nearest_point[1]
                else:
                    dx, dy = 0, 1  # Default vertical
                
                # Calculate perpendicular direction (rotate 90 degrees)
                # Normalize and scale
                length = math.sqrt(dx * dx + dy * dy)
                if length > 0:
                    dx, dy = dx / length, dy / length
                    # Perpendicular vector (rotate 90 degrees counterclockwise)
                    perpendicular_offset_x = -dy * 15
                    perpendicular_offset_y = dx * 15
            
            # Calculate offset for second light on two-way roads (opposite side)
            if len(existing_lights) == 1:
                perpendicular_offset_x = -perpendicular_offset_x
                perpendicular_offset_y = -perpendicular_offset_y
            
            # Draw traffic light as filled circle with border (scaled)
            sx, sy = self.world_to_screen(*nearest_point)
            sx += perpendicular_offset_x * self.scale
            sy += perpendicular_offset_y * self.scale
            
            # Scale the sizes
            outer_radius = 10 * self.scale
            inner_radius = 8 * self.scale
            border_width = max(1, int(2 * self.scale))
            
            # Draw outer circle (border) - larger circle in black
            border_id = self.canvas.create_oval(sx - outer_radius, sy - outer_radius, 
                                               sx + outer_radius, sy + outer_radius, 
                                               fill='black', outline='black', width=border_width, tags='marker')
            
            # Draw inner light (starts with green)
            light_id = self.canvas.create_oval(sx - inner_radius, sy - inner_radius, 
                                              sx + inner_radius, sy + inner_radius, 
                                              fill='green', outline='', tags='marker')
            
            # Generate unique ID for this traffic light
            light_unique_id = self.traffic_light_next_id
            self.traffic_light_next_id += 1
            
            # Store marker info with unique key
            light_key = f'traffic_light_{len(existing_lights)}'
            self.node_markers[marker_key][light_key] = {
                'border_id': border_id,
                'light_id': light_id,
                'world_pos': nearest_point,
                'current_color': 'green',
                'perpendicular_offset': (perpendicular_offset_x, perpendicular_offset_y),
                'unique_id': light_unique_id
            }
            
            # Initialize traffic light state with timing
            self.traffic_light_states[light_unique_id] = {
                'state': 'green',
                'state_index': 0,
                'timing': timing,
                'marker_key': marker_key,
                'light_key': light_key,
                'last_change': 0
            }
            
            print(f"Traffic light {len(existing_lights) + 1} added at {nearest_point} with timing: {timing}")
            
            # Start animation if this is the first traffic light
            if len(self.traffic_light_states) == 1:
                self.animate_traffic_lights()
    
    def add_pedestrian_crossing(self, x, y):
        """Add a pedestrian crossing marker on the nearest road node with traffic lights."""
        # Find nearest point from any shape
        min_dist = float('inf')
        nearest_point = None
        nearest_shape = None
        
        thresh = self.grid_size * 1.5
        for shape in self.shapes:
            for px, py in shape['points']:
                dist = math.sqrt((px - x) ** 2 + (py - y) ** 2)
                if dist < min_dist and dist < thresh:
                    min_dist = dist
                    nearest_point = (px, py)
                    nearest_shape = shape
        
        if nearest_point:
            marker_key = (nearest_shape.get('id'), nearest_point)
            
            # Check if this node has traffic lights
            if marker_key not in self.node_markers:
                print(f"No traffic lights at this node. Pedestrian crossings can only be placed at nodes with traffic lights.")
                return
            
            # Check if there are any traffic lights at this node
            has_traffic_light = any(k.startswith('traffic_light_') for k in self.node_markers[marker_key].keys())
            
            if not has_traffic_light:
                print(f"No traffic lights at this node. Pedestrian crossings can only be placed at nodes with traffic lights.")
                return
            
            # Check if pedestrian crossing already exists at this point
            if 'ped_crossing' in self.node_markers[marker_key]:
                print(f"Pedestrian crossing already exists at {nearest_point}")
                return
            
            # Position pedestrian crossing below the traffic lights to avoid obstruction
            sx, sy = self.world_to_screen(*nearest_point)
            ped_offset_y = 25  # Base offset (will be scaled)
            
            # Scale the sizes and offset
            scaled_offset = ped_offset_y * self.scale
            housing_width = 10 * self.scale
            housing_height = 6 * self.scale
            light_radius = 4 * self.scale
            border_width = max(1, int(2 * self.scale))
            
            # Draw pedestrian crossing housing (white rectangle with stripes)
            housing_id = self.canvas.create_rectangle(sx - housing_width, sy + scaled_offset - housing_height, 
                                                     sx + housing_width, sy + scaled_offset + housing_height, 
                                                     fill='white', outline='black', width=border_width, 
                                                     tags='marker')
            
            # Draw pedestrian light indicator (starts with red since traffic lights start green)
            ped_light_id = self.canvas.create_oval(sx - light_radius, sy + scaled_offset - light_radius, 
                                                  sx + light_radius, sy + scaled_offset + light_radius, 
                                                  fill='red', outline='', tags='marker')
            
            # Store marker info
            self.node_markers[marker_key]['ped_crossing'] = {
                'housing_id': housing_id,
                'light_id': ped_light_id,
                'world_pos': nearest_point,
                'current_color': 'red',
                'offset_y': ped_offset_y  # Store offset for redrawing
            }
            
            print(f"Pedestrian crossing added at {nearest_point} (below traffic lights)")

    
    def animate_traffic_lights(self):
        """Animate all traffic lights by cycling through colors with individual timing."""
        import time
        current_time = time.time()
        
        if self.traffic_light_states:
            # In night mode, set all lights to constant yellow
            if self.is_night_mode:
                for light_id, state in list(self.traffic_light_states.items()):
                    marker_key = state['marker_key']
                    light_key = state['light_key']
                    
                    if marker_key in self.node_markers and light_key in self.node_markers[marker_key]:
                        light_id_canvas = self.node_markers[marker_key][light_key]['light_id']
                        current_color = self.node_markers[marker_key][light_key]['current_color']
                        
                        # Only update if not already yellow
                        if current_color != 'yellow':
                            self.canvas.itemconfig(light_id_canvas, fill='yellow')
                            self.node_markers[marker_key][light_key]['current_color'] = 'yellow'
            else:
                # Normal day mode - cycle through colors with timing
                # Group lights by junction and phase for coordination
                junction_phases = {}
                
                for light_id, state in list(self.traffic_light_states.items()):
                    # Check if this is a coordinated junction light
                    if 'phase' in state and 'junction_type' in state:
                        junction_key = state.get('marker_key', None)
                        phase = state['phase']
                        
                        # Group by junction and phase
                        if junction_key not in junction_phases:
                            junction_phases[junction_key] = {}
                        if phase not in junction_phases[junction_key]:
                            junction_phases[junction_key][phase] = []
                        junction_phases[junction_key][phase].append(light_id)
                    
                    # Get timing for current color
                    timing = state['timing']
                    
                    # For coordinated lights with phase offset, calculate color based on cycle position
                    if 'phase_offset' in state and 'cycle_time' in state:
                        cycle_time = state['cycle_time']
                        phase_offset = state['phase_offset']
                        green_time = timing['green']
                        yellow_time = timing['yellow']
                        
                        # Calculate position in cycle
                        elapsed_in_cycle = (current_time % cycle_time)
                        time_in_phase = elapsed_in_cycle - phase_offset
                        if time_in_phase < 0:
                            time_in_phase += cycle_time
                        
                        # Determine color based on position in phase
                        if time_in_phase < green_time:
                            new_color = 'green'
                            new_index = 0
                        elif time_in_phase < green_time + yellow_time:
                            new_color = 'yellow'
                            new_index = 1
                        else:
                            new_color = 'red'
                            new_index = 2
                        
                        # Only update if color changed
                        if new_color != state['state']:
                            state['state'] = new_color
                            state['state_index'] = new_index
                            
                            # Update the traffic light color on canvas
                            marker_key = state['marker_key']
                            light_key = state['light_key']
                            
                            if marker_key in self.node_markers and light_key in self.node_markers[marker_key]:
                                light_id_canvas = self.node_markers[marker_key][light_key]['light_id']
                                self.canvas.itemconfig(light_id_canvas, fill=new_color)
                                self.node_markers[marker_key][light_key]['current_color'] = new_color
                    else:
                        # Original timing logic for non-phase-coordinated lights
                        current_color = state['state']
                        duration = timing[current_color]  # Duration in seconds
                        
                        # Check if enough time has passed
                        elapsed = current_time - state['last_change']
                        if elapsed >= duration:
                            # For coordinated junction lights, calculate phase-based timing
                            if 'phase' in state:
                                # Determine next color based on phase coordination
                                # Phase cycle: Green -> Yellow -> Red -> Green
                                if current_color == 'green':
                                    new_color = 'yellow'
                                    new_index = 1
                                elif current_color == 'yellow':
                                    new_color = 'red'
                                    new_index = 2
                                else:  # red
                                    new_color = 'green'
                                    new_index = 0
                            else:
                                # Regular cycling for non-coordinated lights
                                state['state_index'] = (state['state_index'] + 1) % 3
                                new_color = self.traffic_light_colors[state['state_index']]
                                new_index = state['state_index']
                            
                            state['state'] = new_color
                            state['state_index'] = new_index
                            state['last_change'] = current_time
                            
                            # Update the traffic light color on canvas
                            marker_key = state['marker_key']
                            light_key = state['light_key']
                            
                            if marker_key in self.node_markers and light_key in self.node_markers[marker_key]:
                                light_id_canvas = self.node_markers[marker_key][light_key]['light_id']
                                self.canvas.itemconfig(light_id_canvas, fill=new_color)
                                self.node_markers[marker_key][light_key]['current_color'] = new_color
        
        # Update all pedestrian crossings with inverse logic
        # When traffic light is green or yellow, pedestrian is red
        # When traffic light is red, pedestrian is green
        # In night mode, all pedestrian lights are yellow
        for marker_key, markers in self.node_markers.items():
            if 'ped_crossing' in markers:
                if self.is_night_mode:
                    # Night mode - constant yellow
                    ped_color = 'yellow'
                else:
                    # Day mode - inverse logic
                    ped_color = 'green'  # Default
                    
                    # Check if any traffic light is green or yellow
                    for tl_id, tl_state in self.traffic_light_states.items():
                        if tl_state['state'] in ['green', 'yellow']:
                            ped_color = 'red'
                            break
                        elif tl_state['state'] == 'red':
                            ped_color = 'green'
                
                # Update pedestrian light color
                ped_light_id = markers['ped_crossing']['light_id']
                current_ped_color = markers['ped_crossing'].get('current_color', '')
                if current_ped_color != ped_color:
                    self.canvas.itemconfig(ped_light_id, fill=ped_color)
                    markers['ped_crossing']['current_color'] = ped_color
        
        # Schedule next update (check every 100ms for smoother timing)
        self.after(100, self.animate_traffic_lights)
    
    def parse_route_instructions(self, instructions):
        """Parse route instructions into structured commands.
        
        ONLY supports compact format: DIRECTION_JUNCTION (e.g., "N_A" = north at Junction A)
        Direction codes:
        - N, S, E, W = North, South, East, West
        - NE, NW, SE, SW = Northeast, Northwest, Southeast, Southwest
        - L, R, ST = Left, Right, Straight (relative)
        
        Multiple commands: "N_A E_B S_C" or "N_A, E_B, S_C"
        """
        if not instructions or instructions.strip().lower() == 'auto':
            return []
        
        commands = []
        
        # Parse compact format (DIRECTION_JUNCTION) only
        # Split by spaces or commas
        parts = instructions.upper().replace(',', ' ').split()
        
        for part in parts:
            if '_' in part:
                # Compact format detected
                components = part.split('_')
                if len(components) == 2:
                    dir_code = components[0]
                    junction = components[1]
                    
                    # Validate junction exists
                    if junction in self.junction_labels:
                        # Map direction code to direction name
                        direction_map = {
                            'N': ('north', 'absolute'),
                            'S': ('south', 'absolute'),
                            'E': ('east', 'absolute'),
                            'W': ('west', 'absolute'),
                            'NE': ('northeast', 'absolute'),
                            'NW': ('northwest', 'absolute'),
                            'SE': ('southeast', 'absolute'),
                            'SW': ('southwest', 'absolute'),
                            'L': ('left', 'relative'),
                            'R': ('right', 'relative'),
                            'ST': ('straight', 'relative')
                        }
                        
                        if dir_code in direction_map:
                            direction, dir_type = direction_map[dir_code]
                            commands.append({
                                'junction': junction,
                                'direction': direction,
                                'type': dir_type
                            })
                            print(f"Parsed: {direction} at Junction {junction}")
                        else:
                            print(f"Unknown direction code: {dir_code}. Use N,S,E,W,NE,NW,SE,SW,L,R,ST")
                    else:
                        print(f"Unknown junction: {junction}")
            else:
                # Not in compact format - reject it
                print(f"Invalid format: '{part}'. Use DIRECTION_JUNCTION format (e.g., N_A)")
        
        return commands
    
    def calculate_absolute_direction(self, direction_vec):
        """Calculate the absolute compass direction of a vector.
        Returns: 'north', 'south', 'east', 'west', 'northeast', 'northwest', 'southeast', 'southwest'
        
        In canvas coordinates: 
        - Positive X = East
        - Negative X = West  
        - Negative Y = North (canvas Y increases downward)
        - Positive Y = South
        """
        if direction_vec[0] == 0 and direction_vec[1] == 0:
            return 'north'  # Default
        
        # Calculate angle in degrees from east (0°)
        angle = math.degrees(math.atan2(direction_vec[1], direction_vec[0]))
        
        # Normalize to 0-360
        angle = angle % 360
        
        # In canvas coordinates, we need to flip Y-axis interpretation
        # atan2(y, x) gives: right=0°, down=90°, left=180°, up=270°
        # We want: north=up=270°, east=right=0°, south=down=90°, west=left=180°
        
        # Determine direction based on angle ranges (with 22.5° tolerance for each cardinal)
        if 337.5 <= angle or angle < 22.5:
            return 'east'
        elif 22.5 <= angle < 67.5:
            return 'southeast'
        elif 67.5 <= angle < 112.5:
            return 'south'
        elif 112.5 <= angle < 157.5:
            return 'southwest'
        elif 157.5 <= angle < 202.5:
            return 'west'
        elif 202.5 <= angle < 247.5:
            return 'northwest'
        elif 247.5 <= angle < 292.5:
            return 'north'
        elif 292.5 <= angle < 337.5:
            return 'northeast'
        
        return 'north'  # Fallback
    
    def calculate_turn_direction(self, incoming_vec, outgoing_vec):
        """Calculate if a turn is left, right, or straight based on vectors.
        Returns: 'left', 'right', 'straight', or 'back'
        """
        # Normalize vectors
        in_len = math.sqrt(incoming_vec[0]**2 + incoming_vec[1]**2)
        out_len = math.sqrt(outgoing_vec[0]**2 + outgoing_vec[1]**2)
        
        if in_len == 0 or out_len == 0:
            return 'straight'
        
        in_norm = (incoming_vec[0] / in_len, incoming_vec[1] / in_len)
        out_norm = (outgoing_vec[0] / out_len, outgoing_vec[1] / out_len)
        
        # Calculate cross product (for left/right) and dot product (for forward/back)
        cross = in_norm[0] * out_norm[1] - in_norm[1] * out_norm[0]
        dot = in_norm[0] * out_norm[0] + in_norm[1] * out_norm[1]
        
        # Determine direction based on angle
        if dot < -0.7:  # ~135 degrees or more - going back
            return 'back'
        elif abs(cross) < 0.3:  # Nearly straight (angle < ~17 degrees)
            return 'straight'
        elif cross > 0:  # Positive cross product = left turn
            return 'left'
        else:  # Negative cross product = right turn
            return 'right'
    
    def get_junction_at_point(self, point):
        """Find which junction (if any) is at the given point."""
        tolerance = self.grid_size * 0.5
        
        for junction_name, label_data in self.junction_labels.items():
            jx, jy = label_data['position']
            dist = math.sqrt((point[0] - jx)**2 + (point[1] - jy)**2)
            
            # For roundabouts, check if point is near any exit position
            if label_data.get('junction_type') == 'Roundabout':
                g = self.grid_size
                octagon_radius = 2 * g
                exit_distance = octagon_radius + g
                
                # Check each exit position
                for i in range(8):
                    ang = math.radians(i * 45 - 90)
                    ex = jx + exit_distance * math.cos(ang)
                    ey = jy + exit_distance * math.sin(ang)
                    exit_dist = math.sqrt((point[0] - ex)**2 + (point[1] - ey)**2)
                    if exit_dist < tolerance:
                        return junction_name
            elif dist < tolerance:
                # For regular junctions, check distance to center
                return junction_name
        
        return None
    
    def get_exit_roads_from_junction(self, junction_point, incoming_point):
        """Get all possible exit roads from a junction, excluding the incoming road."""
        tolerance = 5
        exit_roads = []
        
        for shape in self.shapes:
            if shape['type'] in ['line', 'poly', 'junction'] and len(shape['points']) >= 2:
                # Check if this road connects to the junction
                for i, point in enumerate(shape['points']):
                    dist = math.sqrt((point[0] - junction_point[0])**2 + 
                                   (point[1] - junction_point[1])**2)
                    
                    if dist < tolerance:
                        # This road connects to junction
                        # Get the next point to determine direction
                        if i < len(shape['points']) - 1:
                            next_point = shape['points'][i + 1]
                        elif i > 0:
                            next_point = shape['points'][i - 1]
                        else:
                            continue
                        
                        # Don't include the road we came from
                        if incoming_point:
                            dist_to_incoming = math.sqrt((next_point[0] - incoming_point[0])**2 + 
                                                        (next_point[1] - incoming_point[1])**2)
                            if dist_to_incoming < tolerance:
                                continue
                        
                        # Calculate direction vector
                        direction_vec = (next_point[0] - junction_point[0], 
                                       next_point[1] - junction_point[1])
                        
                        exit_roads.append({
                            'shape': shape,
                            'start_index': i,
                            'next_point': next_point,
                            'direction_vec': direction_vec
                        })
                        break
        
        return exit_roads
    
    def build_vehicle_path_with_route(self, start_shape, start_index, route_commands):
        """Build a path through connected roads following route instructions."""
        path_points = start_shape['points'][start_index:].copy()
        current_endpoint = path_points[-1]
        prev_point = path_points[-2] if len(path_points) >= 2 else None
        visited_shapes = {id(start_shape)}
        processed_junctions = set()  # Track junctions we've already processed
        
        command_index = 0
        max_extensions = 30
        extensions = 0
        
        while extensions < max_extensions:
            # Check if we're at a junction
            junction_name = self.get_junction_at_point(current_endpoint)
            
            if junction_name and command_index < len(route_commands) and junction_name not in processed_junctions:
                # Check if this is the junction mentioned in the next command
                next_command = route_commands[command_index]
                
                if next_command['junction'] == junction_name:
                    # We need to make a decision here
                    desired_direction = next_command['direction']
                    direction_type = next_command.get('type', 'relative')
                    
                    # Get all possible exits
                    exit_roads = self.get_exit_roads_from_junction(current_endpoint, prev_point)

                    # Special handling for Roundabout: route vehicles around octagon ring
                    jl = self.junction_labels.get(junction_name)
                    if jl and jl.get('junction_type') == 'Roundabout':
                        print(f"DEBUG: Entering roundabout routing for Junction {junction_name}")
                        # Build roundabout-specific path: follow octagon vertices between incoming and desired exit
                        center_x, center_y = jl['position']
                        g = self.grid_size
                        octagon_radius = 2 * g
                        exit_distance = octagon_radius + g

                        # Build list of exit outer positions in same indexing as template (i*45 -90)
                        exit_positions = []
                        for i in range(8):
                            ang = math.radians(i * 45 - 90)
                            px = center_x + exit_distance * math.cos(ang)
                            py = center_y + exit_distance * math.sin(ang)
                            exit_positions.append((px, py))

                        # Map compass to index
                        compass_to_index = {'N':0,'NE':1,'E':2,'SE':3,'S':4,'SW':5,'W':6,'NW':7}

                        # Determine desired index
                        desired_index = None
                        if direction_type == 'absolute':
                            want = desired_direction.upper()
                            print(f"  Looking for direction: '{want}'")
                            desired_index = compass_to_index.get(want)
                            print(f"  Mapped to index: {desired_index}")
                            # If 4-exit roundabout, snap to nearest cardinal (0,2,4,6)
                            if jl.get('roundabout_exit_count') == 4 and desired_index is not None:
                                cardinals = [0,2,4,6]
                                best = min(cardinals, key=lambda c: min((desired_index - c) % 8, (c - desired_index) % 8))
                                desired_index = best
                                print(f"  4-exit roundabout: snapped to cardinal index {desired_index}")
                        else:
                            # Relative routing: will pick next exit later
                            pass

                        # Find incoming index by finding the closest exit position to current_endpoint
                        # This tells us which road the vehicle is entering from
                        incoming_index = 0
                        min_dist = float('inf')
                        for i, exit_pos in enumerate(exit_positions):
                            dist = math.sqrt((current_endpoint[0] - exit_pos[0])**2 + 
                                           (current_endpoint[1] - exit_pos[1])**2)
                            if dist < min_dist:
                                min_dist = dist
                                incoming_index = i
                        
                        print(f"  Current endpoint: {current_endpoint}, closest to exit index {incoming_index} (dist: {min_dist:.1f})")

                        # If desired_index is still None (relative), pick next exit
                        if desired_index is None:
                            desired_index = (incoming_index + (2 if jl.get('roundabout_exit_count') == 4 else 1)) % 8
                        
                        # Make sure we don't exit at the same place we entered
                        if incoming_index == desired_index:
                            print(f"Warning: desired exit same as entrance! Adjusting to next exit.")
                            desired_index = (incoming_index + (2 if jl.get('roundabout_exit_count') == 4 else 1)) % 8

                        # Determine rotation sign from stored junction config (CW -> +1, CCW -> -1)
                        rot = jl.get('roundabout_direction', 'clockwise')
                        
                        print(f"Roundabout: entering at index {incoming_index}, exiting at index {desired_index}, direction: {rot}")
                        if rot == 'clockwise' or rot == 'CW':
                            sign = 1
                        else:
                            sign = -1

                        step = 1 if jl.get('roundabout_exit_count') == 8 else 2

                        # Build octagon vertex positions
                        vertex_positions = []
                        for i in range(8):
                            angv = math.radians(i * 45 - 90)
                            vx = center_x + octagon_radius * math.cos(angv)
                            vy = center_y + octagon_radius * math.sin(angv)
                            vertex_positions.append((vx, vy))

                        # Start from incoming vertex and traverse to desired exit
                        traversal_indices = [incoming_index]
                        idx = incoming_index
                        while idx != desired_index:
                            idx = (idx + sign * step) % 8
                            traversal_indices.append(idx)
                        
                        # Debug: show direction names for indices
                        index_names = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
                        traversal_names = [index_names[i] for i in traversal_indices]
                        print(f"  Traversal path: {' -> '.join(traversal_names)} (indices: {traversal_indices})")

                        # Add vertex positions to path_points
                        for vi in traversal_indices:
                            path_points.append(vertex_positions[vi])

                        # Add the exit outer point for desired_index
                        path_points.append(exit_positions[desired_index])

                        # After adding exit outer point, continue on connected roads from that endpoint
                        prev_point = path_points[-2] if len(path_points) >= 2 else None
                        current_endpoint = path_points[-1]
                        print(f"  Looking for connected road at exit position: {current_endpoint}")
                        found = self.continue_on_connected_road(path_points, current_endpoint, visited_shapes, prev_point)
                        if found:
                            # Update to new endpoint after extending path
                            prev_point = current_endpoint
                            current_endpoint = path_points[-1]
                            print(f"  Found connected road, new endpoint: {current_endpoint}")
                        else:
                            print(f"  WARNING: No connected road found at exit!")
                        command_index += 1
                        processed_junctions.add(junction_name)  # Mark this junction as processed
                        extensions += 1
                        continue
                    
                    if not exit_roads:
                        print(f"No exit roads found at Junction {junction_name}")
                        break
                    
                    # Find the exit that matches desired direction
                    best_exit = None
                    
                    if direction_type == 'absolute':
                        # Match based on absolute compass direction
                        for exit_road in exit_roads:
                            exit_direction = self.calculate_absolute_direction(exit_road['direction_vec'])
                            
                            # Check for exact match or compatible match
                            if exit_direction == desired_direction:
                                best_exit = exit_road
                                break
                            # Also check if main cardinal direction matches (e.g., "north" matches "northeast")
                            elif desired_direction in exit_direction or exit_direction in desired_direction:
                                if not best_exit:  # Take first compatible match as fallback
                                    best_exit = exit_road
                        
                        if best_exit:
                            exit_dir_name = self.calculate_absolute_direction(best_exit['direction_vec'])
                            print(f"Taking {exit_dir_name} exit at Junction {junction_name} (requested: {desired_direction})")
                        else:
                            print(f"Could not find {desired_direction} exit at Junction {junction_name}")
                            # Show available directions for debugging
                            available = [self.calculate_absolute_direction(e['direction_vec']) for e in exit_roads]
                            print(f"Available exits: {available}")
                            if exit_roads:
                                best_exit = exit_roads[0]  # Take first available
                    
                    else:
                        # Match based on relative direction (left/right/straight)
                        # Calculate incoming direction vector
                        if prev_point:
                            incoming_vec = (current_endpoint[0] - prev_point[0],
                                          current_endpoint[1] - prev_point[1])
                        else:
                            incoming_vec = (1, 0)  # Default direction
                        
                        for exit_road in exit_roads:
                            turn = self.calculate_turn_direction(incoming_vec, exit_road['direction_vec'])
                            if turn == desired_direction:
                                best_exit = exit_road
                                break
                        
                        if not best_exit and exit_roads:
                            print(f"Could not find {desired_direction} turn at Junction {junction_name}, taking available exit")
                            best_exit = exit_roads[0]
                    
                    if best_exit:
                        # Add this road to path
                        shape = best_exit['shape']
                        start_idx = best_exit['start_index']
                        
                        if id(shape) not in visited_shapes:
                            # Add points from this shape
                            new_points = shape['points'][start_idx + 1:]
                            if new_points:
                                prev_point = current_endpoint
                                path_points.extend(new_points)
                                current_endpoint = path_points[-1]
                                visited_shapes.add(id(shape))
                                command_index += 1
                                processed_junctions.add(junction_name)  # Mark as processed
                            else:
                                # Try reversed direction
                                new_points = list(reversed(shape['points'][:start_idx]))
                                if new_points:
                                    prev_point = current_endpoint
                                    path_points.extend(new_points)
                                    current_endpoint = path_points[-1]
                                    visited_shapes.add(id(shape))
                                    command_index += 1
                                    processed_junctions.add(junction_name)  # Mark as processed
                                else:
                                    break
                        else:
                            break
                    else:
                        break
                else:
                    # Not the junction we're looking for, continue straight
                    found = self.continue_on_connected_road(path_points, current_endpoint, 
                                                           visited_shapes, prev_point)
                    if found:
                        prev_point = current_endpoint
                        current_endpoint = path_points[-1]
                    else:
                        break
            else:
                # No junction or no more commands, just continue on connected roads
                found = self.continue_on_connected_road(path_points, current_endpoint, 
                                                       visited_shapes, prev_point)
                if found:
                    prev_point = current_endpoint
                    current_endpoint = path_points[-1]
                else:
                    break
            
            extensions += 1
        
        return path_points
    
    def continue_on_connected_road(self, path_points, current_endpoint, visited_shapes, prev_point):
        """Continue path on any connected road (helper for auto-routing)."""
        tolerance = 5
        
        for shape in self.shapes:
            if shape['type'] in ['line', 'poly', 'junction'] and id(shape) not in visited_shapes:
                if len(shape['points']) >= 2:
                    shape_start = shape['points'][0]
                    shape_end = shape['points'][-1]
                    
                    dist_to_start = math.sqrt((current_endpoint[0] - shape_start[0])**2 + 
                                             (current_endpoint[1] - shape_start[1])**2)
                    dist_to_end = math.sqrt((current_endpoint[0] - shape_end[0])**2 + 
                                           (current_endpoint[1] - shape_end[1])**2)
                    
                    if dist_to_start < tolerance:
                        path_points.extend(shape['points'][1:])
                        visited_shapes.add(id(shape))
                        return True
                    elif dist_to_end < tolerance:
                        path_points.extend(list(reversed(shape['points'][:-1])))
                        visited_shapes.add(id(shape))
                        return True
        
        return False
    
    def build_vehicle_path(self, start_shape, start_index):
        """Build a continuous path through connected road segments (auto-mode)."""
        path_points = start_shape['points'][start_index:].copy()
        current_endpoint = path_points[-1]
        visited_shapes = {id(start_shape)}
        
        # Keep extending path by finding connected roads
        max_extensions = 20  # Prevent infinite loops
        extensions = 0
        
        while extensions < max_extensions:
            found = self.continue_on_connected_road(path_points, current_endpoint, 
                                                   visited_shapes, None)
            if found:
                current_endpoint = path_points[-1]
            else:
                break
            
            extensions += 1
        
        return path_points
    
    def spawn_vehicle(self):
        """Enable spawn mode - click on a node to spawn a vehicle there."""
        self.tool = 'spawn_vehicle'
        self.status.config(text='Tool: Click on a road node to spawn vehicle | Grid: %d' % self.grid_size)
        print("Click on any road node to spawn a vehicle")
    
    def spawn_vehicle_at_node(self, x, y):
        """Spawn a vehicle at a specific node location."""
        if not self.shapes:
            print("No roads available. Draw some roads first!")
            return
        
        # Find nearest node from any shape
        min_dist = float('inf')
        nearest_point = None
        nearest_shape = None
        
        thresh = self.grid_size * 1.5
        for shape in self.shapes:
            if shape['type'] in ['line', 'poly', 'junction'] and len(shape['points']) >= 2:
                for i, (px, py) in enumerate(shape['points']):
                    dist = math.sqrt((px - x) ** 2 + (py - y) ** 2)
                    if dist < min_dist and dist < thresh:
                        min_dist = dist
                        nearest_point = (px, py)
                        nearest_shape = shape
        
        if not nearest_point or not nearest_shape:
            print("No road node found nearby. Click closer to a road node.")
            return
        
        # Find the point index in the shape
        point_index = None
        for i, point in enumerate(nearest_shape['points']):
            if point == nearest_point:
                point_index = i
                break
        
        if point_index is None:
            return
        
        # Get list of available junction names
        junction_names = sorted(self.junction_labels.keys())
        
        # Show route configuration dialog FIRST
        route_dialog = VehicleRouteDialog(self, junction_names)
        
        if not route_dialog.result:
            print("Vehicle spawn cancelled")
            return
        
        route_info = route_dialog.result
        
        # Parse route instructions
        route_commands = []
        if route_info['type'] == 'custom':
            route_commands = self.parse_route_instructions(route_info['instructions'])
            print(f"Parsed route commands: {route_commands}")
        
        # Build path using route commands (if custom) or auto (if skip)
        if route_commands:
            path_points = self.build_vehicle_path_with_route(nearest_shape, point_index, route_commands)
            print(f"Built path with {len(path_points)} points using route commands")
        else:
            path_points = self.build_vehicle_path(nearest_shape, point_index)
        
        if len(path_points) < 2:
            print("Not enough road segments from this point. Choose a different node.")
            return
        
        # Create vehicle with random speed
        vehicle_id = self.vehicle_next_id
        self.vehicle_next_id += 1
        
        # Random color for vehicle
        colors = ['red', 'blue', 'green', 'orange', 'purple', 'cyan']
        vehicle_color = random.choice(colors)
        
        # Create vehicle visual (small circle, scaled)
        start_pos = path_points[0]
        sx, sy = self.world_to_screen(*start_pos)
        vehicle_radius = 6 * self.scale
        border_width = max(1, int(2 * self.scale))
        canvas_id = self.canvas.create_oval(sx - vehicle_radius, sy - vehicle_radius, 
                                           sx + vehicle_radius, sy + vehicle_radius,
                                           fill=vehicle_color, outline='black', width=border_width, tags='vehicle')
        
        # Speed in pixels per frame (higher = faster, 1-3 pixels per frame is good)
        speed = random.uniform(1.0, 3.0)  # Random speed in pixels per update
        
        # Collect all junction positions for the vehicle process
        # For roundabouts, need larger detection radius
        junction_positions = []
        for name, data in self.junction_labels.items():
            pos = (data['position'][0], data['position'][1])
            jtype = data.get('junction_type', 'regular')
            # Store junction info with type for proper zone detection
            junction_positions.append({
                'position': pos,
                'type': jtype,
                'grid_size': self.grid_size
            })
        
        # Create process but DON'T start it yet - wait for simulation to start
        process = Process(target=vehicle_movement_process,
                         args=(vehicle_id, path_points, speed, 
                               self.vehicle_position_queue, self.traffic_light_queue, 
                               self.stop_event, junction_positions, self.grid_size))
        
        # Store vehicle info (process not started yet)
        self.vehicles[vehicle_id] = {
            'process': process,
            'canvas_id': canvas_id,
            'path': path_points,
            'position': start_pos,
            'color': vehicle_color,
            'started': False,  # Track if process has been started
            'route': route_info
        }
        
        print(f"Vehicle {vehicle_id} ready at node with route: {route_info['instructions']}")
        print(f"Press 'Start Simulation' to begin vehicle movement")
    
    def toggle_simulation_control(self):
        """Start or stop the simulation."""
        self.simulation_running = not self.simulation_running
        
        if self.simulation_running:
            self.stop_event.clear()
            
            # Start all vehicles that haven't been started yet
            for vehicle_id, vehicle_data in self.vehicles.items():
                if not vehicle_data.get('started', False):
                    vehicle_data['process'].start()
                    vehicle_data['started'] = True
                    print(f"Started vehicle {vehicle_id} (Process ID: {vehicle_data['process'].pid})")
            
            self.sim_control_btn.config(text='Stop Simulation')
            print("Simulation started - vehicles moving in parallel processes")
        else:
            self.stop_event.set()
            self.sim_control_btn.config(text='Start Simulation')
            print("Simulation stopped")
    
    def clear_vehicles(self):
        """Remove all vehicles and stop their processes."""
        # Stop all vehicle processes
        self.stop_event.set()
        
        for vehicle_id, vehicle_data in list(self.vehicles.items()):
            # Terminate process forcefully
            try:
                if vehicle_data['process'].is_alive():
                    vehicle_data['process'].terminate()
                    vehicle_data['process'].join(timeout=0.5)
                    # If still alive, kill it
                    if vehicle_data['process'].is_alive():
                        vehicle_data['process'].kill()
                        vehicle_data['process'].join(timeout=0.5)
            except Exception as e:
                print(f"Error terminating vehicle {vehicle_id}: {e}")
            
            # Remove from canvas
            try:
                self.canvas.delete(vehicle_data['canvas_id'])
            except:
                pass
        
        # Clear vehicles dict
        self.vehicles.clear()
        
        # Clear queues
        while not self.vehicle_position_queue.empty():
            try:
                self.vehicle_position_queue.get_nowait()
            except:
                break
        
        while not self.traffic_light_queue.empty():
            try:
                self.traffic_light_queue.get_nowait()
            except:
                break
        
        print("All vehicles cleared")
        self.simulation_running = False
        if hasattr(self, 'sim_control_btn'):
            self.sim_control_btn.config(text='Start Simulation')
    
    def find_shortest_route(self):
        """Calculate shortest route considering traffic light timing."""
        # Get junction names
        junction_names = list(self.junction_labels.keys())
        
        # Show dialog
        dialog = ShortestRouteDialog(self, junction_names)
        
        if not dialog.result:
            print("Shortest route calculation cancelled")
            return
        
        start_junction = dialog.result['start']
        dest_junction = dialog.result['destination']
        
        print(f"\nCalculating shortest route from Junction {start_junction} to Junction {dest_junction}...")
        
        # Get junction positions
        if start_junction not in self.junction_labels or dest_junction not in self.junction_labels:
            tk.messagebox.showerror("Invalid Input", "Selected junctions not found.")
            return
        
        # Find all possible routes between junctions
        routes = self.find_all_junction_routes(start_junction, dest_junction)
        
        if not routes:
            tk.messagebox.showinfo("No Routes Found", 
                                  "No valid routes found between the specified junctions.")
            return
        
        # Simulate each route and calculate travel time
        print(f"Found {len(routes)} possible routes. Simulating...")
        route_times = []
        
        for i, route in enumerate(routes):
            travel_time = self.simulate_route_time(route['path'], route['commands'])
            route_times.append({
                'route_num': i + 1,
                'path_description': route['description'],
                'commands': route['commands'],
                'travel_time': travel_time,
                'path_points': route['path']
            })
            print(f"  Route {i+1}: {travel_time:.2f}s - {route['description']}")
        
        # Find shortest route
        fastest_route = min(route_times, key=lambda r: r['travel_time'])
        
        # Display results
        self.show_route_results(fastest_route, route_times, 
                               f"Junction {start_junction}", f"Junction {dest_junction}")
    
    def find_all_junction_routes(self, start_junction, dest_junction):
        """Find all possible routes between two junctions."""
        routes = []
        
        # Get starting position from the start junction's exit roads
        start_pos = self.junction_labels[start_junction]['position']
        
        # Find a road connected to the start junction to use as starting point
        start_shape = None
        start_idx = 0
        tolerance = self.grid_size * 3.5  # Use large tolerance for roundabouts
        
        for shape in self.shapes:
            if shape['type'] in ['line', 'poly'] and len(shape['points']) >= 2:
                for i, point in enumerate(shape['points']):
                    dist = math.sqrt((point[0] - start_pos[0])**2 + (point[1] - start_pos[1])**2)
                    if dist < tolerance:
                        start_shape = shape
                        start_idx = i
                        break
                if start_shape:
                    break
        
        if not start_shape:
            print(f"No road found connected to Junction {start_junction}")
            return []
        
        # Try direct route (auto-follow to destination)
        try:
            direct_path = self.build_vehicle_path(start_shape, start_idx)
            # Check if path reaches destination junction
            junctions_in_path = self.get_junctions_in_path(direct_path, dest_junction)
            if dest_junction in junctions_in_path:
                path_str = ' → '.join(junctions_in_path)
                routes.append({
                    'path': direct_path,
                    'commands': [],
                    'description': f'Direct route: {path_str}',
                    'junction_path': junctions_in_path
                })
        except:
            pass
        
        # Try routes with explicit directions at destination junction
        for direction in ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']:
            command_str = f"{direction}_{dest_junction}"
            commands = self.parse_route_instructions(command_str)
            if commands:
                try:
                    path = self.build_vehicle_path_with_route(start_shape, start_idx, commands)
                    if len(path) >= 2:
                        junctions_in_path = self.get_junctions_in_path(path, dest_junction)
                        path_str = ' → '.join(junctions_in_path)
                        routes.append({
                            'path': path,
                            'commands': commands,
                            'description': f'{path_str} (exit {direction})',
                            'junction_path': junctions_in_path
                        })
                except Exception as e:
                    pass
        
        # Try routes through intermediate junctions
        all_junctions = list(self.junction_labels.keys())
        intermediate_junctions = [j for j in all_junctions 
                                  if j != start_junction and j != dest_junction]
        
        for mid_junction in intermediate_junctions[:5]:  # Limit to avoid too many routes
            for dir1 in ['N', 'E', 'S', 'W']:
                for dir2 in ['N', 'E', 'S', 'W']:
                    command_str = f"{dir1}_{mid_junction} {dir2}_{dest_junction}"
                    commands = self.parse_route_instructions(command_str)
                    if commands:
                        try:
                            path = self.build_vehicle_path_with_route(start_shape, start_idx, commands)
                            if len(path) >= 2:
                                junctions_in_path = self.get_junctions_in_path(path, dest_junction)
                                path_str = ' → '.join(junctions_in_path)
                                routes.append({
                                    'path': path,
                                    'commands': commands,
                                    'description': f'{path_str}',
                                    'junction_path': junctions_in_path
                                })
                        except:
                            pass
        
        print(f"Generated {len(routes)} possible routes")
        return routes
    
    def get_junctions_in_path(self, path_points, dest_junction=None):
        """Extract list of junctions that the path passes through, in order.
        If dest_junction is provided, ensure it's included at the end."""
        junctions_found = []
        tolerance = self.grid_size * 5.0  # Increased to detect junctions vehicle passes near
        
        # Track when we enter each junction zone (use first encounter)
        junction_encounters = {}  # {junction_name: first_index}
        
        for i, point in enumerate(path_points):
            for junction_name, junction_data in self.junction_labels.items():
                junction_pos = junction_data['position']
                
                dist = math.sqrt((point[0] - junction_pos[0])**2 + 
                               (point[1] - junction_pos[1])**2)
                
                if dist < tolerance:
                    if junction_name not in junction_encounters:
                        junction_encounters[junction_name] = i
        
        # Sort junctions by the order they were first encountered in the path
        sorted_junctions = sorted(junction_encounters.items(), key=lambda x: x[1])
        junctions_found = [name for name, _ in sorted_junctions]
        
        # Ensure destination junction is included at the end if provided and not already there
        if dest_junction and dest_junction not in junctions_found:
            junctions_found.append(dest_junction)
        
        return junctions_found
    
    def path_reaches_junction(self, path_points, junction_name):
        """Check if a path reaches a specific junction."""
        if junction_name not in self.junction_labels:
            return False
        
        junction_pos = self.junction_labels[junction_name]['position']
        tolerance = self.grid_size * 5.0  # Increased to match get_junctions_in_path
        
        for point in path_points:
            dist = math.sqrt((point[0] - junction_pos[0])**2 + 
                           (point[1] - junction_pos[1])**2)
            if dist < tolerance:
                return True
        return False
    
    def parse_position_input(self, input_str):
        """Parse position input: junction name or 'N nodes DIR junction'."""
        input_str = input_str.strip().upper()
        
        # Check if it's just a junction name
        if input_str in self.junction_labels:
            pos = self.junction_labels[input_str]['position']
            return pos, f"Junction {input_str}"
        
        # Parse "N nodes DIR junction" format
        parts = input_str.split()
        if len(parts) >= 4 and parts[1].upper() == 'NODES':
            try:
                num_nodes = int(parts[0])
                direction = parts[2].upper()
                junction = parts[3]
                
                if junction not in self.junction_labels:
                    return None, f"Junction {junction} not found"
                
                junction_pos = self.junction_labels[junction]['position']
                
                # Calculate position N nodes in specified direction
                dir_map = {
                    'NORTH': (0, -1), 'N': (0, -1),
                    'SOUTH': (0, 1), 'S': (0, 1),
                    'EAST': (1, 0), 'E': (1, 0),
                    'WEST': (-1, 0), 'W': (-1, 0),
                    'NORTHEAST': (1, -1), 'NE': (1, -1),
                    'NORTHWEST': (-1, -1), 'NW': (-1, -1),
                    'SOUTHEAST': (1, 1), 'SE': (1, 1),
                    'SOUTHWEST': (-1, 1), 'SW': (-1, 1)
                }
                
                if direction not in dir_map:
                    return None, f"Unknown direction: {direction}"
                
                dx, dy = dir_map[direction]
                # Normalize diagonal directions
                if abs(dx) + abs(dy) == 2:
                    dx /= 1.414
                    dy /= 1.414
                
                offset_x = dx * num_nodes * self.grid_size
                offset_y = dy * num_nodes * self.grid_size
                
                pos = (junction_pos[0] + offset_x, junction_pos[1] + offset_y)
                return pos, f"{num_nodes} nodes {direction.title()} of Junction {junction}"
                
            except (ValueError, IndexError):
                return None, "Invalid format"
        
        return None, "Invalid format"
    
    def find_all_routes(self, start_pos, dest_pos):
        """Find all possible routes between two positions."""
        # For now, implement a simple version that finds routes through each junction
        routes = []
        
        # Find nearest shapes to start and dest
        start_shape, start_idx = self.find_nearest_shape_and_point(start_pos)
        dest_shape, dest_idx = self.find_nearest_shape_and_point(dest_pos)
        
        if not start_shape or not dest_shape:
            return []
        
        # Try direct route (no junction commands)
        direct_path = self.build_vehicle_path(start_shape, start_idx)
        if direct_path:
            routes.append({
                'path': direct_path,
                'commands': [],
                'description': 'Direct route'
            })
        
        # Try routes through each junction with different directions
        junction_names = list(self.junction_labels.keys())
        for junction in junction_names:
            for direction in ['N', 'S', 'E', 'W']:
                command_str = f"{direction}_{junction}"
                commands = self.parse_route_instructions(command_str)
                if commands:
                    try:
                        path = self.build_vehicle_path_with_route(start_shape, start_idx, commands)
                        if len(path) >= 2:
                            routes.append({
                                'path': path,
                                'commands': commands,
                                'description': f'Via Junction {junction} ({direction})'
                            })
                    except:
                        pass
        
        return routes
    
    def find_nearest_shape_and_point(self, position):
        """Find nearest shape and point index to a position."""
        min_dist = float('inf')
        nearest_shape = None
        nearest_index = 0
        
        for shape in self.shapes:
            if shape['type'] in ['line', 'poly', 'junction'] and len(shape['points']) >= 2:
                for i, point in enumerate(shape['points']):
                    dist = math.sqrt((point[0] - position[0])**2 + (point[1] - position[1])**2)
                    if dist < min_dist:
                        min_dist = dist
                        nearest_shape = shape
                        nearest_index = i
        
        return nearest_shape, nearest_index
    
    def simulate_route_time(self, path_points, route_commands):
        """Simulate travel time for a route considering traffic lights."""
        if len(path_points) < 2:
            return float('inf')
        
        # Calculate base travel time (distance / average speed)
        total_distance = 0
        for i in range(len(path_points) - 1):
            dx = path_points[i+1][0] - path_points[i][0]
            dy = path_points[i+1][1] - path_points[i][1]
            total_distance += math.sqrt(dx*dx + dy*dy)
        
        average_speed = 2.0  # pixels per update (20ms per update)
        base_time = (total_distance / average_speed) * 0.02  # seconds
        
        # Add traffic light delays
        traffic_delay = 0
        junction_positions = [(data['position'][0], data['position'][1]) 
                             for data in self.junction_labels.values()]
        
        # Check each segment for traffic light encounters
        for i in range(len(path_points) - 1):
            point = path_points[i]
            
            # Check if near any traffic light
            for marker_key, markers in self.node_markers.items():
                for marker_id, marker_data in markers.items():
                    if marker_id.startswith('traffic_light_'):
                        light_pos = marker_data.get('world_pos')
                        if light_pos:
                            dist = math.sqrt((point[0] - light_pos[0])**2 + 
                                           (point[1] - light_pos[1])**2)
                            if dist < self.grid_size * 0.5:
                                # Assume worst case: hit red light
                                # Average wait time = half of red duration
                                traffic_delay += 5.0  # Approximate average wait
        
        total_time = base_time + traffic_delay
        return total_time
    
    def show_route_results(self, fastest_route, all_routes, start_desc, dest_desc):
        """Display route calculation results in a dialog."""
        result_window = tk.Toplevel(self)
        result_window.title("Shortest Route Results")
        result_window.geometry("600x500")
        
        # Header
        header_frame = tk.Frame(result_window, bg='#4CAF50', height=60)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)
        
        tk.Label(header_frame, text="✓ Shortest Route Found", 
                font=('Arial', 16, 'bold'), bg='#4CAF50', fg='white').pack(pady=15)
        
        # Route info frame
        info_frame = tk.Frame(result_window, padx=20, pady=20)
        info_frame.pack(fill='both', expand=True)
        
        # Start and destination
        tk.Label(info_frame, text=f"From: {start_desc}", 
                font=('Arial', 11), anchor='w').pack(fill='x', pady=2)
        tk.Label(info_frame, text=f"To: {dest_desc}", 
                font=('Arial', 11), anchor='w').pack(fill='x', pady=2)
        
        tk.Label(info_frame, text="", height=1).pack()  # Spacer
        
        # Fastest route details
        tk.Label(info_frame, text="Fastest Route:", 
                font=('Arial', 12, 'bold')).pack(anchor='w', pady=(5, 2))
        
        # Show junction path prominently
        junction_path = fastest_route.get('junction_path', [])
        if junction_path:
            path_display = ' → '.join(junction_path)
            tk.Label(info_frame, text=f"  Path: {path_display}", 
                    font=('Arial', 12, 'bold'), fg='#2196F3').pack(anchor='w')
        
        tk.Label(info_frame, text=f"  {fastest_route['path_description']}", 
                font=('Arial', 10), fg='#666').pack(anchor='w')
        tk.Label(info_frame, text=f"  Estimated Time: {fastest_route['travel_time']:.2f} seconds", 
                font=('Arial', 11, 'bold'), fg='#2196F3').pack(anchor='w')
        
        # All routes comparison
        tk.Label(info_frame, text="", height=1).pack()  # Spacer
        tk.Label(info_frame, text="All Routes Comparison:", 
                font=('Arial', 12, 'bold')).pack(anchor='w', pady=(5, 5))
        
        # Scrollable text for all routes
        text_frame = tk.Frame(info_frame)
        text_frame.pack(fill='both', expand=True, pady=5)
        
        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side='right', fill='y')
        
        routes_text = tk.Text(text_frame, height=10, font=('Courier', 9), 
                             yscrollcommand=scrollbar.set, wrap='none')
        routes_text.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=routes_text.yview)
        
        # Sort routes by time
        sorted_routes = sorted(all_routes, key=lambda r: r['travel_time'])
        
        for i, route in enumerate(sorted_routes):
            marker = "★ " if route['route_num'] == fastest_route['route_num'] else "  "
            routes_text.insert('end', f"{marker}Route {route['route_num']}: "
                                     f"{route['travel_time']:.2f}s - {route['path_description']}\n")
        
        routes_text.config(state='disabled')
        
        # Close button
        tk.Button(result_window, text="Close", command=result_window.destroy, 
                 width=15, height=2).pack(pady=10)
        
        print(f"\n✓ Fastest route: {fastest_route['path_description']} "
              f"({fastest_route['travel_time']:.2f}s)")
    
    def update_vehicle_positions(self):
        """Update vehicle positions from the queue (runs in main thread)."""
        # Process all position updates from the queue
        updates_processed = 0
        while not self.vehicle_position_queue.empty() and updates_processed < 50:
            try:
                update = self.vehicle_position_queue.get_nowait()
                vehicle_id = update['vehicle_id']
                
                if vehicle_id in self.vehicles:
                    if update['active']:
                        # Update vehicle position on canvas
                        new_pos = update['position']
                        self.vehicles[vehicle_id]['position'] = new_pos
                        
                        # Convert to screen coords and move vehicle (scaled)
                        sx, sy = self.world_to_screen(*new_pos)
                        canvas_id = self.vehicles[vehicle_id]['canvas_id']
                        vehicle_radius = 6 * self.scale
                        
                        # Move the oval to new position
                        self.canvas.coords(canvas_id, sx - vehicle_radius, sy - vehicle_radius, 
                                         sx + vehicle_radius, sy + vehicle_radius)
                    else:
                        # Vehicle reached end - remove it
                        vehicle_data = self.vehicles[vehicle_id]
                        if vehicle_data['process'].is_alive():
                            vehicle_data['process'].terminate()
                            vehicle_data['process'].join(timeout=0.5)
                        
                        try:
                            self.canvas.delete(vehicle_data['canvas_id'])
                        except:
                            pass
                        
                        del self.vehicles[vehicle_id]
                        print(f"Vehicle {vehicle_id} completed its route")
                
                updates_processed += 1
            except:
                break
        
        # Send traffic light states to vehicle processes
        if self.traffic_light_states:
            for light_id, state in self.traffic_light_states.items():
                marker_key = state.get('marker_key')
                if marker_key and marker_key in self.node_markers:
                    # Get the position of this traffic light
                    for key, marker_data in self.node_markers[marker_key].items():
                        if key.startswith('traffic_light_'):
                            pos = marker_data.get('world_pos')
                            color = state.get('state', 'green')
                            try:
                                self.traffic_light_queue.put_nowait({
                                    'position': pos,
                                    'color': color
                                })
                            except:
                                pass
        
        # Schedule next update
        self.after(50, self.update_vehicle_positions)
    
    def select_junction(self, junction_type):
        """Handle selection of a specific junction type."""
        # Special handling for Roundabout - show config dialog immediately
        if junction_type == 'Roundabout':
            config_dialog = RoundaboutConfigDialog(self)
            if not config_dialog.result:
                print("Roundabout selection cancelled")
                return
            
            self.roundabout_exit_count = config_dialog.result['exit_count']
            self.roundabout_direction = config_dialog.result['direction']
            print(f"Roundabout configured with {self.roundabout_exit_count} exits, {self.roundabout_direction}")
        else:
            self.roundabout_exit_count = None
            self.roundabout_direction = None
        
        self.selected_junction_type = junction_type
        self.tool = 'junction'
        self.junction_rotation = 0  # Reset rotation
        self.junction_flipped = False  # Reset flip
        self.clear_junction_preview()  # Clear any existing preview
        print(f"Selected junction type: {junction_type}")
        self.status.config(text=f'Tool: Place {junction_type} | Grid: %d | R: Rotate | T: Flip | Space: Place' % self.grid_size)
    
    def rotate_point(self, x, y, cx, cy, degrees):
        """Rotate point (x, y) around center (cx, cy) by given degrees."""
        rad = math.radians(degrees)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        
        # Translate to origin
        dx = x - cx
        dy = y - cy
        
        # Rotate
        new_x = dx * cos_a - dy * sin_a
        new_y = dx * sin_a + dy * cos_a
        
        # Translate back
        return (new_x + cx, new_y + cy)
    
    def flip_point(self, x, y, cx):
        """Flip point (x, y) horizontally around center x coordinate cx."""
        return (2 * cx - x, y)
    
    def transform_template(self, template_lines, center_x, center_y):
        """Apply rotation and flip transformations to template lines."""
        transformed = []
        
        for line_points in template_lines:
            transformed_line = []
            for x, y in line_points:
                # Apply rotation
                if self.junction_rotation != 0:
                    x, y = self.rotate_point(x, y, center_x, center_y, self.junction_rotation)
                
                # Apply flip
                if self.junction_flipped:
                    x, y = self.flip_point(x, y, center_x)
                
                transformed_line.append((x, y))
            
            transformed.append(transformed_line)
        
        return transformed
    
    def clear_junction_preview(self):
        """Clear the junction preview from canvas."""
        for cid in self.junction_preview_ids:
            try:
                self.canvas.delete(cid)
            except:
                pass
        self.junction_preview_ids.clear()
    
    def draw_junction_preview(self, x, y):
        """Draw translucent preview of junction at position."""
        if not self.selected_junction_type:
            return
        
        # Clear previous preview
        self.clear_junction_preview()
        
        # Snap to grid
        x, y = self.snap(x, y)
        self.junction_preview_pos = (x, y)
        
        # Get exit_count for roundabouts
        exit_count = None
        if self.selected_junction_type == 'Roundabout':
            exit_count = getattr(self, 'roundabout_exit_count', None)
        
        # Get template and transform it
        template_lines = self.get_junction_template(self.selected_junction_type, x, y, exit_count)
        template_lines = self.transform_template(template_lines, x, y)
        
        # Get current theme for line color
        theme = self.theme['night'] if self.is_night_mode else self.theme['day']
        
        # Draw each line in the template with transparency
        for line_points in template_lines:
            pts_screen = [self.world_to_screen(px, py) for px, py in line_points]
            flat_pts = []
            for px, py in pts_screen:
                flat_pts.extend((px, py))
            
            # Draw with stipple pattern for translucency effect
            cid = self.canvas.create_line(*flat_pts, fill=theme['line'], width=2, 
                                          dash=(4, 4), stipple='gray50')
            self.junction_preview_ids.append(cid)
    
    def on_mouse_motion(self, ev):
        """Handle mouse motion for junction preview."""
        if self.tool == 'junction' and self.selected_junction_type:
            wx, wy = self.screen_to_world(ev.x, ev.y)
            self.draw_junction_preview(wx, wy)
    
    def on_space_press(self, ev):
        """Handle space bar press to place junction."""
        print(f"Space pressed - tool: {self.tool}, preview_pos: {self.junction_preview_pos}")
        if self.tool == 'junction' and self.junction_preview_pos:
            x, y = self.junction_preview_pos
            print(f"Placing junction at {x}, {y}")
            self.place_junction(x, y)
            self.clear_junction_preview()
            # Switch back to pen mode and clear any current drawing
            self.selected_junction_type = None
            self.junction_preview_pos = None
            self.junction_rotation = 0
            self.junction_flipped = False
            self.current = None  # Clear any current shape to prevent dialog
            self.set_tool('pen')
    
    def on_rotate_press(self, ev):
        """Handle R key press to rotate junction template."""
        if self.tool == 'junction' and self.selected_junction_type:
            self.junction_rotation = (self.junction_rotation + 45) % 360
            print(f"Rotation: {self.junction_rotation}°")
            # Redraw preview with new rotation
            if self.junction_preview_pos:
                self.draw_junction_preview(*self.junction_preview_pos)
    
    def on_flip_press(self, ev):
        """Handle T key press to flip junction template."""
        if self.tool == 'junction' and self.selected_junction_type:
            self.junction_flipped = not self.junction_flipped
            print(f"Flipped: {self.junction_flipped}")
            # Redraw preview with new flip state
            if self.junction_preview_pos:
                self.draw_junction_preview(*self.junction_preview_pos)
    
    def get_junction_template(self, junction_type, center_x, center_y, exit_count=None):
        """Return the template points for a junction type centered at (center_x, center_y).
        
        For Roundabout: exit_count can be 4 or 8 to determine number of exits.
        """
        g = self.grid_size
        templates = {
            'T-Section': [
                # Horizontal road (1 grid unit each side from center)
                [(center_x - g, center_y), (center_x, center_y)],
                [(center_x, center_y), (center_x + g, center_y)],
                # Vertical road (1 grid unit up from center)
                [(center_x, center_y), (center_x, center_y - g)]
            ],
            'Crossroads': [
                # Horizontal road (1 grid unit each side)
                [(center_x - g, center_y), (center_x, center_y)],
                [(center_x, center_y), (center_x + g, center_y)],
                # Vertical road (1 grid unit up and down)
                [(center_x, center_y - g), (center_x, center_y)],
                [(center_x, center_y), (center_x, center_y + g)]
            ],
            'Y-Intersection': [
                # Bottom vertical road (1 grid unit)
                [(center_x, center_y + g), (center_x, center_y)],
                # Top-left diagonal (1 grid unit)
                [(center_x, center_y), (center_x - g, center_y - g)],
                # Top-right diagonal (1 grid unit)
                [(center_x, center_y), (center_x + g, center_y - g)]
            ],
            'Ramp Merge': [
                # Main highway (1 grid unit each side)
                [(center_x - g, center_y), (center_x, center_y)],
                [(center_x, center_y), (center_x + g, center_y)],
                # Merge ramp (1 grid unit diagonal approach)
                [(center_x - g, center_y + g), (center_x, center_y)]
            ]
        }
        
        # Special handling for Roundabout with configurable exits
        if junction_type == 'Roundabout':
            lines = []
            
            # Always draw the octagon roundabout ring (2 grid units radius)
            octagon_radius = 2 * g
            octagon_points = []
            # Start from North (270° in standard math = -90° = up on screen)
            # Go clockwise: N, NE, E, SE, S, SW, W, NW
            for i in range(8):
                angle = math.radians(i * 45 - 90)  # -90° to start from North
                px = center_x + octagon_radius * math.cos(angle)
                py = center_y + octagon_radius * math.sin(angle)
                octagon_points.append((px, py))
            
            # Connect octagon points in a loop
            for i in range(8):
                p1 = octagon_points[i]
                p2 = octagon_points[(i + 1) % 8]
                lines.append([p1, p2])
            
            if exit_count == 4:
                # 4-exit roundabout: N, E, S, W
                # Exits at octagon vertices 0, 2, 4, 6 (N, E, S, W)
                exit_indices = [0, 2, 4, 6]  # N, E, S, W
                for idx in exit_indices:
                    vertex_point = octagon_points[idx]
                    # Calculate exit point 1 grid unit further from octagon vertex
                    angle = math.radians(idx * 45 - 90)
                    exit_x = center_x + (octagon_radius + g) * math.cos(angle)
                    exit_y = center_y + (octagon_radius + g) * math.sin(angle)
                    lines.append([vertex_point, (exit_x, exit_y)])
                    
            elif exit_count == 8:
                # 8-exit roundabout: N, NE, E, SE, S, SW, W, NW (all 8 vertices)
                for i in range(8):
                    vertex_point = octagon_points[i]
                    # Calculate exit point 1 grid unit further from octagon vertex
                    angle = math.radians(i * 45 - 90)  # Match octagon angle offset
                    exit_x = center_x + (octagon_radius + g) * math.cos(angle)
                    exit_y = center_y + (octagon_radius + g) * math.sin(angle)
                    lines.append([vertex_point, (exit_x, exit_y)])
            else:
                # Default to old octagon style if no exit_count specified
                return [
                    [(center_x + 2*g * math.cos(math.radians(i * 45)), 
                      center_y + 2*g * math.sin(math.radians(i * 45))),
                     (center_x + 2*g * math.cos(math.radians((i + 1) * 45)), 
                      center_y + 2*g * math.sin(math.radians((i + 1) * 45)))]
                    for i in range(8)
                ]
            
            return lines
        
        if junction_type == 'Landmark':
            # Landmark has no geometry - just a point marker
            return []
        
        return templates.get(junction_type, [])
    
    def get_junction_name(self):
        """Generate junction name like A, B, C, ..., Z, AA, AB, etc."""
        name = ''
        num = self.junction_counter
        
        while True:
            name = chr(65 + (num % 26)) + name
            num = num // 26
            if num == 0:
                break
            num -= 1  # Adjust for AA, AB pattern
        
        self.junction_counter += 1
        return name
    
    def place_junction(self, x, y):
        """Place a junction template at the given coordinates."""
        if not self.selected_junction_type:
            return
        
        # For Roundabout, use the stored exit_count from select_junction
        if self.selected_junction_type == 'Roundabout':
            exit_count = getattr(self, 'roundabout_exit_count', None)
            if exit_count is None:
                print("Roundabout not configured")
                return
        else:
            exit_count = None
        
        # Snap to grid
        x, y = self.snap(x, y)
        
        # Get template for this junction type and apply transformations
        template_lines = self.get_junction_template(self.selected_junction_type, x, y, exit_count)
        template_lines = self.transform_template(template_lines, x, y)
        
        # Get current theme for line color
        theme = self.theme['night'] if self.is_night_mode else self.theme['day']
        
        # Generate junction name (A, B, C, ... Z, AA, AB, etc.)
        junction_name = self.get_junction_name()
        
        # For Landmark, we don't draw any lines
        if self.selected_junction_type == 'Landmark':
            # Just create the label, no road geometry
            pass
        else:
            # Draw each line in the template as two-way roads
            for line_points in template_lines:
                # Convert world coords to screen coords
                pts_screen = [self.world_to_screen(px, py) for px, py in line_points]
                cid = self.canvas.create_line(*self.flatten(pts_screen), fill=theme['line'], width=2)
                
                # Store as a shape with junction metadata - all junction roads are two-way
                shape = {
                    'type': 'junction',
                    'junction_type': self.selected_junction_type,
                    'junction_name': junction_name,
                    'points': line_points,
                    'id': cid,
                    'road_config': {
                        'road_type': 'two_way',
                        'directions': None  # Two-way roads allow traffic in both directions
                    }
                }
                self.shapes.append(shape)
        
        # Draw junction label at center (scaled)
        sx, sy = self.world_to_screen(x, y)
        label_offset = 40 * self.scale
        font_size = max(8, int(10 * self.scale))
        label_text = f"Junction {junction_name}"
        text_color = theme['text']
        label_id = self.canvas.create_text(sx, sy - label_offset, text=label_text, 
                                          fill=text_color, font=('Arial', font_size, 'bold'),
                                          tags='junction_label')
        self.junction_labels[junction_name] = {
            'text_id': label_id,
            'position': (x, y),
            'name': junction_name,
            'junction_type': self.selected_junction_type,
            'roundabout_exit_count': exit_count if self.selected_junction_type == 'Roundabout' else None,
            'roundabout_direction': getattr(self, 'roundabout_direction', None) if self.selected_junction_type == 'Roundabout' else None
        }
        
        # Install pre-configured traffic lights for this junction
        self.install_junction_traffic_lights(self.selected_junction_type, x, y, template_lines, exit_count)
        
        print(f"Placed {self.selected_junction_type} at ({x}, {y}) - Junction {junction_name}")

    def install_junction_traffic_lights(self, junction_type, center_x, center_y, template_lines, exit_count=None):
        """Automatically install traffic lights on junction nodes with coordinated timing."""
        import time
        
        # Skip traffic lights for Landmark junctions
        if junction_type == 'Landmark':
            print(f"Landmark placed at ({center_x}, {center_y}) - no traffic lights installed")
            return
        
        print(f"Installing traffic lights for {junction_type} at center ({center_x}, {center_y})")
        print(f"Total shapes in system: {len(self.shapes)}")
        
        if junction_type == 'Crossroads':
            # Crossroads has 4 arms meeting at center
            # Phase A: North/South (8s green, 2s yellow)
            # Phase B: East/West (8s green, 2s yellow)
            
            g = self.grid_size
            
            # Define the nodes and their phases
            # North and South are Phase A, East and West are Phase B
            nodes_config = [
                # North arm (top) - Phase A
                {'pos': (center_x, center_y - g), 'phase': 'A', 'offset_direction': 'vertical'},
                # South arm (bottom) - Phase A
                {'pos': (center_x, center_y + g), 'phase': 'A', 'offset_direction': 'vertical'},
                # East arm (right) - Phase B
                {'pos': (center_x + g, center_y), 'phase': 'B', 'offset_direction': 'horizontal'},
                # West arm (left) - Phase B
                {'pos': (center_x - g, center_y), 'phase': 'B', 'offset_direction': 'horizontal'},
            ]
            
            # Phase timings
            phase_timings = {
                'A': {'green': 8, 'yellow': 2, 'red': 10},  # Red = Phase B duration
                'B': {'green': 8, 'yellow': 2, 'red': 10}   # Red = Phase A duration
            }
            
            # Current time for staggering
            current_time = time.time()
            
            for node_config in nodes_config:
                pos = node_config['pos']
                phase = node_config['phase']
                timing = phase_timings[phase]
                
                # Find the shape that contains this node
                nearest_shape = None
                for shape in self.shapes:
                    if shape.get('junction_type') == junction_type:
                        for px, py in shape['points']:
                            if (px, py) == pos:
                                nearest_shape = shape
                                break
                    if nearest_shape:
                        break
                
                if not nearest_shape:
                    continue
                
                # Create marker key
                marker_key = (nearest_shape.get('id'), pos)
                if marker_key not in self.node_markers:
                    self.node_markers[marker_key] = {}
                
                # Calculate perpendicular offset based on direction
                if node_config['offset_direction'] == 'vertical':
                    # For north/south arms, offset horizontally
                    perpendicular_offset_x = 15
                    perpendicular_offset_y = 0
                else:
                    # For east/west arms, offset vertically
                    perpendicular_offset_x = 0
                    perpendicular_offset_y = 15
                
                # Add two traffic lights (one on each side of two-way road)
                for light_num in range(2):
                    offset_x = perpendicular_offset_x if light_num == 0 else -perpendicular_offset_x
                    offset_y = perpendicular_offset_y if light_num == 0 else -perpendicular_offset_y
                    
                    # Draw traffic light (scaled)
                    sx, sy = self.world_to_screen(*pos)
                    sx += offset_x * self.scale
                    sy += offset_y * self.scale
                    
                    # Scale the sizes
                    outer_radius = 10 * self.scale
                    inner_radius = 8 * self.scale
                    border_width = max(1, int(2 * self.scale))
                    
                    # Draw border (outer circle)
                    border_id = self.canvas.create_oval(sx - outer_radius, sy - outer_radius, 
                                                       sx + outer_radius, sy + outer_radius, 
                                                       fill='black', outline='black', width=border_width, tags='marker')
                    
                    # Determine initial color based on phase
                    # Phase A starts with green (0-10s), Phase B starts with red (wait for Phase A)
                    if phase == 'A':
                        initial_color = 'green'
                        state_index = 0  # green
                    else:  # Phase B
                        initial_color = 'red'
                        state_index = 2  # red
                    
                    # Draw inner light
                    light_id = self.canvas.create_oval(sx - inner_radius, sy - inner_radius, 
                                                      sx + inner_radius, sy + inner_radius, 
                                                      fill=initial_color, outline='', tags='marker')
                    
                    # Generate unique ID for this light
                    light_unique_id = self.traffic_light_next_id
                    self.traffic_light_next_id += 1
                    
                    # Store marker info
                    light_key = f'traffic_light_{light_num}'
                    self.node_markers[marker_key][light_key] = {
                        'border_id': border_id,
                        'light_id': light_id,
                        'world_pos': pos,
                        'current_color': initial_color,
                        'perpendicular_offset': (offset_x, offset_y),
                        'unique_id': light_unique_id
                    }
                    
                    # Initialize traffic light state with phase timing
                    self.traffic_light_states[light_unique_id] = {
                        'state': initial_color,
                        'state_index': state_index,
                        'timing': timing,
                        'marker_key': marker_key,
                        'light_key': light_key,
                        'last_change': current_time,
                        'phase': phase,
                        'junction_type': junction_type
                    }
            
            print(f"Installed coordinated traffic lights on {junction_type}")
            
            # Start animation if this is the first set of traffic lights
            if len(self.traffic_light_states) > 0:
                # Check if animation is already running by checking if we have a pending after call
                # For safety, always ensure animation is running
                if not hasattr(self, '_animation_started'):
                    self._animation_started = True
                    self.animate_traffic_lights()
        
        elif junction_type == 'Roundabout' and exit_count is not None:
            # Roundabout with 4 or 8 exits
            # Opposite exits get green at the same time
            g = self.grid_size
            current_time = time.time()
            octagon_radius = 2 * g  # Octagon has 2-node radius
            
            if exit_count == 4:
                # 4-exit roundabout: 20-second cycle
                # 0–8s   : N+S Green
                # 8–10s  : N+S Yellow
                # 10–18s : E+W Green
                # 18–20s : E+W Yellow
                
                # Traffic lights at end of exit roads (octagon_radius + g from center)
                exit_distance = octagon_radius + g
                nodes_config = [
                    {'pos': (center_x, center_y - exit_distance), 'phase': 'A', 'green': 8, 'yellow': 2, 'offset': 0},   # North (Phase A)
                    {'pos': (center_x + exit_distance, center_y), 'phase': 'B', 'green': 8, 'yellow': 2, 'offset': 10},  # East (Phase B)
                    {'pos': (center_x, center_y + exit_distance), 'phase': 'A', 'green': 8, 'yellow': 2, 'offset': 0},   # South (Phase A, same as North)
                    {'pos': (center_x - exit_distance, center_y), 'phase': 'B', 'green': 8, 'yellow': 2, 'offset': 10}   # West (Phase B, same as East)
                ]
                cycle_time = 20
                
            elif exit_count == 8:
                # 8-exit roundabout: 24-second cycle
                # 0–8s   : N,E,S,W -> GREEN
                # 8–11s  : N,E,S,W -> YELLOW
                # 11–12s : ALL RED (buffer)
                # 12–20s : NE,SE,SW,NW -> GREEN
                # 20–23s : NE,SE,SW,NW -> YELLOW
                # 23–24s : ALL RED (buffer)
                
                exit_distance = octagon_radius + g
                
                # Calculate positions for all 8 exits: N, NE, E, SE, S, SW, W, NW
                positions = []
                for idx in range(8):
                    angle_rad = math.radians(idx * 45 - 90)
                    pos_x = center_x + exit_distance * math.cos(angle_rad)
                    pos_y = center_y + exit_distance * math.sin(angle_rad)
                    positions.append((pos_x, pos_y))
                
                # Phase A: Cardinal directions (N, E, S, W) - indices 0, 2, 4, 6
                # Phase B: Diagonal directions (NE, SE, SW, NW) - indices 1, 3, 5, 7
                nodes_config = [
                    {'pos': positions[0], 'phase': 'A', 'green': 8, 'yellow': 3, 'red_buffer': 1, 'offset': 0},   # N (Phase A - cardinals)
                    {'pos': positions[1], 'phase': 'B', 'green': 8, 'yellow': 3, 'red_buffer': 1, 'offset': 12},  # NE (Phase B - diagonals)
                    {'pos': positions[2], 'phase': 'A', 'green': 8, 'yellow': 3, 'red_buffer': 1, 'offset': 0},   # E (Phase A - cardinals)
                    {'pos': positions[3], 'phase': 'B', 'green': 8, 'yellow': 3, 'red_buffer': 1, 'offset': 12},  # SE (Phase B - diagonals)
                    {'pos': positions[4], 'phase': 'A', 'green': 8, 'yellow': 3, 'red_buffer': 1, 'offset': 0},   # S (Phase A - cardinals)
                    {'pos': positions[5], 'phase': 'B', 'green': 8, 'yellow': 3, 'red_buffer': 1, 'offset': 12},  # SW (Phase B - diagonals)
                    {'pos': positions[6], 'phase': 'A', 'green': 8, 'yellow': 3, 'red_buffer': 1, 'offset': 0},   # W (Phase A - cardinals)
                    {'pos': positions[7], 'phase': 'B', 'green': 8, 'yellow': 3, 'red_buffer': 1, 'offset': 12}   # NW (Phase B - diagonals)
                ]
                cycle_time = 24
            
            # Install traffic lights for each exit
            for node_config in nodes_config:
                pos = node_config['pos']
                phase = node_config['phase']
                green_time = node_config['green']
                yellow_time = node_config['yellow']
                offset = node_config['offset']
                red_buffer = node_config.get('red_buffer', 0)  # Optional red buffer time
                
                # Calculate red time (includes buffer if specified)
                red_time = cycle_time - green_time - yellow_time
                
                timing = {
                    'green': green_time,
                    'yellow': yellow_time,
                    'red': red_time,
                    'red_buffer': red_buffer
                }
                
                # Calculate the road direction vector (from center to exit)
                road_dx = pos[0] - center_x
                road_dy = pos[1] - center_y
                road_length = math.sqrt(road_dx * road_dx + road_dy * road_dy)
                
                # Normalize road direction
                if road_length > 0:
                    road_dx /= road_length
                    road_dy /= road_length
                else:
                    road_dx, road_dy = 0, 1
                
                # Calculate perpendicular direction (rotate 90 degrees)
                # Perpendicular to (dx, dy) is (-dy, dx)
                perp_dx = -road_dy
                perp_dy = road_dx
                
                # Scale to desired offset distance
                offset_distance = 15
                perpendicular_offset_x = perp_dx * offset_distance
                perpendicular_offset_y = perp_dy * offset_distance
                
                # Find the shape that contains this node
                nearest_shape = None
                for shape in self.shapes:
                    if shape.get('junction_type') == junction_type:
                        for px, py in shape['points']:
                            # Check with small tolerance for floating point
                            if abs(px - pos[0]) < 0.1 and abs(py - pos[1]) < 0.1:
                                nearest_shape = shape
                                break
                    if nearest_shape:
                        break
                
                if not nearest_shape:
                    continue
                
                # Create marker key
                marker_key = (nearest_shape.get('id'), pos)
                if marker_key not in self.node_markers:
                    self.node_markers[marker_key] = {}
                
                # Determine initial state based on offset
                elapsed = (current_time % cycle_time)
                time_in_phase = elapsed - offset
                if time_in_phase < 0:
                    time_in_phase += cycle_time
                
                if time_in_phase < green_time:
                    initial_color = 'green'
                    state_index = 0
                elif time_in_phase < green_time + yellow_time:
                    initial_color = 'yellow'
                    state_index = 1
                else:
                    initial_color = 'red'
                    state_index = 2
                
                # Add two traffic lights (one on each side)
                for light_num in range(2):
                    offset_x = perpendicular_offset_x if light_num == 0 else -perpendicular_offset_x
                    offset_y = perpendicular_offset_y if light_num == 0 else -perpendicular_offset_y
                    
                    # Draw traffic light (scaled)
                    sx, sy = self.world_to_screen(*pos)
                    sx += offset_x * self.scale
                    sy += offset_y * self.scale
                    
                    # Scale the sizes
                    outer_radius = 10 * self.scale
                    inner_radius = 8 * self.scale
                    border_width = max(1, int(2 * self.scale))
                    
                    # Draw border
                    border_id = self.canvas.create_oval(sx - outer_radius, sy - outer_radius, 
                                                       sx + outer_radius, sy + outer_radius, 
                                                       fill='black', outline='black', width=border_width, tags='marker')
                    
                    # Draw inner light
                    light_id = self.canvas.create_oval(sx - inner_radius, sy - inner_radius, 
                                                      sx + inner_radius, sy + inner_radius, 
                                                      fill=initial_color, outline='', tags='marker')
                    
                    # Generate unique ID
                    light_unique_id = self.traffic_light_next_id
                    self.traffic_light_next_id += 1
                    
                    # Store marker info
                    light_key = f'traffic_light_{light_num}'
                    self.node_markers[marker_key][light_key] = {
                        'border_id': border_id,
                        'light_id': light_id,
                        'world_pos': pos,
                        'current_color': initial_color,
                        'perpendicular_offset': (offset_x, offset_y),
                        'unique_id': light_unique_id
                    }
                    
                    # Initialize traffic light state
                    self.traffic_light_states[light_unique_id] = {
                        'state': initial_color,
                        'state_index': state_index,
                        'timing': timing,
                        'marker_key': marker_key,
                        'light_key': light_key,
                        'last_change': current_time - time_in_phase,  # Adjust for phase offset
                        'phase': phase,
                        'junction_type': junction_type,
                        'cycle_time': cycle_time,
                        'phase_offset': offset
                    }
            
            print(f"Installed {exit_count}-exit roundabout with {cycle_time}s cycle at {junction_type}")
            
            # Start animation
            if len(self.traffic_light_states) > 0:
                if not hasattr(self, '_animation_started'):
                    self._animation_started = True
                    self.animate_traffic_lights()

    def export_coords(self):
        out = []
        for s in self.shapes:
            out.append((s['type'], s['points']))
        dlg = tk.Toplevel(self)
        dlg.title('Exported coordinates')
        text = tk.Text(dlg, width=80, height=20)
        text.pack(fill='both', expand=True)
        text.insert('1.0', repr(out))

    def snap(self, x, y):
        g = self.grid_size
        return (round(x / g) * g, round(y / g) * g)
    
    def screen_to_world(self, sx, sy):
        """Convert screen coordinates to world coordinates."""
        wx = (sx - self.offset_x) / self.scale
        wy = (sy - self.offset_y) / self.scale
        return (wx, wy)
    
    def world_to_screen(self, wx, wy):
        """Convert world coordinates to screen coordinates."""
        sx = wx * self.scale + self.offset_x
        sy = wy * self.scale + self.offset_y
        return (sx, sy)

    def draw_grid(self):
        # get current theme colors
        theme = self.theme['night'] if self.is_night_mode else self.theme['day']
        
        # update canvas background
        self.canvas.config(bg=theme['bg'])
        
        self.canvas.delete('grid')
        g = self.grid_size
        w = self.canvas.winfo_width() or self.width
        h = self.canvas.winfo_height() or self.height
        
        # calculate world bounds visible on screen
        world_x0, world_y0 = self.screen_to_world(0, 0)
        world_x1, world_y1 = self.screen_to_world(w, h)
        
        # find grid range
        grid_x_start = math.floor(world_x0 / g) * g
        grid_x_end = math.ceil(world_x1 / g) * g
        grid_y_start = math.floor(world_y0 / g) * g
        grid_y_end = math.ceil(world_y1 / g) * g
        
        # draw grid dots with theme color
        r = 2
        for i in range(int(grid_x_start), int(grid_x_end) + g, g):
            for j in range(int(grid_y_start), int(grid_y_end) + g, g):
                sx, sy = self.world_to_screen(i, j)
                self.canvas.create_oval(sx - r, sy - r, sx + r, sy + r, fill=theme['grid'], outline='', tags='grid')
        
        # redraw shapes on top with theme color
        for s in self.shapes:
            pts_screen = [self.world_to_screen(x, y) for x, y in s['points']]
            if s['type'] == 'line':
                if 'id' in s and s['id']:
                    self.canvas.delete(s['id'])
                s['id'] = self.canvas.create_line(*self.flatten(pts_screen), fill=theme['line'], width=2)
            elif s['type'] == 'poly':
                if 'id' in s and s['id']:
                    self.canvas.delete(s['id'])
                s['id'] = self.canvas.create_line(*self.flatten(pts_screen), fill=theme['line'], width=2, smooth=False)
        
        # Redraw markers (traffic lights and pedestrian crossings)
        self.canvas.delete('marker')
        for marker_key, markers in self.node_markers.items():
            # Redraw all traffic lights at this node
            for key, marker_data in markers.items():
                if key.startswith('traffic_light_'):
                    wx, wy = marker_data['world_pos']
                    sx, sy = self.world_to_screen(wx, wy)
                    
                    # Apply perpendicular offset (scaled)
                    offset_x, offset_y = marker_data.get('perpendicular_offset', (0, 15))
                    sx += offset_x * self.scale
                    sy += offset_y * self.scale
                    
                    # Scale the sizes
                    outer_radius = 10 * self.scale
                    inner_radius = 8 * self.scale
                    border_width = max(1, int(2 * self.scale))
                    
                    # Redraw border (outer circle)
                    border_id = self.canvas.create_oval(sx - outer_radius, sy - outer_radius, 
                                                       sx + outer_radius, sy + outer_radius, 
                                                       fill='black', outline='black', width=border_width, tags='marker')
                    
                    # Redraw light with current color (inner circle)
                    current_color = marker_data.get('current_color', 'green')
                    light_id = self.canvas.create_oval(sx - inner_radius, sy - inner_radius, 
                                                      sx + inner_radius, sy + inner_radius, 
                                                      fill=current_color, outline='', tags='marker')
                    
                    # Update stored IDs
                    marker_data['border_id'] = border_id
                    marker_data['light_id'] = light_id
            
            # Redraw pedestrian crossing
            if 'ped_crossing' in markers:
                wx, wy = markers['ped_crossing']['world_pos']
                sx, sy = self.world_to_screen(wx, wy)
                
                # Apply vertical offset to avoid obstructing traffic lights (scaled)
                ped_offset_y = markers['ped_crossing'].get('offset_y', 25)
                sy += ped_offset_y * self.scale
                
                # Scale the sizes
                housing_width = 10 * self.scale
                housing_height = 6 * self.scale
                light_radius = 4 * self.scale
                border_width = max(1, int(2 * self.scale))
                
                # Redraw housing (white rectangle)
                housing_id = self.canvas.create_rectangle(sx - housing_width, sy - housing_height, 
                                                         sx + housing_width, sy + housing_height, 
                                                         fill='white', outline='black', width=border_width, tags='marker')
                
                # Redraw pedestrian light with current color
                current_color = markers['ped_crossing'].get('current_color', 'red')
                ped_light_id = self.canvas.create_oval(sx - light_radius, sy - light_radius, 
                                                      sx + light_radius, sy + light_radius, 
                                                      fill=current_color, outline='', tags='marker')
                
                # Update stored IDs
                markers['ped_crossing']['housing_id'] = housing_id
                markers['ped_crossing']['light_id'] = ped_light_id
        
        # Redraw junction labels
        self.canvas.delete('junction_label')
        for junction_name, label_data in self.junction_labels.items():
            wx, wy = label_data['position']
            sx, sy = self.world_to_screen(wx, wy)
            
            # Scale the label offset and font size
            label_offset = 40 * self.scale
            font_size = max(8, int(10 * self.scale))
            
            label_text = f"Junction {junction_name}"
            text_id = self.canvas.create_text(sx, sy - label_offset, text=label_text,
                                             fill=theme['text'], font=('Arial', font_size, 'bold'),
                                             tags='junction_label')
            label_data['text_id'] = text_id

    def flatten(self, pts):
        out = []
        for x, y in pts:
            out.extend((x, y))
        return out

    def on_down(self, ev):
        # get current theme
        theme = self.theme['night'] if self.is_night_mode else self.theme['day']
        
        # convert screen to world coordinates
        wx, wy = self.screen_to_world(ev.x, ev.y)
        x, y = self.snap(wx, wy)
        self._dragging = True

        if self.tool == 'junction':
            # Junction mode - preview only, placement happens with space bar
            # Don't place on click, just update preview position
            self._dragging = False
            return

        elif self.tool == 'pen':
            # start with two identical points so create_line receives 4 coords
            pts = [(x, y), (x, y)]
            pts_screen = [self.world_to_screen(px, py) for px, py in pts]
            cid = self.canvas.create_line(*self.flatten(pts_screen), fill=theme['line'], width=2)
            self.current = {'type': 'poly', 'points': pts, 'id': cid}
            self.shapes.append(self.current)

        elif self.tool == 'line':
            pts = [(x, y), (x, y)]
            pts_screen = [self.world_to_screen(px, py) for px, py in pts]
            cid = self.canvas.create_line(*self.flatten(pts_screen), fill=theme['line'], width=2)
            self.current = {'type': 'line', 'points': pts, 'id': cid}
            self.shapes.append(self.current)

        elif self.tool == 'traffic_light':
            # Add traffic light to nearest junction/intersection
            self.add_traffic_light(x, y)
            self._dragging = False
            return

        elif self.tool == 'ped_crossing':
            # Add pedestrian crossing to nearest road point
            self.add_pedestrian_crossing(x, y)
            self._dragging = False
            return
        
        elif self.tool == 'spawn_vehicle':
            # Spawn vehicle at clicked node
            self.spawn_vehicle_at_node(x, y)
            self._dragging = False
            # Return to pen mode after spawning
            self.tool = 'pen'
            self.status.config(text='Tool: %s | Grid: %d' % (self.tool, self.grid_size))
            return

        elif self.tool == 'erase':
            # remove any shape with a point near (in world coords)
            to_remove = None
            thresh = self.grid_size * 0.5
            for s in reversed(self.shapes):
                for px, py in s['points']:
                    if (px - x) ** 2 + (py - y) ** 2 < thresh ** 2:
                        to_remove = s
                        break
                if to_remove:
                    break
            if to_remove:
                try:
                    self.canvas.delete(to_remove.get('id'))
                except Exception:
                    pass
                try:
                    self.shapes.remove(to_remove)
                except Exception:
                    pass

        elif self.tool == 'move':
            # pick shape under cursor (in world coords)
            sel = None
            for s in reversed(self.shapes):
                # bounding box
                xs = [p[0] for p in s['points']]
                ys = [p[1] for p in s['points']]
                if min(xs) - 4 <= x <= max(xs) + 4 and min(ys) - 4 <= y <= max(ys) + 4:
                    sel = s
                    break
            self.selection = sel
            self._move_prev = (x, y)

    def on_move(self, ev):
        if not self._dragging:
            return
        # convert screen to world coordinates
        x_raw, y_raw = self.screen_to_world(ev.x, ev.y)
        x, y = self.snap(x_raw, y_raw)
        
        if not self.current and self.tool == 'move' and self.selection:
            dx = x - self._move_prev[0]
            dy = y - self._move_prev[1]
            for i, (px, py) in enumerate(self.selection['points']):
                self.selection['points'][i] = (px + dx, py + dy)
            self._move_prev = (x, y)
            self.draw_grid()
            return
        if not self.current:
            return
        if self.current['type'] == 'poly':
            self.current['points'].append((x, y))
            pts_screen = [self.world_to_screen(px, py) for px, py in self.current['points']]
            self.canvas.coords(self.current['id'], *self.flatten(pts_screen))
        elif self.current['type'] == 'line':
            # if Shift is held, constrain line to nearest 45-degree multiple
            shift = (ev.state & 0x0001) != 0
            x0, y0 = self.current['points'][0]
            if shift:
                dx = x_raw - x0
                dy = y_raw - y0
                if dx == 0 and dy == 0:
                    ang = 0
                else:
                    ang = math.atan2(dy, dx)
                # snap to nearest 45 degrees (pi/4)
                step = math.pi / 4
                ang_snap = round(ang / step) * step
                dist = math.hypot(dx, dy)
                nx = x0 + math.cos(ang_snap) * dist
                ny = y0 + math.sin(ang_snap) * dist
                x, y = self.snap(nx, ny)
            self.current['points'][1] = (x, y)
            pts_screen = [self.world_to_screen(px, py) for px, py in self.current['points']]
            self.canvas.coords(self.current['id'], *self.flatten(pts_screen))

    def on_up(self, ev):
        self._dragging = False
        
        # If a road was just drawn (pen or line tool), show configuration dialog
        if self.current and self.current['type'] in ['poly', 'line']:
            shape = self.current
            # Show dialog for road configuration
            dialog = RoadConfigDialog(self, shape['type'], shape['points'])
            
            if dialog.result:
                # Store road configuration in shape
                shape['road_config'] = dialog.result
                print(f"Road configured: {dialog.result}")
            else:
                # If cancelled, still keep the road but with default config
                shape['road_config'] = {
                    'road_type': 'two_way',
                    'detected_direction': 'Unknown'
                }
                print("Road configuration cancelled, using defaults")
        
        self.current = None

    def on_pan_start(self, ev):
        """Start panning with middle mouse button."""
        self._panning = True
        self._pan_start = (ev.x, ev.y)

    def on_pan_move(self, ev):
        """Update pan offset during middle mouse drag."""
        if not self._panning or not self._pan_start:
            return
        dx = ev.x - self._pan_start[0]
        dy = ev.y - self._pan_start[1]
        self.offset_x += dx
        self.offset_y += dy
        self._pan_start = (ev.x, ev.y)
        self.draw_grid()

    def on_pan_end(self, ev):
        """End panning."""
        self._panning = False
        self._pan_start = None

    def on_zoom(self, ev):
        """Zoom in/out with mouse wheel, centered on cursor."""
        # determine zoom direction
        if ev.num == 5 or ev.delta < 0:  # zoom out
            factor = 0.9
        elif ev.num == 4 or ev.delta > 0:  # zoom in
            factor = 1.1
        else:
            return
        
        # get mouse position in world coords before zoom
        old_world_x, old_world_y = self.screen_to_world(ev.x, ev.y)
        
        # update scale
        self.scale *= factor
        
        # get mouse position in world coords after zoom (without offset adjustment)
        # we want the same world point to remain under the cursor
        new_world_x, new_world_y = self.screen_to_world(ev.x, ev.y)
        
        # adjust offsets so old_world point stays at cursor
        self.offset_x += (old_world_x - new_world_x) * self.scale
        self.offset_y += (old_world_y - new_world_y) * self.scale
        
        self.draw_grid()

if __name__ == '__main__':
    multiprocessing.freeze_support()  # Required for Windows
    app = GraphPaper()
    
    # Cleanup on exit
    def on_closing():
        print("Closing application...")
        try:
            # Stop simulation and set stop event
            app.simulation_running = False
            app.stop_event.set()
            
            # Clear all vehicles and terminate processes
            for vehicle_id, vehicle_data in list(app.vehicles.items()):
                try:
                    process = vehicle_data['process']
                    if process.is_alive():
                        print(f"Terminating vehicle {vehicle_id} process...")
                        process.terminate()
                        process.join(timeout=0.5)
                        
                        # If still alive, kill it
                        if process.is_alive():
                            print(f"Force killing vehicle {vehicle_id} process...")
                            process.kill()
                            process.join(timeout=0.5)
                except Exception as e:
                    print(f"Error stopping vehicle {vehicle_id}: {e}")
            
            # Clear the vehicles dictionary
            app.vehicles.clear()
            
            print("All processes terminated. Exiting...")
        except Exception as e:
            print(f"Error during cleanup: {e}")
        finally:
            # Destroy the window and quit
            app.quit()
            try:
                app.destroy()
            except:
                pass
            # Force exit the Python process
            sys.exit(0)
    
    app.protocol("WM_DELETE_WINDOW", on_closing)
    
    try:
        app.mainloop()
    except KeyboardInterrupt:
        print("\nKeyboard interrupt detected")
        on_closing()

