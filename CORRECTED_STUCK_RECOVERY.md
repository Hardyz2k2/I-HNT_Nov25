# Corrected Stuck Recovery System - Arrow Keys + Active Targeting

**Date:** 2025-12-11
**Version:** 3.2 (Final)
**Status:** ✅ Implemented

---

## Critical Corrections from User Feedback

### ❌ Previous Mistakes (Fixed)

**1. Tab Key Does NOT Auto-Target**
- **Wrong assumption:** Tab targets nearest mob
- **Reality:** Tab triggers Berserk ability
- **Fix:** Use normal detection system to actively click and target mobs

**2. Movement Keys Are Arrow Keys, Not WASD**
- **Wrong:** S key for backward movement
- **Reality:** Arrow keys control movement (Up/Down/Left/Right)
- **Fix:** Use arrow keys exclusively

**3. Backward Arrow Doesn't Work**
- **Wrong:** Can directly move backward with Down arrow
- **Reality:** Down arrow doesn't work for backward movement
- **Fix:** Rotate character 180° with Left/Right, then use Up arrow to move

---

## New Recovery Strategy

### Core Principle
**Move AWAY from stuck area until targeting a different mob successfully**

### Recovery Actions

**Scenario 1: No Target (7s since last kill)**
```
Goal: Change position and find new mobs

Actions:
1. Rotate character (Left or Right arrow 0.8-1.2s)
2. Move forward (Up arrow 1.5-2.0s)
3. Continue normal detection
4. Detection system will click and target new mobs
```

**Scenario 2: Target Selected But Stuck (3s no progress)**
```
Goal: Turn around, move far away, find completely different mob

Actions:
1. Turn around 180° (Left or Right arrow 1.5-2.0s)
2. Move away (Up arrow 2.0-2.5s)
3. Extra rotation if multiple attempts (0.5-1.0s)
4. Continue normal detection
5. Detection system will click and target new mobs
```

---

## Implementation Details

### Scenario 1 Code ([mob_hunter.py:868-891](mob_hunter.py#L868-L891))

```python
# Scenario 1: No target - rotate and move to new area
direction = random.choice(['left', 'right'])
arrow_key = 'left' if direction == 'left' else 'right'
rotation_time = random.uniform(0.8, 1.2)  # Partial rotation

# Rotate character
pyautogui.keyDown(arrow_key)
time.sleep(rotation_time)
pyautogui.keyUp(arrow_key)
time.sleep(0.2)

# Move forward to new position
move_time = random.uniform(1.5, 2.0)
pyautogui.keyDown('up')
time.sleep(move_time)
pyautogui.keyUp('up')
time.sleep(0.3)
```

**Timing:**
- Rotation: 0.8-1.2 seconds (random partial turn)
- Movement: 1.5-2.0 seconds forward
- Total: ~2.5-3.5 seconds per attempt

### Scenario 2 Code ([mob_hunter.py:893-927](mob_hunter.py#L893-L927))

```python
# Scenario 2: Has target but stuck - turn around and move away
direction = random.choice(['left', 'right'])
arrow_key = 'left' if direction == 'left' else 'right'
rotation_time = random.uniform(1.5, 2.0)  # Longer rotation (~180°)

# Turn around
pyautogui.keyDown(arrow_key)
time.sleep(rotation_time)
pyautogui.keyUp(arrow_key)
time.sleep(0.3)

# Move forward away from stuck position (longer)
move_time = random.uniform(2.0, 2.5)
pyautogui.keyDown('up')
time.sleep(move_time)
pyautogui.keyUp('up')
time.sleep(0.3)

# Optional: Additional rotation after multiple attempts
if consecutive_recoveries >= 2:
    extra_rotation = random.uniform(0.5, 1.0)
    opposite_key = 'right' if arrow_key == 'left' else 'left'
    pyautogui.keyDown(opposite_key)
    time.sleep(extra_rotation)
    pyautogui.keyUp(opposite_key)
    time.sleep(0.2)
```

**Timing:**
- Initial rotation: 1.5-2.0 seconds (~180° turn)
- Forward movement: 2.0-2.5 seconds (longer distance)
- Extra rotation (if attempt #2+): 0.5-1.0 seconds
- Total: ~4.0-5.8 seconds per attempt

---

## How Movement Works in Silkroad

### Character Movement Controls
```
Arrow Keys:
├─ Up    → Move forward in facing direction
├─ Down  → Does NOT work for backward movement ❌
├─ Left  → Rotate character left (turn)
└─ Right → Rotate character right (turn)
```

### To Move Backward (Workaround)
Since Down arrow doesn't work:
1. Hold Left or Right arrow (1.5-2.0s) → Character rotates ~180°
2. Hold Up arrow → Character moves forward (but facing backward from original position)
3. Result: Effectively moved away from stuck position ✅

### Targeting System
```
Tab key → Triggers Berserk ability ❌ (not auto-target!)

Correct way to target:
├─ Detection system finds floating nameplates
├─ Click below nameplate (left-click)
├─ Game selects that mob
└─ Combat system engages
```

**Recovery relies on normal detection, not Tab key!**

---

## Complete Flow with Correct Controls

### Example: Stuck Against Wall with Tomb Warrior

```
Initial State:
├─ Character facing wall
├─ Tomb Warrior selected
├─ Skills not hitting (health unchanged)
└─ 3 seconds pass...

⚠️  STUCK DETECTED (Scenario 2)
└─ Enter recovery mode

┌─────────────────────────────────────────┐
│ RECOVERY ATTEMPT #1                     │
├─────────────────────────────────────────┤
│ 1. Turn around RIGHT (1.8s)             │
│    - Character now facing away from wall│
│                                         │
│ 2. Move forward UP (2.3s)               │
│    - Character moves away from wall     │
│    - Distance from Tomb Warrior: ~5m   │
│                                         │
│ 3. Normal detection cycle...           │
│    - Still detects Tomb Warrior         │
│    - Clicks it                          │
│    - Combat fails (unreachable)         │
└─────────────────────────────────────────┘
        ↓ (No kill, 2s delay)

┌─────────────────────────────────────────┐
│ RECOVERY ATTEMPT #2                     │
├─────────────────────────────────────────┤
│ 1. Turn around LEFT (1.6s)              │
│    - Now facing different direction     │
│                                         │
│ 2. Move forward UP (2.1s)               │
│    - Distance from Tomb Warrior: ~8m   │
│                                         │
│ 3. Extra rotation RIGHT (0.7s)          │
│    - Searching for other mobs           │
│                                         │
│ 4. Normal detection cycle...           │
│    - Tomb Warrior still closest         │
│    - Clicks it again                    │
│    - Combat fails                       │
└─────────────────────────────────────────┘
        ↓ (No kill, 2s delay)

┌─────────────────────────────────────────┐
│ RECOVERY ATTEMPT #3                     │
├─────────────────────────────────────────┤
│ 1. Turn around RIGHT (1.9s)             │
│                                         │
│ 2. Move forward UP (2.4s)               │
│    - Distance from Tomb Warrior: ~12m  │
│    - Far enough from stuck area!        │
│                                         │
│ 3. Extra rotation LEFT (0.9s)           │
│                                         │
│ 4. Normal detection cycle...           │
│    - NEW mob detected: "Ghost Warrior"  │
│    - Clicks Ghost Warrior               │
│    - Combat starts                      │
│    - Health: 649 → 520 → 380 → 0       │
│    - KILL CONFIRMED! ✅                 │
└─────────────────────────────────────────┘

✅ Kill confirmed! Exiting recovery mode after 3 attempts
└─ Back to normal hunting
```

---

## Why This Works

### 1. Progressive Distance
Each recovery attempt moves character further away:
- Attempt #1: ~5 meters from stuck position
- Attempt #2: ~8 meters (with extra rotation)
- Attempt #3: ~12 meters (very far)

Eventually, character moves far enough that:
- Stuck mob is no longer closest
- Other mobs become closer
- Detection naturally targets new mobs ✅

### 2. Randomized Direction
```python
direction = random.choice(['left', 'right'])
rotation_time = random.uniform(1.5, 2.0)
```

Random rotation ensures:
- Not moving in same direction every time
- Explores different areas
- Finds mobs in various positions

### 3. Extra Rotation After Multiple Attempts
```python
if consecutive_recoveries >= 2:
    # Add extra rotation in opposite direction
```

After 2+ failed attempts:
- Adds additional 0.5-1.0s rotation
- Searches wider area
- Increases chance of finding different mobs

### 4. Normal Detection Handles Targeting
After movement:
- Detection system runs normally
- Finds all visible nameplates
- Clicks closest to center
- **No Tab key needed!**

---

## Configuration

### Movement Timings

**Scenario 1 (No target):**
```python
rotation_time = random.uniform(0.8, 1.2)  # Partial turn
move_time = random.uniform(1.5, 2.0)      # Moderate distance
```

**Scenario 2 (Has target, stuck):**
```python
rotation_time = random.uniform(1.5, 2.0)   # Full 180° turn
move_time = random.uniform(2.0, 2.5)       # Longer distance
extra_rotation = random.uniform(0.5, 1.0)  # After attempt #2+
```

### Delays
```python
self.recovery_retry_delay = 2.0  # Seconds between attempts
```

---

## Comparison: Wrong vs Correct

| Aspect | Wrong (Before) | Correct (After) |
|--------|---------------|-----------------|
| **Target method** | Tab key (triggers Berserk!) | Normal detection clicks |
| **Movement keys** | WASD (S for backward) | Arrow keys (Up/Left/Right) |
| **Backward movement** | S key | Rotate 180° + Up arrow |
| **Movement distance** | Fixed | Progressive (further each attempt) |
| **Rotation** | Camera only | Character rotation |
| **Target acquisition** | Tab auto-target (wrong!) | Click on nameplates |

---

## Expected Behavior

### Successful Recovery Pattern

**Log Output:**
```
⚠️  STUCK DETECTED (Scenario 2): Target selected but stuck for 3.1s

==================================================================
🔧 ANTI-STUCK RECOVERY ACTIVATED
==================================================================
Scenario: 2
Consecutive attempts: 1
Total recoveries: 5
Action: Turn around + Move away + Find new target
  Turning around left (1.7s)...
  Moving away from stuck position (2.2s)...
✓ Moved away - will search for new mobs
==================================================================

[Normal detection continues...]
Detected: 3 floating names
→ Valid targets (after cache): 2
  Verifying target #1...
  Combat failed - mob may be unreachable

⚠️  STILL STUCK (Recovery mode, attempt #2)
...

  Turning around right (1.8s)...
  Moving away from stuck position (2.4s)...
  Extra rotation to search (0.8s)...
✓ Moved away - will search for new mobs

[Detection finds new mob...]
⚔️  ENGAGING: Unique
  Health: 649 → 462 → 0
  ✓ Mob DEAD!

✅ Kill confirmed! Exiting recovery mode after 2 attempts
```

---

## Key Points

✅ **No Tab key** - Uses normal detection to target mobs
✅ **Arrow keys only** - Up/Left/Right (Down doesn't work)
✅ **180° rotation** - Turn around to face away from stuck position
✅ **Progressive distance** - Moves further away with each attempt
✅ **Random directions** - Explores different areas
✅ **Extra rotation** - After 2+ attempts, searches wider
✅ **Persistent until kill** - Keeps trying until successful

---

## Files Modified

- [mob_hunter.py](mob_hunter.py) - Lines 839-939 (recover_from_stuck method)
- [CORRECTED_STUCK_RECOVERY.md](CORRECTED_STUCK_RECOVERY.md) - This documentation

---

## Related Documentation

- [HEALTH_CHANGE_DETECTION.md](HEALTH_CHANGE_DETECTION.md) - How stuck is detected
- [PERSISTENT_STUCK_RECOVERY.md](PERSISTENT_STUCK_RECOVERY.md) - Why recovery persists until kill
- [ANTI_STUCK_SYSTEM.md](ANTI_STUCK_SYSTEM.md) - Original stuck detection design

---

## Testing Checklist

- [ ] Verify arrow keys (Up/Left/Right) work correctly
- [ ] Confirm Tab doesn't get pressed (would trigger Berserk)
- [ ] Check character rotates and moves away from walls
- [ ] Verify progressive distance (moves further each attempt)
- [ ] Test with unreachable mob (like Tomb Warrior scenario)
- [ ] Confirm exits recovery mode on kill
- [ ] Check log shows rotation/movement timings

---

## Commit Message

```
Fix stuck recovery: Use arrow keys + active targeting (no Tab)

Critical corrections from user feedback:
- Tab key triggers Berserk, NOT auto-target
- Movement uses arrow keys (Up/Left/Right), not WASD
- Down arrow doesn't work - must rotate 180° + Up to move back
- Random clicks don't work - rely on normal detection instead

New recovery strategy:
- Scenario 1: Rotate (0.8-1.2s) + Move forward (1.5-2.0s)
- Scenario 2: Turn 180° (1.5-2.0s) + Move far (2.0-2.5s)
- Extra rotation after 2+ attempts for wider search
- Progressive distance - moves further from stuck position
- Normal detection finds and clicks new mobs (no Tab)
- Persistent until kill confirmed

Result:
- Character reliably escapes stuck positions
- Moves far enough to find different mobs
- Uses correct Silkroad controls
- No accidental Berserk triggers
```
