"""
MOB HUNTER v1.0 - Real-time Mob Detection and Combat Automation

A Python application for automated mob hunting in MMORPG games.
Uses computer vision and OCR to detect and engage enemies automatically.

USAGE:
1. Run: python mob_hunter.py
2. Press CapsLock to START detection and combat
3. Press CapsLock again to PAUSE (stops all actions immediately)
4. Press Ctrl+C to EXIT

REQUIREMENTS:
- Screen resolution: 1920x1080
- Game window must be visible and active
- Ensure game UI elements (nameplate, health bar) are visible

FEATURES:
- Automatic entity detection using edge detection
- OCR-based mob identification
- Automated combat with skill rotation
- Health monitoring for combat state
- Debug mode with visual overlays

Author: Auto-generated
Version: 1.0
"""

from pynput import keyboard
import threading
import mss
import cv2
import numpy as np
import pyautogui
import easyocr
import time
import random
import math

DEBUG = True  # Toggle debug mode


class MobHunter:
    def __init__(self):
        self.is_running = threading.Event()  # Start paused
        self.should_exit = False
        self.sct = mss.mss()
        self.monitor = {"top": 0, "left": 0, "width": 1920, "height": 1080}
        self.reader = easyocr.Reader(['en'], gpu=False)
        self.checked_positions = set()
        self.setup_keyboard_listener()
        pyautogui.PAUSE = 0
        pyautogui.FAILSAFE = False
        
        # Screen center for distance calculations
        self.screen_center = (960, 540)  # 1920x1080 center
        
        # Coordinate regions (scaled from 1280x720 to 1920x1080)
        # Nameplate region: y=45-105, x=780-1095
        self.nameplate_region = {
            "top": 45,
            "left": 780,
            "width": 315,  # 1095 - 780
            "height": 60   # 105 - 45
        }
        
        # Health bar region: y=67-83, x=833-1080
        self.health_region = {
            "top": 67,
            "left": 833,
            "width": 247,  # 1080 - 833
            "height": 16   # 83 - 67
        }
        
        # Detection parameters
        self.center_margin = 0.15  # 70% center = 15% margin on each side
        self.min_area = 1000
        self.max_area = 4000
        self.min_aspect = 1.5
        self.max_aspect = 3.0
        
        # Performance settings
        self.detection_fps = 12  # Target 10-15 FPS
        self.frame_delay = 1.0 / self.detection_fps
        self.health_check_interval = 0.2  # 200ms
        
        # State tracking
        self.current_action = "Scanning"
        self.entities_found = 0
        self.ocr_result = ""
        self.health_percentage = 0
        self.no_entity_count = 0
        
    def setup_keyboard_listener(self):
        """Setup CapsLock listener in daemon thread"""
        def on_press(key):
            try:
                if key == keyboard.Key.caps_lock:
                    if self.is_running.is_set():
                        self.is_running.clear()
                        print("\n⏸ PAUSED - Press CapsLock to resume")
                        self.current_action = "Paused"
                    else:
                        self.is_running.set()
                        print("\n▶ RUNNING - Press CapsLock to pause")
                        self.current_action = "Scanning"
            except Exception as e:
                print(f"Error in keyboard listener: {e}")
        
        listener = keyboard.Listener(on_press=on_press)
        listener.daemon = True
        listener.start()
    
    def capture_screen(self):
        """Capture screen using mss, return numpy array"""
        if not self.is_running.is_set():
            return None
        
        try:
            img = self.sct.grab(self.monitor)
            return np.array(img)
        except Exception as e:
            if DEBUG:
                print(f"Screen capture error: {e}")
            return None
    
    def detect_entities(self, frame):
        """
        Detect character-shaped entities using edge detection and contour analysis
        Returns list of (x, y) positions sorted by distance to screen center
        """
        if frame is None:
            return []
        
        try:
            # Convert to grayscale
            gray = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
            
            # Apply Canny edge detection
            edges = cv2.Canny(gray, 50, 150)
            
            # Find contours
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            entities = []
            center_x, center_y = self.screen_center
            
            # Calculate center region bounds (70% of screen)
            margin_x = int(1920 * self.center_margin)
            margin_y = int(1080 * self.center_margin)
            
            for contour in contours:
                # Calculate area
                area = cv2.contourArea(contour)
                if area < self.min_area or area > self.max_area:
                    continue
                
                # Get bounding rectangle
                x, y, w, h = cv2.boundingRect(contour)
                
                # Check if within center 70% of screen
                if (x < margin_x or x + w > 1920 - margin_x or
                    y < margin_y or y + h > 1080 - margin_y):
                    continue
                
                # Calculate aspect ratio (height/width)
                if w == 0:
                    continue
                aspect_ratio = h / w
                if aspect_ratio < self.min_aspect or aspect_ratio > self.max_aspect:
                    continue
                
                # Calculate center point of entity
                entity_x = x + w // 2
                entity_y = y + h // 2
                
                # Check if position was recently checked
                pos_key = (entity_x // 10, entity_y // 10)  # Round to avoid exact matches
                if pos_key in self.checked_positions:
                    continue
                
                # Calculate distance to screen center
                distance = math.sqrt((entity_x - center_x)**2 + (entity_y - center_y)**2)
                
                entities.append((entity_x, entity_y, distance, x, y, w, h))
            
            # Sort by distance to center (closest first)
            entities.sort(key=lambda e: e[2])
            
            # Return only (x, y) positions
            return [(e[0], e[1], e[3], e[4], e[5], e[6]) for e in entities]
            
        except Exception as e:
            if DEBUG:
                print(f"Entity detection error: {e}")
            return []
    
    def click_and_identify(self, position):
        """
        Click entity and identify if it's a mob using OCR
        Returns (is_mob: bool, text: str)
        """
        if not self.is_running.is_set():
            return False, ""
        
        x, y = position[0], position[1]
        
        # Add random offset ±5 pixels
        offset_x = random.randint(-5, 5)
        offset_y = random.randint(-5, 5)
        click_x = x + offset_x
        click_y = y + offset_y
        
        # Ensure coordinates are within screen bounds
        click_x = max(0, min(1919, click_x))
        click_y = max(0, min(1079, click_y))
        
        try:
            # Click the entity
            if not self.is_running.is_set():
                return False, ""
            
            pyautogui.click(click_x, click_y)
            
            # Wait for nameplate to appear
            time.sleep(0.15)
            
            if not self.is_running.is_set():
                return False, ""
            
            # Capture nameplate region
            frame = self.capture_screen()
            if frame is None:
                return False, ""
            
            # Extract nameplate region
            nameplate = frame[
                self.nameplate_region["top"]:self.nameplate_region["top"] + self.nameplate_region["height"],
                self.nameplate_region["left"]:self.nameplate_region["left"] + self.nameplate_region["width"]
            ]
            
            # Convert BGRA to RGB for OCR
            nameplate_rgb = cv2.cvtColor(nameplate, cv2.COLOR_BGRA2RGB)
            
            # Perform OCR
            try:
                results = self.reader.readtext(nameplate_rgb)
                text = " ".join([result[1] for result in results]).lower()
                
                # Check for mob keywords
                keywords = ["general", "champion", "giant", "lv"]
                is_mob = any(keyword in text for keyword in keywords)
                
                return is_mob, text
                
            except Exception as e:
                if DEBUG:
                    print(f"OCR error: {e}")
                return False, ""
                
        except Exception as e:
            if DEBUG:
                print(f"Click and identify error: {e}")
            return False, ""
    
    def get_health_percentage(self, frame):
        """
        Monitor health bar region and return percentage of red pixels
        Returns percentage (0-100)
        """
        if frame is None:
            return 0
        
        try:
            # Extract health bar region
            health_bar = frame[
                self.health_region["top"]:self.health_region["top"] + self.health_region["height"],
                self.health_region["left"]:self.health_region["left"] + self.health_region["width"]
            ]
            
            # Convert BGRA to BGR for easier processing
            health_bgr = cv2.cvtColor(health_bar, cv2.COLOR_BGRA2BGR)
            
            # Count red pixels: R > 150, G < 100, B < 100
            red_mask = ((health_bgr[:, :, 2] > 150) & 
                       (health_bgr[:, :, 1] < 100) & 
                       (health_bgr[:, :, 0] < 100))
            
            red_pixels = np.sum(red_mask)
            total_pixels = health_bgr.shape[0] * health_bgr.shape[1]
            
            if total_pixels == 0:
                return 0
            
            percentage = (red_pixels / total_pixels) * 100
            return percentage
            
        except Exception as e:
            if DEBUG:
                print(f"Health monitoring error: {e}")
            return 0
    
    def attack_sequence(self):
        """
        Execute attack sequence: 1,2,3,1,4,5 with random delays
        Returns True if completed, False if paused mid-sequence
        """
        keys = ['1', '2', '3', '1', '4', '5']
        
        for key in keys:
            if not self.is_running.is_set():
                return False  # Paused mid-sequence
            
            pyautogui.press(key)
            time.sleep(random.uniform(0.8, 1.2))
        
        return True
    
    def combat_loop(self, initial_health):
        """
        Combat loop: attack until health < 5% of baseline or paused
        Returns True if mob died, False if paused
        """
        if initial_health <= 0:
            initial_health = 1  # Avoid division by zero
        
        self.current_action = "Fighting"
        last_health_check = time.time()
        
        while self.is_running.is_set():
            # Check health periodically
            current_time = time.time()
            if current_time - last_health_check >= self.health_check_interval:
                frame = self.capture_screen()
                if frame is not None:
                    current_health = self.get_health_percentage(frame)
                    self.health_percentage = (current_health / initial_health) * 100 if initial_health > 0 else 0
                    
                    # Check if mob is dead (< 5% of baseline)
                    if current_health < (initial_health * 0.05):
                        self.current_action = "Mob Defeated"
                        return True
                
                last_health_check = current_time
            
            # Execute attack sequence
            if not self.attack_sequence():
                return False  # Paused
        
        return False  # Paused
    
    def draw_debug_overlay(self, frame, entities, current_entity_pos, ocr_text, health_pct):
        """Draw debug visualizations on frame"""
        if not DEBUG or frame is None:
            return frame
        
        try:
            overlay = frame.copy()
            
            # Draw green rectangles around detected entities
            for entity in entities:
                x, y, rect_x, rect_y, w, h = entity
                cv2.rectangle(overlay, (rect_x, rect_y), (rect_x + w, rect_y + h), (0, 255, 0), 2)
                cv2.circle(overlay, (x, y), 5, (0, 255, 0), -1)
            
            # Draw blue circle on entity being clicked
            if current_entity_pos:
                x, y = current_entity_pos[0], current_entity_pos[1]
                cv2.circle(overlay, (x, y), 15, (255, 0, 0), 3)
            
            # Draw red rectangle around nameplate OCR region
            cv2.rectangle(overlay,
                         (self.nameplate_region["left"], self.nameplate_region["top"]),
                         (self.nameplate_region["left"] + self.nameplate_region["width"],
                          self.nameplate_region["top"] + self.nameplate_region["height"]),
                         (0, 0, 255), 2)
            
            # Draw yellow rectangle around health bar monitoring region
            cv2.rectangle(overlay,
                         (self.health_region["left"], self.health_region["top"]),
                         (self.health_region["left"] + self.health_region["width"],
                          self.health_region["top"] + self.health_region["height"]),
                         (0, 255, 255), 2)
            
            # Add text overlays
            status_text = "RUNNING" if self.is_running.is_set() else "PAUSED"
            cv2.putText(overlay, f"Entities found: {len(entities)}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(overlay, f"Current action: {self.current_action}", (10, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(overlay, f"OCR result: {ocr_text[:30]}", (10, 90),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(overlay, f"Health: {health_pct:.1f}%", (10, 120),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(overlay, f"Status: {status_text}", (10, 150),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            return overlay
            
        except Exception as e:
            if DEBUG:
                print(f"Debug overlay error: {e}")
            return frame
    
    def run(self):
        """Main loop: detect → identify → combat"""
        print("⏳ Waiting for CapsLock to start...")
        
        last_frame_time = time.time()
        current_entity_pos = None
        
        while not self.should_exit:
            # Wait for running state
            self.is_running.wait()
            
            if not self.is_running.is_set():
                # Paused - show last frame if debug
                if DEBUG:
                    frame = self.capture_screen()
                    if frame is not None:
                        overlay = self.draw_debug_overlay(
                            frame, [], current_entity_pos, self.ocr_result, self.health_percentage
                        )
                        cv2.imshow("Mob Hunter Debug", overlay)
                        cv2.waitKey(1)
                continue
            
            # Control FPS for detection loop
            current_time = time.time()
            elapsed = current_time - last_frame_time
            if elapsed < self.frame_delay:
                time.sleep(self.frame_delay - elapsed)
            last_frame_time = time.time()
            
            # Phase 1: Entity Detection
            frame = self.capture_screen()
            if frame is None:
                continue
            
            entities = self.detect_entities(frame)
            self.entities_found = len(entities)
            
            if len(entities) == 0:
                self.no_entity_count += 1
                if self.no_entity_count >= 5:
                    if DEBUG:
                        print("⚠ Warning: No entities found for 5 consecutive frames")
                    self.no_entity_count = 0
                self.current_action = "Scanning (no entities)"
            else:
                self.no_entity_count = 0
                self.current_action = "Scanning"
            
            # Phase 2: Mob Identification
            mob_found = False
            for entity in entities:
                if not self.is_running.is_set():
                    break
                
                x, y = entity[0], entity[1]
                current_entity_pos = (x, y)
                
                # Check if position was already checked
                pos_key = (x // 10, y // 10)
                if pos_key in self.checked_positions:
                    continue
                
                # Click and identify
                is_mob, ocr_text = self.click_and_identify((x, y))
                self.ocr_result = ocr_text
                
                if not self.is_running.is_set():
                    break
                
                if is_mob:
                    mob_found = True
                    self.current_action = "Mob Identified"
                    
                    # Mark position as checked
                    self.checked_positions.add(pos_key)
                    
                    # Clear checked positions if set is too large
                    if len(self.checked_positions) > 50:
                        self.checked_positions.clear()
                    
                    # Phase 3: Combat
                    # Get initial health
                    combat_frame = self.capture_screen()
                    if combat_frame is not None:
                        initial_health = self.get_health_percentage(combat_frame)
                        
                        if initial_health > 0:
                            # Enter combat loop
                            mob_died = self.combat_loop(initial_health)
                            
                            if mob_died:
                                if DEBUG:
                                    print("✓ Mob defeated!")
                                self.current_action = "Returning to scan"
                                time.sleep(0.5)  # Brief pause after combat
                        else:
                            if DEBUG:
                                print("⚠ Health bar not visible, skipping combat")
                    
                    break  # Exit entity loop after finding mob
                else:
                    # Not a mob, mark as checked
                    self.checked_positions.add(pos_key)
                    self.current_action = "Not a mob, continuing scan"
            
            # Update debug display
            if DEBUG:
                overlay = self.draw_debug_overlay(
                    frame, entities, current_entity_pos, self.ocr_result, self.health_percentage
                )
                cv2.imshow("Mob Hunter Debug", overlay)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    self.should_exit = True


def main():
    print("=" * 50)
    print("MOB HUNTER v1.0")
    print("=" * 50)
    print("Press CapsLock to START")
    print("Press CapsLock again to PAUSE")
    print("Press Ctrl+C to EXIT")
    print("=" * 50)
    
    hunter = MobHunter()
    
    try:
        hunter.run()
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down...")
        hunter.should_exit = True
        hunter.is_running.clear()
        if DEBUG:
            cv2.destroyAllWindows()
        print("Goodbye!")
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        if DEBUG:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
