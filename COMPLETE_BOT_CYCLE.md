# Complete Bot Cycle - Exact Full Flow

**Date:** 2025-12-11
**Version:** 4.0 (Production)
**Purpose:** Detailed explanation of the complete bot cycle from startup to hunting

---

## Bot Startup Sequence

```
1. Initialize Components
   ├─ Setup logger → Log file created
   ├─ Screen capture system
   ├─ Floating name detector (CV2)
   ├─ Position cache (5s timeout)
   ├─ Nameplate reader (OCR)
   ├─ Combat system
   ├─ Buffer system (15min interval)
   ├─ Death detector
   ├─ Stuck detector
   └─ Overlay window

2. Start Global Keyboard Listener
   ├─ CapsLock = Pause/Resume
   └─ O = Toggle overlay

3. Run Initial Buffer Sequence
   ├─ Press '5' (buff skill)
   ├─ Wait 1 second
   ├─ Press '6' (buff skill)
   └─ Wait 1 second

4. Enter Main Loop
   └─ Start hunting cycles
```

---

## Main Loop (Runs Continuously)

```
┌─────────────────────────────────────────────────────────────┐
│ MAIN LOOP (Every ~0.4 seconds)                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Check CapsLock Toggle                                  │
│     ├─ Pressed? → Toggle pause state                       │
│     ├─ If paused: Skip cycle, update overlay, sleep        │
│     └─ If resumed: Run buffer sequence, continue           │
│                                                             │
│  2. Check 'O' Key Toggle                                   │
│     └─ Pressed? → Toggle overlay visibility                │
│                                                             │
│  3. Check Buffer Timer (15 min interval)                   │
│     └─ Time to buff? → Run buffer sequence                 │
│                                                             │
│  4. Run Detection Cycle ← MAIN HUNTING LOGIC               │
│     └─ See "Detection Cycle" below                         │
│                                                             │
│  5. Sleep 0.4 seconds                                      │
│     └─ Config.CYCLE_DELAY                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Detection Cycle (The Core Hunting Loop)

### Phase 1: Death Detection

```
┌─────────────────────────────────────────────────────────────┐
│ PHASE 1: DEATH DETECTION (Highest Priority)                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Capture Screenshot                                     │
│     └─ pyautogui.screenshot()                              │
│                                                             │
│  2. Skip Death Check If Just Resumed                       │
│     └─ Prevents false positive from buff visual effects    │
│                                                             │
│  3. Check If Player Dead                                   │
│     Method: Count blue pixels in health bar region         │
│     └─ > 2000 blue pixels = DEAD                           │
│                                                             │
│     IF DEAD:                                               │
│     ├─ Save death screenshot                               │
│     ├─ Increment death counter                             │
│     ├─ Wait 2 seconds (death popup stabilize)              │
│     ├─ Press F4 (open revive menu)                         │
│     ├─ Wait 0.5s                                           │
│     ├─ Press 0 (resurrect at specified point)              │
│     ├─ Wait 3s (respawn animation)                         │
│     ├─ Run buffer sequence                                 │
│     └─ Skip rest of cycle, return to main loop             │
│                                                             │
│     IF ALIVE:                                              │
│     └─ Continue to Phase 2                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Phase 2: Stuck Detection

```
┌─────────────────────────────────────────────────────────────┐
│ PHASE 2: STUCK DETECTION                                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Check Stuck Conditions:                                   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ SCENARIO 1: No Target for 7+ Seconds               │  │
│  ├─────────────────────────────────────────────────────┤  │
│  │ Condition:                                          │  │
│  │  - target_selected = False                          │  │
│  │  - time_since_last_kill >= 7.0 seconds              │  │
│  │                                                      │  │
│  │ Meaning:                                            │  │
│  │  - No mobs detected for 7+ seconds                  │  │
│  │  - Character standing idle                          │  │
│  │  - Need to move to find new mobs                    │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ SCENARIO 2: Target Selected But Stuck              │  │
│  ├─────────────────────────────────────────────────────┤  │
│  │ Condition:                                          │  │
│  │  - target_selected = True                           │  │
│  │  - time_since_last_action >= 3.0 seconds            │  │
│  │                                                      │  │
│  │ Meaning:                                            │  │
│  │  - Mob was clicked and selected                     │  │
│  │  - Combat attempted but failed                      │  │
│  │  - Health didn't decrease (< 5% AND < 50px)         │  │
│  │  - Mob is unreachable (behind wall, etc.)           │  │
│  │  - Need to move away and find different mob        │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ RECOVERY MODE: Already In Recovery                 │  │
│  ├─────────────────────────────────────────────────────┤  │
│  │ Condition:                                          │  │
│  │  - in_recovery_mode = True                          │  │
│  │  - time_since_last_recovery >= 2.0 seconds          │  │
│  │                                                      │  │
│  │ Meaning:                                            │  │
│  │  - Previous recovery didn't result in kill         │  │
│  │  - Continue recovery with more movement             │  │
│  │  - Progressive escalation kicks in                  │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  IF STUCK:                                                 │
│  ├─ Set in_recovery_mode = True                            │
│  ├─ Execute Recovery Movement (see Phase 2.1)              │
│  ├─ Capture new screenshot after movement                  │
│  └─ Continue to Phase 3 with new position                  │
│                                                             │
│  IF NOT STUCK:                                             │
│  └─ Continue to Phase 3                                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Phase 2.1: Recovery Movement (When Stuck)

```
┌─────────────────────────────────────────────────────────────┐
│ PHASE 2.1: RECOVERY MOVEMENT EXECUTION                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Calculate Progressive Escalation:                         │
│  ├─ attempt_multiplier = min(consecutive_recoveries, 5)    │
│  ├─ base_move_time = 2.0 seconds                           │
│  └─ escalated_move_time = 2.0 + (attempts × 0.5)           │
│                                                             │
│      Attempt #1: 2.0s movement                             │
│      Attempt #2: 2.5s movement                             │
│      Attempt #3: 3.0s movement                             │
│      Attempt #4: 3.5s movement                             │
│      Attempt #5+: 4.0s movement (capped)                   │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  IF SCENARIO 1 (No Target):                                │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ Goal: Move to new area and find mobs                 │ │
│  ├───────────────────────────────────────────────────────┤ │
│  │                                                       │ │
│  │  num_steps = random.randint(2, 4)  ← Variable!       │ │
│  │                                                       │ │
│  │  FOR EACH STEP (2-4 times):                          │ │
│  │    ├─ Step A: Rotate Character                       │ │
│  │    │   direction = random.choice(['left', 'right'])  │ │
│  │    │   rotation_time = random.uniform(0.5, 2.5)      │ │
│  │    │   pyautogui.keyDown(direction)                  │ │
│  │    │   sleep(rotation_time)                          │ │
│  │    │   pyautogui.keyUp(direction)                    │ │
│  │    │                                                  │ │
│  │    ├─ Step B: Move Forward                           │ │
│  │    │   pyautogui.keyDown('up')                       │ │
│  │    │   sleep(escalated_move_time)  ← 2.0-4.0s        │ │
│  │    │   pyautogui.keyUp('up')                         │ │
│  │    │                                                  │ │
│  │    └─ Step C: Camera Change (50% chance)             │ │
│  │        if random.random() < 0.5:                     │ │
│  │          drag_distance = random.randint(-400, 400)   │ │
│  │          Right-click drag horizontal                 │ │
│  │                                                       │ │
│  │  Total Distance: ~6-20 meters (depends on steps)     │ │
│  │  Pattern: Completely random zigzag exploration       │ │
│  │                                                       │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  IF SCENARIO 2 (Has Target, Stuck):                        │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ Goal: Turn around, escape, find different mob        │ │
│  ├───────────────────────────────────────────────────────┤ │
│  │                                                       │ │
│  │  Step 1: Turn Around (~180°)                         │ │
│  │    direction = random.choice(['left', 'right'])      │ │
│  │    rotation_time = random.uniform(1.3, 2.5)          │ │
│  │    pyautogui.keyDown(direction)                      │ │
│  │    sleep(rotation_time)                              │ │
│  │    pyautogui.keyUp(direction)                        │ │
│  │                                                       │ │
│  │  Step 2: Move Forward (Away from Stuck Mob)          │ │
│  │    pyautogui.keyDown('up')                           │ │
│  │    sleep(escalated_move_time)  ← 2.0-4.0s            │ │
│  │    pyautogui.keyUp('up')                             │ │
│  │                                                       │ │
│  │  Step 3: Camera Angle Change                         │ │
│  │    drag_distance = random.randint(-400, 400)         │ │
│  │    Right-click drag horizontal                       │ │
│  │                                                       │ │
│  │  Steps 4+: Additional Random Movements               │ │
│  │    extra_steps = random.randint(1, 3)                │ │
│  │                                                       │ │
│  │    FOR EACH EXTRA STEP (1-3 times):                  │ │
│  │      ├─ Rotate: random direction, 0.3-1.5s           │ │
│  │      └─ Forward: random 1.5-3.0s                     │ │
│  │                                                       │ │
│  │  Total Distance: ~8-25 meters (progressive)          │ │
│  │  Pattern: Aggressive escape with random exploration  │ │
│  │                                                       │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  After Recovery Movement:                                  │
│  ├─ Reset action timer: last_action_time = now()           │
│  ├─ DON'T exit recovery mode                               │
│  ├─ Capture new screenshot                                 │
│  └─ Continue to Phase 3 (detection at new location)        │
│                                                             │
│  Recovery Only Exits When:                                 │
│  └─ on_kill() is called (confirmed kill)                   │
│      ├─ consecutive_recoveries = 0                         │
│      ├─ in_recovery_mode = False                           │
│      └─ last_kill_time = now()                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Phase 3: Detection

```
┌─────────────────────────────────────────────────────────────┐
│ PHASE 3: FLOATING NAME DETECTION                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Detect Floating Names (CV2)                            │
│     Method: Color-based detection (orange RGB)             │
│     ├─ Convert screenshot to HSV                           │
│     ├─ Filter orange color range                           │
│     ├─ Find contours                                       │
│     ├─ Filter by size (MIN_AREA to MAX_AREA)               │
│     └─ Filter by aspect ratio                              │
│                                                             │
│     Result: List of bounding boxes [x, y, w, h]            │
│                                                             │
│  2. Calculate Distance From Center                         │
│     FOR EACH detection:                                    │
│       center_x = x + w/2                                   │
│       center_y = y + h/2                                   │
│       screen_center = (SCREEN_WIDTH/2, SCREEN_HEIGHT/2)    │
│       distance = sqrt((center_x - screen_center_x)² +      │
│                       (center_y - screen_center_y)²)       │
│                                                             │
│  3. Log Results                                            │
│     "Detected: X floating names"                           │
│                                                             │
│     IF NO DETECTIONS:                                      │
│     ├─ Log "No floating names found"                       │
│     ├─ Update stuck detector: set_target_status(False)     │
│     ├─ Update overlay                                      │
│     └─ Return to main loop (skip rest of cycle)            │
│                                                             │
│     IF DETECTIONS FOUND:                                   │
│     └─ Continue to Phase 4                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Phase 4: Cache Filtering

```
┌─────────────────────────────────────────────────────────────┐
│ PHASE 4: POSITION CACHE FILTERING                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Purpose: Skip recently checked positions                  │
│  Cache Timeout: 5 seconds                                  │
│                                                             │
│  FOR EACH detection:                                       │
│    ├─ Get center position (x, y)                           │
│    ├─ Check if in cache (within 50px, < 5s old)            │
│    │                                                        │
│    ├─ IF IN CACHE:                                         │
│    │   └─ Skip (already checked recently)                  │
│    │                                                        │
│    └─ IF NOT IN CACHE:                                     │
│        ├─ Calculate click position (below nameplate)       │
│        │   click_x = x + w/2                               │
│        │   click_y = y + h + 25  ← Below text              │
│        │                                                    │
│        └─ Add to valid_targets list:                       │
│            {                                                │
│              'click_pos': (click_x, click_y),               │
│              'center': (center_x, center_y),                │
│              'distance': distance_from_center               │
│            }                                                │
│                                                             │
│  Sort valid_targets by distance (CLOSEST FIRST)            │
│                                                             │
│  Log: "Valid targets (after cache): X"                     │
│  Log: Target priority list (top 5 with distances)          │
│                                                             │
│  IF NO VALID TARGETS:                                      │
│  └─ All were cached, return to main loop                   │
│                                                             │
│  IF VALID TARGETS EXIST:                                   │
│  └─ Continue to Phase 5                                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Phase 5: Target Verification

```
┌─────────────────────────────────────────────────────────────┐
│ PHASE 5: TARGET VERIFICATION (Max 3 per cycle)              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Process up to MAX_TARGETS_PER_CYCLE (3) targets           │
│  Strategy: Closest to center first                         │
│                                                             │
│  FOR EACH valid target (sorted by distance):               │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ 5.1: Click and Wait for Nameplate                    │ │
│  ├───────────────────────────────────────────────────────┤ │
│  │                                                       │ │
│  │  Log: "Verifying target #X (D=Ypx)..."               │ │
│  │                                                       │ │
│  │  1. Click Position                                   │ │
│  │     pyautogui.click(click_x, click_y)                │ │
│  │     sleep(CLICK_DELAY = 0.25s)                       │ │
│  │                                                       │ │
│  │  2. Wait for Nameplate (1.0s timeout)                │ │
│  │     Retry up to 10 times (0.1s each)                 │ │
│  │     Check if nameplate appeared on screen            │ │
│  │                                                       │ │
│  │     IF NO NAMEPLATE:                                 │ │
│  │     └─ Log "No valid nameplate or is a pet"          │ │
│  │        Continue to next target                       │ │
│  │                                                       │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ 5.2: Read Nameplate Information (OCR)                │ │
│  ├───────────────────────────────────────────────────────┤ │
│  │                                                       │ │
│  │  Capture nameplate region (450x170 pixels)           │ │
│  │  Location: (SCREEN_WIDTH/2 - 225, 3)                 │ │
│  │                                                       │ │
│  │  Extract Information:                                │ │
│  │  ├─ Class Icon Detection (CV2 template matching)     │ │
│  │  │   Check for class icons in nameplate              │ │
│  │  │   IF NO CLASS ICON: is_pet = True                 │ │
│  │  │                                                    │ │
│  │  ├─ Health Bar Status (Red pixel count)              │ │
│  │  │   Count red pixels in health bar region           │ │
│  │  │   IF red_pixels > 50: is_alive = True             │ │
│  │  │   IF red_pixels <= 50: is_alive = False (DEAD)    │ │
│  │  │                                                    │ │
│  │  └─ Mob Class (OCR - pytesseract)                    │ │
│  │      Read text from nameplate                        │ │
│  │      Examples: "Tomb Warrior", "Ghost Warrior"       │ │
│  │                                                       │ │
│  │  Returns: {                                          │ │
│  │    'class': "Tomb Warrior",                          │ │
│  │    'is_alive': True,                                 │ │
│  │    'is_pet': False,                                  │ │
│  │    'initial_health': 649  (red pixel count)          │ │
│  │  }                                                    │ │
│  │                                                       │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ 5.3: Filter Results                                  │ │
│  ├───────────────────────────────────────────────────────┤ │
│  │                                                       │ │
│  │  IF is_pet = True:                                   │ │
│  │  ├─ Log "Filtered: PET (no class icon)"              │ │
│  │  └─ Continue to next target                          │ │
│  │                                                       │ │
│  │  IF class = None:                                    │ │
│  │  ├─ Log "No class detected"                          │ │
│  │  └─ Continue to next target                          │ │
│  │                                                       │ │
│  │  IF is_alive = False:                                │ │
│  │  ├─ Log "Mob already DEAD"                           │ │
│  │  ├─ Update stuck detector: set_target_status(True)   │ │
│  │  │   (Even dead mobs count as "target selected")     │ │
│  │  └─ Continue to next target                          │ │
│  │                                                       │ │
│  │  IF VALID MOB (has class, alive, not pet):           │ │
│  │  ├─ Log "✓ {class} | Status: ALIVE"                  │ │
│  │  ├─ Add to confirmed_mobs list                       │ │
│  │  ├─ Update stuck detector: set_target_status(True)   │ │
│  │  └─ Continue to Phase 6 (Combat)                     │ │
│  │                                                       │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Phase 6: Combat

```
┌─────────────────────────────────────────────────────────────┐
│ PHASE 6: COMBAT ENGAGEMENT                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Log: "⚔️  ENGAGING: {mob_class}"                          │
│  Log: "  Initial health: {initial_health} red pixels"      │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ 6.1: Skill Rotation (Max 4 skills)                   │ │
│  ├───────────────────────────────────────────────────────┤ │
│  │                                                       │ │
│  │  skill_keys = ['1', '2', '3', '4']                   │ │
│  │  health_history = [initial_health]                   │ │
│  │                                                       │ │
│  │  FOR skill_index in range(4):                        │ │
│  │                                                       │ │
│  │    Step 1: Press Skill Key                           │ │
│  │      skill = skill_keys[skill_index]                 │ │
│  │      Log: "  → Skill {skill_index+1}: {skill}"       │ │
│  │      pyautogui.press(skill)                          │ │
│  │      sleep(HEALTH_CHECK_INTERVAL = 1.0s)             │ │
│  │                                                       │ │
│  │    Step 2: Check Health After Skill                  │ │
│  │      Capture screenshot                              │ │
│  │      Count red pixels in health bar region           │ │
│  │      current_health = red_pixel_count                │ │
│  │      health_history.append(current_health)           │ │
│  │                                                       │ │
│  │      Log: "    Health check: {current} red pixels"   │ │
│  │                                                       │ │
│  │    Step 3: Check If Dead                             │ │
│  │      IF current_health <= RED_PIXEL_THRESHOLD (50):  │ │
│  │        Log: "  ✓ Mob DEAD after skill {i+1}!"        │ │
│  │        BREAK (stop skill rotation early)             │ │
│  │                                                       │ │
│  │      ELSE:                                           │ │
│  │        Log: "    → ALIVE"                            │ │
│  │        Continue to next skill                        │ │
│  │                                                       │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ 6.2: Health Change Analysis (CRITICAL)               │ │
│  ├───────────────────────────────────────────────────────┤ │
│  │                                                       │ │
│  │  After skill rotation completes:                     │ │
│  │                                                       │ │
│  │  final_health = health_history[-1]                   │ │
│  │  max_health = max(health_history)                    │ │
│  │  min_health = min(health_history)                    │ │
│  │  health_decreased = max_health - min_health          │ │
│  │                                                       │ │
│  │  Calculate Percentage:                               │ │
│  │    IF initial_health > 0:                            │ │
│  │      percentage = (health_decreased / initial) × 100 │ │
│  │    ELSE:                                             │ │
│  │      percentage = 0                                  │ │
│  │                                                       │ │
│  │  Check If Stuck (BOTH must be true):                 │ │
│  │    is_stuck = (percentage < 5.0% AND                 │ │
│  │                health_decreased < 50 pixels)         │ │
│  │                                                       │ │
│  │  IF is_stuck:                                        │ │
│  │    ├─ Log: "⚠️  Health barely changed                │ │
│  │    │         ({initial} → {final}, {%:.1f}%)         │ │
│  │    │         - NOT hitting mob!"                     │ │
│  │    ├─ Log: "Character may be stuck or unreachable"  │ │
│  │    ├─ Update stuck detector: DON'T reset timer      │ │
│  │    │   (Allows Scenario 2 to trigger)                │ │
│  │    └─ Return False (combat failed)                   │ │
│  │                                                       │ │
│  │  ELSE (Health decreased enough):                     │ │
│  │    ├─ Log: "  ℹ️  Rotation complete                  │ │
│  │    │         (health decreased: {X} pixels)"         │ │
│  │    ├─ Increment kill counter                         │ │
│  │    ├─ Log: "💀 Total kills: {total_kills}"           │ │
│  │    ├─ Update stuck detector:                         │ │
│  │    │   ├─ reset_timer()  (progress made)             │ │
│  │    │   ├─ set_target_status(False)                   │ │
│  │    │   └─ on_kill()  (exits recovery if active)      │ │
│  │    └─ Return True (combat successful)                │ │
│  │                                                       │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ 6.3: Post-Combat Actions                             │ │
│  ├───────────────────────────────────────────────────────┤ │
│  │                                                       │ │
│  │  IF combat successful (returned True):               │ │
│  │    ├─ on_kill() was called                           │ │
│  │    ├─ Recovery mode exited (if was in recovery)      │ │
│  │    ├─ consecutive_recoveries = 0                     │ │
│  │    ├─ last_kill_time = now                           │ │
│  │    └─ Continue to next target (if any left)          │ │
│  │                                                       │ │
│  │  IF combat failed (returned False):                  │ │
│  │    ├─ target_selected stays True                     │ │
│  │    ├─ Timer keeps running                            │ │
│  │    ├─ If timer reaches 3s → Scenario 2 triggers      │ │
│  │    └─ Continue to next target (if any left)          │ │
│  │                                                       │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Phase 7: Cycle Completion

```
┌─────────────────────────────────────────────────────────────┐
│ PHASE 7: CYCLE COMPLETION                                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Update Overlay                                         │
│     ├─ Current stats (cycle, kills, deaths, etc.)          │
│     ├─ Detection rectangles                                │
│     └─ Status text                                         │
│                                                             │
│  2. Save Periodic Screenshot (if enabled)                  │
│     IF cycle % PERIODIC_SCREENSHOT_INTERVAL == 0:          │
│       Save screenshot for debugging                        │
│                                                             │
│  3. Return to Main Loop                                    │
│     └─ Sleep 0.4s, then start next cycle                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Complete Example: Stuck Scenario with Recovery

### Timeline: Tomb Warrior Encounter (Unreachable Mob)

```
TIME 0:00 - CYCLE #1
├─ Death check: ALIVE ✓
├─ Stuck check: Not stuck (last kill was recent)
├─ Detection: Found 2 floating names
├─ Cache filter: 2 valid targets
├─ Target #1 verification:
│   ├─ Click position
│   ├─ Nameplate appears: "Tomb Warrior"
│   ├─ Class icon detected: ✓
│   ├─ Health: 649 red pixels (ALIVE)
│   └─ Confirmed valid mob
├─ Combat engagement:
│   ├─ Skill 1: Health = 649 (unchanged)
│   ├─ Skill 2: Health = 649 (unchanged)
│   ├─ Skill 3: Health = 649 (unchanged)
│   ├─ Skill 4: Health = 649 (unchanged)
│   └─ Health change: 0 pixels (0.0%)
├─ Health analysis:
│   ├─ 0.0% < 5% ✓ AND 0px < 50px ✓
│   └─ is_stuck = True → Combat FAILED
├─ Stuck detector updated:
│   ├─ target_selected = True (mob was selected)
│   ├─ Timer NOT reset (no progress)
│   └─ last_action_time = TIME 0:00
└─ Cycle complete

TIME 0:04 - CYCLE #2
├─ Death check: ALIVE ✓
├─ Stuck check:
│   ├─ target_selected = True
│   ├─ elapsed = 0:04 - 0:00 = 4.0 seconds
│   └─ 4.0s >= 3.0s threshold → STUCK! (Scenario 2)
├─ STUCK DETECTED: "Target selected but stuck for 4.0s"
├─ Enter recovery mode: in_recovery_mode = True
├─ Recovery execution (Attempt #1):
│   ├─ Progressive escalation: 2.0s base
│   ├─ Step 1: Turn right 1.7s (character faces away)
│   ├─ Step 2: Move forward 2.0s (~4m from wall)
│   ├─ Step 3: Camera drag -200px (new angle)
│   ├─ Step 4: Rotate left 0.9s (face new direction)
│   ├─ Step 5: Move forward 2.0s (~3m sideways)
│   └─ Total movement: ~5m from stuck position
├─ Capture new screenshot (new position)
├─ Detection: Found 2 floating names (Tomb Warrior still visible!)
├─ Target #1: "Tomb Warrior" (still closest)
├─ Combat: Health 649 → 649 (0% change) → FAILED
├─ Recovery continues (no kill confirmed)
└─ Cycle complete

TIME 0:06 - CYCLE #3
├─ Stuck check:
│   ├─ in_recovery_mode = True
│   ├─ elapsed since last recovery = 2.0s
│   └─ STILL STUCK (attempt #2)
├─ Recovery execution (Attempt #2):
│   ├─ Progressive escalation: 2.5s (increased!)
│   ├─ Step 1: Turn left 1.9s
│   ├─ Step 2: Move forward 2.5s (~5m from wall)
│   ├─ Step 3: Camera drag +300px
│   ├─ Extra steps: 3 random movements
│   │   ├─ Rotate right 0.8s + Forward 2.1s
│   │   ├─ Rotate left 1.2s + Forward 2.7s
│   │   └─ Rotate right 0.5s + Forward 1.9s
│   └─ Total movement: ~12m from stuck position
├─ Detection: Still finds "Tomb Warrior"
├─ Combat: Health 649 → 649 → FAILED
└─ Cycle complete

TIME 0:08 - CYCLE #4
├─ Stuck check: STILL STUCK (attempt #3)
├─ Recovery execution (Attempt #3):
│   ├─ Progressive escalation: 3.0s (even more!)
│   ├─ Step 1: Turn right 2.2s
│   ├─ Step 2: Move forward 3.0s (~6m)
│   ├─ Step 3: Camera drag -350px
│   ├─ Extra steps: 2 random movements
│   │   ├─ Rotate left 1.1s + Forward 2.8s
│   │   └─ Rotate right 0.7s + Forward 2.3s
│   └─ Total movement: ~18m from stuck position
├─ Detection: NEW MOB! "Ghost Warrior" (distance: 150px)
│   └─ Tomb Warrior also visible but further (distance: 420px)
├─ Target #1: "Ghost Warrior" (closest to center)
├─ Combat engagement:
│   ├─ Skill 1: Health = 649 → 520 (decreased 129px!)
│   ├─ Skill 2: Health = 520 → 380 (decreased 140px)
│   ├─ Skill 3: Health = 380 → 0 (DEAD!)
│   └─ Mob DEAD after skill 3!
├─ Health analysis:
│   ├─ health_decreased = 649 pixels
│   ├─ percentage = 100.0%
│   └─ NOT stuck → Combat SUCCESSFUL ✓
├─ on_kill() called:
│   ├─ consecutive_recoveries = 0 (reset)
│   ├─ in_recovery_mode = False (EXIT RECOVERY!)
│   ├─ last_kill_time = TIME 0:08
│   └─ Log: "✅ Kill confirmed! Exiting recovery mode after 3 attempts"
├─ Total kills: 45
└─ Cycle complete

TIME 0:12 - CYCLE #5
├─ Death check: ALIVE ✓
├─ Stuck check: Not stuck (just killed mob)
├─ Detection: Found 3 floating names
├─ Normal hunting resumes...
└─ (Back to normal cycle)
```

---

## Key Timing Constants

```python
# Cycle timing
Config.CYCLE_DELAY = 0.4  # Seconds between cycles

# Death detection
Config.DEATH_REVIVE_DELAY = 2.0  # Wait before reviving
RESPAWN_WAIT = 3.0  # Wait for respawn animation

# Buffer system
Config.BUFFER_INTERVAL = 900  # 15 minutes (900s)

# Nameplate reading
Config.NAMEPLATE_TIMEOUT = 1.0  # Wait for nameplate
Config.CLICK_DELAY = 0.25  # After clicking

# Combat
Config.HEALTH_CHECK_INTERVAL = 1.0  # Between skills
Config.RED_PIXEL_THRESHOLD = 50  # Mob considered dead
Config.HEALTH_CHANGE_THRESHOLD = 50  # Absolute pixel threshold
MIN_PERCENTAGE_DECREASE = 5.0  # Percentage threshold

# Stuck detection
no_target_duration = 7.0  # Scenario 1 threshold
with_target_duration = 3.0  # Scenario 2 threshold
recovery_retry_delay = 2.0  # Between recovery attempts

# Recovery movement
base_move_time = 2.0  # Base forward movement
escalation_per_attempt = 0.5  # Additional time per attempt
max_escalation_multiplier = 5  # Cap at 5x
```

---

## Summary

The bot operates in a continuous loop checking for death, stuck conditions, detecting mobs, verifying targets, and engaging in combat. The critical improvements are:

1. **Percentage-based health detection** - Prevents false stuck detection on small health bars
2. **Highly randomized recovery** - Ensures varied movement patterns to escape any stuck situation
3. **Progressive escalation** - Moves further with each failed attempt (2.0s → 2.5s → 3.0s → etc.)
4. **Persistent recovery mode** - Only exits when confirmed kill, not just after movement
5. **Correct arrow key mechanics** - Rotate then forward for actual movement

The system reliably handles all hunting scenarios including normal combat, stuck detection, death, and recovery.
