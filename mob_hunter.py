"""
MOB HUNTER v3.0 - FINAL OPTIMIZED VERSION
Center-out targeting + Binary health detection + Pet filtering via nameplate
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

# Disable PyAutoGUI fail-safe
pyautogui.FAILSAFE = False

# CapsLock detection for Windows
VK_CAPITAL = 0x14
user32 = ctypes.windll.user32

def is_capslock_on():
    """Check if CapsLock is currently on"""
    return bool(user32.GetKeyState(VK_CAPITAL) & 0x0001)

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
    MAX_TARGETS_PER_CYCLE = 3  # Max verifications per cycle
    CYCLE_DELAY = 0.4          # Seconds between cycles
    NAMEPLATE_TIMEOUT = 1.0    # Nameplate wait time
    CLICK_DELAY = 0.25         # Delay after clicking
    HEALTH_CHECK_INTERVAL = 1.0  # Check health every 1 second during combat
    
    # Cache settings
    POSITION_CACHE_DURATION = 2.5
    POSITION_PROXIMITY = 35
    
    # Priority system (only used for tie-breaking at same distance)
    CLASS_PRIORITIES = {
        'Unique': 1,
        'Champion': 2,
        'Giant': 3,
        'General': 4,
        'Elite': 5,
    }
    
    # Combat rotation
    SKILL_KEYS = ['1', '2', '3', '4']
    SKILL_ANIMATION_TIME = 0.6  # Time for skill animation
    
    # Overlay settings
    SHOW_OVERLAY = True
    OVERLAY_UPDATE_FPS = 10
    
    # Debug
    DEBUG_MODE = True
    SAVE_SCREENSHOTS = False


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
    """Fast screen capture"""
    
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
        """
        # Convert to HSV
        hsv = cv2.cvtColor(nameplate, cv2.COLOR_BGR2HSV)
        
        # Check for golden/yellow colors (elite/unique)
        yellow_lower = np.array([20, 100, 100])
        yellow_upper = np.array([30, 255, 255])
        yellow_mask = cv2.inRange(hsv, yellow_lower, yellow_upper)
        yellow_pixels = cv2.countNonZero(yellow_mask)
        
        # Check for purple colors (champion)
        purple_lower = np.array([130, 100, 100])
        purple_upper = np.array([160, 255, 255])
        purple_mask = cv2.inRange(hsv, purple_lower, purple_upper)
        purple_pixels = cv2.countNonZero(purple_mask)
        
        # Check for red colors (boss/unique)
        red_lower1 = np.array([0, 100, 100])
        red_upper1 = np.array([10, 255, 255])
        red_lower2 = np.array([170, 100, 100])
        red_upper2 = np.array([180, 255, 255])
        red_mask1 = cv2.inRange(hsv, red_lower1, red_upper1)
        red_mask2 = cv2.inRange(hsv, red_lower2, red_upper2)
        red_pixels = cv2.countNonZero(red_mask1) + cv2.countNonZero(red_mask2)
        
        # Classify based on color
        # If no significant colored pixels, it's likely a pet (no class icon)
        total_class_pixels = yellow_pixels + purple_pixels
        
        if total_class_pixels < 30:
            # Not enough colored pixels = no class icon = pet
            return None
        
        if yellow_pixels > 50:
            return 'Elite'
        elif purple_pixels > 50:
            return 'Champion'
        elif red_pixels > 100:
            return 'Unique'
        else:
            return 'General'  # Default for mobs with class
    
    def is_mob_alive(self, nameplate=None):
        """
        Binary health detection: ALIVE or DEAD
        Returns True if red pixels exist (alive), False otherwise (dead)
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
            
            # Binary decision: more than threshold = ALIVE
            is_alive = red_pixels > Config.RED_PIXEL_THRESHOLD
            
            self.logger.debug(f"    Health check: {red_pixels} red pixels -> {'ALIVE' if is_alive else 'DEAD'}")
            
            return is_alive
            
        except Exception as e:
            self.logger.error(f"Health check error: {e}")
            return True  # Assume alive on error to be safe


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
        Returns True if mob was killed, False otherwise
        """
        try:
            mob_class = target_info.get('class', 'Unknown')
            
            self.logger.info(f"\n{'>'*60}")
            self.logger.info(f"⚔️  ENGAGING: {mob_class}")
            self.logger.info(f"{'>'*60}")
            
            # Initial health check
            if not self.nameplate_reader.is_mob_alive():
                self.logger.info("✗ Mob already dead, skipping")
                return False
            
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
                
                # Check if mob still alive
                if not self.nameplate_reader.is_mob_alive():
                    self.logger.info(f"  ✓ Mob DEAD after skill {i}!")
                    self.total_kills += 1
                    self.early_stops += 1
                    self.logger.info(f"{'<'*60}")
                    self.logger.info(f"💀 Total kills: {self.total_kills} | Skills saved: {4-i}")
                    self.logger.info(f"{'<'*60}\n")
                    return True
            
            # Rotation complete
            self.logger.info(f"  ℹ️  Rotation complete (mob status unknown)")
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
    """Display detection overlay"""
    
    def __init__(self, logger):
        self.logger = logger
        self.running = False
        self.current_frame = None
        self.detections = []
        self.stats = {}
        self.thread = None
    
    def start(self):
        """Start overlay in separate thread"""
        if Config.SHOW_OVERLAY:
            self.running = True
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
    
    def stop(self):
        """Stop overlay"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
    
    def update(self, frame, detections, stats):
        """Update overlay data"""
        self.current_frame = frame.copy() if frame is not None else None
        self.detections = detections
        self.stats = stats
    
    def _run(self):
        """Overlay loop"""
        while self.running:
            try:
                if self.current_frame is not None:
                    display = self.current_frame.copy()
                    
                    # Draw screen center crosshair
                    center_x = Config.SCREEN_WIDTH // 2
                    center_y = Config.SCREEN_HEIGHT // 2
                    cv2.line(display, (center_x - 30, center_y), (center_x + 30, center_y), (255, 255, 0), 2)
                    cv2.line(display, (center_x, center_y - 30), (center_x, center_y + 30), (255, 255, 0), 2)
                    cv2.circle(display, (center_x, center_y), 100, (255, 255, 0), 1)
                    
                    # Draw detections with distance indicators
                    for i, det in enumerate(self.detections, 1):
                        x, y, w, h = det['region']
                        center = det['center']
                        distance = det.get('distance_from_center', 0)
                        
                        # Color based on distance (green = close, red = far)
                        color_intensity = min(255, int(distance / 3))
                        color = (0, 255 - color_intensity, color_intensity)
                        
                        # Draw box
                        cv2.rectangle(display, (x, y), (x+w, y+h), color, 2)
                        
                        # Draw center dot
                        cv2.circle(display, center, 5, (0, 0, 255), -1)
                        
                        # Draw line to center
                        cv2.line(display, center, (center_x, center_y), (100, 100, 100), 1)
                        
                        # Draw distance text
                        dist_text = f"#{i} D:{int(distance)}"
                        cv2.putText(display, dist_text, (x, y - 5), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
                    
                    # Draw stats
                    y_pos = 30
                    for key, value in self.stats.items():
                        text = f"{key}: {value}"
                        # Color based on status
                        if key == 'Status' and 'PAUSED' in str(value):
                            text_color = (0, 165, 255)  # Orange for paused
                        else:
                            text_color = (0, 255, 0)  # Green for normal
                        
                        # Black outline
                        cv2.putText(display, text, (12, y_pos + 2), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3)
                        # Colored text
                        cv2.putText(display, text, (10, y_pos), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, text_color, 2)
                        y_pos += 30
                    
                    # Draw large PAUSED overlay if paused
                    if 'Status' in self.stats and 'PAUSED' in str(self.stats.get('Status', '')):
                        # Semi-transparent overlay
                        overlay = display.copy()
                        cv2.rectangle(overlay, (0, 0), (display.shape[1], display.shape[0]), (0, 0, 0), -1)
                        display = cv2.addWeighted(display, 0.7, overlay, 0.3, 0)
                        
                        # Large PAUSED text
                        text = "PAUSED"
                        font_scale = 3
                        thickness = 5
                        (text_width, text_height), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
                        text_x = (display.shape[1] - text_width) // 2
                        text_y = (display.shape[0] + text_height) // 2
                        
                        # Black outline
                        cv2.putText(display, text, (text_x + 2, text_y + 2), 
                                   cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), thickness + 2)
                        # Orange text
                        cv2.putText(display, text, (text_x, text_y), 
                                   cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 165, 255), thickness)
                    
                    # Show
                    cv2.imshow('MOB HUNTER v3.0 - Detection Overlay', display)
                    cv2.waitKey(1)
                
                time.sleep(1.0 / Config.OVERLAY_UPDATE_FPS)
                
            except Exception as e:
                self.logger.error(f"Overlay error: {e}")
                break
        
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
        self.overlay = OverlayWindow(self.logger)
        
        self.cycle = 0
        self.running = True
        self.paused = False
        self.start_time = time.time()
        self.last_capslock_state = False
    
    def run(self):
        """Main loop"""
        self.logger.info("\n🚀 Bot started! Press Ctrl+C to stop.\n")
        self.logger.info("💡 Controls: CapsLock = Pause/Resume\n")
        
        # Start overlay
        self.overlay.start()
        
        try:
            while self.running:
                # Check CapsLock for pause/resume
                caps_state = is_capslock_on()
                
                # Toggle pause on CapsLock press (edge detection)
                if caps_state and not self.last_capslock_state:
                    self.paused = not self.paused
                    if self.paused:
                        self.logger.info("\n⏸️  PAUSED - Press CapsLock to resume\n")
                    else:
                        self.logger.info("\n▶️  RESUMED - Press CapsLock to pause\n")
                
                self.last_capslock_state = caps_state
                
                # Skip cycle if paused, but update overlay
                if self.paused:
                    # Update overlay with paused state
                    screenshot = self.screen_capture.capture()
                    self.update_overlay(screenshot, [], 0, 0)
                    time.sleep(0.1)  # Short sleep when paused
                    continue
                
                self.cycle += 1
                self.run_cycle()
                time.sleep(Config.CYCLE_DELAY)
                
        except KeyboardInterrupt:
            self.logger.info("\n\n⛔ Bot stopped by user")
        except Exception as e:
            self.logger.error(f"\n💥 FATAL ERROR: {e}")
            self.logger.error(traceback.format_exc())
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
            
            # Detect all floating names
            detections = self.detector.find_floating_names(screenshot)
            self.logger.info(f"Detected: {len(detections)} floating names")
            
            if not detections:
                self.logger.info("→ No floating names found")
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
                    continue
                
                # Valid mob!
                self.logger.info(f"    ✓ {info['class']} | Status: ALIVE")
                confirmed_mobs.append(info)
                
                # Attack immediately (closest first strategy)
                self.combat.engage(info)
            
            # Update overlay
            self.update_overlay(screenshot, detections, len(valid_targets), len(confirmed_mobs))
            
            # Save screenshot occasionally
            if Config.SAVE_SCREENSHOTS and self.cycle % 10 == 0:
                cv2.imwrite(f"{self.log_dir}/screenshots/cycle_{self.cycle:04d}.png", screenshot)
            
        except Exception as e:
            self.logger.error(f"Cycle error: {e}")
            self.logger.error(traceback.format_exc())
    
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
            'Early_Stops': self.combat.early_stops,
            'Cache': f"{len(self.cache.cache)}",
            'Uptime': f"{int(time.time() - self.start_time)}s"
        }
        self.overlay.update(screenshot, detections, stats)
    
    def print_statistics(self):
        """Print final statistics"""
        uptime = int(time.time() - self.start_time)
        cache_stats = self.cache.get_stats()
        
        self.logger.info("\n" + "="*70)
        self.logger.info("FINAL STATISTICS")
        self.logger.info("="*70)
        self.logger.info(f"Total Cycles: {self.cycle}")
        self.logger.info(f"Total Clicks: {self.nameplate_reader.click_count}")
        self.logger.info(f"Verified Mobs: {self.nameplate_reader.verified_mobs}")
        self.logger.info(f"Filtered Pets: {self.nameplate_reader.filtered_pets}")
        self.logger.info(f"Total Kills: {self.combat.total_kills}")
        self.logger.info(f"Early Stops: {self.combat.early_stops} (stopped rotation early due to death)")
        self.logger.info(f"Skills Used: {self.combat.skills_used}")
        self.logger.info(f"Avg Skills/Kill: {self.combat.skills_used/self.combat.total_kills:.1f}" if self.combat.total_kills > 0 else "N/A")
        self.logger.info(f"Uptime: {uptime}s ({uptime//60}m {uptime%60}s)")
        self.logger.info(f"Cache Hit Rate: {cache_stats['hit_rate']:.1f}%")
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

    # Wait for CapsLock to be pressed to start
    print("Press CapsLock to start the bot...")
    while not is_capslock_on():
        time.sleep(0.1)
    
    # Wait for CapsLock to be released
    while is_capslock_on():
        time.sleep(0.1)
    
    print("Bot starting...\n")
    time.sleep(0.5)

    bot = MobHunter()
    bot.run()


if __name__ == "__main__":
    main()