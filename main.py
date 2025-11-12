import tkinter as tk
from tkinter import ttk, simpledialog
import math

DEFAULT_GRID = 32


class GraphPaper(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Virtual Graph Paper - simplified')
        self.grid_size = DEFAULT_GRID
        self.width = 960
        self.height = 600

        self.tool = 'pen'  # pen, line, erase, move
        self.shapes = []  # list of {'type':'line'/'poly', 'points':[(x,y)...], 'id': canvas_id}
        self.current = None
        self.selection = None

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

        self.create_ui()
        self.draw_grid()
        self.apply_theme()

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
        # pan with middle mouse or space+left
        self.canvas.bind('<ButtonPress-2>', self.on_pan_start)
        self.canvas.bind('<B2-Motion>', self.on_pan_move)
        self.canvas.bind('<ButtonRelease-2>', self.on_pan_end)
        # zoom with mouse wheel
        self.canvas.bind('<MouseWheel>', self.on_zoom)
        self.canvas.bind('<Button-4>', self.on_zoom)  # Linux scroll up
        self.canvas.bind('<Button-5>', self.on_zoom)  # Linux scroll down

        # status
        self.status = ttk.Label(self, text='Tool: pen | Grid: %d' % self.grid_size)
        self.status.pack(side='bottom', fill='x')

    def set_tool(self, t):
        self.tool = t
        self.status.config(text='Tool: %s | Grid: %d' % (self.tool, self.grid_size))
    
    def toggle_edit_roads(self):
        """Toggle the Edit Roads submenu."""
        self.edit_roads_expanded = not self.edit_roads_expanded
        
        if self.edit_roads_expanded:
            # Collapse View if it's open
            if self.view_expanded:
                self.view_expanded = False
                self.view_frame.pack_forget()
            # Show Edit Roads buttons
            self.edit_roads_frame.pack(side='left', padx=4, pady=4, after=self.edit_roads_btn)
        else:
            # Hide Edit Roads buttons
            self.edit_roads_frame.pack_forget()
        
        self.apply_theme()
    
    def toggle_view(self):
        """Toggle the View submenu."""
        self.view_expanded = not self.view_expanded
        
        if self.view_expanded:
            # Collapse Edit Roads if it's open
            if self.edit_roads_expanded:
                self.edit_roads_expanded = False
                self.edit_roads_frame.pack_forget()
            # Show View buttons
            self.view_frame.pack(side='left', padx=4, pady=4, after=self.view_btn)
        else:
            # Hide View buttons
            self.view_frame.pack_forget()
        
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
        
        # update button symbol
        if self.is_night_mode:
            self.theme_btn.config(text='☀️')
        else:
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
        for s in list(self.shapes):
            if 'id' in s and s['id']:
                try:
                    self.canvas.delete(s['id'])
                except Exception:
                    pass
        self.shapes.clear()

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

        if self.tool == 'pen':
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
    app = GraphPaper()
    app.mainloop()

