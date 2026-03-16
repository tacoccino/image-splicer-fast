# Image Splicer

A desktop utility for cropping multiple named regions out of an image and saving each one as a separate file. Drag and drop images, draw selections, name them, and export — no confirmation dialogs in the way.

## Requirements

- Python 3.10+
- [PyQt6](https://pypi.org/project/PyQt6/)
- [Pillow](https://python-pillow.org/)

Both are auto-installed on first run if missing.

## Running from source

```bash
cd image_splicer
python main.py
```

## Project structure

```
image_splicer/
├── main.py          # Entry point
├── window.py        # MainWindow — top-level UI shell
├── canvas.py        # Image canvas and selection drawing
├── panels.py        # Side panel, selection rows, toast overlay
├── dialogs.py       # Settings dialog
├── models.py        # Sel data class (no Qt dependency)
├── config.py        # Load/save ~/.image_splicer_config.json
├── theme.py         # Stylesheet loading and theme application
├── style.qss        # All visual styling
├── icon.png         # App icon (optional, .icns/.ico also supported)
├── icons/
│   ├── dark/        # Toolbar icons for dark theme
│   └── light/       # Toolbar icons for light theme
├── build_mac.sh     # macOS build script
├── build_windows.bat# Windows build script
└── .gitignore
```

## Usage

### Opening an image

- Click **Open Image** or press `Cmd+O` / `Ctrl+O`
- Drag and drop an image file onto the window

### Drawing selections

Click and drag anywhere on the canvas to draw a rectangle. Each selection appears in the side panel where you can give it a name. Selections are stored in image-space coordinates — they stay locked to the same pixel region regardless of zoom level or window size.

### Naming selections

Each row in the side panel has an editable name field. Names are used in saved filenames: `prefix_name.ext`. If a selection has no name, its index is used instead (`prefix_01.ext`).

### Adjusting selections

- **Move** — click inside a selection and drag
- **Resize** — drag any edge or corner handle
- **Delete one** — select it and press `Delete` / `Backspace`
- **Undo last added** — `Cmd+Z` / `Ctrl+Z`
- **Clear all** — **✕ Clear All** in the toolbar

### Navigating the canvas

- **Zoom in/out** — scroll wheel, or `Cmd+=` / `Cmd+−`
- **Fit to window** — **⊡** button or `Cmd+0` / `Ctrl+0`
- **Pan** — hold `Shift` and drag

### Selection overlay

Toggle a semi-transparent fill over all selections with **Cmd+T** / **Ctrl+T** or the overlay button in the toolbar. Useful when working on light images where the selection outline is hard to see. The fill colour and opacity are configurable in Settings.

### Saving crops

1. Open **Settings** (`Cmd+,` / `Ctrl+,`) and set a **Save Location**
2. Set the **filename prefix** in the side panel
3. Click **Save Crops** or press `Cmd+S` / `Ctrl+S`

Files are saved as `prefix_name.ext` (or `prefix_01.ext` if unnamed). Existing files are never overwritten — a counter is appended instead. A brief toast confirms how many crops were saved.

### Keep Selections

The **Keep selections** checkbox at the bottom of the side panel controls what happens when a new image is loaded. When checked, any selections that fit within the new image's bounds are carried over — handy when cropping the same regions across a batch of similar images.

## Keyboard Shortcuts

> On macOS, `Ctrl` below means `Cmd` (⌘) unless noted otherwise.

| Shortcut | Action |
|---|---|
| `Ctrl+O` | Open image |
| `Ctrl+S` | Save all crops |
| `Ctrl+Z` | Delete last selection |
| `Ctrl+=` | Zoom in |
| `Ctrl+−` | Zoom out |
| `Ctrl+0` | Fit image to window |
| `Ctrl+T` | Toggle selection overlay |
| `Ctrl+,` | Open Settings |
| `Delete` / `Backspace` | Delete active selection |
| `Escape` | Cancel current draw |
| Scroll wheel | Zoom in / out |
| `Shift+drag` | Pan the canvas |

## Settings

Accessible via the **⚙ Settings** button or `Ctrl+,`. All settings are saved to `~/.image_splicer_config.json`.

| Setting | Description |
|---|---|
| Save Location | Folder where crops are written |
| Output Format | PNG, JPEG, WEBP, BMP, or TIFF |
| JPEG Quality | Compression level (1–100), shown only when JPEG is selected |
| Theme | Dark or Light |
| Font Scale | Scale all UI text (0.8× – 1.6×) — useful on HiDPI displays |
| Accent Colour | Colour used for selections, highlights, and active states |
| Selection Overlay | Fill colour and opacity (0–100%) for overlay mode |

## Icons

Drop PNG files into `icons/dark/` and `icons/light/` to provide toolbar icons. The app falls back to text labels for any missing icon. Expected filenames:

| Filename | Button |
|---|---|
| `open.png` | Open Image |
| `save.png` | Save Crops |
| `folder.png` | Open Folder |
| `delete.png` | Delete Selection |
| `clear.png` | Clear All |
| `settings.png` | Settings |
| `overlay.png` | Overlay (off state) |
| `overlay_on.png` | Overlay (on state) |
| `fit.png` | Fit to Window |
| `zoom_in.png` | Zoom In |
| `zoom_out.png` | Zoom Out |
| `panel_open.png` | Toggle Panel (panel visible) |
| `panel_closed.png` | Toggle Panel (panel hidden) |

Recommended size: 64×64px source, displayed at 20×20px.

## Building

Install PyInstaller first:

```bash
pip install pyinstaller
```

### macOS

```bash
chmod +x build_mac.sh
./build_mac.sh
```

Output: `dist/mac/Image Splicer.app`

For the best Dock icon, provide `icon.icns` alongside `main.py`. You can generate one from a PNG using:

```bash
# Create iconset from a 1024x1024 PNG
mkdir icon.iconset
sips -z 16 16     icon.png --out icon.iconset/icon_16x16.png
sips -z 32 32     icon.png --out icon.iconset/icon_16x16@2x.png
sips -z 32 32     icon.png --out icon.iconset/icon_32x32.png
sips -z 64 64     icon.png --out icon.iconset/icon_32x32@2x.png
sips -z 128 128   icon.png --out icon.iconset/icon_128x128.png
sips -z 256 256   icon.png --out icon.iconset/icon_128x128@2x.png
sips -z 256 256   icon.png --out icon.iconset/icon_256x256.png
sips -z 512 512   icon.png --out icon.iconset/icon_256x256@2x.png
sips -z 512 512   icon.png --out icon.iconset/icon_512x512.png
cp icon.png           icon.iconset/icon_512x512@2x.png
iconutil -c icns icon.iconset
```

### Windows

```bat
build_windows.bat
```

Output: `dist\windows\Image Splicer\Image Splicer.exe`

Provide `icon.ico` for the best taskbar and title bar icon. A `.ico` file should contain multiple sizes (16, 32, 48, 256px) — GIMP or online converters can create these from a PNG.

To distribute, zip the entire `Image Splicer\` output folder — the `.exe` requires the files alongside it.

## Theming

All colours in `style.qss` use a small set of named token hex values defined in `theme.py`. To change a colour, update both the `DARK_TOKENS` dict in `theme.py` and the corresponding entry in `_light_tokens()`. The QSS itself only needs to use those hex values — `apply_theme()` handles substitution automatically.

To add a completely new themeable colour:
1. Add it to `DARK_TOKENS` in `theme.py`
2. Add a light-mode equivalent to `_light_tokens()`
3. Use the dark hex value in `style.qss`
