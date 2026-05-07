# WSS Expedition Console

Manual Tkinter survival game for CS3560 using local PNG and MP3 assets.

## Setup

```bash
python3 -m pip install -r requirements.txt
```

## Run

```bash
python3 gui_app.py
```

## Controls

- `WASD` or arrow keys: move
- `E`: trade when near a trader
- `Esc`: return to setup

## Audio note

All MP3 files in `assets/` are used. On macOS, sound uses `afplay`. On other systems, install `ffplay` or `mpg123`. The game still runs if no audio player is available.

## Test

```bash
python3 -m unittest -v test_wss.py
```
