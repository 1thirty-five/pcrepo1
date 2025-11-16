# Parallel Computing Implementation

## Overview
This traffic control system now includes **parallel computing** using Python's `multiprocessing` module to simulate vehicle movement along roads.

## How It Works

### 1. **Separate Processes for Each Vehicle**
- Each vehicle runs in its own independent process
- Uses `multiprocessing.Process` to create separate Python processes
- Each process calculates vehicle position independently in parallel

### 2. **Inter-Process Communication**
- **Position Queue**: Vehicles send their position updates to main thread via `multiprocessing.Queue`
- **Traffic Light Queue**: Main thread sends traffic light states to vehicle processes
- **Stop Event**: `multiprocessing.Event` to coordinate stopping all processes

### 3. **Vehicle Movement Process**
```python
def vehicle_movement_process(vehicle_id, path_points, speed, position_queue, traffic_light_queue, stop_event)
```
- Runs in separate process (true parallel execution)
- Calculates vehicle position along road path
- Checks for red/yellow traffic lights and stops accordingly
- Sends position updates every 50ms

### 4. **Main Thread Integration**
- `update_vehicle_positions()` runs in main Tkinter thread
- Reads position updates from queue
- Updates vehicle visuals on canvas
- Sends traffic light states to vehicles

## Usage

### Starting Simulation
1. Draw some roads using the pen or line tool
2. Place junction templates if desired
3. Click **Simulation** → **Spawn Vehicle** to add vehicles
4. Click **Start Simulation** to begin parallel movement
5. Watch vehicles move independently in parallel processes!

### Controls
- **Spawn Vehicle**: Creates a new vehicle on a random road
  - Each vehicle gets its own process
  - Random color and speed
  - Process ID is printed to console
- **Start/Stop Simulation**: Controls vehicle movement
- **Clear Vehicles**: Removes all vehicles and terminates processes

## Parallel Computing Benefits

1. **True Parallelism**: Each vehicle's position is calculated independently in separate CPU cores
2. **Scalability**: Can handle multiple vehicles simultaneously
3. **Non-blocking**: Main GUI remains responsive while vehicles move
4. **Realistic**: Simulates real-world traffic with independent vehicle behaviors

## Traffic Light Integration
- Vehicles check traffic light states via queue
- When approaching a red/yellow light (>80% of segment), vehicles stop
- When light turns green, vehicles resume movement
- Demonstrates process synchronization and communication

## Technical Details

### Process Creation
```python
process = Process(target=vehicle_movement_process,
                 args=(vehicle_id, path_points, speed, 
                       vehicle_position_queue, traffic_light_queue, 
                       stop_event))
process.start()
```

### Queue Communication
- **Non-blocking**: Uses `get_nowait()` and `put_nowait()`
- **Buffered**: Queue can hold multiple messages
- **Thread-safe**: Automatically handled by multiprocessing

### Cleanup
- All processes are properly terminated on exit
- `WM_DELETE_WINDOW` protocol ensures cleanup
- Uses `freeze_support()` for Windows compatibility

## Requirements
- Python 3.x with multiprocessing support
- Works on Windows, Linux, macOS
- No additional packages required

## Notes
- This is a **temporary** implementation for demonstration
- Can be easily reverted by removing the Simulation category
- Demonstrates parallel computing concepts in a visual, interactive way
