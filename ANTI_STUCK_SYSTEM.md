# Anti-Stuck System

**Date:** 2025-12-10
**Feature:** Automatic detection and recovery from stuck situations

---

## Summary

Implements an intelligent anti-stuck system that detects when the character is stuck against walls or obstacles and automatically recovers using two different strategies.

**Key Features:**
- ✅ **Scenario 1:** No target for 7+ seconds since last kill → Camera rotation
- ✅ **Scenario 2:** Target selected but stuck 3+ seconds → Character movement
- ✅ **Automatic timer tracking** with kill-based reset
- ✅ **Statistics tracking** for stuck recoveries
- ✅ **Integrated into overlay** and final statistics

---

## Problem

**Stuck Situations in Silkroad Online:**

The character can get stuck in two main scenarios:

### **Scenario 1: Stuck Against Wall, No Target Selected**
- Character is against a wall
- No monsters selected for 7+ seconds **since last kill**
- Character can't move forward to find targets
- **Solution:** Rotate camera to look around

### **Scenario 2: Stuck Against Wall, Target Selected**
- Character is against a wall
- Monster is already selected (nameplate visible)
- Can't reach the monster to attack
- **Solution:** Move character away from wall

---

## Solution: StuckDetector Class

### **Class Structure** ([mob_hunter.py:738-863](mob_hunter.py#L738-L863))

```python
class StuckDetector:
    """Detect and recover from stuck situations"""

    def __init__(self, logger):
        self.logger = logger
        self.last_action_time = time.time()
        self.last_kill_time = time.time()  # Track last kill separately
        self.target_selected = False
        self.stuck_recoveries = 0
        self.no_target_duration = 7.0  # Seconds since last kill before stuck
        self.with_target_duration = 3.0  # Seconds with target but no progress
```

---

## Detection Logic

### **Timer Tracking**

The stuck detector tracks time since last progress:

**Progress is defined as:**
- Combat successfully completed → **Resets kill timer (Scenario 1)**
- Target selection changed → Resets action timer (Scenario 2)
- Mob was killed → Records kill time

**Timer Resets When:**
```python
# 1. Combat completes and mob killed
if self.combat.engage(info):
    self.stuck_detector.reset_timer()  # Scenario 2 timer
    self.stuck_detector.on_kill()      # Scenario 1 timer (NEW)

# 2. Target status changes
self.stuck_detector.set_target_status(has_target)
```

**Timer Increases When:**
- No targets found (continues hunting but nothing to click)
- Target selected but no combat progress (stuck against wall)

---

### **Stuck Detection** ([mob_hunter.py:762-784](mob_hunter.py#L762-L784))

```python
def is_stuck(self):
    """
    Check if character is stuck

    Returns:
        (is_stuck, scenario_type) where scenario_type is:
        - 1: No target selected for 7+ seconds since last kill
        - 2: Target selected but stuck for 3+ seconds
        - None: Not stuck
    """
    # Scenario 1: Use time since last kill
    time_since_kill = time.time() - self.last_kill_time

    # Scenario 2: Use time since last action
    elapsed = time.time() - self.last_action_time

    # Scenario 1: No target selected for 7+ seconds since last kill
    if not self.target_selected and time_since_kill >= self.no_target_duration:
        self.logger.warning(f"⚠️  STUCK DETECTED (Scenario 1): No target for {time_since_kill:.1f}s since last kill")
        return True, 1

    # Scenario 2: Target selected but stuck for 3+ seconds
    if self.target_selected and elapsed >= self.with_target_duration:
        self.logger.warning(f"⚠️  STUCK DETECTED (Scenario 2): Target selected but stuck for {elapsed:.1f}s")
        return True, 2

    return False, None
```

---

## Recovery Actions

### **Scenario 1: Camera Rotation** ([mob_hunter.py:806-830](mob_hunter.py#L806-L830))

**When:** No target selected for 7+ seconds since last kill

**Action:**
1. Press and hold right mouse button
2. Drag horizontally (left to right) over 2 seconds
3. Release right mouse button

**Effect:**
- Rotates camera view
- Character looks around for new targets
- Can see monsters that were off-screen

```python
# Press right mouse button
pyautogui.mouseDown(button='right')

# Drag horizontally (left to right) over 2 seconds
drag_distance = 300  # pixels
steps = 20
step_delay = 2.0 / steps

for i in range(steps):
    offset = int((drag_distance / steps) * i)
    pyautogui.moveTo(center_x - drag_distance//2 + offset, center_y)
    time.sleep(step_delay)

# Release right mouse button
pyautogui.mouseUp(button='right')
```

---

### **Scenario 2: Character Movement** ([mob_hunter.py:832-851](mob_hunter.py#L832-L851))

**When:** Target selected but stuck for 3+ seconds

**Action:**
1. Press and hold right mouse button for 2 seconds
2. Release right mouse button
3. Left-click at random location

**Effect:**
- Character moves away from wall
- Random movement creates new position
- Can try attacking target from different angle
- **Note:** Random click doesn't need to be on a mob - anywhere is fine

```python
# Press and hold right mouse button for 2 seconds
pyautogui.mouseDown(button='right')
self.logger.info("  Holding right-click for 2s...")
time.sleep(2.0)
pyautogui.mouseUp(button='right')

# Random left-click location (avoid edges)
import random
margin = 100
random_x = random.randint(margin, Config.SCREEN_WIDTH - margin)
random_y = random.randint(margin, Config.SCREEN_HEIGHT - margin)

self.logger.info(f"  Left-clicking random location: ({random_x}, {random_y})")
pyautogui.click(random_x, random_y)
```

---

## Integration into Main Loop

### **Stuck Check in run_cycle()** ([mob_hunter.py:1342-1350](mob_hunter.py#L1342-L1350))

Stuck detection runs **after death detection** but **before main hunting logic**:

```python
# Check for stuck condition
is_stuck, scenario = self.stuck_detector.is_stuck()
if is_stuck:
    # Execute recovery action
    if self.stuck_detector.recover_from_stuck(scenario):
        self.logger.info("✅ Stuck recovery completed - resuming hunting")
        return  # Skip this cycle
    else:
        self.logger.error("❌ Stuck recovery failed")
```

---

### **Timer Updates Throughout Cycle**

**1. No Detections Found** ([mob_hunter.py:1356-1362](mob_hunter.py#L1356-L1362))
```python
if not detections:
    self.logger.info("→ No floating names found")
    # Update stuck detector: no targets available
    self.stuck_detector.set_target_status(False)
    return
```

**2. Target Selected** ([mob_hunter.py:1425-1426](mob_hunter.py#L1425-L1426))
```python
# Update stuck detector: target selected
self.stuck_detector.set_target_status(True)
```

**3. Combat Successful** ([mob_hunter.py:1429-1432](mob_hunter.py#L1429-L1432))
```python
if self.combat.engage(info):
    # Combat successful - reset stuck timer (progress made)
    self.stuck_detector.reset_timer()
    self.stuck_detector.set_target_status(False)
```

---

## Configuration

### **Timing Thresholds:**

```python
self.no_target_duration = 7.0  # Scenario 1 threshold (since last kill)
self.with_target_duration = 3.0  # Scenario 2 threshold
```

**Adjustable:**
- Increase `no_target_duration` if triggering too early after kills
- Decrease for faster stuck detection
- `with_target_duration` controls Scenario 2 sensitivity

### **Recovery Actions:**

**Scenario 1 Settings:**
```python
drag_distance = 300  # pixels to drag
steps = 20  # smoothness of drag
step_delay = 2.0 / steps  # total time = 2 seconds
```

**Scenario 2 Settings:**
```python
hold_duration = 2.0  # seconds to hold right-click
margin = 100  # pixels from screen edge for random click
```

---

## Statistics Tracking

### **Overlay Display** ([mob_hunter.py:1467](mob_hunter.py#L1467))

```python
'Stuck_Recoveries': self.stuck_detector.stuck_recoveries
```

Shows in real-time overlay how many times stuck recovery has been triggered.

---

### **Final Statistics** ([mob_hunter.py:1515](mob_hunter.py#L1515))

```python
self.logger.info("⚙️  System:")
self.logger.info(f"   Buffer Sequences: {self.buffer.total_buffs}")
self.logger.info(f"   Stuck Recoveries: {self.stuck_detector.stuck_recoveries}")
self.logger.info(f"   Cache Hit Rate: {cache_stats['hit_rate']:.1f}%")
```

**Example Output:**
```
⚙️  System:
   Buffer Sequences: 12
   Stuck Recoveries: 3
   Cache Hit Rate: 85.2%
   Cache Size: 15 entries
```

---

## Logging

### **Detection Logged:**
```
⚠️  STUCK DETECTED (Scenario 1): No target for 5.2s
```
or
```
⚠️  STUCK DETECTED (Scenario 2): Target selected but stuck for 3.5s
```

---

### **Recovery Logged:**
```
======================================================================
🔧 ANTI-STUCK RECOVERY ACTIVATED
======================================================================
Scenario: 1
Total recoveries: 3
Action: Right-click drag (horizontal movement)
✓ Horizontal drag completed
======================================================================

✅ Stuck recovery completed - resuming hunting
```

---

## Example Flow

### **Scenario 1 Example:**

```
Cycle #40: Combat successful, mob killed
  → stuck_detector.on_kill()
  → Kill timer: 0.0s

Cycle #41: No floating names found
  → Kill timer: 2.1s

Cycle #42: No floating names found
  → Kill timer: 4.2s

Cycle #43: No floating names found
  → Kill timer: 6.3s

Cycle #44: No floating names found
  → Kill timer: 8.4s > 7.0s threshold
  → ⚠️ STUCK DETECTED (Scenario 1): No target for 8.4s since last kill
  → 🔧 ANTI-STUCK RECOVERY
  → Right-click drag (camera rotation)
  → ✓ Recovery completed

Cycle #45: Detected 3 floating names
  → Hunting resumes normally
```

---

### **Scenario 2 Example:**

```
Cycle #23: Detected 2 floating names
  → Target #1: Click on mob
  → stuck_detector.set_target_status(True)
  → Timer: 0.0s
  → Engage combat: ❌ Failed (mob out of range)

Cycle #24: Detected 2 floating names
  → Timer: 2.1s
  → Same mob still there, can't reach

Cycle #25: Detected 2 floating names
  → Timer: 4.2s > 3.0s threshold
  → ⚠️ STUCK DETECTED (Scenario 2)
  → 🔧 ANTI-STUCK RECOVERY
  → Right-click hold 2s + random left-click
  → ✓ Recovery completed

Cycle #26: Character moved, can now reach mob
  → Combat successful
  → Timer reset
```

---

## Benefits

### ✅ **Automatic Recovery**
- No manual intervention needed
- Bot continues hunting after stuck situations
- Reduces downtime significantly

### ✅ **Intelligent Detection**
- Different strategies for different situations
- Timer-based (not guess-work)
- Resets on actual progress

### ✅ **Non-Intrusive**
- Only activates when truly stuck
- Doesn't interfere with normal hunting
- Skips single cycle for recovery

### ✅ **Trackable**
- Statistics show how often it triggers
- Helps identify problematic hunting areas
- Can adjust thresholds based on data

---

## Troubleshooting

### **Too Many Scenario 1 Triggers:**

**Problem:** Stuck recovery triggering too soon after killing mobs

**Solution:** Increase threshold
```python
self.no_target_duration = 10.0  # From 7.0 to 10.0
```

---

### **Too Many Scenario 2 Triggers:**

**Problem:** Stuck recovery triggering during valid combat

**Solution:** Increase threshold
```python
self.with_target_duration = 5.0  # From 3.0 to 5.0
```

---

### **Not Triggering When Actually Stuck:**

**Problem:** Character stays stuck longer than expected

**Solution:** Decrease thresholds
```python
self.no_target_duration = 5.0  # Faster response (from 7.0)
self.with_target_duration = 2.0  # Faster response (from 3.0)
```

---

### **Recovery Not Working:**

**Problem:** Stuck recovery executes but character still stuck

**Solutions:**
1. **Scenario 1:** Increase drag distance
   ```python
   drag_distance = 500  # From 300 to 500
   ```

2. **Scenario 2:** Increase hold time or random click range
   ```python
   time.sleep(3.0)  # From 2.0 to 3.0
   margin = 200  # From 100 to 200
   ```

---

## Technical Details

### **Timer Management:**

**State Tracking:**
- `last_action_time` - Timestamp of last action (Scenario 2 timer)
- `last_kill_time` - Timestamp of last kill (Scenario 1 timer)
- `target_selected` - Boolean flag for current target status
- `stuck_recoveries` - Counter for statistics

**Methods:**
- `reset_timer()` - Resets action timer (Scenario 2)
- `on_kill()` - Resets kill timer (Scenario 1)
- `set_target_status(bool)` - Updates target status, resets action timer if changed
- `is_stuck()` - Checks both timers against thresholds
- `recover_from_stuck(scenario)` - Executes recovery action

---

### **Mouse Control:**

**pyautogui Functions Used:**
- `mouseDown(button='right')` - Press right mouse button
- `mouseUp(button='right')` - Release right mouse button
- `moveTo(x, y)` - Move mouse to position
- `click(x, y)` - Left-click at position

---

## Performance Impact

- **CPU:** Negligible (simple timer checks)
- **Memory:** Minimal (few variables)
- **Cycle Time:** Only adds checks, no delays unless stuck
- **Recovery Time:**
  - Scenario 1: ~2 seconds (drag duration)
  - Scenario 2: ~2.5 seconds (hold + click)

---

## Future Enhancements

**Possible Improvements:**
- [ ] Add Scenario 3: Detect if character hasn't moved in X seconds
- [ ] Multiple recovery attempts before giving up
- [ ] Learn from stuck locations (heatmap)
- [ ] Teleport to town if stuck repeatedly in same area
- [ ] Configurable recovery actions via config file
- [ ] Screenshot on stuck detection for analysis

---

## Conclusion

The anti-stuck system provides **automatic recovery** from common stuck situations in Silkroad Online:

1. ✅ **Scenario 1:** No targets (7s since last kill) → Camera rotation
2. ✅ **Scenario 2:** Target but stuck (3s) → Character movement
3. ✅ **Smart timer tracking** with kill-based reset
4. ✅ **Statistics and logging** for monitoring
5. ✅ **Configurable thresholds** for tuning

**Improvements:**
- Timer now starts from **last kill** (more accurate)
- Increased threshold to **7 seconds** (less false positives)
- Random click doesn't need to target a mob

**The bot can now recover from stuck situations automatically and continue hunting without manual intervention!** 🔧✅
