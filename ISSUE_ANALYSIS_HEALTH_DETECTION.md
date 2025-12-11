# Critical Issue Analysis: Health Detection & Stuck Recovery

**Date:** 2025-12-11
**Issue:** Bot runs away from mobs even when surrounded

---

## Log Analysis: session_20251211_205231

### Timeline

**Cycle #1 (20:52:35-20:52:50):**
```
Player Status: DEAD (0 red pixels in player health bar)
Death Detection: Skipped (buffer cooldown)
Mobs Detected: 9 floating names
Valid Targets: 9 (surrounded by mobs!)

Target #1 Combat (Unique):
  Initial: 121 red pixels
  Skill 1: 123 red pixels (INCREASED +2)
  Skill 2: 123 red pixels (no change)
  Skill 3: 124 red pixels (INCREASED +1)
  Skill 4: 124 red pixels (no change)

  Health change: 121 → 124 (Δ=-3, INCREASED!)
  Percentage: 2.5% change
  Result: ❌ STUCK - "Health barely changed"

Target #2 Combat (Unique):
  Initial: 121 red pixels
  Skill 1: 121 red pixels
  Skill 2: 122 red pixels (INCREASED +1)
  Skill 3: 123 red pixels (INCREASED +1)
  Skill 4: 121 red pixels (decreased -2)

  Health change: 121 → 121 (Δ=0)
  Percentage: 1.7%
  Result: ❌ STUCK

Target #3 Combat (Unique):
  Initial: 123 red pixels
  Skill 1: 122 red pixels (decreased -1)
  Skill 2: 122 red pixels (no change)
  Skill 3: 121 red pixels (decreased -1)
  Skill 4: 121 red pixels (no change)

  Health change: 123 → 121 (Δ=2)
  Percentage: 1.6%
  Result: ❌ STUCK

All 3 combat attempts failed!
```

**Cycle #2 (20:52:51-20:52:56):**
```
Death detection: TRIGGERED (no buffer cooldown)
Revive sequence: F4 → 0 → Wait 3s → Buffer
```

**Cycle #3 (20:53:01):**
```
Player Status: STILL DEAD (0 red pixels)
Death Detection: Skipped (buffer cooldown 0.4s)
Stuck Detection: TRIGGERED (25.1s since last action)
Action: Recovery activated → Bot runs away!
```

---

## Root Cause Analysis

### Issue #1: Mob Health Detection is UNRELIABLE

**Current Implementation:**
```python
# Get health from ENTIRE nameplate region
x, y, w, h = Config.NAMEPLATE_REGION  # (660, 10, 600, 100)
nameplate = screenshot[y:y+h, x:x+w]

# Count ALL red pixels in 600x100 region
red_pixels = cv2.countNonZero(red_mask)
```

**The Problem:**
- Nameplate region: 600x100 pixels (60,000 pixels total)
- Includes: Class icon, mob name, health bar, borders, decorations
- Health bar is only ~10-15 pixels tall, ~200-300 pixels wide
- **Counting red pixels in ENTIRE nameplate picks up non-health elements!**

**Evidence from Logs:**
- Health "increased" from 121 → 124 pixels
- Health fluctuates randomly (121 → 123 → 124)
- These are NOT actual health changes - they're OTHER red elements!

**Possible Red Elements in Nameplate:**
1. Class icons (Unique = red/orange icon)
2. Mob name text if orange/red
3. Border decorations
4. Status effect icons
5. Actually health bar

**Result:** Health measurements are **noise**, not actual mob health!

---

### Issue #2: Character Was Dead - But That's Not Why Stuck Triggered

**What I Initially Thought:**
- Character dead → Can't hit mobs → Health doesn't decrease → Stuck

**What Actually Happened:**
- Health detection is unreliable REGARDLESS of character state
- Health readings fluctuate due to counting wrong pixels
- Even with alive character, health readings would be unreliable

**The Real Problem:**
- We're measuring the WRONG region (entire nameplate vs just health bar)
- Even alive character would trigger false stuck detection
- Dead character just made it obvious

---

### Issue #3: Revive Didn't Work

**Evidence:**
```
Line 181: Player health bar: 0 red pixels  (AFTER revive!)
```

**After F4 → 0 → Wait 3s → Buffer:**
- Player health bar STILL shows 0 red pixels
- This means either:
  1. Revive failed (wrong key sequence?)
  2. 3 seconds not enough for respawn
  3. Player health bar region is wrong

---

### Issue #4: Stuck Timer Not Reset After Revive

**Evidence:**
```
Line 183: STUCK DETECTED (Scenario 2): stuck for 25.1s
```

**The 25.1 second timer:**
- Started when combat first failed in Cycle #1
- Death handler ran but didn't reset stuck timers
- After revive, timer still shows 25.1s
- Immediately triggered Scenario 2 stuck recovery
- Bot ran away from mobs

---

## The Complete Problem Chain

```
1. Bot starts with DEAD character
   ↓
2. Initial buffer runs (no death check yet - we'll fix this)
   ↓
3. Cycle #1: Death detected but SKIPPED (buffer cooldown)
   ↓
4. Combat attempted with dead character
   ↓
5. Health readings unreliable (wrong region being measured)
   ↓
6. All combat fails → target_selected = True, timer starts
   ↓
7. Cycle #2: Death detected → Revive sequence
   ↓
8. Revive FAILS or takes too long (still shows 0 health)
   ↓
9. Cycle #3: Death skipped (buffer cooldown)
   ↓
10. Stuck timer = 25.1s (never reset after death)
    ↓
11. Stuck Scenario 2 triggered → Bot runs away!
```

---

## Fixes Needed (Priority Order)

### FIX #1: Isolate Health Bar Region in Nameplate ⚠️ CRITICAL
**Problem:** Counting ALL red pixels in 600x100 nameplate region
**Solution:** Extract ONLY the health bar sub-region within nameplate

**Implementation:**
```python
# Current (wrong):
NAMEPLATE_REGION = (660, 10, 600, 100)  # Entire nameplate
red_pixels = count_red_in_entire_region()  # Picks up icons, text, etc.

# Fixed (correct):
NAMEPLATE_REGION = (660, 10, 600, 100)  # Still need full region for OCR
HEALTH_BAR_REGION_OFFSET = (50, 70, 500, 15)  # (x_offset, y_offset, w, h) within nameplate
# Extract health bar only:
health_bar = nameplate[70:85, 50:550]
red_pixels = count_red_in_health_bar_only()
```

**Expected Result:**
- Consistent health readings
- Health only decreases (never increases)
- Accurate stuck detection

---

### FIX #2: Reset Stuck Timers on Death/Revive ⚠️ CRITICAL
**Problem:** Stuck timer persists after death, triggers false recovery
**Solution:** Reset timers in `handle_death()`

**Implementation:**
```python
def handle_death(self):
    """Execute revive sequence"""
    # ... existing revive code ...

    # RESET STUCK TIMERS after revive
    self.stuck_detector.reset_timer()
    self.stuck_detector.last_kill_time = time.time()
    self.stuck_detector.target_selected = False
    self.stuck_detector.consecutive_recoveries = 0
    self.stuck_detector.in_recovery_mode = False

    return True
```

**Expected Result:**
- After revive, stuck timer resets to 0
- No immediate stuck detection after respawn
- Fresh start for hunting

---

### FIX #3: Increase Respawn Wait Time ⚠️ HIGH
**Problem:** 3 seconds not enough for respawn animation
**Solution:** Increase to 5-6 seconds

**Implementation:**
```python
# Current:
time.sleep(3.0)  # Wait for respawn animation

# Fixed:
time.sleep(5.0)  # Wait longer for respawn + health bar update
```

**Expected Result:**
- Player health bar shows red pixels after revive
- Death detection works correctly after respawn

---

### FIX #4: Verify Revive Success ⚠️ MEDIUM
**Problem:** No verification that revive worked
**Solution:** Check player health after revive

**Implementation:**
```python
def handle_death(self):
    # ... revive sequence ...
    time.sleep(5.0)

    # Verify revive worked
    verify_screenshot = self.screen_capture.capture()
    if self.death_detector.is_player_dead(verify_screenshot):
        self.logger.error("❌ Revive failed - player still dead!")
        return False
    else:
        self.logger.info("✅ Revive verified - player alive!")
        return True
```

---

### FIX #5: Pre-Startup Death Check ✅ ALREADY DONE
**Status:** Implemented in previous commit
**What it does:** Checks if dead before initial buffer

---

## Health Bar Region Analysis

**Current Nameplate Region:** (660, 10, 600, 100)

**Estimated Sub-Regions:**
```
Nameplate (600x100):
├─ Row 0-30: Empty space / border
├─ Row 30-50: Mob name text (orange)
├─ Row 50-65: Class icon (left), empty space (right)
├─ Row 65-80: Health bar ← THIS IS WHAT WE NEED!
└─ Row 80-100: Empty space / border

Health Bar Position (estimated):
- X offset from nameplate left: ~50px
- Y offset from nameplate top: ~70px
- Width: ~500px
- Height: ~10-15px
```

**Need to:**
1. Take screenshot of actual nameplate
2. Measure exact health bar position
3. Update code to use precise health bar sub-region

---

## Expected Behavior After Fixes

**Scenario: Character Alive, Mobs Present**
```
Cycle #1:
  → Detect 9 mobs
  → Attack Target #1
    - Health: 450 → 380 → 290 → 150 → 0
    - Decreased: 450 pixels (100%)
    - Result: ✅ KILL
  → Attack Target #2
    - Health: 380 → 320 → 240 → 0
    - Decreased: 380 pixels (100%)
    - Result: ✅ KILL
  → Continue hunting
```

**Scenario: Character Dead at Startup**
```
Startup:
  → Pre-check: Player dead (0 health)
  → Revive: F4 → 0 → Wait 5s
  → Verify: Player alive (450 health)
  → Buffer sequence
  → Start hunting with alive character
```

**Scenario: Character Dies During Hunting**
```
Cycle #N:
  → Death detected (0 player health)
  → Revive: F4 → 0 → Wait 5s
  → Verify: Player alive
  → Reset stuck timers ← FIX #2
  → Buffer sequence
  → Continue hunting (fresh timers, no false stuck)
```

**Scenario: Actually Stuck (Unreachable Mob)**
```
Cycle #N:
  → Attack mob
    - Health: 450 → 450 → 450 → 450 (no change)
    - Decreased: 0 pixels (0%)
    - Result: ❌ STUCK (correct!)
  → Scenario 2 triggered (after 3s)
  → Recovery: Turn, move, find new mob
  → Continue hunting
```

---

## Testing Plan

### Test 1: Health Bar Region Accuracy
1. Start bot with alive character
2. Attack mob and watch health readings
3. Verify health ONLY decreases (never increases)
4. Verify health reaches 0 when mob dies

### Test 2: Revive Sequence
1. Start bot with dead character
2. Verify pre-startup check detects death
3. Verify revive completes successfully
4. Verify player health shows > 0 after revive
5. Verify no stuck detection after revive

### Test 3: Stuck Detection Accuracy
1. Attack unreachable mob (behind wall)
2. Verify health doesn't decrease
3. Verify stuck triggers after 3s
4. Verify recovery activates correctly

### Test 4: Normal Hunting Flow
1. Start with alive character in mob area
2. Let bot hunt for 5 minutes
3. Verify kills are counted correctly
4. Verify no false stuck detection
5. Verify smooth hunting flow

---

## Summary

**Root Causes:**
1. ❌ Health detection uses ENTIRE nameplate (600x100) instead of just health bar
2. ❌ Stuck timers not reset after death/revive
3. ❌ Respawn wait time too short (3s → need 5s)
4. ❌ No verification that revive succeeded

**Symptoms:**
- Health readings fluctuate randomly (121 → 124 → 123)
- All combat marked as "stuck" even when mobs present
- Bot runs away after revive due to stale timer
- False stuck detection dominates

**Priority Fixes:**
1. **Fix health bar region** (isolate actual health bar)
2. **Reset timers on revive** (prevent false stuck)
3. **Increase respawn wait** (ensure successful revive)
4. **Verify revive success** (check player health)

**Impact:**
- Current: Bot is essentially non-functional (false stuck everywhere)
- After fixes: Reliable combat, accurate stuck detection, proper revive flow
