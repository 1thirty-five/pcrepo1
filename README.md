Traffic control multiprocessing demo

This small demo shows a simple traffic simulation running in a separate
process while a Tkinter GUI displays the road grid, vehicles and traffic
lights. It's deliberately minimal so you can extend it for your project.

Run on Windows with PowerShell:

```powershell
python main.py
```

Controls
- Start Simulation: spawn the worker process
- Stop Simulation: stop/terminate it
- Click canvas: toggle a road cell on/off (sends update to simulation)

Notes
- The simulation uses multiprocessing.Queue for IPC. Always run the GUI
  script with the `if __name__ == '__main__'` guard (already present).
- This is a prototype. For production consider stronger synchronization,
  more realistic vehicle routing, and better process lifecycle handling.
# pcrepo1
```