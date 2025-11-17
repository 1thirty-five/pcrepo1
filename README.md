# Traffic Simulation Editor

A comprehensive traffic simulation and road network editor built with Python and Tkinter, featuring real-time vehicle movement, traffic light coordination, and intelligent route planning.

## Features

### 🎨 Road Network Editor
- **Drawing Tools**: Create roads, curves, and complex road networks with mouse-based drawing
- **Junction Types**: Multiple pre-built junction templates
  - T-Section
  - Crossroads (4-way intersection)
  - Y-Intersection
  - Roundabout (octagonal with configurable direction: CW/CCW)
  - Ramp Merge
  - Landmark (waypoint markers without geometry)
- **Road Configuration**: Two-way and one-way roads with directional arrows
- **Grid System**: Adjustable grid size (16px to 64px) with snap-to-grid functionality
- **Pan & Zoom**: Infinite canvas with middle-mouse pan and mouse wheel zoom
- **Pedestrian Crossings**: Add crosswalks at any location

### 🚦 Traffic Light System
- **Automatic Installation**: Traffic lights automatically placed at junctions
- **Phase Coordination**: Synchronize lights across the network with configurable:
  - Cycle time (duration of full light cycle)
  - Phase offset (timing offset for coordination)
  - Green time (duration of green phase)
- **Manual Control**: Individual light editing and traffic light deletion
- **Visual Indicators**: Real-time display of light states (Red/Yellow/Green)

### 🚗 Vehicle Simulation
- **Multiprocessing Architecture**: Each vehicle runs in a separate process for true parallelism
- **Realistic Movement**: Vehicles follow roads, stop at red lights, and navigate junctions
- **Smart Routing**: Advanced route following with multiple command formats:
  - **Relative directions**: LEFT/L, RIGHT/R, STRAIGHT/ST at junctions
  - **Compass directions**: N, S, E, W, NE, SE, SW, NW (global coordinates)
  - **Compact format**: `N_A` (go north at Junction A)
  - **Multi-junction routes**: `N_A E_B S_C` (navigate through multiple junctions)
- **Junction Intelligence**:
  - Green light commitment: vehicles that enter junctions on green can pass through
  - Junction zone pass-through: ignore traffic lights while inside junction to prevent impossible stops
  - Roundabout navigation: proper octagon traversal with correct exit selection
- **Speed Control**: Adjustable vehicle speed (0.5x to 3.0x)
- **Auto-follow Mode**: Vehicles automatically follow connected roads without explicit commands

### 📊 Route Optimization
- **Shortest Route Calculator**: Find optimal paths between junctions
  - Tests multiple route options (direct, via intermediate junctions, different exit directions)
  - Considers traffic light timing in travel time calculations
  - Displays all possible routes sorted by estimated time
  - Shows complete junction path (A → B → C → D format)
- **Traffic Light Simulation**: Estimates delays based on light phases and timing

### 🎛️ User Interface
- **Tabbed Layout**: Organized into Drawing, Junctions, Traffic Lights, Roads, and Simulation tabs
- **Theme Support**: Light and dark themes
- **Real-time Updates**: Live display of vehicle positions and traffic light states
- **Status Bar**: Shows current tool, grid size, and zoom level
- **Keyboard Shortcuts**: 
  - Space + Drag: Pan canvas
  - Mouse Wheel: Zoom in/out
  - Delete: Remove selected elements

### 💾 File Operations
- **Save/Load**: Persist road networks, junctions, traffic lights, and vehicles
- **JSON Format**: Human-readable file format for easy editing and version control

### 🔧 Configuration
- **Grid Settings**: Adjustable grid size with visual display
- **Theme Customization**: Switch between light and dark color schemes
- **Junction Properties**: Configure roundabout direction and junction names
- **Traffic Light Timing**: Fine-tune cycle times, phase offsets, and green durations

## Technical Architecture

### Parallel Processing
- Each vehicle runs in a separate Python process using `multiprocessing`
- Inter-process communication via `Queue` objects for position updates
- Stop events for clean process termination
- Proper cleanup on application exit

### Coordinate System
- World coordinates for logical positioning
- Screen coordinates with zoom/pan transforms
- Automatic scaling of all visual elements (vehicles, lights, labels) with zoom level

### Traffic Light Coordination
- Phase-based system for synchronized traffic flow
- Configurable timing parameters for realistic traffic patterns
- Individual light control for special scenarios

## Installation & Usage

### Requirements
- Python 3.7+
- tkinter (usually included with Python)
- multiprocessing (standard library)

### Running the Application

```powershell
python main.py
```

### Basic Workflow
1. **Draw Roads**: Use the Drawing tab to create your road network
2. **Add Junctions**: Place junctions at intersections using the Junctions tab
3. **Configure Traffic Lights**: Adjust timing in the Traffic Lights tab (auto-installed at junctions)
4. **Spawn Vehicles**: Add vehicles with routes in the Simulation tab
5. **Optimize Routes**: Use Shortest Route to find optimal paths between junctions
6. **Save Your Work**: Save the complete network to a JSON file

## Notes
- Junction zones extend beyond the visible junction geometry to ensure proper vehicle behavior
- Roundabouts require sufficient tolerance (5.0 × grid_size) for proper exit detection
- Traffic lights are automatically managed but can be customized per junction
- Vehicle processes are properly terminated on application exit
```