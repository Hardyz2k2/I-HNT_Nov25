# Transparent Click-Through Overlay Update

## Date: 2025-12-03

---

## Summary

Updated the overlay system to be **fully transparent** with **click-through** capability, allowing you to see the game underneath and click through the overlay as if it wasn't there.

---

## What Changed

### **1. Added Windows API Support**
- Imported `win32gui`, `win32con`, `win32api` for Windows window manipulation
- Enables low-level window style modification

### **2. Transparent Background**
**Before:** Showed game screenshot with overlays drawn on top
**After:** Pure black background (RGB 0,0,0) that becomes transparent

```python
# Black background = transparent when using color key
display = np.zeros((Config.SCREEN_HEIGHT, Config.SCREEN_WIDTH, 3), dtype=np.uint8)
```

### **3. Click-Through Functionality**
New `make_click_through()` method applies Windows API flags:

```python
# Key Windows API flags:
WS_EX_LAYERED      # Enables transparency
WS_EX_TRANSPARENT  # Makes window click-through
WS_EX_TOPMOST      # Keeps window on top
LWA_COLORKEY       # Black pixels = transparent
```

### **4. Text Readability Improvements**
- **Dark gray backgrounds** (RGB 50,50,50) behind all text
- **White outlines** on text for maximum contrast
- **Colored text** on top for status indication

---

## How It Works

### **Transparency Magic:**
1. **Black pixels (0,0,0)** → Fully transparent (invisible)
2. **Any colored pixels** → Fully visible
3. **Color key transparency** → No blending, pure transparency

### **Click-Through:**
- `WS_EX_TRANSPARENT` flag makes ALL mouse clicks pass through
- You can click the game normally as if overlay doesn't exist
- Overlay stays on top but doesn't interfere

---

## Visual Elements

### **What You'll See:**

1. **Screen Center Crosshair** (Cyan)
   - Horizontal and vertical lines
   - Circle showing target range

2. **Detection Boxes** (Green → Red gradient)
   - Green = Close to center
   - Red = Far from center
   - Box around each detected name
   - Center dot on each detection
   - Line connecting to screen center

3. **Distance Labels** (Per detection)
   - Format: `#1 D:125` (detection #1, 125px from center)
   - Dark gray background for readability
   - Colored text matching detection box

4. **Statistics Panel** (Top-left)
   - Dark gray backgrounds behind each stat
   - White outline + colored text
   - Green text = normal
   - Orange text = paused

5. **PAUSED Indicator** (When paused)
   - Large centered text
   - White outline + orange text
   - No dimmed background (fully transparent)

---

## Benefits

### ✅ **See-Through:**
- Complete view of the game underneath
- No visual obstruction
- Black areas are invisible

### ✅ **Click-Through:**
- Click anywhere on screen normally
- Overlay doesn't block mouse input
- Play game naturally while bot runs

### ✅ **Always On Top:**
- Overlay stays visible even when game is focused
- Fullscreen borderless mode
- Perfect alignment with game window

### ✅ **Readable Text:**
- Dark backgrounds behind all text
- White outlines for contrast
- Easy to read even over bright game areas

---

## Technical Implementation

### **Window Setup:**
```python
# Fullscreen borderless window
cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

# Apply transparency and click-through
make_click_through()
```

### **Transparency Setup:**
```python
# Black = transparent
win32gui.SetLayeredWindowAttributes(
    hwnd,
    0,                      # Color key: Black (RGB 0,0,0)
    0,                      # Alpha: Not used with color key
    win32con.LWA_COLORKEY  # Mode: Color key transparency
)
```

### **Click-Through Setup:**
```python
# Window style with transparency and click-through
new_ex_style = (
    win32con.WS_EX_LAYERED |      # Enable transparency
    win32con.WS_EX_TRANSPARENT |  # Enable click-through
    win32con.WS_EX_TOPMOST        # Always on top
)
```

---

## Color Scheme

### **Detection Colors:**
- **Cyan (0, 255, 255)** - Crosshair
- **Green → Red gradient** - Detection boxes (by distance)
- **Red (0, 0, 255)** - Detection center dots
- **Gray (100, 100, 100)** - Lines to center

### **Text Colors:**
- **Green (0, 255, 0)** - Normal stats
- **Orange (0, 165, 255)** - Paused status
- **White (255, 255, 255)** - Text outlines
- **Dark Gray (50, 50, 50)** - Text backgrounds

### **Transparent:**
- **Black (0, 0, 0)** - Main background (invisible)

---

## Code Changes Summary

### **Modified Files:**
- `mob_hunter.py:21-23` - Added win32 imports
- `mob_hunter.py:602-817` - Complete OverlayWindow class rewrite

### **New Methods:**
- `make_click_through()` - Apply Windows API transparency
- Enhanced `_run()` - Black background rendering

### **Removed:**
- Screenshot copying to display
- Semi-transparent overlays
- Background dimming when paused

---

## Usage

### **No Configuration Needed:**
Overlay is automatically transparent and click-through when enabled.

### **To Disable Overlay:**
```python
class Config:
    SHOW_OVERLAY = False
```

### **To Close Overlay Manually:**
Press 'Q' key (though it won't respond to clicks, keyboard works)

---

## Troubleshooting

### **If overlay isn't transparent:**
- Check Windows API imports installed: `pip install pywin32`
- Verify overlay window is created
- Check console for "✅ Overlay is now CLICK-THROUGH" message

### **If clicks aren't passing through:**
- Restart the bot
- Verify `WS_EX_TRANSPARENT` flag is applied
- Check for error messages in console

### **If text is hard to read:**
- Dark gray backgrounds already added for readability
- White outlines on all text
- Adjust text colors in code if needed

---

## Performance

### **Impact:**
- **Minimal** - Only drawing colored elements, no screenshot processing
- Black background is fastest to render
- Fullscreen mode is hardware accelerated

### **Frame Rate:**
- Still 10 FPS (configurable via `OVERLAY_UPDATE_FPS`)
- Independent of game frame rate

---

## Compatibility

### **Requirements:**
- ✅ Windows OS (uses Win32 API)
- ✅ Python with `pywin32` package
- ✅ OpenCV (cv2)

### **Tested On:**
- Windows 10/11
- Python 3.12
- 1920x1080 resolution

---

## Example Output

### **Console Messages:**
```
🖥️  Click-through overlay starting...
✅ Overlay is now CLICK-THROUGH and transparent
```

### **Visual Display:**
```
[Transparent overlay with:]
- Cyan crosshair at screen center
- Green boxes around nearby mobs
- Red boxes around distant mobs
- Stats panel in top-left:
  Status: ▶️ RUNNING
  Cycle: 42
  Detected: 5
  Valid: 3
  ...
```

---

## Conclusion

The overlay is now:
- ✅ **Fully transparent** (black = invisible)
- ✅ **Click-through** (doesn't block mouse)
- ✅ **Always on top** (stays visible)
- ✅ **Readable text** (dark backgrounds + outlines)
- ✅ **No game obstruction** (see everything underneath)

Perfect for monitoring bot activity without interfering with gameplay! 🎯
