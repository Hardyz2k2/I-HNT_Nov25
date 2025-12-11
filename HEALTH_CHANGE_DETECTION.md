# Health Change Detection - Stuck Detection Fix

**Date:** 2025-12-11
**Version:** 3.0
**Status:** ✅ Implemented

---

## Problem Summary

The bot was getting stuck when attacking unreachable mobs but stuck detection never triggered because the combat system always reported "success" even when skills weren't actually hitting the mob.

### Root Cause

When the character is stuck (e.g., against a wall with a mob nearby):
- Bot selects mob → Combat starts
- Skills press (1, 2, 3, 4) but **don't hit** the mob
- Health pixels remain **unchanged** (e.g., 649 → 649 → 649 → 649)
- Combat rotation completes → Returns `True` anyway
- Stuck detector timers **reset** → Never accumulates time → **Stuck detection never triggers**

### Evidence from Logs

**Stuck mob pattern** (session_20251211_102009):
```
Health check: 649 red pixels -> ALIVE
→ Skill 1: 1
Health check: 649 red pixels -> ALIVE  ← Same!
→ Skill 2: 2
Health check: 649 red pixels -> ALIVE  ← Same!
→ Skill 3: 3
Health check: 649 red pixels -> ALIVE  ← Same!
→ Skill 4: 4
Health check: 649 red pixels -> ALIVE  ← Same!
ℹ️  Rotation complete (mob status unknown)
💀 Total kills: X  ← FAKE KILL - mob not actually damaged!
```

**Real kill pattern** (when working correctly):
```
Health check: 649 red pixels -> ALIVE
→ Skill 1: 1
Health check: 649 red pixels -> ALIVE
→ Skill 2: 2
Health check: 462 red pixels -> ALIVE  ← Decreasing!
→ Skill 3: 3
Health check: 342 red pixels -> ALIVE  ← Decreasing!
→ Skill 4: 4
```

Notice: Real kills show **decreasing** health pixels (649 → 462 → 342).

---

## Solution: Health Change Detection

### Implementation

Added health tracking throughout combat rotation to detect when skills aren't actually hitting:

**1. New Method: `get_health_pixels()`** ([mob_hunter.py:487-518](mob_hunter.py#L487-L518))
```python
def get_health_pixels(self, nameplate=None):
    """
    Get the actual red pixel count from health bar
    Returns the number of red pixels (0 if error)
    """
    # ... extracts and returns red pixel count
```

**2. Modified: `is_mob_alive()`** ([mob_hunter.py:520-532](mob_hunter.py#L520-L532))
```python
def is_mob_alive(self, nameplate=None):
    """Now uses get_health_pixels() internally"""
    red_pixels = self.get_health_pixels(nameplate)
    is_alive = red_pixels > Config.RED_PIXEL_THRESHOLD
    return is_alive
```

**3. Enhanced: `CombatSystem.engage()`** ([mob_hunter.py:908-992](mob_hunter.py#L908-L992))

**Key changes:**
- Track health history throughout combat rotation
- Calculate health decrease: `max_health - min_health`
- Return `False` if health didn't decrease by at least threshold (50 pixels)

```python
def engage(self, target_info):
    """
    Returns True if mob was killed, False if:
    - Mob already dead
    - Health didn't decrease (character stuck, can't reach mob)
    """

    # Track health throughout combat
    initial_health = self.nameplate_reader.get_health_pixels()
    health_history = [initial_health]

    # ... combat rotation ...

    for skill in skills:
        press_skill()
        current_health = get_health_pixels()
        health_history.append(current_health)

        if current_health <= threshold:
            return True  # Mob died

    # Check if health actually decreased
    health_decreased = max(health_history) - min(health_history)

    if health_decreased < Config.HEALTH_CHANGE_THRESHOLD:
        # Health unchanged - NOT hitting mob!
        return False  # Combat failed

    # Health decreased - we're hitting, assume kill
    return True
```

### Configuration

**New Config Parameter:** ([mob_hunter.py:102](mob_hunter.py#L102))
```python
HEALTH_CHANGE_THRESHOLD = 50  # Minimum health decrease to confirm hitting mob
```

This allows small variance (±50 pixels) for animation/detection noise while still detecting stuck situations.

---

## How It Works Now

### Normal Combat (Working)
1. Select mob → `set_target_status(True)`
2. Combat starts → Initial health: 649 pixels
3. Skills hit mob → Health decreases: 649 → 462 → 342
4. Health decreased by 307 pixels (> 50 threshold)
5. Combat returns `True` → Timers reset
6. ✅ **Correct behavior**

### Stuck Combat (Fixed!)
1. Select mob → `set_target_status(True)`
2. Combat starts → Initial health: 649 pixels
3. Skills miss (character stuck) → Health stays: 649 → 649 → 649 → 649
4. Health decreased by 0 pixels (< 50 threshold)
5. Combat returns `False` → **Timers NOT reset**
6. `target_selected` remains `True`
7. After 3 seconds → **Scenario 2 triggers!**
8. ✅ **Stuck recovery activates**

### Integration with Stuck Detection

**Main cycle flow** ([mob_hunter.py:1497-1507](mob_hunter.py#L1497-L1507)):

```python
if self.combat.engage(info):
    # Combat successful - mob was damaged/killed
    self.stuck_detector.reset_timer()
    self.stuck_detector.set_target_status(False)
    self.stuck_detector.on_kill()
else:
    # Combat failed - health didn't decrease
    # Keep target_selected=True
    # Timers continue accumulating
    # After 3s → Scenario 2 triggers!
    self.logger.debug(f"Combat failed - mob may be unreachable")
    pass
```

---

## Stuck Detection Scenarios

**Scenario 1:** No target for 7+ seconds since last kill
- **Trigger:** `target_selected=False` AND `time_since_kill >= 7.0s`
- **Action:** Right-click 1s + random left-click (move character)

**Scenario 2:** Target selected but stuck for 3+ seconds
- **Trigger:** `target_selected=True` AND `time_since_action >= 3.0s`
- **Action:** Right-click 2s + random left-click (move character away)

**NEW:** Scenario 2 now triggers when health doesn't decrease!

---

## Testing Evidence

### Before Fix
- Health stays constant (649 → 649 → 649)
- Combat always returns `True`
- Timers reset every cycle
- **Stuck detection never triggers**
- Bot loops infinitely on stuck mob

### After Fix
- Health tracked throughout combat
- Combat returns `False` when health unchanged
- Timers continue accumulating
- **Scenario 2 triggers after 3 seconds**
- Bot recovers from stuck position

---

## Complete Timer Logic Review

All timer reset locations verified for consistency:

**1. Line 785:** `reset_timer()` in `set_target_status()`
   - ✅ Correct: Resets Scenario 2 timer when target status changes

**2. Line 884:** `reset_timer()` in `recover_from_stuck()`
   - ✅ Correct: Resets after successful stuck recovery

**3. Line 1321:** `buffer.reset_timer()`
   - ✅ Correct: Different system (buffer cooldown)

**4. Line 1424:** `set_target_status(False)` when no detections
   - ✅ Correct: No targets available, clear flag

**5. Line 1486:** `set_target_status(True)` for dead mobs
   - ✅ Correct: Allows Scenario 2 for unreachable mobs

**6. Line 1494:** `set_target_status(True)` before combat
   - ✅ Correct: Target selected

**7. Lines 1499-1502:** Reset on combat success
   - ✅ Correct: Only when `engage()` returns `True` (health decreased)

**8. Line 1503-1507:** No reset on combat failure
   - ✅ Correct: Timers continue, allowing stuck detection

---

## Benefits

✅ **Accurate Stuck Detection:** No longer fooled by fake "kills"
✅ **Automatic Recovery:** Scenario 2 triggers reliably for stuck situations
✅ **No False Positives:** 50-pixel threshold allows for normal variance
✅ **Consistent Logic:** All timer resets verified and correct
✅ **Better Logging:** Clear warnings when health doesn't decrease

---

## Related Files

- `mob_hunter.py` - Main implementation
- `ANTI_STUCK_SYSTEM.md` - Stuck detection documentation
- `BUFFER_COOLDOWN_FIX.md` - Related fix for false death detection
- Session logs in `logs/session_*` directories

---

## Commit Message

```
Fix stuck detection by tracking health changes during combat

Problem:
- Combat system always returned True even when skills didn't hit
- Health stayed constant (649→649→649) when character stuck
- Timers reset every cycle, stuck detection never triggered

Solution:
- Added get_health_pixels() to extract actual red pixel count
- Track health history throughout combat rotation
- Return False if health doesn't decrease by 50+ pixels
- Stuck detector timers now accumulate when not hitting mob
- Scenario 2 triggers after 3s of failed combat

Result:
- Stuck detection works reliably for unreachable mobs
- Bot automatically recovers from stuck positions
- No false positives due to 50-pixel threshold variance
```
