"""Simple traffic simulation process.

This module exposes `run_simulation(command_queue, state_queue, initial)` which
runs a loop in a separate process, updates vehicle positions on a grid of road
cells, toggles traffic lights at intersections, and sends state dicts back to
the GUI via `state_queue`.

This is intentionally small and synchronous to keep complexity low for the
demo. It's picklable-friendly and uses only stdlib.
"""
import time
import math


def run_simulation(cmd_q, state_q, initial):
    # state
    roads = set(tuple(r) for r in initial.get('roads', []))
    vehicles = {}  # id -> dict(pos=(x,y), dir=(dx,dy), color)
    lights = {}  # pos -> mode 'NS' or 'EW'

    next_vid = 1

    # initialize lights at road intersections (simple rule: cells with >=2 road neighbors)
    for x, y in list(roads):
        neighbors = 0
        for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
            if (x+dx, y+dy) in roads:
                neighbors += 1
        if neighbors >= 2:
            lights[(x,y)] = 'NS'

    running = True
    tick = 0
    last_send = 0
    send_interval = 0.15

    while running:
        t0 = time.time()
        # process commands
        try:
            while True:
                cmd = cmd_q.get_nowait()
                c = cmd.get('cmd')
                if c == 'stop':
                    running = False
                elif c == 'set_roads':
                    roads = set(tuple(r) for r in cmd.get('roads', []))
                elif c == 'add_vehicle':
                    pos = tuple(cmd.get('pos'))
                    dir = tuple(cmd.get('dir'))
                    vehicles[next_vid] = {'pos': pos, 'dir': dir, 'color': 'blue'}
                    next_vid += 1
        except Exception:
            # queue empty or other; ignore
            pass

        # update lights: toggle every 20 ticks
        if tick % 20 == 0:
            for p in list(lights.keys()):
                lights[p] = 'EW' if lights[p] == 'NS' else 'NS'

        # move vehicles: try to step by dir if destination is a road cell
        remove = []
        for vid, v in vehicles.items():
            x, y = v['pos']
            dx, dy = v['dir']
            nx, ny = x + dx, y + dy
            if (nx, ny) in roads:
                # simple traffic light stop: if next is intersection, check light
                if (nx, ny) in lights:
                    mode = lights[(nx, ny)]
                    # if going north/south but light is EW, stop
                    if dx == 0 and mode == 'EW':
                        # wait
                        pass
                    elif dy == 0 and mode == 'NS':
                        pass
                    else:
                        v['pos'] = (nx, ny)
                else:
                    v['pos'] = (nx, ny)
            else:
                # off road -> remove
                remove.append(vid)

        for vid in remove:
            vehicles.pop(vid, None)

        # occasionally send state
        now = time.time()
        if now - last_send > send_interval:
            try:
                state_q.put({'vehicles': vehicles, 'lights': lights})
            except Exception:
                pass
            last_send = now

        tick += 1
        # simple fixed tick rate
        dt = time.time() - t0
        sleep_for = max(0.03, 0.12 - dt)
        time.sleep(sleep_for)
