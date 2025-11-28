"""
Quick test script to verify all dependencies are installed correctly
"""

print("Testing imports and basic functionality...")
print("=" * 50)

# Test imports
try:
    print("✓ Testing pynput...", end=" ")
    from pynput import keyboard
    print("OK")
except ImportError as e:
    print(f"FAILED: {e}")

try:
    print("✓ Testing mss...", end=" ")
    import mss
    print("OK")
except ImportError as e:
    print(f"FAILED: {e}")

try:
    print("✓ Testing cv2 (OpenCV)...", end=" ")
    import cv2
    print(f"OK (version: {cv2.__version__})")
except ImportError as e:
    print(f"FAILED: {e}")

try:
    print("✓ Testing numpy...", end=" ")
    import numpy as np
    print(f"OK (version: {np.__version__})")
except ImportError as e:
    print(f"FAILED: {e}")

try:
    print("✓ Testing pyautogui...", end=" ")
    import pyautogui
    print("OK")
except ImportError as e:
    print(f"FAILED: {e}")

try:
    print("✓ Testing easyocr...", end=" ")
    import easyocr
    print("OK (this may take a moment on first run...)")
except ImportError as e:
    print(f"FAILED: {e}")

print("=" * 50)

# Test basic functionality
try:
    print("\nTesting screen capture...", end=" ")
    import mss
    sct = mss.mss()
    monitor = {"top": 0, "left": 0, "width": 1920, "height": 1080}
    img = sct.grab(monitor)
    print(f"OK (captured {img.width}x{img.height})")
except Exception as e:
    print(f"FAILED: {e}")

try:
    print("Testing OpenCV operations...", end=" ")
    import cv2
    import numpy as np
    test_img = np.zeros((100, 100, 3), dtype=np.uint8)
    gray = cv2.cvtColor(test_img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    print("OK")
except Exception as e:
    print(f"FAILED: {e}")

try:
    print("Testing keyboard listener setup...", end=" ")
    from pynput import keyboard
    def dummy_callback(key):
        pass
    listener = keyboard.Listener(on_press=dummy_callback)
    listener.daemon = True
    listener.start()
    listener.stop()
    print("OK")
except Exception as e:
    print(f"FAILED: {e}")

print("\n" + "=" * 50)
print("All basic tests completed!")
print("=" * 50)
print("\nTo run the full application:")
print("  python mob_hunter.py")


