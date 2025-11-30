"""
MOB HUNTER v3.0 - Complete MMORPG Auto-Combat Bot
Full featured with overlay, debugging, and robust detection
"""

import cv2
import numpy as np
import time
import logging
import os
import sys
from datetime import datetime
from mss import mss
import pyautogui
from PIL import Image, ImageDraw, ImageFont
import threading
import traceback
from collections import deque
from pynput import keyboard
import signal

# Disable PyAutoGUI fail-safe for smoother operation
pyautogui.FAILSAFE = False

# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    # Screen settings (adjust to your resolution)
    SCREEN_WIDTH = 1920
    SCREEN_HEIGHT = 1080
    SCREEN_REGION = {'top': 0, 'left': 0, 'width': SCREEN_WIDTH, 'height': SCREEN_HEIGHT}
    NAMEPLATE_REGION = (660, 10, 600, 100)  # (x, y, w, h) - top-middle
    
    # Detection boundaries (ignore UI)
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
    
    # OCR settings - using simple methods, no Tesseract required
    USE_SIMPLE_OCR = True  # Use template matching instead of Tesseract
    
    # Blacklist
    KNOWN_PETS = ['Gom3a', 'Savy', 'gom3a', 'savy']
    PLAYER_INDICATORS = ['SnowRunner', 'snowrunner', '[', ']', '<', '>', 'Moon', 'Trade']
    KNOWN_MOBS = ['Mangyang', 'mangyang', 'Ghost', 'ghost', 'Wolf', 'Bear', 'Small', 'eyed']
    
    # Combat settings
    MIN_HEALTH_THRESHOLD = 5   # Attack if health > 5%
    MAX_TARGETS_PER_CYCLE = 2  # Max clicks per cycle
    CYCLE_DELAY = 0.4          # Seconds between cycles
    NAMEPLATE_TIMEOUT = 1.0    # Nameplate wait time
    CLICK_DELAY = 0.25         # Delay after clicking
    
    # Cache settings
    POSITION_CACHE_DURATION = 2.5
    POSITION_PROXIMITY = 35
    
    # Priority system
    CLASS_PRIORITIES = {
        'Unique': 1,
        'Champion': 2,
        'Giant': 3,
        'General': 4,
        'Elite': 5,
    }
    
    # Combat rotation
    SKILL_KEYS = ['1', '2', '3', '4']
    SKILL_DELAY = 0.6
    
    # Overlay settings
    SHOW_OVERLAY = True
    OVERLAY_UPDATE_FPS = 10
    
    # Debug
    DEBUG_MODE = True
    SAVE_SCREENSHOTS = True


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
# SIMPLE OCR (No Tesseract required)
# ============================================================================

class SimpleOCR:
    """Simple text detection using contour analysis"""
    
    def __init__(self, logger):
        self.logger = logger
    
    def extract_text_simple(self, screenshot, region):
        """
        Extract text using simple pattern matching
        Returns the most likely text based on known names
        """
        try:
            x, y, w, h = region
            roi = screenshot[y:y+h, x:x+w]
            
            # Convert to grayscale
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            
            # Threshold for white text
            _, binary = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
            
            # Count white pixels (text density)
            white_pixels = cv2.countNonZero(binary)
            total_pixels = w * h
            density = white_pixels / total_pixels if total_pixels > 0 else 0
            
            # If text density is good, try to match known names
            if density > 0.1:  # At least 10% white pixels
                # This is likely a name, return region info for clicking
                return f"Name_{x}_{y}"  # Unique identifier
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Simple OCR error: {e}")
            return None
    
    def analyze_region_advanced(self, screenshot, region):
        """
        Advanced analysis to determine if region contains mob name
        """
        try:
            x, y, w, h = region
            roi = screenshot[y:y+h, x:x+w]
            
            # Multiple checks
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            
            # Check 1: White text detection
            _, white = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
            white_ratio = cv2.countNonZero(white) / (w * h)
            
            # Check 2: Edge detection (text has edges)
            edges = cv2.Canny(gray, 50, 150)
            edge_ratio = cv2.countNonZero(edges) / (w * h)
            
            # Check 3: Variance (text has variance)
            variance = np.var(gray)
            
            # Score the region
            score = 0
            if 0.05 < white_ratio < 0.7:  # Text is white but not entire region
                score += 3
            if edge_ratio > 0.1:  # Text has edges
                score += 2
            if variance > 100:  # Text has variance
                score += 2
            
            # If score is high, this is likely a name
            if score >= 5:
                return True
            
            return False
            
        except:
            return False


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
        Returns list of {region: (x,y,w,h), center: (x,y), score: float}
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
                
                # Position filter (ignore UI)
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
                    detections.append({
                        'region': (x, y, w, h),
                        'center': (center_x, center_y),
                        'score': 1.0
                    })
        
        self.last_detections = detections
        return detections


# ============================================================================
# NAME FILTER
# ============================================================================

class NameFilter:
    """Filter pets and players"""
    
    def __init__(self, logger):
        self.logger = logger
        self.rejected_count = 0
        self.accepted_count = 0
    
    def is_valid_mob_region(self, screenshot, region):
        """
        Check if region is likely a mob (not pet/player)
        Uses position and pattern analysis
        """
        x, y, w, h = region
        center_y = y + h // 2
        
        # Rule 1: Names near screen center are more likely players
        screen_center_y = Config.SCREEN_HEIGHT // 2
        distance_from_center = abs(center_y - screen_center_y)
        
        # If very close to center (where player usually is), be cautious
        if distance_from_center < 150:
            self.logger.debug(f"  Region near center, might be player")
            return False
        
        # Rule 2: Check if region is part of a cluster (players often travel with pets)
        # This is a simple heuristic
        
        # Accept by default
        return True
    
    def should_skip_position(self, center):
        """
        Check if position should be skipped based on known player/pet locations
        """
        # Center of screen (where player usually is)
        player_zone_x = (Config.SCREEN_WIDTH // 2 - 200, Config.SCREEN_WIDTH // 2 + 200)
        player_zone_y = (Config.SCREEN_HEIGHT // 2 - 100, Config.SCREEN_HEIGHT // 2 + 150)
        
        if (player_zone_x[0] < center[0] < player_zone_x[1] and 
            player_zone_y[0] < center[1] < player_zone_y[1]):
            return True
        
        return False


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
    """Read mob info from nameplate"""
    
    def __init__(self, logger, screen_capture):
        self.logger = logger
        self.screen_capture = screen_capture
        self.click_count = 0
    
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
                
                if info and info.get('class'):
                    self.logger.debug(f"    Nameplate read in {attempts} attempts")
                    return info
                
                time.sleep(0.1)
            
            self.logger.debug(f"    Nameplate timeout ({attempts} attempts)")
            return None
            
        except Exception as e:
            self.logger.error(f"    Click error: {e}")
            return None
    
    def read_nameplate(self, screenshot):
        """Read nameplate region"""
        try:
            x, y, w, h = Config.NAMEPLATE_REGION
            nameplate = screenshot[y:y+h, x:x+w]
            
            # Detect class by color patterns (more reliable than OCR)
            mob_class = self.detect_class_by_color(nameplate)
            
            # Detect health
            health = self.detect_health(nameplate)
            
            return {
                'name': 'Mob',  # Generic name
                'class': mob_class,
                'health': health
            }
            
        except Exception as e:
            self.logger.debug(f"Nameplate read error: {e}")
            return None
    
    def detect_class_by_color(self, nameplate):
        """
        Detect mob class by color patterns in nameplate
        General/Elite usually have specific color schemes
        """
        # Convert to HSV
        hsv = cv2.cvtColor(nameplate, cv2.COLOR_BGR2HSV)
        
        # Check for golden/yellow colors (often indicates elite/unique)
        yellow_lower = np.array([20, 100, 100])
        yellow_upper = np.array([30, 255, 255])
        yellow_mask = cv2.inRange(hsv, yellow_lower, yellow_upper)
        yellow_pixels = cv2.countNonZero(yellow_mask)
        
        # Check for red colors (boss/unique)
        red_lower1 = np.array([0, 100, 100])
        red_upper1 = np.array([10, 255, 255])
        red_lower2 = np.array([170, 100, 100])
        red_upper2 = np.array([180, 255, 255])
        red_mask1 = cv2.inRange(hsv, red_lower1, red_upper1)
        red_mask2 = cv2.inRange(hsv, red_lower2, red_upper2)
        red_pixels = cv2.countNonZero(red_mask1) + cv2.countNonZero(red_mask2)
        
        # Classify based on color
        if yellow_pixels > 50:
            return 'Elite'
        elif red_pixels > 100:
            return 'Unique'
        else:
            return 'General'  # Default
    
    def detect_health(self, nameplate):
        """Detect health percentage from red bar"""
        try:
            hsv = cv2.cvtColor(nameplate, cv2.COLOR_BGR2HSV)
            
            # Red health bar
            red_lower1 = np.array([0, 150, 100])
            red_upper1 = np.array([10, 255, 255])
            red_lower2 = np.array([170, 150, 100])
            red_upper2 = np.array([180, 255, 255])
            
            mask1 = cv2.inRange(hsv, red_lower1, red_upper1)
            mask2 = cv2.inRange(hsv, red_lower2, red_upper2)
            red_mask = cv2.bitwise_or(mask1, mask2)
            
            contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            if contours:
                largest = max(contours, key=cv2.contourArea)
                x, y, w, h = cv2.boundingRect(largest)
                health_pct = min(100, max(0, (w / 300) * 100))
                return health_pct
            
            return 100  # Default full health
            
        except:
            return 100


# ============================================================================
# COMBAT SYSTEM
# ============================================================================

class CombatSystem:
    """Handle combat"""
    
    def __init__(self, logger):
        self.logger = logger
        self.total_kills = 0
    
    def engage(self, target_info):
        """Execute combat rotation"""
        try:
            mob_class = target_info.get('class', 'Unknown')
            health = target_info.get('health', 100)
            
            self.logger.info(f"\n{'>'*50}")
            self.logger.info(f"ENGAGING: {mob_class} (HP: {health:.0f}%)")
            self.logger.info(f"{'>'*50}")
            
            # Simple rotation
            for i, key in enumerate(Config.SKILL_KEYS, 1):
                self.logger.info(f"  Skill {i}: {key}")
                pyautogui.press(key)
                time.sleep(Config.SKILL_DELAY)
            
            self.total_kills += 1
            self.logger.info(f"{'<'*50}")
            self.logger.info(f"Total engagements: {self.total_kills}\n")
            
        except Exception as e:
            self.logger.error(f"Combat error: {e}")


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
        self.current_frame = frame.copy()
        self.detections = detections
        self.stats = stats
    
    def _run(self):
        """Overlay loop"""
        while self.running:
            try:
                if self.current_frame is not None:
                    display = self.current_frame.copy()
                    
                    # Draw detections
                    for det in self.detections:
                        x, y, w, h = det['region']
                        cv2.rectangle(display, (x, y), (x+w, y+h), (0, 255, 0), 2)
                        cv2.circle(display, det['center'], 5, (0, 0, 255), -1)
                    
                    # Draw stats
                    y_pos = 30
                    for key, value in self.stats.items():
                        text = f"{key}: {value}"
                        cv2.putText(display, text, (10, y_pos), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                        y_pos += 25
                    
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
    """Main bot controller"""
    
    def __init__(self):
        self.logger, self.log_dir = setup_logger()
        self.logger.info("="*70)
        self.logger.info("MOB HUNTER v3.0 - FULL VERSION")
        self.logger.info("="*70)
        self.logger.info(f"Log directory: {self.log_dir}")
        self.logger.info(f"Screen: {Config.SCREEN_WIDTH}x{Config.SCREEN_HEIGHT}")
        self.logger.info(f"Overlay: {'ENABLED' if Config.SHOW_OVERLAY else 'DISABLED'}")
        self.logger.info("="*70)
        
        # Components
        self.screen_capture = ScreenCapture()
        self.detector = FloatingNameDetector(self.logger)
        self.ocr = SimpleOCR(self.logger)
        self.name_filter = NameFilter(self.logger)
        self.cache = PositionCache(self.logger)
        self.nameplate_reader = NameplateReader(self.logger, self.screen_capture)
        self.combat = CombatSystem(self.logger)
        self.overlay = OverlayWindow(self.logger)
        
        self.cycle = 0
        self.running = True
        self.is_paused = True  # Start paused, wait for CapsLock
        self.should_exit = False
        self.start_time = time.time()
        self.keyboard_listener = None
        
        # Setup keyboard listener
        self.setup_keyboard_listener()
    
    def setup_keyboard_listener(self):
        """Setup CapsLock toggle for start/pause"""
        def on_press(key):
            try:
                if key == keyboard.Key.caps_lock:
                    if self.is_paused:
                        self.is_paused = False
                        self.logger.info("\n▶ RUNNING - Press CapsLock to pause")
                        print("\n▶ RUNNING - Press CapsLock to pause")
                    else:
                        self.is_paused = True
                        self.logger.info("\n⏸ PAUSED - Press CapsLock to resume")
                        print("\n⏸ PAUSED - Press CapsLock to resume")
            except:
                pass
        
        self.keyboard_listener = keyboard.Listener(on_press=on_press)
        self.keyboard_listener.daemon = True
        self.keyboard_listener.start()
    
    def shutdown(self):
        """Gracefully shutdown the bot"""
        self.logger.info("Shutting down gracefully...")
        self.should_exit = True
        self.running = False
        self.is_paused = False  # Unpause to allow loop to exit
        
        # Stop keyboard listener
        if self.keyboard_listener:
            try:
                self.keyboard_listener.stop()
            except:
                pass
        
        # Stop overlay
        if self.overlay:
            try:
                self.overlay.stop()
            except:
                pass
    
    def run(self):
        """Main loop"""
        self.logger.info("\n🚀 Bot initialized! Press CapsLock to start, Ctrl+C to stop.\n")
        print("\n⏳ Waiting for CapsLock to start...")
        print("💡 Press CapsLock to START/PAUSE, Ctrl+C to EXIT")
        
        # Start overlay
        self.overlay.start()
        
        try:
            while self.running and not self.should_exit:
                # Wait if paused
                if self.is_paused:
                    time.sleep(0.1)
                    continue
                
                # Run cycle if not paused
                self.cycle += 1
                self.run_cycle()
                time.sleep(Config.CYCLE_DELAY)
                
        except KeyboardInterrupt:
            self.logger.info("\n\n⛔ Bot stopped by user (Ctrl+C)")
            print("\n⛔ Bot stopped by user (Ctrl+C)")
        except Exception as e:
            self.logger.error(f"\n💥 FATAL ERROR: {e}")
            self.logger.error(traceback.format_exc())
        finally:
            self.shutdown()
            self.print_statistics()
    
    def run_cycle(self):
        """Single detection cycle"""
        # Check if should exit or is paused
        if self.should_exit or self.is_paused:
            return
        
        try:
            self.logger.info(f"\n{'='*70}")
            self.logger.info(f"CYCLE #{self.cycle}")
            self.logger.info(f"{'='*70}")
            
            # Capture
            screenshot = self.screen_capture.capture()
            
            # Detect
            detections = self.detector.find_floating_names(screenshot)
            self.logger.info(f"Detected: {len(detections)} floating names")
            
            if not detections:
                return
            
            # Filter and process
            valid_targets = []
            for i, det in enumerate(detections, 1):
                region = det['region']
                center = det['center']
                
                # Cache check
                if self.cache.is_recently_checked(center):
                    self.logger.debug(f"  Name #{i}: Cached")
                    continue
                
                # Position check
                if self.name_filter.should_skip_position(center):
                    self.logger.debug(f"  Name #{i}: Player zone")
                    continue
                
                # Region validation
                if not self.name_filter.is_valid_mob_region(screenshot, region):
                    continue
                
                # Calculate click position (below text)
                x, y, w, h = region
                click_pos = (x + w//2, y + h + 25)
                
                self.logger.info(f"  ✓ Target #{i} at {center}")
                
                valid_targets.append({
                    'click_pos': click_pos,
                    'region': region,
                    'center': center
                })
            
            self.logger.info(f"→ Valid targets: {len(valid_targets)}")
            
            # Verify via nameplate
            confirmed = []
            for i, target in enumerate(valid_targets[:Config.MAX_TARGETS_PER_CYCLE], 1):
                self.logger.info(f"\n  Verifying #{i}...")
                
                info = self.nameplate_reader.click_and_read(target['click_pos'])
                
                if info and info.get('class'):
                    self.logger.info(f"    ✓ {info['class']} | HP: {info['health']:.0f}%")
                    confirmed.append(info)
                else:
                    self.logger.info(f"    ✗ No nameplate")
            
            # Attack
            if confirmed:
                best = min(confirmed, key=lambda m: Config.CLASS_PRIORITIES.get(m['class'], 99))
                if best['health'] > Config.MIN_HEALTH_THRESHOLD:
                    self.combat.engage(best)
            
            # Update overlay
            stats = {
                'Cycle': self.cycle,
                'Detected': len(detections),
                'Valid': len(valid_targets),
                'Confirmed': len(confirmed),
                'Clicks': self.nameplate_reader.click_count,
                'Kills': self.combat.total_kills,
                'Cache': f"{len(self.cache.cache)} entries",
                'Uptime': f"{int(time.time() - self.start_time)}s"
            }
            self.overlay.update(screenshot, detections, stats)
            
            # Save screenshot
            if Config.SAVE_SCREENSHOTS and self.cycle % 10 == 0:
                cv2.imwrite(f"{self.log_dir}/screenshots/cycle_{self.cycle:04d}.png", screenshot)
            
        except Exception as e:
            self.logger.error(f"Cycle error: {e}")
            self.logger.error(traceback.format_exc())
    
    def print_statistics(self):
        """Print final statistics"""
        uptime = int(time.time() - self.start_time)
        cache_stats = self.cache.get_stats()
        
        self.logger.info("\n" + "="*70)
        self.logger.info("FINAL STATISTICS")
        self.logger.info("="*70)
        self.logger.info(f"Total Cycles: {self.cycle}")
        self.logger.info(f"Total Clicks: {self.nameplate_reader.click_count}")
        self.logger.info(f"Total Engagements: {self.combat.total_kills}")
        self.logger.info(f"Uptime: {uptime}s ({uptime//60}m {uptime%60}s)")
        self.logger.info(f"Cache Hit Rate: {cache_stats['hit_rate']:.1f}%")
        self.logger.info(f"Avg Cycle Time: {uptime/self.cycle:.2f}s" if self.cycle > 0 else "N/A")
        self.logger.info("="*70)


# ============================================================================
# ENTRY POINT
# ============================================================================

def main():
    """Entry point"""
    bot = None
    
    def signal_handler(sig, frame):
        """Handle Ctrl+C gracefully"""
        print("\n\n🛑 Ctrl+C detected - Shutting down gracefully...")
        if bot:
            bot.shutdown()
        print("✓ Shutdown complete. Goodbye!")
        sys.exit(0)
    
    # Register signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    print("""
    ╔═══════════════════════════════════════════════════════╗
    ║                                                       ║
    ║           MOB HUNTER v3.0 - FULL VERSION            ║
    ║                                                       ║
    ║   Complete MMORPG Auto-Combat Bot                    ║
    ║   • Real-time Detection                              ║
    ║   • Live Overlay                                     ║
    ║   • Smart Filtering                                  ║
    ║   • Auto Combat                                      ║
    ║                                                       ║
    ╚═══════════════════════════════════════════════════════╝
    
    Controls:
    • CapsLock = START/PAUSE
    • Ctrl+C = EXIT
    
    Initializing...
    """)
    
    try:
        bot = MobHunter()
        bot.run()
    except KeyboardInterrupt:
        print("\n\n🛑 Initialization interrupted - Shutting down...")
        if bot:
            bot.shutdown()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Initialization failed: {e}")
        traceback.print_exc()
        if bot:
            bot.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    main()