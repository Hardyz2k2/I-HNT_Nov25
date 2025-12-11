"""
MOB HUNTER v3.0 - FINAL OPTIMIZED VERSION
Center-out targeting + Binary health detection + Pet filtering via classification

Pet Detection Logic:
- Has classification (General/Champion/Giant/Unique) = MOB
- No classification = PET (100% filtered out)
"""

import cv2
import numpy as np
import time
import logging
import os
from datetime import datetime
from mss import mss
import pyautogui
import threading
import traceback
import ctypes
import win32gui
import win32con
import win32api
from pynput import keyboard

# Disable PyAutoGUI fail-safe
pyautogui.FAILSAFE = False

# Global keyboard state flags (thread-safe)
_capslock_toggled = False
_overlay_toggled = False
_keyboard_lock = threading.Lock()

def _on_key_press(key):
    """Global keyboard listener callback for key presses"""
    global _capslock_toggled, _overlay_toggled

    try:
        # Check for CapsLock
        if key == keyboard.Key.caps_lock:
            with _keyboard_lock:
                _capslock_toggled = True
        # Check for 'O' key
        elif hasattr(key, 'char') and key.char and key.char.lower() == 'o':
            with _keyboard_lock:
                _overlay_toggled = True
    except AttributeError:
        pass

def check_capslock_toggle():
    """Check if CapsLock was pressed and reset flag"""
    global _capslock_toggled
    with _keyboard_lock:
        if _capslock_toggled:
            _capslock_toggled = False
            return True
        return False

def check_overlay_toggle():
    """Check if 'O' key was pressed and reset flag"""
    global _overlay_toggled
    with _keyboard_lock:
        if _overlay_toggled:
            _overlay_toggled = False
            return True
        return False

def start_keyboard_listener():
    """Start global keyboard listener in background thread"""
    listener = keyboard.Listener(on_press=_on_key_press)
    listener.daemon = True
    listener.start()
    return listener

# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    # Screen settings
    SCREEN_WIDTH = 1920
    SCREEN_HEIGHT = 1080
    SCREEN_REGION = {'top': 0, 'left': 0, 'width': SCREEN_WIDTH, 'height': SCREEN_HEIGHT}
    NAMEPLATE_REGION = (660, 10, 600, 100)  # (x, y, w, h) - top-middle
    
    # Detection boundaries (ignore UI only)
    IGNORE_TOP = 120
    IGNORE_BOTTOM = 200
    IGNORE_LEFT = 60
    IGNORE_RIGHT = 60
    
    # Name detection parameters
    MIN_NAME_WIDTH = 25
    MAX_NAME_WIDTH = 300
    MIN_NAME_HEIGHT = 8
    MAX_NAME_HEIGHT = 35
    MIN_ASPECT_RATIO = 1.5
    MAX_ASPECT_RATIO = 20
    
    # Combat settings
    RED_PIXEL_THRESHOLD = 50   # Pixels needed to consider mob "alive"
    HEALTH_CHANGE_THRESHOLD = 50  # Minimum health decrease to confirm hitting mob (anti-stuck)
    MAX_TARGETS_PER_CYCLE = 3  # Max verifications per cycle
    CYCLE_DELAY = 0.4          # Seconds between cycles
    NAMEPLATE_TIMEOUT = 1.0    # Nameplate wait time
    CLICK_DELAY = 0.25         # Delay after clicking
    HEALTH_CHECK_INTERVAL = 1.0  # Check health every 1 second during combat
    
    # Cache settings
    POSITION_CACHE_DURATION = 2.5
    POSITION_PROXIMITY = 35
    
    # Priority system (only used for tie-breaking at same distance)
    # Valid classifications: General, Champion, Giant, Unique
    # No classification = Pet (filtered out)
    CLASS_PRIORITIES = {
        'Unique': 1,    # Red color
        'Champion': 2,  # Purple color
        'Giant': 3,     # Yellow/Gold color
        'General': 4,   # No special color but has classification
    }
    
    # Combat rotation
    SKILL_KEYS = ['1', '2', '3', '4']
    SKILL_ANIMATION_TIME = 0.6  # Time for skill animation

    # Buffer rotation settings
    BUFFER_ENABLED = True
    BUFFER_INTERVAL = 120  # Seconds (2 minutes)
    BUFFER_SEQUENCE = [
        ('F2', 0),      # (key, delay_after_in_seconds)
        ('1', 0),
        ('2', 1.0),
        ('3', 1.0),
        ('4', 1.0),
        ('F1', 0),
    ]

    # Overlay settings
    SHOW_OVERLAY = True
    OVERLAY_UPDATE_FPS = 10

    # Death detection settings
    DEATH_CHECK_ENABLED = True  # Set to False to disable death detection
    PLAYER_HEALTH_BAR_REGION = (67, 36, 88, 8)  # (x, y, w, h) - Player health bar in top-left nameplate
    DEATH_REVIVE_DELAY = 2.0  # Seconds to wait before reviving
    DEATH_COOLDOWN = 10.0  # Seconds cooldown after revive (prevents repeated detection)
    MIN_HEALTH_RED_PIXELS = 50  # Minimum red pixels to consider player alive

    # Debug & Logging
    DEBUG_MODE = True  # Enable debug logging

    # Screenshot settings (selective capture for debugging)
    SAVE_DEATH_SCREENSHOTS = True      # Capture screenshot when death detected
    SAVE_ERROR_SCREENSHOTS = True      # Capture screenshot on errors
    SAVE_PERIODIC_SCREENSHOTS = False  # Periodic screenshots (every N cycles)
    PERIODIC_SCREENSHOT_INTERVAL = 50  # Save every 50 cycles if enabled


# ============================================================================
# LOGGING
# ============================================================================

def setup_logger():
    """Setup logging system"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = f"logs/session_{timestamp}"
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(f"{log_dir}/screenshots", exist_ok=True)
    
    logger = logging.getLogger('MobHunter')
    logger.setLevel(logging.DEBUG)
    
    # File handler
    fh = logging.FileHandler(f'{log_dir}/bot.log', encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    
    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger, log_dir


# ============================================================================
# SCREEN CAPTURE
# ============================================================================

class ScreenCapture:
    """Fast screen capture using mss"""

    def __init__(self):
        self.sct = mss()

    def capture(self):
        """Capture and return BGR image"""
        screenshot = self.sct.grab(Config.SCREEN_REGION)
        img = np.array(screenshot)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)


# ============================================================================
# FLOATING NAME DETECTOR
# ============================================================================

class FloatingNameDetector:
    """Detect floating names using color and shape analysis"""
    
    def __init__(self, logger):
        self.logger = logger
        self.last_detections = []
    
    def find_floating_names(self, screenshot):
        """
        Detect white text regions (floating names)
        Returns list of {region: (x,y,w,h), center: (x,y)}
        """
        height, width = screenshot.shape[:2]
        
        # Convert to grayscale
        gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        
        # Multiple thresholds to catch different text brightness
        detections = []
        
        for threshold_value in [200, 180, 160]:
            _, binary = cv2.threshold(gray, threshold_value, 255, cv2.THRESH_BINARY)
            
            # Morphological operations to connect text
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 1))
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
            
            # Find contours
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, 
                                          cv2.CHAIN_APPROX_SIMPLE)
            
            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                
                # Size filter
                if w < Config.MIN_NAME_WIDTH or w > Config.MAX_NAME_WIDTH:
                    continue
                if h < Config.MIN_NAME_HEIGHT or h > Config.MAX_NAME_HEIGHT:
                    continue
                
                # Aspect ratio filter
                aspect_ratio = w / h if h > 0 else 0
                if aspect_ratio < Config.MIN_ASPECT_RATIO or aspect_ratio > Config.MAX_ASPECT_RATIO:
                    continue
                
                # Position filter (ignore UI only)
                if y < Config.IGNORE_TOP or y > height - Config.IGNORE_BOTTOM:
                    continue
                if x < Config.IGNORE_LEFT or x > width - Config.IGNORE_RIGHT:
                    continue
                
                # Calculate center
                center_x = x + w // 2
                center_y = y + h // 2
                
                # Check if similar detection already exists
                is_duplicate = False
                for existing in detections:
                    ex, ey = existing['center']
                    if abs(ex - center_x) < 20 and abs(ey - center_y) < 20:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    # Calculate distance from screen center
                    center_screen_x = Config.SCREEN_WIDTH // 2
                    center_screen_y = Config.SCREEN_HEIGHT // 2
                    distance = np.sqrt(
                        (center_x - center_screen_x)**2 + 
                        (center_y - center_screen_y)**2
                    )
                    
                    detections.append({
                        'region': (x, y, w, h),
                        'center': (center_x, center_y),
                        'distance_from_center': distance
                    })
        
        self.last_detections = detections
        return detections


# ============================================================================
# POSITION CACHE
# ============================================================================

class PositionCache:
    """Remember recently checked positions"""
    
    def __init__(self, logger):
        self.logger = logger
        self.cache = {}
        self.hit_count = 0
        self.miss_count = 0
    
    def is_recently_checked(self, position):
        """Check if position was recently checked"""
        current_time = time.time()
        
        # Clean old entries
        self.cache = {
            pos: ts for pos, ts in self.cache.items()
            if current_time - ts < Config.POSITION_CACHE_DURATION
        }
        
        # Check proximity
        for cached_pos in self.cache.keys():
            distance = np.sqrt(
                (position[0] - cached_pos[0])**2 + 
                (position[1] - cached_pos[1])**2
            )
            if distance < Config.POSITION_PROXIMITY:
                self.hit_count += 1
                return True
        
        # Add to cache
        self.cache[tuple(position)] = current_time
        self.miss_count += 1
        return False
    
    def get_stats(self):
        """Get cache statistics"""
        total = self.hit_count + self.miss_count
        hit_rate = (self.hit_count / total * 100) if total > 0 else 0
        return {
            'size': len(self.cache),
            'hits': self.hit_count,
            'misses': self.miss_count,
            'hit_rate': hit_rate
        }


# ============================================================================
# NAMEPLATE READER
# ============================================================================

class NameplateReader:
    """Read mob info from nameplate with binary health detection"""
    
    def __init__(self, logger, screen_capture):
        self.logger = logger
        self.screen_capture = screen_capture
        self.click_count = 0
        self.verified_mobs = 0
        self.filtered_pets = 0
    
    def click_and_read(self, position, timeout=None):
        """Click and read nameplate with timeout"""
        if timeout is None:
            timeout = Config.NAMEPLATE_TIMEOUT
        
        try:
            # Click
            self.logger.debug(f"    Clicking {position}")
            pyautogui.click(position[0], position[1])
            self.click_count += 1
            
            time.sleep(Config.CLICK_DELAY)
            
            # Try to read nameplate
            start_time = time.time()
            attempts = 0
            
            while time.time() - start_time < timeout:
                screenshot = self.screen_capture.capture()
                info = self.read_nameplate(screenshot)
                
                attempts += 1
                
                if info is not None:
                    if info.get('class'):
                        # Has class = it's a mob
                        self.verified_mobs += 1
                        self.logger.debug(f"    ✓ Verified MOB in {attempts} attempts")
                        return info
                    else:
                        # No class = it's a pet
                        self.filtered_pets += 1
                        self.logger.debug(f"    ✗ Filtered PET (no class)")
                        return None
                
                time.sleep(0.1)
            
            self.logger.debug(f"    ✗ Nameplate timeout ({attempts} attempts)")
            return None
            
        except Exception as e:
            self.logger.error(f"    Click error: {e}")
            return None
    
    def read_nameplate(self, screenshot):
        """Read nameplate region"""
        try:
            x, y, w, h = Config.NAMEPLATE_REGION
            nameplate = screenshot[y:y+h, x:x+w]
            
            # Detect class by color patterns
            mob_class = self.detect_class_by_color(nameplate)
            
            # If no class detected, this is a pet
            if not mob_class:
                return {'class': None, 'is_pet': True}
            
            # Check if mob is alive (binary)
            is_alive = self.is_mob_alive(nameplate)
            
            return {
                'name': 'Mob',
                'class': mob_class,
                'is_alive': is_alive,
                'is_pet': False
            }
            
        except Exception as e:
            self.logger.debug(f"Nameplate read error: {e}")
            return None
    
    def detect_class_by_color(self, nameplate):
        """
        Detect mob class by color patterns in nameplate
        Returns class name or None if no class (pet)

        SIMPLE LOGIC:
        - Has classification (General/Champion/Giant/Unique) = MOB
        - No classification = PET (100%)
        """
        # Convert to HSV
        hsv = cv2.cvtColor(nameplate, cv2.COLOR_BGR2HSV)

        # Check for golden/yellow colors (Giant)
        yellow_lower = np.array([20, 100, 100])
        yellow_upper = np.array([30, 255, 255])
        yellow_mask = cv2.inRange(hsv, yellow_lower, yellow_upper)
        yellow_pixels = cv2.countNonZero(yellow_mask)

        # Check for purple colors (Champion)
        purple_lower = np.array([130, 100, 100])
        purple_upper = np.array([160, 255, 255])
        purple_mask = cv2.inRange(hsv, purple_lower, purple_upper)
        purple_pixels = cv2.countNonZero(purple_mask)

        # Check for red colors (Unique)
        red_lower1 = np.array([0, 100, 100])
        red_upper1 = np.array([10, 255, 255])
        red_lower2 = np.array([170, 100, 100])
        red_upper2 = np.array([180, 255, 255])
        red_mask1 = cv2.inRange(hsv, red_lower1, red_upper1)
        red_mask2 = cv2.inRange(hsv, red_lower2, red_upper2)
        red_pixels = cv2.countNonZero(red_mask1) + cv2.countNonZero(red_mask2)

        # CLASSIFICATION LOGIC:
        # If ANY classification color is detected = MOB
        # If NO classification color detected = PET

        # Check for any classification indicator
        has_yellow = yellow_pixels > 50
        has_purple = purple_pixels > 50
        has_red = red_pixels > 100

        # If no classification colors detected = PET
        if not has_yellow and not has_purple and not has_red:
            return None  # No classification = PET

        # Has classification = MOB, determine which type
        if has_red:
            return 'Unique'
        elif has_purple:
            return 'Champion'
        elif has_yellow:
            return 'Giant'
        else:
            return 'General'  # Has some color but below thresholds
    
    def get_health_pixels(self, nameplate=None):
        """
        Get the actual red pixel count from health bar
        Returns the number of red pixels (0 if error)
        """
        try:
            # If no nameplate provided, capture it
            if nameplate is None:
                screenshot = self.screen_capture.capture()
                x, y, w, h = Config.NAMEPLATE_REGION
                nameplate = screenshot[y:y+h, x:x+w]

            # Convert to HSV
            hsv = cv2.cvtColor(nameplate, cv2.COLOR_BGR2HSV)

            # Red health bar detection
            red_lower1 = np.array([0, 150, 100])
            red_upper1 = np.array([10, 255, 255])
            red_lower2 = np.array([170, 150, 100])
            red_upper2 = np.array([180, 255, 255])

            mask1 = cv2.inRange(hsv, red_lower1, red_upper1)
            mask2 = cv2.inRange(hsv, red_lower2, red_upper2)
            red_mask = cv2.bitwise_or(mask1, mask2)

            red_pixels = cv2.countNonZero(red_mask)

            return red_pixels

        except Exception as e:
            self.logger.error(f"Health pixel count error: {e}")
            return 0

    def is_mob_alive(self, nameplate=None):
        """
        Binary health detection: ALIVE or DEAD
        Returns True if red pixels exist (alive), False otherwise (dead)
        """
        red_pixels = self.get_health_pixels(nameplate)

        # Binary decision: more than threshold = ALIVE
        is_alive = red_pixels > Config.RED_PIXEL_THRESHOLD

        self.logger.debug(f"    Health check: {red_pixels} red pixels -> {'ALIVE' if is_alive else 'DEAD'}")

        return is_alive


# ============================================================================
# BUFFER SYSTEM
# ============================================================================

class BufferSystem:
    """Handle buff rotation on timer"""

    def __init__(self, logger):
        self.logger = logger
        self.last_buffer_time = 0
        self.total_buffs = 0

    def should_run_buffer(self):
        """Check if it's time to run buffer rotation"""
        if not Config.BUFFER_ENABLED:
            return False

        current_time = time.time()
        elapsed = current_time - self.last_buffer_time

        # Run if never run before OR if interval has passed
        return self.last_buffer_time == 0 or elapsed >= Config.BUFFER_INTERVAL

    def run_buffer_sequence(self):
        """Execute the buffer rotation"""
        try:
            self.logger.info(f"\n{'='*60}")
            self.logger.info("RUNNING BUFFER SEQUENCE")
            self.logger.info(f"{'='*60}")

            for i, (key, delay) in enumerate(Config.BUFFER_SEQUENCE, 1):
                self.logger.info(f"  [{i}/{len(Config.BUFFER_SEQUENCE)}] Pressing: {key}")
                pyautogui.press(key)

                if delay > 0:
                    self.logger.info(f"      Waiting {delay}s...")
                    time.sleep(delay)
                else:
                    time.sleep(0.1)  # Small delay between instant presses

            self.last_buffer_time = time.time()
            self.total_buffs += 1

            self.logger.info(f"{'='*60}")
            self.logger.info(f"Buffer sequence complete (Total: {self.total_buffs})")
            self.logger.info(f"Next buffer in {Config.BUFFER_INTERVAL}s ({Config.BUFFER_INTERVAL//60}m)")
            self.logger.info(f"{'='*60}\n")

            return True

        except Exception as e:
            self.logger.error(f"Buffer sequence error: {e}")
            return False

    def get_time_until_next(self):
        """Get seconds until next buffer"""
        if self.last_buffer_time == 0:
            return 0

        elapsed = time.time() - self.last_buffer_time
        remaining = Config.BUFFER_INTERVAL - elapsed
        return max(0, remaining)

    def reset_timer(self):
        """Reset buffer timer (used when resuming from pause)"""
        self.last_buffer_time = 0
        self.logger.info("Buffer timer reset - will run on next cycle")


# ============================================================================
# DEATH DETECTION AND AUTO-REVIVE
# ============================================================================

class DeathDetector:
    """Detect player death and handle auto-revive"""

    def __init__(self, logger):
        self.logger = logger
        self.death_count = 0
        self.last_death_time = 0
        self.buffer_system = None  # Will be set by MobHunter

    def is_player_dead(self, screenshot):
        """
        Check if player is dead by examining health bar in top-left nameplate

        Detection method:
        - Extract player health bar region (top-left corner of screen)
        - Count RED pixels in health bar
        - If red pixels < threshold → Player is DEAD (no health)
        - If red pixels >= threshold → Player is ALIVE

        Returns True if player is dead
        """
        if not Config.DEATH_CHECK_ENABLED:
            return False

        try:
            # Extract player health bar region from top-left nameplate
            x, y, w, h = Config.PLAYER_HEALTH_BAR_REGION
            health_bar = screenshot[y:y+h, x:x+w]

            # Convert to HSV for better red color detection
            hsv = cv2.cvtColor(health_bar, cv2.COLOR_BGR2HSV)

            # Red color has two ranges in HSV (wraps around at 180)
            # Range 1: Red hues 0-10
            red_lower1 = np.array([0, 100, 100])
            red_upper1 = np.array([10, 255, 255])
            red_mask1 = cv2.inRange(hsv, red_lower1, red_upper1)

            # Range 2: Red hues 170-180
            red_lower2 = np.array([170, 100, 100])
            red_upper2 = np.array([180, 255, 255])
            red_mask2 = cv2.inRange(hsv, red_lower2, red_upper2)

            # Combine both red ranges
            red_mask = cv2.bitwise_or(red_mask1, red_mask2)
            red_pixels = cv2.countNonZero(red_mask)

            # Debug logging
            if Config.DEBUG_MODE:
                self.logger.debug(f"Player health bar: {red_pixels} red pixels")

            # Check cooldown - don't detect death if we just revived
            time_since_last_death = time.time() - self.last_death_time if self.last_death_time > 0 else 999
            in_death_cooldown = time_since_last_death < Config.DEATH_COOLDOWN

            # Check buffer cooldown - don't detect death right after buffer (buff effects can trigger false positive)
            in_buffer_cooldown = False
            if self.buffer_system and self.buffer_system.last_buffer_time > 0:
                time_since_buffer = time.time() - self.buffer_system.last_buffer_time
                in_buffer_cooldown = time_since_buffer < 5.0  # Skip death detection for 5 seconds after buffer

            # Player is DEAD if red pixels < threshold
            is_dead = red_pixels < Config.MIN_HEALTH_RED_PIXELS

            if is_dead and not in_death_cooldown and not in_buffer_cooldown:
                self.logger.warning("💀 DEATH DETECTED - Player health bar empty!")
                self.logger.warning(f"   Health bar red pixels: {red_pixels} (threshold: {Config.MIN_HEALTH_RED_PIXELS})")
                return True
            elif is_dead and in_death_cooldown:
                self.logger.debug(f"Death detected but in death cooldown ({time_since_last_death:.1f}s since last death)")
            elif is_dead and in_buffer_cooldown:
                time_since_buffer = time.time() - self.buffer_system.last_buffer_time
                self.logger.debug(f"Death detected but in buffer cooldown ({time_since_buffer:.1f}s since buffer)")

            return False

        except Exception as e:
            self.logger.error(f"Death detection error: {e}")
            return False

    def handle_death(self):
        """
        Execute revive sequence

        Sequence:
        1. Wait 2 seconds for popup to stabilize
        2. Press F4 (open revive menu)
        3. Wait 0.5s
        4. Press 0 (select resurrect option)
        5. Wait for respawn
        """
        try:
            self.death_count += 1
            self.last_death_time = time.time()

            self.logger.info("\n" + "="*70)
            self.logger.info("💀 DEATH HANDLER ACTIVATED")
            self.logger.info("="*70)
            self.logger.info(f"Death #{self.death_count}")
            self.logger.info(f"Waiting {Config.DEATH_REVIVE_DELAY}s before reviving...")

            # Wait for popup to stabilize
            time.sleep(Config.DEATH_REVIVE_DELAY)

            # Press F4 to open revive menu
            self.logger.info("Pressing F4 (open revive menu)...")
            pyautogui.press('f4')
            time.sleep(0.5)

            # Press 0 to resurrect at specified point
            self.logger.info("Pressing 0 (resurrect at specified point)...")
            pyautogui.press('0')

            # Wait for respawn animation
            self.logger.info("Waiting for respawn (3s)...")
            time.sleep(3.0)

            self.logger.info("✅ Revive sequence completed!")
            self.logger.info("="*70 + "\n")

            return True

        except Exception as e:
            self.logger.error(f"Death handler error: {e}")
            return False


# ============================================================================
# ANTI-STUCK SYSTEM
# ============================================================================

class StuckDetector:
    """Detect and recover from stuck situations"""

    def __init__(self, logger):
        self.logger = logger
        self.last_action_time = time.time()
        self.last_kill_time = time.time()  # Track last kill separately
        self.target_selected = False
        self.stuck_recoveries = 0
        self.consecutive_recoveries = 0  # Track recoveries since last kill
        self.in_recovery_mode = False  # Flag to indicate we're actively trying to unstuck
        self.no_target_duration = 7.0  # Seconds since last kill before stuck (increased from 5.0)
        self.with_target_duration = 3.0  # Seconds with target but no progress
        self.recovery_retry_delay = 2.0  # Seconds between recovery attempts

    def reset_timer(self):
        """Reset the action timer (called when progress is made)"""
        self.last_action_time = time.time()

    def on_kill(self):
        """Called when a mob is killed - resets the no-target timer and clears recovery mode"""
        self.last_kill_time = time.time()

        # Log if we were in recovery mode
        if self.consecutive_recoveries > 0:
            self.logger.info(f"✅ Kill confirmed! Exiting recovery mode after {self.consecutive_recoveries} attempts")

        # Clear recovery state
        self.consecutive_recoveries = 0
        self.in_recovery_mode = False

        self.logger.debug(f"Stuck detector: Kill recorded, timer reset")

    def set_target_status(self, has_target):
        """Update whether a target is currently selected"""
        old_status = self.target_selected
        self.target_selected = has_target

        # If status changed, reset timer (only for Scenario 2)
        if old_status != has_target:
            self.reset_timer()

    def is_stuck(self):
        """
        Check if character is stuck

        Returns:
            (is_stuck, scenario_type) where scenario_type is:
            - 1: No target selected for 7+ seconds since last kill
            - 2: Target selected but stuck for 3+ seconds
            - None: Not stuck
        """
        # If in recovery mode, continue recovery until kill
        if self.in_recovery_mode:
            elapsed = time.time() - self.last_action_time
            if elapsed >= self.recovery_retry_delay:
                scenario = 1 if not self.target_selected else 2
                self.logger.warning(f"⚠️  STILL STUCK (Recovery mode, attempt #{self.consecutive_recoveries + 1})")
                return True, scenario
            return False, None

        # Scenario 1: Use time since last kill
        time_since_kill = time.time() - self.last_kill_time

        # Scenario 2: Use time since last action
        elapsed = time.time() - self.last_action_time

        # Scenario 1: No target selected for 7+ seconds since last kill
        if not self.target_selected and time_since_kill >= self.no_target_duration:
            self.logger.warning(f"⚠️  STUCK DETECTED (Scenario 1): No target for {time_since_kill:.1f}s since last kill")
            self.in_recovery_mode = True
            return True, 1

        # Scenario 2: Target selected but stuck for 3+ seconds
        if self.target_selected and elapsed >= self.with_target_duration:
            self.logger.warning(f"⚠️  STUCK DETECTED (Scenario 2): Target selected but stuck for {elapsed:.1f}s")
            self.in_recovery_mode = True
            return True, 2

        return False, None

    def recover_from_stuck(self, scenario):
        """
        Execute recovery action with HIGHLY VARIED RANDOM movements

        IMPORTANT: Left/Right arrows only ROTATE character, don't move.
        To move: rotate to face direction, then press Up arrow.

        Scenario 1: No target selected (7s since last kill)
        - Execute 2-4 random movement steps (varies each attempt)
        - Each step: Random rotation (0.5-2.5s) + Forward movement
        - 50% chance of camera angle change between steps
        - Movement distance escalates with consecutive attempts

        Scenario 2: Target selected but stuck (3s no progress)
        - Turn around (1.3-2.5s random rotation)
        - Move forward (escalated distance based on attempts)
        - Camera angle change (random ±400px)
        - 1-3 additional random movements
        - Each movement: random direction, rotation, distance

        Progressive Escalation:
        - Attempt 1: 2.0s base movement
        - Attempt 2: 2.5s movement
        - Attempt 3: 3.0s movement
        - Attempt 4+: 3.5s+ movement (capped at 5x)

        Prevents going back-and-forth in same area by using:
        - Highly randomized directions and timings
        - Variable number of steps
        - Progressive distance increases
        - Random camera angles

        Recovery continues until a kill is confirmed (on_kill() is called)
        """
        try:
            self.stuck_recoveries += 1
            self.consecutive_recoveries += 1

            self.logger.info("\n" + "="*70)
            self.logger.info("🔧 ANTI-STUCK RECOVERY ACTIVATED")
            self.logger.info("="*70)
            self.logger.info(f"Scenario: {scenario}")
            self.logger.info(f"Consecutive attempts: {self.consecutive_recoveries}")
            self.logger.info(f"Total recoveries: {self.stuck_recoveries}")

            import random

            # Progressive escalation: increase movement distance and variation based on attempts
            attempt_multiplier = min(self.consecutive_recoveries, 5)  # Cap at 5x
            base_move_time = 2.0
            escalated_move_time = base_move_time + (attempt_multiplier * 0.5)  # Adds 0.5s per attempt

            if scenario == 1:
                # Scenario 1: No target - highly varied random movement
                self.logger.info("Action: Random varied movement to explore new area")

                # Randomize number of movement steps (2-4 steps)
                num_steps = random.randint(2, 4)
                self.logger.info(f"  Executing {num_steps} random movement steps...")

                for step in range(num_steps):
                    # Random rotation direction and amount
                    direction = random.choice(['left', 'right'])
                    rotation_time = random.uniform(0.5, 2.5)  # Wide range

                    self.logger.info(f"  Step {step+1}: Rotate {direction} ({rotation_time:.1f}s) + Forward ({escalated_move_time:.1f}s)")

                    # Rotate
                    pyautogui.keyDown(direction)
                    time.sleep(rotation_time)
                    pyautogui.keyUp(direction)
                    time.sleep(0.2)

                    # Move forward in that direction
                    pyautogui.keyDown('up')
                    time.sleep(escalated_move_time)
                    pyautogui.keyUp('up')
                    time.sleep(0.2)

                    # Random camera angle change (50% chance each step)
                    if random.random() < 0.5:
                        drag_distance = random.randint(-400, 400)
                        self.logger.info(f"    Camera angle change ({drag_distance}px)")
                        start_x = Config.SCREEN_WIDTH // 2
                        start_y = Config.SCREEN_HEIGHT // 2
                        pyautogui.moveTo(start_x, start_y)
                        pyautogui.mouseDown(button='right')
                        pyautogui.moveTo(start_x + drag_distance, start_y, duration=0.5)
                        pyautogui.mouseUp(button='right')
                        time.sleep(0.2)

                self.logger.info(f"✓ Completed {num_steps} varied movements - exploring new area")

            elif scenario == 2:
                # Scenario 2: Has target but stuck - aggressive escape pattern
                self.logger.info("Action: Aggressive escape + random exploration")

                # Step 1: Turn around (escalated rotation for more variety)
                direction = random.choice(['left', 'right'])
                rotation_time = random.uniform(1.3, 2.5)  # More variation

                self.logger.info(f"  Step 1: Turning {direction} ({rotation_time:.1f}s)...")
                pyautogui.keyDown(direction)
                time.sleep(rotation_time)
                pyautogui.keyUp(direction)
                time.sleep(0.2)

                # Step 2: Move forward (escalated distance)
                self.logger.info(f"  Step 2: Moving forward ({escalated_move_time:.1f}s)...")
                pyautogui.keyDown('up')
                time.sleep(escalated_move_time)
                pyautogui.keyUp('up')
                time.sleep(0.2)

                # Step 3: Camera angle change
                drag_distance = random.randint(-400, 400)
                self.logger.info(f"  Step 3: Changing camera angle ({drag_distance}px)...")
                start_x = Config.SCREEN_WIDTH // 2
                start_y = Config.SCREEN_HEIGHT // 2
                pyautogui.moveTo(start_x, start_y)
                pyautogui.mouseDown(button='right')
                pyautogui.moveTo(start_x + drag_distance, start_y, duration=0.5)
                pyautogui.mouseUp(button='right')
                time.sleep(0.3)

                # Steps 4-5: Additional random movements (1-3 more steps)
                extra_steps = random.randint(1, 3)
                self.logger.info(f"  Steps 4+: {extra_steps} additional random movements...")

                for i in range(extra_steps):
                    # Random direction and rotation
                    rand_direction = random.choice(['left', 'right'])
                    rand_rotation = random.uniform(0.3, 1.5)
                    rand_move_time = random.uniform(1.5, 3.0)

                    self.logger.info(f"    Extra {i+1}: Rotate {rand_direction} ({rand_rotation:.1f}s) + Forward ({rand_move_time:.1f}s)")

                    pyautogui.keyDown(rand_direction)
                    time.sleep(rand_rotation)
                    pyautogui.keyUp(rand_direction)
                    time.sleep(0.1)

                    pyautogui.keyDown('up')
                    time.sleep(rand_move_time)
                    pyautogui.keyUp('up')
                    time.sleep(0.2)

                self.logger.info(f"✓ Aggressive escape complete - should be in completely new area")

            self.logger.info("="*70 + "\n")

            # DON'T reset timers - only on_kill() should do that
            # Reset action timer to delay next recovery attempt
            self.reset_timer()

            return True

        except Exception as e:
            self.logger.error(f"Stuck recovery error: {e}")
            return False


# ============================================================================
# COMBAT SYSTEM WITH HEALTH MONITORING
# ============================================================================

class CombatSystem:
    """Handle combat with live health monitoring"""
    
    def __init__(self, logger, nameplate_reader):
        self.logger = logger
        self.nameplate_reader = nameplate_reader
        self.total_kills = 0
        self.skills_used = 0
        self.early_stops = 0  # Times we stopped rotation early due to death
    
    def engage(self, target_info):
        """
        Execute combat rotation with health monitoring
        Returns True if mob was killed, False if:
        - Mob already dead
        - Health didn't decrease (character stuck, can't reach mob)
        """
        try:
            mob_class = target_info.get('class', 'Unknown')

            self.logger.info(f"\n{'>'*60}")
            self.logger.info(f"⚔️  ENGAGING: {mob_class}")
            self.logger.info(f"{'>'*60}")

            # Initial health check
            initial_health = self.nameplate_reader.get_health_pixels()

            if initial_health <= Config.RED_PIXEL_THRESHOLD:
                self.logger.info("✗ Mob already dead, skipping")
                return False

            self.logger.debug(f"    Initial health: {initial_health} red pixels")

            # Track health changes to detect if we're actually hitting the mob
            health_history = [initial_health]

            # Combat rotation with health checks
            for i, skill_key in enumerate(Config.SKILL_KEYS, 1):
                # Use skill
                self.logger.info(f"  → Skill {i}: {skill_key}")
                pyautogui.press(skill_key)
                self.skills_used += 1

                # Wait for skill animation
                time.sleep(Config.SKILL_ANIMATION_TIME)

                # Wait additional time to reach 1 second check interval
                time.sleep(Config.HEALTH_CHECK_INTERVAL - Config.SKILL_ANIMATION_TIME)

                # Check current health
                current_health = self.nameplate_reader.get_health_pixels()
                health_history.append(current_health)

                # Check if mob still alive
                if current_health <= Config.RED_PIXEL_THRESHOLD:
                    self.logger.info(f"  ✓ Mob DEAD after skill {i}!")
                    self.total_kills += 1
                    self.early_stops += 1
                    self.logger.info(f"{'<'*60}")
                    self.logger.info(f"💀 Total kills: {self.total_kills} | Skills saved: {4-i}")
                    self.logger.info(f"{'<'*60}\n")
                    return True
                else:
                    self.logger.debug(f"    Health check: {current_health} red pixels -> ALIVE")

            # Rotation complete - check if health actually decreased
            final_health = health_history[-1]
            max_health = max(health_history)
            min_health = min(health_history)
            health_decreased = max_health - min_health

            self.logger.debug(f"    Health change: {initial_health} → {final_health} (Δ={initial_health - final_health})")

            # Calculate percentage of health decreased
            if initial_health > 0:
                health_decrease_percentage = (health_decreased / initial_health) * 100
            else:
                health_decrease_percentage = 0

            # If health didn't change significantly, we're not hitting the mob (stuck)
            # Use percentage-based threshold: if health decreased by less than 5% OR less than 5 pixels
            # This handles both large health bars (649px) and small health bars (98px)
            MIN_PERCENTAGE_DECREASE = 5.0  # 5% of initial health
            MIN_ABSOLUTE_DECREASE = 5       # At least 5 pixels

            is_stuck = (health_decrease_percentage < MIN_PERCENTAGE_DECREASE and
                       health_decreased < Config.HEALTH_CHANGE_THRESHOLD)

            if is_stuck:
                self.logger.warning(f"  ⚠️  Health barely changed ({initial_health} → {final_health}, {health_decrease_percentage:.1f}%) - NOT hitting mob!")
                self.logger.warning(f"  Character may be stuck or mob unreachable")
                self.logger.info(f"{'<'*60}\n")
                return False  # Combat failed - mob wasn't damaged

            # Health decreased - we're hitting the mob, assume kill
            self.logger.info(f"  ℹ️  Rotation complete (health decreased: {health_decreased} pixels)")
            self.total_kills += 1
            self.logger.info(f"{'<'*60}")
            self.logger.info(f"💀 Total kills: {self.total_kills}")
            self.logger.info(f"{'<'*60}\n")

            return True

        except Exception as e:
            self.logger.error(f"Combat error: {e}")
            return False


# ============================================================================
# OVERLAY
# ============================================================================

class OverlayWindow:
    """Display detection overlay with transparent background and click-through"""

    def __init__(self, logger):
        self.logger = logger
        self.running = False
        self.visible = True  # Overlay visibility (can be toggled with Tab key)
        self.current_frame = None
        self.detections = []
        self.stats = {}
        self.thread = None
        self.window_name = 'MOB HUNTER v3.0 - Overlay'
        self.hwnd = None

    def start(self):
        """Start overlay in separate thread"""
        if Config.SHOW_OVERLAY:
            self.running = True
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
            self.logger.info("🖥️  Click-through overlay starting...")

    def stop(self):
        """Stop overlay"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
        cv2.destroyAllWindows()

    def update(self, frame, detections, stats):
        """Update overlay data"""
        self.current_frame = frame.copy() if frame is not None else None
        self.detections = detections
        self.stats = stats

    def toggle_visibility(self):
        """Toggle overlay visibility"""
        self.visible = not self.visible
        if self.visible:
            self.logger.info("👁️  Overlay: VISIBLE")
        else:
            self.logger.info("🙈 Overlay: HIDDEN")

    def make_click_through(self):
        """Make the window transparent and click-through using Windows API"""
        try:
            # Wait for window to be created
            time.sleep(0.5)

            # Find the OpenCV window
            self.hwnd = win32gui.FindWindow(None, self.window_name)

            if not self.hwnd:
                self.logger.warning("⚠️  Could not find overlay window")
                return False

            # Get current extended window style
            ex_style = win32gui.GetWindowLong(self.hwnd, win32con.GWL_EXSTYLE)

            # Add layered and transparent flags
            # WS_EX_LAYERED: Enables transparency
            # WS_EX_TRANSPARENT: Makes window click-through
            # WS_EX_TOPMOST: Keeps window on top
            new_ex_style = ex_style | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOPMOST

            # Apply the new style
            win32gui.SetWindowLong(self.hwnd, win32con.GWL_EXSTYLE, new_ex_style)

            # Set transparency using color key - black pixels (RGB 0,0,0) will be fully transparent
            # This makes the background invisible while keeping colored elements visible
            win32gui.SetLayeredWindowAttributes(
                self.hwnd,
                0,  # Color key (RGB 0,0,0 = black, will be transparent)
                0,  # Alpha value (not used with LWA_COLORKEY)
                win32con.LWA_COLORKEY  # Use color key transparency (black = transparent)
            )

            # Make window always on top
            win32gui.SetWindowPos(
                self.hwnd,
                win32con.HWND_TOPMOST,  # Place above all non-topmost windows
                0, 0, 0, 0,  # Position and size (ignored with flags below)
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE  # Don't change position/size
            )

            # Remove window borders and make it truly borderless
            style = win32gui.GetWindowLong(self.hwnd, win32con.GWL_STYLE)
            style = style & ~win32con.WS_CAPTION & ~win32con.WS_THICKFRAME
            win32gui.SetWindowLong(self.hwnd, win32con.GWL_STYLE, style)

            self.logger.info("✅ Overlay is now CLICK-THROUGH and transparent")
            return True

        except Exception as e:
            self.logger.error(f"Failed to make window click-through: {e}")
            return False
    
    def _run(self):
        """Overlay rendering loop with transparent background"""
        try:
            # Create named window in fullscreen mode
            cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
            cv2.setWindowProperty(self.window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

            # Make it click-through
            self.make_click_through()

            while self.running:
                try:
                    # Create BLACK background (will be transparent)
                    # Same dimensions as screen for perfect alignment
                    display = np.zeros((Config.SCREEN_HEIGHT, Config.SCREEN_WIDTH, 3), dtype=np.uint8)

                    # Only draw elements if overlay is visible
                    if self.visible:
                        # Draw screen center crosshair
                        center_x = Config.SCREEN_WIDTH // 2
                        center_y = Config.SCREEN_HEIGHT // 2
                        cv2.line(display, (center_x - 30, center_y), (center_x + 30, center_y), (0, 255, 255), 2)
                        cv2.line(display, (center_x, center_y - 30), (center_x, center_y + 30), (0, 255, 255), 2)
                        cv2.circle(display, (center_x, center_y), 100, (0, 255, 255), 1)

                        # Draw detections with distance indicators
                        for i, det in enumerate(self.detections, 1):
                            x, y, w, h = det['region']
                            center = det['center']
                            distance = det.get('distance_from_center', 0)

                            # Color based on distance (green = close, red = far)
                            color_intensity = min(255, int(distance / 3))
                            color = (0, 255 - color_intensity, color_intensity)

                            # Draw box around detected name
                            cv2.rectangle(display, (x, y), (x+w, y+h), color, 2)

                            # Draw center dot
                            cv2.circle(display, center, 5, (0, 0, 255), -1)

                            # Draw line from detection to screen center
                            cv2.line(display, center, (center_x, center_y), (100, 100, 100), 1)

                            # Draw distance label with background for readability
                            dist_text = f"#{i} D:{int(distance)}"
                            (text_width, text_height), baseline = cv2.getTextSize(dist_text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)

                            # Draw dark background rectangle behind text
                            padding = 2
                            cv2.rectangle(display,
                                        (x - padding, y - text_height - 8 - padding),
                                        (x + text_width + padding, y - 5 + padding),
                                        (50, 50, 50), -1)  # Dark gray background

                            # Colored text
                            cv2.putText(display, dist_text, (x, y-5),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

                        # Draw stats in top-left corner (smaller, green only, not bold)
                        y_pos = 25
                        for key, value in self.stats.items():
                            text = f"{key}: {value}"
                            # Green color only (no orange for paused)
                            text_color = (0, 255, 0)

                            # Get text size for background rectangle (smaller font: 0.45 instead of 0.6)
                            (text_width, text_height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)

                            # Draw dark background rectangle behind text for readability
                            padding = 4
                            cv2.rectangle(display,
                                        (5, y_pos - text_height - padding),
                                        (10 + text_width, y_pos + padding),
                                        (50, 50, 50), -1)  # Dark gray background

                            # Green text only (no white outline, not bold - thickness 1)
                            cv2.putText(display, text, (8, y_pos),
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.45, text_color, 1)
                            y_pos += 22

                    # Draw large PAUSED overlay if paused
                    if 'Status' in self.stats and 'PAUSED' in str(self.stats.get('Status', '')):
                        # Large PAUSED text
                        text = "PAUSED"
                        font_scale = 3
                        thickness = 5
                        (text_width, text_height), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
                        text_x = (Config.SCREEN_WIDTH - text_width) // 2
                        text_y = (Config.SCREEN_HEIGHT + text_height) // 2

                        # White outline
                        cv2.putText(display, text, (text_x + 2, text_y + 2),
                                   cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), thickness + 2)
                        # Orange text
                        cv2.putText(display, text, (text_x, text_y),
                                   cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 165, 255), thickness)

                    # Show overlay
                    cv2.imshow(self.window_name, display)

                    # Check for 'q' key to close (though clicks won't register due to transparency)
                    key = cv2.waitKey(1)
                    if key == ord('q'):
                        self.logger.info("Overlay closed by user")
                        self.running = False

                except Exception as e:
                    self.logger.error(f"Overlay rendering error: {e}")
                    continue

                # Control frame rate
                time.sleep(1.0 / Config.OVERLAY_UPDATE_FPS)

        except Exception as e:
            self.logger.error(f"Overlay thread error: {e}")
            self.logger.error(traceback.format_exc())
        finally:
            cv2.destroyAllWindows()


# ============================================================================
# MAIN BOT
# ============================================================================

class MobHunter:
    """Main bot controller with center-out targeting"""
    
    def __init__(self):
        self.logger, self.log_dir = setup_logger()
        self.logger.info("="*70)
        self.logger.info("MOB HUNTER v3.0 - CENTER-OUT + BINARY HEALTH")
        self.logger.info("="*70)
        self.logger.info(f"Log directory: {self.log_dir}")
        self.logger.info(f"Screen: {Config.SCREEN_WIDTH}x{Config.SCREEN_HEIGHT}")
        self.logger.info(f"Strategy: Attack closest to center first")
        self.logger.info(f"Health: Binary (ALIVE/DEAD) detection")
        self.logger.info(f"Pet Filter: Via nameplate class detection")
        self.logger.info("="*70)
        
        # Components
        self.screen_capture = ScreenCapture()
        self.detector = FloatingNameDetector(self.logger)
        self.cache = PositionCache(self.logger)
        self.nameplate_reader = NameplateReader(self.logger, self.screen_capture)
        self.combat = CombatSystem(self.logger, self.nameplate_reader)
        self.buffer = BufferSystem(self.logger)
        self.death_detector = DeathDetector(self.logger)
        self.death_detector.buffer_system = self.buffer  # Link buffer system for cooldown checking
        self.stuck_detector = StuckDetector(self.logger)
        self.overlay = OverlayWindow(self.logger)

        self.cycle = 0
        self.running = True
        self.paused = False
        self.start_time = time.time()
        self.just_resumed = False  # Track if just resumed (skip death detection)

        # Start global keyboard listener
        self.keyboard_listener = start_keyboard_listener()

        # Screenshot counter
        self.screenshot_counter = 0

    def save_screenshot(self, screenshot, event_type, extra_info=""):
        """
        Save screenshot with meaningful filename

        Args:
            screenshot: The image to save
            event_type: Type of event (death, error, cycle, etc.)
            extra_info: Additional context for filename
        """
        try:
            self.screenshot_counter += 1
            timestamp = datetime.now().strftime("%H%M%S")

            # Create filename with context
            if extra_info:
                filename = f"{self.screenshot_counter:04d}_{timestamp}_{event_type}_{extra_info}.png"
            else:
                filename = f"{self.screenshot_counter:04d}_{timestamp}_{event_type}.png"

            filepath = f"{self.log_dir}/screenshots/{filename}"
            cv2.imwrite(filepath, screenshot)
            self.logger.info(f"📸 Screenshot saved: {filename}")

        except Exception as e:
            self.logger.error(f"Failed to save screenshot: {e}")

    def run(self):
        """Main loop with buffer system and pause/resume"""
        self.logger.info("\n🚀 Bot started! Press Ctrl+C to stop.\n")
        self.logger.info("💡 Controls: CapsLock = Pause/Resume | O = Toggle Overlay\n")
        self.logger.info("⌨️  Global keyboard listener active (works in any window)\n")

        # Log configuration
        self.logger.info("📋 Configuration:")
        self.logger.info(f"   Death Detection: {'✅ Enabled' if Config.DEATH_CHECK_ENABLED else '❌ Disabled'}")
        self.logger.info(f"   Death Screenshots: {'✅ Enabled' if Config.SAVE_DEATH_SCREENSHOTS else '❌ Disabled'}")
        self.logger.info(f"   Error Screenshots: {'✅ Enabled' if Config.SAVE_ERROR_SCREENSHOTS else '❌ Disabled'}")
        self.logger.info(f"   Periodic Screenshots: {'✅ Enabled' if Config.SAVE_PERIODIC_SCREENSHOTS else '❌ Disabled'}")
        if Config.SAVE_PERIODIC_SCREENSHOTS:
            self.logger.info(f"   Screenshot Interval: Every {Config.PERIODIC_SCREENSHOT_INTERVAL} cycles")
        self.logger.info(f"   Buffer Interval: {Config.BUFFER_INTERVAL}s")
        self.logger.info(f"   Overlay: {'✅ Enabled' if Config.SHOW_OVERLAY else '❌ Disabled'}")
        self.logger.info("")

        # Start overlay
        self.overlay.start()

        # Run initial buffer sequence
        self.logger.info("\nRunning INITIAL buffer sequence...")
        self.buffer.run_buffer_sequence()

        try:
            while self.running:
                # Check for CapsLock toggle (global keyboard listener)
                if check_capslock_toggle():
                    self.paused = not self.paused
                    if self.paused:
                        self.logger.info("\n⏸️  PAUSED - Press CapsLock to resume\n")
                    else:
                        self.logger.info("\n▶️  RESUMED - Running buffer sequence...\n")
                        # Reset buffer timer and run sequence on resume
                        self.buffer.reset_timer()
                        self.buffer.run_buffer_sequence()
                        # Set flag to skip death detection on next cycle
                        self.just_resumed = True
                        # Update overlay immediately to clear PAUSED text
                        screenshot = self.screen_capture.capture()
                        self.update_overlay(screenshot, [], 0, 0)

                # Check for 'O' key toggle (global keyboard listener)
                if check_overlay_toggle():
                    self.overlay.toggle_visibility()
                    time.sleep(0.1)  # Small debounce delay

                # Skip cycle if paused, but update overlay
                if self.paused:
                    # Update overlay with paused state
                    screenshot = self.screen_capture.capture()
                    self.update_overlay(screenshot, [], 0, 0)
                    time.sleep(0.1)  # Short sleep when paused
                    continue

                # Check if buffer needs to run
                if self.buffer.should_run_buffer():
                    self.buffer.run_buffer_sequence()

                # Run detection cycle
                self.cycle += 1
                self.run_cycle()

                time.sleep(Config.CYCLE_DELAY)
                
        except KeyboardInterrupt:
            self.logger.info("\n\n⛔ Bot stopped by user")
        except Exception as e:
            self.logger.error(f"\n💥 FATAL ERROR: {e}")
            self.logger.error(traceback.format_exc())

            # Save error screenshot if possible
            if Config.SAVE_ERROR_SCREENSHOTS:
                try:
                    error_screenshot = self.screen_capture.capture()
                    self.save_screenshot(error_screenshot, "ERROR", "fatal_error")
                except:
                    pass  # Don't crash while trying to save error screenshot
        finally:
            self.overlay.stop()
            self.print_statistics()
    
    def run_cycle(self):
        """Single detection cycle with center-out targeting"""
        try:
            self.logger.info(f"\n{'='*70}")
            self.logger.info(f"CYCLE #{self.cycle}")
            self.logger.info(f"{'='*70}")

            # Capture
            screenshot = self.screen_capture.capture()

            # Skip death detection if just resumed (avoid false positive from buff effects)
            if self.just_resumed:
                self.logger.debug("Skipping death detection (just resumed)")
                self.just_resumed = False  # Reset flag
            else:
                # Check for death FIRST (highest priority)
                if self.death_detector.is_player_dead(screenshot):
                    self.logger.warning("⚠️  Player is dead - pausing hunting")

                    # Save death screenshot
                    if Config.SAVE_DEATH_SCREENSHOTS:
                        self.save_screenshot(screenshot, "DEATH", f"death_{self.death_detector.death_count + 1}")

                    # Handle death and revive
                    if self.death_detector.handle_death():
                        self.logger.info("🔄 Running buffer sequence after revive...")
                        # Run buffer sequence after revival
                        self.buffer.run_buffer_sequence()
                        self.logger.info("✅ Ready to resume hunting!")
                    else:
                        self.logger.error("❌ Revive failed - skipping cycle")

                    # Skip this cycle after death handling
                    return

            # Check for stuck condition
            is_stuck, scenario = self.stuck_detector.is_stuck()
            if is_stuck:
                # Execute recovery action
                if self.stuck_detector.recover_from_stuck(scenario):
                    self.logger.info("✅ Stuck recovery completed - continuing with detection")
                    # Don't return - continue with detection to check new location
                    # Capture new screenshot after movement
                    screenshot = self.screen_capture.capture()
                else:
                    self.logger.error("❌ Stuck recovery failed")
                    return  # Skip cycle if recovery failed

            # Detect all floating names
            detections = self.detector.find_floating_names(screenshot)
            self.logger.info(f"Detected: {len(detections)} floating names")
            
            if not detections:
                self.logger.info("→ No floating names found")
                # Update stuck detector: no targets available
                self.stuck_detector.set_target_status(False)
                # Update overlay even with no detections
                self.update_overlay(screenshot, [], 0, 0)
                return
            
            # Filter cached positions
            valid_targets = []
            for i, det in enumerate(detections, 1):
                center = det['center']
                
                # Cache check only
                if self.cache.is_recently_checked(center):
                    self.logger.debug(f"  Name #{i}: Cached, skipping")
                    continue
                
                # Calculate click position (below text)
                x, y, w, h = det['region']
                click_pos = (x + w//2, y + h + 25)
                
                valid_targets.append({
                    'click_pos': click_pos,
                    'center': center,
                    'distance': det['distance_from_center'],
                    'detection': det
                })
            
            # SORT BY DISTANCE FROM CENTER (closest first)
            valid_targets.sort(key=lambda t: t['distance'])
            
            self.logger.info(f"→ Valid targets (after cache): {len(valid_targets)}")
            
            if valid_targets:
                self.logger.info(f"→ Target priority (closest to farthest):")
                for i, target in enumerate(valid_targets[:5], 1):
                    dist = int(target['distance'])
                    self.logger.info(f"   #{i}: Distance={dist}px from center")
            
            # Verify and attack (max per cycle)
            confirmed_mobs = []
            for i, target in enumerate(valid_targets[:Config.MAX_TARGETS_PER_CYCLE], 1):
                self.logger.info(f"\n  Verifying target #{i} (D={int(target['distance'])}px)...")
                
                # Click and read nameplate
                info = self.nameplate_reader.click_and_read(target['click_pos'])
                
                if info is None:
                    self.logger.info(f"    ✗ No valid nameplate or is a pet")
                    continue

                if info.get('is_pet'):
                    self.logger.info(f"    ✗ Filtered: PET (no class icon)")
                    continue

                if not info.get('class'):
                    self.logger.info(f"    ✗ No class detected")
                    continue

                # Check if alive
                if not info.get('is_alive'):
                    self.logger.info(f"    ✗ Mob already DEAD")
                    # Mark as target selected even for dead/unreachable mobs
                    # This allows Scenario 2 to trigger if repeatedly clicking same unreachable mob
                    self.stuck_detector.set_target_status(True)
                    continue

                # Valid mob!
                self.logger.info(f"    ✓ {info['class']} | Status: ALIVE")
                confirmed_mobs.append(info)

                # Update stuck detector: target selected
                self.stuck_detector.set_target_status(True)

                # Attack immediately (closest first strategy)
                if self.combat.engage(info):
                    # Combat successful - reset stuck timer (progress made)
                    self.stuck_detector.reset_timer()
                    self.stuck_detector.set_target_status(False)
                    # Record kill for Scenario 1 timer
                    self.stuck_detector.on_kill()
                else:
                    # Combat failed - mob might be unreachable (stuck scenario)
                    # Keep target_selected=True so Scenario 2 can trigger
                    self.logger.debug(f"    Combat failed - mob may be unreachable")
                    pass
            
            # Update overlay
            self.update_overlay(screenshot, detections, len(valid_targets), len(confirmed_mobs))

            # Save periodic screenshots for debugging
            if Config.SAVE_PERIODIC_SCREENSHOTS and self.cycle % Config.PERIODIC_SCREENSHOT_INTERVAL == 0:
                self.save_screenshot(screenshot, "CYCLE", f"cycle_{self.cycle}")

        except Exception as e:
            self.logger.error(f"❌ CYCLE ERROR: {e}")
            self.logger.error(f"Cycle #{self.cycle} failed")
            self.logger.error(traceback.format_exc())

            # Save error screenshot
            if Config.SAVE_ERROR_SCREENSHOTS:
                try:
                    self.save_screenshot(screenshot, "ERROR", f"cycle_{self.cycle}_error")
                except:
                    pass
    
    def update_overlay(self, screenshot, detections, valid_count, confirmed_count):
        """Update overlay with current stats"""
        status = "⏸️ PAUSED" if self.paused else "▶️ RUNNING"
        stats = {
            'Status': status,
            'Cycle': self.cycle,
            'Detected': len(detections),
            'Valid': valid_count,
            'Confirmed': confirmed_count,
            'Clicks': self.nameplate_reader.click_count,
            'Mobs': self.nameplate_reader.verified_mobs,
            'Pets': self.nameplate_reader.filtered_pets,
            'Kills': self.combat.total_kills,
            'Deaths': self.death_detector.death_count,
            'Stuck_Recoveries': self.stuck_detector.stuck_recoveries,
            'Early_Stops': self.combat.early_stops,
            'Cache': f"{len(self.cache.cache)}",
            'Next_Buffer': f"{int(self.buffer.get_time_until_next())}s",
            'Uptime': f"{int(time.time() - self.start_time)}s"
        }
        self.overlay.update(screenshot, detections, stats)
    
    def print_statistics(self):
        """Print final statistics with enhanced metrics"""
        uptime = int(time.time() - self.start_time)
        cache_stats = self.cache.get_stats()

        self.logger.info("\n" + "="*70)
        self.logger.info("📊 FINAL STATISTICS")
        self.logger.info("="*70)

        # Session Info
        self.logger.info(f"📁 Log Directory: {self.log_dir}")
        self.logger.info(f"⏱️  Uptime: {uptime}s ({uptime//60}m {uptime%60}s)")
        self.logger.info(f"🔄 Total Cycles: {self.cycle}")
        self.logger.info(f"📸 Screenshots Saved: {self.screenshot_counter}")
        self.logger.info("")

        # Detection Stats
        self.logger.info("🔍 Detection:")
        self.logger.info(f"   Total Clicks: {self.nameplate_reader.click_count}")
        self.logger.info(f"   Verified Mobs: {self.nameplate_reader.verified_mobs}")
        self.logger.info(f"   Filtered Pets: {self.nameplate_reader.filtered_pets}")
        pet_rate = (self.nameplate_reader.filtered_pets / self.nameplate_reader.click_count * 100) if self.nameplate_reader.click_count > 0 else 0
        self.logger.info(f"   Pet Filter Rate: {pet_rate:.1f}%")
        self.logger.info("")

        # Combat Stats
        self.logger.info("⚔️  Combat:")
        self.logger.info(f"   Total Kills: {self.combat.total_kills}")
        self.logger.info(f"   Deaths: {self.death_detector.death_count}")
        self.logger.info(f"   Early Stops: {self.combat.early_stops}")
        self.logger.info(f"   Skills Used: {self.combat.skills_used}")
        avg_skills = self.combat.skills_used / self.combat.total_kills if self.combat.total_kills > 0 else 0
        self.logger.info(f"   Avg Skills/Kill: {avg_skills:.1f}")
        kills_per_hour = (self.combat.total_kills / uptime * 3600) if uptime > 0 else 0
        self.logger.info(f"   Kills/Hour: {kills_per_hour:.1f}")
        self.logger.info("")

        # System Stats
        self.logger.info("⚙️  System:")
        self.logger.info(f"   Buffer Sequences: {self.buffer.total_buffs}")
        self.logger.info(f"   Stuck Recoveries: {self.stuck_detector.stuck_recoveries}")
        self.logger.info(f"   Cache Hit Rate: {cache_stats['hit_rate']:.1f}%")
        self.logger.info(f"   Cache Size: {len(self.cache.cache)} entries")
        self.logger.info("")

        # Efficiency Metrics
        if self.cycle > 0:
            avg_cycle_time = uptime / self.cycle
            self.logger.info("📈 Efficiency:")
            self.logger.info(f"   Avg Cycle Time: {avg_cycle_time:.2f}s")
            clicks_per_cycle = self.nameplate_reader.click_count / self.cycle
            self.logger.info(f"   Avg Clicks/Cycle: {clicks_per_cycle:.1f}")
            kills_per_cycle = self.combat.total_kills / self.cycle
            self.logger.info(f"   Avg Kills/Cycle: {kills_per_cycle:.2f}")

        self.logger.info("="*70)


# ============================================================================
# ENTRY POINT
# ============================================================================

def main():
    """Entry point"""
    print("""
╔═══════════════════════════════════════════════════════╗
║                                                       ║
║     MOB HUNTER v3.0 - FINAL OPTIMIZED VERSION        ║
║                                                       ║
║   ✅ Center-Out Targeting (closest first)           ║
║   ✅ Binary Health (ALIVE/DEAD only)                ║
║   ✅ Pet Filter (via nameplate class)               ║
║   ✅ Health Check Every 1 Second                    ║
║   ✅ Stop Rotation When Mob Dies                    ║
║   ✅ Continue Scanning Always                       ║
║                                                       ║
╚═══════════════════════════════════════════════════════╝
Controls:
• CapsLock = Start bot / Pause/Resume
• Ctrl+C = Stop bot

Waiting for CapsLock to start...
""")

    # Start keyboard listener
    print("Starting global keyboard listener...")
    listener = start_keyboard_listener()
    time.sleep(0.5)

    # Wait for CapsLock to be pressed to start
    print("Press CapsLock to start the bot...")
    while True:
        if check_capslock_toggle():
            break
        time.sleep(0.1)

    print("Bot starting...\n")
    time.sleep(0.5)

    bot = MobHunter()
    bot.run()


if __name__ == "__main__":
    main()