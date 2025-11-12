
import multiprocessing
import queue
import tkinter as tk
from tkinter import ttk
import time

CELL = 40
GRID_W = 15
GRID_H = 12
DOT_RADIUS = 4


def make_default_roads():
	# Start with an empty set of active nodes; user will draw the roads
	return set()


class TrafficApp:
	def __init__(self, root):
		self.root = root
		root.title('Traffic Sim (multiprocess Tkinter demo)')

		self.command_queue = None
		self.state_queue = None
		self.sim_proc = None

		self.roads = make_default_roads()

		self.vehicles = {}
		self.lights = {}

		# poll interval ms
		self.poll_interval = 100

		self.create_ui()

	def create_ui(self):
		frm = ttk.Frame(self.root)
		frm.pack(fill='both', expand=True)

		left = ttk.Frame(frm)
		left.pack(side='left', fill='y')

		btn_start = ttk.Button(left, text='Start Simulation', command=self.start_sim)
		btn_start.pack(padx=8, pady=6)
		btn_stop = ttk.Button(left, text='Stop Simulation', command=self.stop_sim)
		btn_stop.pack(padx=8, pady=6)

		# drawing mode: diagonal-only checkbox
		self.diagonal_only_var = tk.BooleanVar(value=False)
		chk = ttk.Checkbutton(left, text='Diagonal-only mode', variable=self.diagonal_only_var)
		chk.pack(padx=8, pady=6)

		info = ttk.Label(left, text='Click canvas to toggle road cell')
		info.pack(padx=8, pady=6)

		self.canvas = tk.Canvas(frm, width=GRID_W * CELL, height=GRID_H * CELL, bg='white')
		self.canvas.pack(side='left')
		# enable drag-to-draw: press -> motion -> release
		self.canvas.bind('<ButtonPress-1>', self.on_mouse_down)
		self.canvas.bind('<B1-Motion>', self.on_mouse_move)
		self.canvas.bind('<ButtonRelease-1>', self.on_mouse_up)

		self.draw_grid()

		# ensure clean shutdown
		self.root.protocol('WM_DELETE_WINDOW', self.on_close)

	def draw_grid(self):
		# draw dot grid and connecting lines for active nodes
		self.canvas.delete('grid')
		# first draw connections
		for x in range(GRID_W):
			for y in range(GRID_H):
				if (x, y) not in self.roads:
					continue
				# check right neighbor
				# skip straight if currently performing a diagonal drag on these nodes
				skipping = getattr(self, '_drag_diagonal', False) and ((x, y) in getattr(self, '_drag_nodes', set()) or (x+1, y) in getattr(self, '_drag_nodes', set()))
				if (x + 1, y) in self.roads and not self.diagonal_only_var.get() and not skipping:
					x1 = x * CELL + CELL // 2
					y1 = y * CELL + CELL // 2
					x2 = (x + 1) * CELL + CELL // 2
					y2 = y1
					# straight horizontal: darker/thicker
					self.canvas.create_line(x1, y1, x2, y2, fill='#222', width=4, tags='grid')
				# check down neighbor
				# skip straight vertical if diagonal drag touches these nodes
				skipping_v = getattr(self, '_drag_diagonal', False) and ((x, y) in getattr(self, '_drag_nodes', set()) or (x, y+1) in getattr(self, '_drag_nodes', set()))
				if (x, y + 1) in self.roads and not self.diagonal_only_var.get() and not skipping_v:
					x1 = x * CELL + CELL // 2
					y1 = y * CELL + CELL // 2
					x2 = x1
					y2 = (y + 1) * CELL + CELL // 2
					# straight vertical: darker/thicker
					self.canvas.create_line(x1, y1, x2, y2, fill='#222', width=4, tags='grid')
				# check down-right diagonal
				if (x + 1, y + 1) in self.roads:
					x1 = x * CELL + CELL // 2
					y1 = y * CELL + CELL // 2
					x2 = (x + 1) * CELL + CELL // 2
					y2 = (y + 1) * CELL + CELL // 2
					# diagonal: lighter/thinner to match sketch
					self.canvas.create_line(x1, y1, x2, y2, fill='#666', width=2, tags='grid')
				# check up-right diagonal
				if (x + 1, y - 1) in self.roads:
					x1 = x * CELL + CELL // 2
					y1 = y * CELL + CELL // 2
					x2 = (x + 1) * CELL + CELL // 2
					y2 = (y - 1) * CELL + CELL // 2
					# diagonal: lighter/thinner to match sketch
					self.canvas.create_line(x1, y1, x2, y2, fill='#666', width=2, tags='grid')

		# then draw dots
		for x in range(GRID_W):
			for y in range(GRID_H):
				cx = x * CELL + CELL // 2
				cy = y * CELL + CELL // 2
				# active dots darker, inactive lighter
				fill = '#000' if (x, y) in self.roads else '#ddd'
				r = DOT_RADIUS if (x, y) in self.roads else max(2, DOT_RADIUS - 1)
				self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=fill, outline='', tags='grid')

	def draw_state(self, state):
		# state: {'vehicles': {id: {pos:(x,y),color:str}}, 'lights': {pos: 'NS'|'EW'}}
		self.canvas.delete('vehicle')
		self.canvas.delete('light')
		vehicles = state.get('vehicles', {})
		lights = state.get('lights', {})
		for vid, v in vehicles.items():
			x, y = v['pos']
			cx = x * CELL + CELL // 2
			cy = y * CELL + CELL // 2
			r = CELL * 0.28
			self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=v.get('color', 'blue'), tags='vehicle')
		for (x, y), mode in lights.items():
			x1, y1 = x * CELL, y * CELL
			color = 'green' if mode == 'NS' else 'red'
			# show as small rectangle in corner
			self.canvas.create_rectangle(x1 + 4, y1 + 4, x1 + 14, y1 + 14, fill=color, tags='light')

		# redraw grid overlay so vehicles appear above connections but below dots
		self.draw_grid()

	def on_mouse_down(self, ev):
		x = ev.x // CELL
		y = ev.y // CELL
		x = max(0, min(GRID_W - 1, x))
		y = max(0, min(GRID_H - 1, y))
		# determine drag target state: if initial was active, we'll deactivate while dragging; otherwise activate
		initial_active = (x, y) in self.roads
		self._dragging = True
		self._drag_target_state = not initial_active
		self._drag_touched = set()
		self._drag_nodes = set()
		self._drag_diagonal = False
		# apply to starting cell
		if self._drag_target_state:
			self.roads.add((x, y))
		else:
			self.roads.discard((x, y))
		self._drag_touched.add((x, y))
		self.draw_grid()

	def on_mouse_move(self, ev):
		if not getattr(self, '_dragging', False):
			return
		x = ev.x // CELL
		y = ev.y // CELL
		x = max(0, min(GRID_W - 1, x))
		y = max(0, min(GRID_H - 1, y))
		if (x, y) in getattr(self, '_drag_touched', set()):
			return
		# detect if movement from any touched cell to this new cell is diagonal
		if getattr(self, '_drag_touched', None):
			for (px, py) in self._drag_touched:
				if abs(px - x) == 1 and abs(py - y) == 1:
					self._drag_diagonal = True
					break
		# apply drag target state to new cell
		if self._drag_target_state:
			self.roads.add((x, y))
		else:
			self.roads.discard((x, y))
		self._drag_touched.add((x, y))
		self._drag_nodes.add((x, y))
		self.draw_grid()

	def on_mouse_up(self, ev):
		if not getattr(self, '_dragging', False):
			return
		self._dragging = False
		# clear touched set but keep drag node set for a moment (draw_grid will ignore orthogonal for them)
		self._drag_touched = set()
		# after finishing drag, reset diagonal suppression
		self._drag_diagonal = False
		self._drag_nodes = set()
		# send final roads to sim if running
		if self.command_queue:
			try:
				self.command_queue.put({'cmd': 'set_roads', 'roads': list(self.roads)})
			except Exception:
				pass

	def start_sim(self):
		if self.sim_proc and self.sim_proc.is_alive():
			return
		self.command_queue = multiprocessing.Queue()
		self.state_queue = multiprocessing.Queue()
		import sim

		# pass roads as list of tuples
		initial = {'roads': list(self.roads)}
