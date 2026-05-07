from pathlib import Path
import math, shutil, subprocess
import tkinter as tk
try:
    from PIL import Image, ImageTk
except Exception:
    Image = ImageTk = None
from tkinter import ttk
from wss import DIFFICULTIES, PROFILES, Position, make_game

ASSETS = Path(__file__).with_name("assets")
BG, PANEL, TEXT, MUTED, LINE, GOLD = "#0E1412", "#16211D", "#EAF2EA", "#96A69C", "#2E433A", "#E2B860"
FONT = "Avenir"
TERRAIN = {"plains": "grass.png", "forest": "forest.png", "mountain": "mountain.png", "swamp": "swamp.png", "desert": "desert.png"}
ITEM_ICON = {"food": "food.png", "water": "water.png", "gold": "gold.png"}
DIALOG = {"accept": "dialog_accept.png", "counter": "dialog_counter.png", "reject": "dialog_reject.png", "angry": "dialog_angry_quit.png"}
SCENE = {"blank": "trade.png", "accept": "trade_accepted.png", "counter": "trader_angry.png", "reject": "trader_angry.png", "angry": "angry_trader.png"}
SOUND = {
    "welcome": "welcome_splash_music.mp3",
    "level": "level_music.mp3",
    "move": "jump.mp3",
    "trade": "trade_accepted.mp3",
    "win": "level-win.mp3",
    "lose": "you_lose.mp3",
}
ALL_AUDIO = set(SOUND.values())
TRADE_ASSETS = {"trade.png", "trade_accepted.png", "trader_angry.png", "angry_trader.png", "trade_accepted.mp3", "no_trader_available.png"} | set(DIALOG.values())
MAP_SIZES = {"Compact 10 x 6": (10, 6), "Standard 12 x 7": (12, 7), "Wide 16 x 8": (16, 8), "Epic 20 x 10": (20, 10)}
KEY_MOVES = dict(w=(0, -1), s=(0, 1), a=(-1, 0), d=(1, 0), up=(0, -1), down=(0, 1), left=(-1, 0), right=(1, 0))
MAP_FONT, BADGE_FONT = (FONT, 10, "bold"), (FONT, 8, "bold")
ALL_PNG = set(TERRAIN.values()) | set(ITEM_ICON.values()) | set(DIALOG.values()) | set(SCENE.values()) | {
    "angry_trader.png", "cost_badge_bg.png", "end.png", "gauge_empty.png", "gauge_food_fill.png", "gauge_gold_fill.png",
    "gauge_strength_fill.png", "gauge_water_fill.png", "item_marker_ring.png", "legend_panel.png", "player_transparent_cropped.png",
    "route_escape_arrow.png", "route_path_arrow.png", "route_trail_segment.png", "selected_tile_outline.png", "splash.png",
    "terminal_escaped_banner.png", "terminal_stopped_banner.png", "tile_overlay_affordable.png", "tile_overlay_trail.png", "tile_overlay_visible.png",
    "no_trader_available.png", "app_icon.png",
}


def asset_path(name: str) -> Path:
    return ASSETS / name


class ExpeditionConsole(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("WSS Expedition Console")
        width, height = 1180, 760
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(width, height)
        self.resizable(False, False)
        self.configure(bg=BG)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=TEXT, background=GOLD, foreground=BG, arrowcolor=BG,
                        selectbackground=GOLD, selectforeground=BG, padding=4)
        self.game = self.snapshot = self.player_render_position = None
        self.raw_assets, self.asset_images = {}, {}
        if icon := self._raw_image("app_icon.png"):
            self.iconphoto(True, icon)
        self.music_process = self.music_scene = None
        self.status_state, self.status_text = "blank", "Find a trader, then press E to trade."
        missing_png = sorted(name for name in ALL_PNG if not asset_path(name).exists())
        missing_audio = sorted(name for name in ALL_AUDIO if not asset_path(name).exists())
        if missing_png or missing_audio:
            raise FileNotFoundError(f"missing assets: png={missing_png}, audio={missing_audio}")
        for name, default in (("difficulty", "normal"), ("profile", "scout")):
            setattr(self, f"{name}_var", tk.StringVar(value=default))
        self.map_size_var, self.map_size = tk.StringVar(value="Standard 12 x 7"), (12, 7)
        self.app_shell = tk.Frame(self, bg=BG)
        self.app_shell.pack(fill="both", expand=True)
        self.welcome_screen, self.game_screen = tk.Frame(self.app_shell, bg=BG), tk.Frame(self.app_shell, bg=BG)
        self._build_welcome(self.welcome_screen)
        self._build_expedition(self.game_screen)
        self.show_welcome()
        self.bind_all("<KeyPress>", self._handle_keypress)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_welcome(self, parent: tk.Frame) -> None:
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(0, weight=1)
        setup = self._panel(parent)
        setup.grid(row=0, column=0, sticky="ns", padx=(36, 18), pady=36)
        setup.grid_columnconfigure(0, weight=1)
        self._title(setup, "New Expedition", "Pick rules, then move manually with WASD or arrows.")
        fields = (("Profile", self.profile_var, PROFILES, 12), ("Difficulty", self.difficulty_var, DIFFICULTIES, 12),
                  ("Map Size", self.map_size_var, MAP_SIZES, 18))
        for row, (label, variable, choices, width) in enumerate(fields, 1):
            field = tk.Frame(setup, bg=PANEL)
            field.grid(row=row, column=0, sticky="ew", padx=18, pady=8)
            field.grid_columnconfigure(0, weight=1)
            self._label(field, label, 10, MUTED).grid(row=0, column=0, sticky="w")
            ttk.Combobox(field, textvariable=variable, values=sorted(choices), width=width, state="readonly").grid(row=1, column=0, sticky="ew", pady=(3, 0))
        self._button(setup, "Start Expedition", self.start_from_welcome).grid(row=8, column=0, sticky="ew", padx=18, pady=(20, 8))
        if goal := self._image("end.png", 145):
            tk.Label(setup, image=goal, bg=PANEL).grid(row=9, column=0, pady=(18, 4))
        self.welcome_art = tk.Canvas(parent, bg="#101714", highlightthickness=0)
        self.welcome_art.grid(row=0, column=1, sticky="nsew", padx=(0, 36), pady=36)
        self.welcome_art.bind("<Configure>", lambda _event: self._draw_welcome_art())

    def _build_expedition(self, parent: tk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)
        toolbar = self._panel(parent)
        toolbar.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        for column, (text, command) in enumerate((("Setup", self.show_welcome), ("Trade  E", self.interact_with_trader))):
            self._button(toolbar, text, command).grid(row=0, column=column, padx=(14 if column == 0 else 4, 4), pady=10)
        self._label(toolbar, "Controls: WASD/arrows move • E trades • Esc setup", 11, MUTED).grid(row=0, column=2, sticky="w", padx=14)
        body = tk.Frame(parent, bg=BG)
        body.grid(row=1, column=0, sticky="nsew", padx=10, pady=6)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        map_panel = self._panel(body)
        map_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        map_panel.grid_rowconfigure(1, weight=1)
        map_panel.grid_columnconfigure(0, weight=1)
        self._title(map_panel, "Tactical Map", "West edge start. East edge escape. Tile badges show entry cost.")
        self.map_canvas = tk.Canvas(map_panel, bg="#101714", highlightthickness=0, takefocus=1)
        self.map_canvas.grid(row=1, column=0, sticky="nsew", padx=14, pady=(4, 14))
        self.map_canvas.bind("<Configure>", lambda _event: self.draw_map())
        right = self._panel(body)
        right.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        right.grid_propagate(False)
        right.configure(width=320)
        right.grid_columnconfigure(0, weight=1)
        self._title(right, "Telemetry", "Reserves stay under profile maximums.")
        self.gauge_canvas: dict[str, tk.Canvas] = {}
        for index, name in enumerate(("strength", "water", "food", "gold")):
            self._gauge_row(right, name, index + 1)
        status_frame = tk.Frame(right, bg=PANEL)
        status_frame.grid(row=6, column=0, sticky="ew", padx=14, pady=(10, 4))
        self._label(status_frame, "Trade Status", 10, MUTED).pack(anchor="w")
        self.status_canvas = tk.Canvas(status_frame, width=286, height=152, bg=PANEL, highlightthickness=0)
        self.status_canvas.pack(anchor="w", pady=(4, 0))
        self.log_label = self._label(right, "", 9, TEXT, wrap=270)
        self.log_label.grid(row=7, column=0, sticky="ew", padx=14, pady=(4, 8))

    def show_welcome(self) -> None:
        self.game_screen.pack_forget()
        self.welcome_screen.pack(fill="both", expand=True)
        self._play_music("welcome")
        self._draw_welcome_art()

    def start_from_welcome(self) -> None:
        self.map_size = MAP_SIZES.get(self.map_size_var.get(), (12, 7))
        self.welcome_screen.pack_forget()
        self.game_screen.pack(fill="both", expand=True)
        self._play_music("level")
        self.after(80, self.map_canvas.focus_set)
        self.new_game()

    def new_game(self) -> None:
        self.player_render_position = None
        self.status_state, self.status_text = "blank", "Find a trader, then press E to trade."
        self.game = make_game(*self.map_size, self.difficulty_var.get(), self.profile_var.get(), 3560)
        self.snapshot = self.game.start()
        self.after_idle(self.refresh)
        self.after(80, self.refresh)

    def _handle_keypress(self, event: tk.Event) -> str | None:
        if event.widget.winfo_class() in {"Entry", "Spinbox", "Text", "TCombobox"}:
            return None
        key = event.keysym.lower()
        if self.welcome_screen.winfo_ismapped() and key == "return":
            self.start_from_welcome(); return "break"
        if not self.game_screen.winfo_ismapped():
            return None
        if key in KEY_MOVES:
            self.move_from(KEY_MOVES[key])
        elif key == "e":
            self.interact_with_trader()
        elif key == "escape":
            self.show_welcome()
        else:
            return None
        return "break"

    def move_from(self, delta: tuple[int, int]) -> None:
        if self.player_render_position is not None:
            return
        if self.game is None or self.snapshot is None:
            return
        assert self.game is not None and self.snapshot is not None
        before = self.snapshot.position
        result = self.game.manual_move(delta)
        self._after_turn(before, result)

    def interact_with_trader(self) -> None:
        if self.game is None or self.snapshot is None:
            return
        assert self.game is not None
        result = self.game.interact_trader()
        self.snapshot = result.snapshot
        self._set_status(result.messages)
        if any("trade complete" in message for message in result.messages):
            self._spawn_audio("trade")
        self.refresh()

    def _after_turn(self, before: Position, result) -> None:
        self.snapshot = result.snapshot
        self._set_status(result.messages)
        moved = self.snapshot.position != before
        if moved:
            self._spawn_audio("move")
        if any("trade complete" in message for message in result.messages):
            self._spawn_audio("trade")
        if self.snapshot.finished:
            self._stop_music()
            self._spawn_audio("win" if self._escaped(self.snapshot) else "lose")
        self._animate_player(before, self.snapshot.position) if moved else self.refresh()

    def _set_status(self, messages: tuple[str, ...]) -> None:
        text = "\n".join(messages[-4:]) or "Ready."
        joined = "\n".join(messages).lower()
        self.status_state = "accept" if "trade complete" in joined else "angry" if "angry quit" in joined else "reject" if "reject" in joined else "counter" if "counter" in joined else "blank"
        self.status_text = text

    def _animate_player(self, start: Position, end: Position, frame: int = 0) -> None:
        frames, amount = 8, frame / 8
        self.player_render_position = (start.x + (end.x - start.x) * amount, start.y + (end.y - start.y) * amount - math.sin(math.pi * amount) * 0.16)
        self.refresh()
        if frame < frames:
            self.after(18, lambda: self._animate_player(start, end, frame + 1))
        else:
            self.player_render_position = None
            self.refresh()

    def refresh(self) -> None:
        if self.game is None:
            return
        self.snapshot = self.game.snapshot()
        self.draw_map()
        self.update_telemetry()
        self.draw_status()

    def draw_map(self) -> None:
        if self.snapshot is None or not hasattr(self, "map_canvas"):
            return
        canvas = self.map_canvas
        canvas.delete("all")
        w, h = canvas.winfo_width(), canvas.winfo_height()
        if w < 80 or h < 80:
            return
        top, bottom, side = 48, 62, 18
        tile = min((w - side * 2) / self.snapshot.width, (h - top - bottom) / self.snapshot.height)
        x0 = (w - tile * self.snapshot.width) / 2
        y0 = top + (h - top - bottom - tile * self.snapshot.height) / 2
        self._draw_splash(canvas, w, h)
        self._draw_route_header(canvas, x0, y0, tile)
        for row in self.snapshot.tiles:
            for tile_info in row:
                x, y = x0 + tile_info.position.x * tile, y0 + tile_info.position.y * tile
                self._draw_tile(canvas, tile_info, x, y, tile)
        self._draw_player(canvas, x0, y0, tile)
        self._draw_terminal_overlay(canvas, x0, y0, tile)
        self._draw_legend(canvas, w, h)

    def _draw_tile(self, canvas: tk.Canvas, tile_info, x: float, y: float, tile: float) -> None:
        if image := self._image(TERRAIN.get(tile_info.terrain, "grass.png"), tile * 1.05):
            canvas.create_image(x + tile / 2, y + tile / 2, image=image)
        pos = tile_info.position
        trail = set(self.game.trail if self.game else ())
        if pos in trail and (overlay := self._image("tile_overlay_trail.png", tile * 1.05)):
            canvas.create_image(x + tile / 2, y + tile / 2, image=overlay)
        elif overlay := self._image("tile_overlay_visible.png", tile * 1.05):
            canvas.create_image(x + tile / 2, y + tile / 2, image=overlay)
        if pos in self.snapshot.affordable_moves and (overlay := self._image("tile_overlay_affordable.png", tile * 1.05)):
            canvas.create_image(x + tile / 2, y + tile / 2, image=overlay)
        if pos in trail and pos != self.snapshot.position and (seg := self._image("route_trail_segment.png", tile * 0.54)):
            canvas.create_image(x + tile / 2, y + tile * 0.52, image=seg)
        if pos.x == self.snapshot.width - 1 and pos.y == self.snapshot.height // 2 and (end := self._image("end.png", tile * 0.52)):
            canvas.create_image(x + tile / 2, y + tile * 0.42, image=end)
        self._draw_item_markers(canvas, tile_info, x, y, tile)
        if abs(pos.x - self.snapshot.position.x) + abs(pos.y - self.snapshot.position.y) == 1:
            self._draw_entry_cost(canvas, tile_info, x, y, tile)
        if pos == self.snapshot.position and (selected := self._image("selected_tile_outline.png", tile * 1.05)):
            canvas.create_image(x + tile / 2, y + tile / 2, image=selected)

    def _draw_item_markers(self, canvas: tk.Canvas, tile_info, x: float, y: float, tile: float) -> None:
        items = [item for item in tile_info.items if item != "Trader"]
        has_trader = "Trader" in tile_info.items
        count = min(3, len(items))
        marker_size = max(20, min(50, tile * (0.36 if count >= 3 else 0.40)))
        layouts = {
            0: (),
            1: ((0.24, 0.28),),
            2: ((0.22, 0.27), (0.52, 0.27)),
            3: ((0.20, 0.25), (0.52, 0.25), (0.36, 0.52)),
        }
        if has_trader and (trader := self._image("angry_trader.png", tile * 0.44)):
            canvas.create_image(x + tile * 0.82, y + tile * 0.30, image=trader)
        for item, (rx, ry) in zip(items[:3], layouts[count]):
            kind = next((name for name in ITEM_ICON if name in item.lower()), "gold")
            cx, cy = x + tile * rx, y + tile * ry
            if ring := self._image("item_marker_ring.png", marker_size):
                canvas.create_image(cx, cy, image=ring)
            if icon := self._image(ITEM_ICON[kind], marker_size * 0.88):
                canvas.create_image(cx, cy, image=icon)

    def _draw_entry_cost(self, canvas: tk.Canvas, tile_info, x: float, y: float, tile: float) -> None:
        if tile < 48:
            return
        badge = self._image("cost_badge_bg.png", tile * 1.22)
        if badge is None:
            return
        by = y + tile - badge.height() / 2 - max(3, tile * 0.04)
        canvas.create_image(x + tile / 2, by, image=badge)
        bw = badge.width()
        values = (tile_info.cost.strength, tile_info.cost.water, tile_info.cost.food)
        for value, ratio in zip(values, (0.24, 0.56, 0.88)):
            canvas.create_text(x + tile / 2 - bw / 2 + bw * ratio, by, text=str(value), fill=TEXT, font=BADGE_FONT)

    def _draw_player(self, canvas: tk.Canvas, x0: float, y0: float, tile: float) -> None:
        if self.snapshot is None:
            return
        grid_x, grid_y = self.player_render_position or (self.snapshot.position.x, self.snapshot.position.y)
        cx, cy = x0 + grid_x * tile + tile / 2, y0 + grid_y * tile + tile * 0.56
        if player := self._image("player_transparent_cropped.png", tile * 0.62):
            canvas.create_image(cx, cy, image=player)

    def _draw_route_header(self, canvas: tk.Canvas, x0: float, y0: float, tile: float) -> None:
        width = tile * self.snapshot.width
        header_y = y0 - 36
        canvas.create_text(x0, header_y, text="WEST START", fill=MUTED, anchor="w", font=MAP_FONT)
        if arrow := self._image("route_path_arrow.png", min(110, width * 0.22)):
            canvas.create_image(x0 + 155, header_y, image=arrow)
        if arrow := self._image("route_escape_arrow.png", min(110, width * 0.22)):
            canvas.create_image(x0 + width - 155, header_y, image=arrow)
        canvas.create_text(x0 + width, header_y, text="EAST ESCAPE", fill=GOLD, anchor="e", font=MAP_FONT)

    def _draw_terminal_overlay(self, canvas: tk.Canvas, x0: float, y0: float, tile: float) -> None:
        if self.snapshot is None or not self.snapshot.finished:
            return
        width = tile * self.snapshot.width
        asset = "terminal_escaped_banner.png" if self._escaped(self.snapshot) else "terminal_stopped_banner.png"
        if banner := self._image(asset, min(width - 30, 760)):
            canvas.create_image(x0 + width / 2, y0 + tile * self.snapshot.height / 2, image=banner)

    def _draw_legend(self, canvas: tk.Canvas, width: int, height: int) -> None:
        labels = [("Plains", "grass.png"), ("Forest", "forest.png"), ("Mountain", "mountain.png"), ("Swamp", "swamp.png"), ("Desert", "desert.png"),
                  ("Food", "food.png"), ("Water", "water.png"), ("Gold", "gold.png")]
        small = width < 760
        y_positions = (height - 48, height - 20) if small else (height - 34,)
        panel_height = 70 if small else 44
        panel = self._image("legend_panel.png", min(width - 30, 900))
        if panel:
            canvas.create_image(width / 2, height - panel_height / 2, image=panel)
        columns = 4 if small else 8
        step = min(102, max(76, (width - 52) / columns))
        start = width / 2 - step * (columns - 1) / 2 - 18
        for index, (label, asset) in enumerate(labels):
            row, col = divmod(index, columns)
            x, y = start + col * step, y_positions[row]
            icon_size = 40 if asset in ITEM_ICON.values() else 28
            if image := self._image(asset, icon_size):
                canvas.create_image(x, y, image=image)
            canvas.create_text(x + 20, y, text=label, fill=TEXT, anchor="w", font=BADGE_FONT)

    def _draw_splash(self, canvas: tk.Canvas, width: int, height: int, dim: bool = True) -> None:
        canvas.create_rectangle(0, 0, width, height, fill="#101714", outline="")
        if splash := self._image("splash.png", max(width, height)):
            canvas.create_image(width / 2, height / 2, image=splash)
        if dim:
            canvas.create_rectangle(0, 0, width, height, fill="#101714", stipple="gray75", outline="")

    def _draw_welcome_art(self) -> None:
        if not hasattr(self, "welcome_art"):
            return
        canvas = self.welcome_art
        canvas.delete("all")
        w, h = canvas.winfo_width(), canvas.winfo_height()
        if w < 80 or h < 80:
            return
        self._draw_splash(canvas, w, h, False)
        text_w = min(420, int(w * 0.42))
        canvas.create_text(28, 34, text="WILDERNESS SURVIVAL SYSTEM", fill=TEXT, anchor="w", font=(FONT, 20, "bold"))
        canvas.create_text(30, 64, text="Manual survival map using local PNG and audio assets.", fill=TEXT, anchor="w", font=MAP_FONT)
        canvas.create_text(30, 108, text="Start an expedition, cross the map, manage resources, and escape from the east edge.",
                           fill=TEXT, anchor="w", font=(FONT, 12), width=text_w)
        canvas.create_text(w * 0.72, h * 0.72, text="Escape Goal", fill=GOLD, font=(FONT, 16, "bold"))
        canvas.create_text(w * 0.72, h * 0.78, text="Reach the east side with strength, food, and water still above zero.",
                           fill=TEXT, font=(FONT, 11), width=260, justify="center")

    def draw_status(self) -> None:
        if not hasattr(self, "status_canvas"):
            return
        canvas = self.status_canvas
        canvas.delete("all")
        state = self.status_state
        nearby = bool(self.game and self.game._nearby_trader())
        if state == "blank":
            scene = "trade.png" if nearby else "no_trader_available.png"
            text = "Trader nearby. Press E to trade gold for your weakest reserve." if nearby else "No trader nearby. Move next to a trader, then press E to trade."
            if art := self._image(scene, 220 if nearby else 118):
                canvas.create_image(143, 66, image=art)
        else:
            scene, dialog, text = SCENE.get(state, "trade.png"), DIALOG.get(state), self.status_text
            scene_size = 88 if scene == "angry_trader.png" else 104
            if art := self._image(scene, scene_size):
                canvas.create_image(60, 64, image=art)
            if dialog and (bubble := self._image(dialog, 156)):
                canvas.create_image(200, 64, image=bubble)
        self.log_label.configure(text=text)

    def update_telemetry(self) -> None:
        if self.snapshot is None:
            return
        width, height = 280, 38
        for name in ("strength", "water", "food", "gold"):
            value = getattr(self.snapshot.resources, name)
            max_value = max(1, getattr(self.snapshot.maximums, name))
            canvas = self.gauge_canvas[name]
            canvas.delete("all")
            if fill := self._image(f"gauge_{name}_fill.png", width):
                canvas.create_image(width / 2, height / 2, image=fill)
            cover_x = width * min(value / max_value, 1)
            canvas.create_rectangle(cover_x, 0, width, height, fill=PANEL, outline="")
            if empty := self._image("gauge_empty.png", width):
                canvas.create_image(width / 2, height / 2, image=empty)
            text_x = 10
            if name in ITEM_ICON and (icon := self._image(ITEM_ICON[name], 30)):
                canvas.create_image(20, height / 2, image=icon)
                text_x = 42
            canvas.create_text(text_x, height / 2, text=f"{name.title()}: {value}/{max_value}", fill=TEXT, anchor="w", font=MAP_FONT)

    def _escaped(self, snapshot) -> bool:
        return snapshot.position.x == snapshot.width - 1 and all(getattr(snapshot.resources, name) > 0 for name in ("strength", "water", "food"))

    def _image(self, name: str, target: float | None = None) -> tk.PhotoImage | None:
        target_size = 0 if target is None else max(8, int(target))
        key = (name, target_size)
        if key in self.asset_images:
            return self.asset_images[key]
        if Image is not None and ImageTk is not None:
            photo = self._pil_image(name, target_size)
            if photo is not None:
                self.asset_images[key] = photo
                return photo
        raw = self._raw_image(name)
        if raw is None:
            return None
        image = raw
        if target_size:
            scale = max(1, math.ceil(max(raw.width(), raw.height()) / target_size))
            try:
                image = raw.subsample(scale, scale)
            except tk.TclError:
                return None
        self.asset_images[key] = image
        return image

    def _pil_image(self, name: str, target_size: int) -> tk.PhotoImage | None:
        path = asset_path(name)
        if not path.exists():
            return None
        try:
            raw = self.raw_assets.get(name)
            if raw is None or not hasattr(raw, "size"):
                raw = Image.open(path).convert("RGBA")
                self.raw_assets[name] = raw
            image = raw
            if target_size:
                w, h = image.size
                largest = max(w, h)
                if largest > target_size:
                    scale = target_size / largest
                    image = image.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(image)
        except Exception:
            return None

    def _raw_image(self, name: str) -> tk.PhotoImage | None:
        if not name:
            return None
        if name in self.raw_assets and hasattr(self.raw_assets[name], "width"):
            return self.raw_assets[name]
        path = asset_path(name)
        if not path.exists():
            return None
        try:
            image = tk.PhotoImage(file=str(path))
        except tk.TclError:
            return None
        self.raw_assets[name] = image
        return image

    def _spawn_audio(self, name: str) -> subprocess.Popen | None:
        path = asset_path(SOUND.get(name, ""))
        if not path.exists():
            return None
        player = shutil.which("afplay")
        cmd = [player, str(path)] if player else None
        if cmd is None and (player := shutil.which("ffplay")):
            cmd = [player, "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)]
        if cmd is None and (player := shutil.which("mpg123")):
            cmd = [player, "-q", str(path)]
        if cmd is None:
            return None
        return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _play_music(self, scene: str) -> None:
        if self.music_scene == scene and self.music_process is not None and self.music_process.poll() is None:
            return
        self._stop_music()
        process = self._spawn_audio(scene)
        if process is None:
            return
        self.music_scene, self.music_process = scene, process
        self.after(1000, lambda: self._music_loop(scene))

    def _music_loop(self, scene: str) -> None:
        if self.music_scene != scene:
            return
        if self.music_process is None or self.music_process.poll() is not None:
            self.music_process = self._spawn_audio(scene)
        self.after(1000, lambda: self._music_loop(scene))

    def _stop_music(self) -> None:
        if self.music_process is not None and self.music_process.poll() is None:
            self.music_process.terminate()
        self.music_process = self.music_scene = None

    def _on_close(self) -> None:
        self._stop_music()
        self.destroy()

    def _button(self, parent: tk.Widget, text: str, command: object) -> tk.Button:
        return tk.Button(parent, text=text, command=command, bg=GOLD, fg="#17110A", activebackground="#F0CF7C", activeforeground="#17110A", relief="flat", padx=12, pady=8, font=(FONT, 11, "bold"))

    def _panel(self, parent: tk.Widget) -> tk.Frame:
        return tk.Frame(parent, bg=PANEL, highlightbackground=LINE, highlightthickness=1)

    def _title(self, parent: tk.Widget, title: str, subtitle: str) -> None:
        frame = tk.Frame(parent, bg=PANEL)
        frame.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 8))
        self._label(frame, title, 18, TEXT, bold=True).pack(anchor="w")
        self._label(frame, subtitle, 10, MUTED).pack(anchor="w")

    def _label(self, parent: tk.Widget, text: str, size: int, color: str, bold: bool = False, wrap: int | None = None) -> tk.Label:
        return tk.Label(parent, text=text, bg=PANEL, fg=color, font=(FONT, size, "bold" if bold else "normal"), wraplength=wrap or 0, justify="left")

    def _gauge_row(self, parent: tk.Widget, name: str, row: int) -> None:
        frame = tk.Frame(parent, bg=PANEL)
        frame.grid(row=row, column=0, sticky="ew", padx=14, pady=4)
        self._label(frame, name.title(), 10, MUTED).pack(anchor="w")
        canvas = tk.Canvas(frame, width=280, height=38, bg=PANEL, highlightthickness=0)
        canvas.pack(anchor="w", pady=(2, 0))
        self.gauge_canvas[name] = canvas


if __name__ == "__main__":
    ExpeditionConsole().mainloop()
