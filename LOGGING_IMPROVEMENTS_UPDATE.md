# Logging System Improvements

**Date:** 2025-12-05
**Feature:** Enhanced logging with selective screenshots and categorized statistics

---

## Summary

Improved the logging system to provide better tracking of bot operations and fixed screenshot functionality to capture only relevant events rather than many unnecessary screenshots.

**Key Improvements:**
1. ✅ **Selective Screenshot Capture** - Only save important events (deaths, errors)
2. ✅ **Context-Aware Filenames** - Meaningful names with event type and timestamp
3. ✅ **Enhanced Statistics** - Categorized final statistics with efficiency metrics
4. ✅ **Configuration Logging** - Display enabled/disabled features at startup

---

## Changes Implemented

### **1. Selective Screenshot Configuration** ([mob_hunter.py:151-155](mob_hunter.py#L151-L155))

**New Configuration Options:**
```python
# Screenshot settings (selective capture for debugging)
SAVE_DEATH_SCREENSHOTS = True      # Capture screenshot when death detected
SAVE_ERROR_SCREENSHOTS = True      # Capture screenshot on errors
SAVE_PERIODIC_SCREENSHOTS = False  # Periodic screenshots (every N cycles)
PERIODIC_SCREENSHOT_INTERVAL = 50  # Save every 50 cycles if enabled
```

**What Changed:**
- **Before:** Screenshots saved every 10 cycles regardless of events (wasteful)
- **After:** Screenshots only saved for important events (death, errors) or optionally periodic

**Benefits:**
- Fewer unnecessary screenshots cluttering the folder
- Screenshots are actually useful for debugging
- Can still enable periodic screenshots if needed
- Configurable interval for periodic captures

---

### **2. Screenshot Helper Method** ([mob_hunter.py:1064-1088](mob_hunter.py#L1064-L1088))

**New Method:**
```python
def save_screenshot(self, screenshot, event_type, extra_info=""):
    """
    Save screenshot with meaningful filename

    Args:
        screenshot: The image to save
        event_type: Type of event (DEATH, ERROR, CYCLE, etc.)
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
```

**Filename Format:**
- `{counter:04d}_{timestamp}_{event_type}_{extra_info}.png`
- Example: `0001_180230_DEATH_death_1.png`
- Example: `0002_180245_ERROR_fatal_error.png`
- Example: `0003_180300_CYCLE.png`

**Components:**
1. **Counter** - Sequential number (0001, 0002, etc.)
2. **Timestamp** - HHMMSS format for easy sorting
3. **Event Type** - DEATH, ERROR, CYCLE
4. **Extra Info** - Optional context (death number, error type, etc.)

**Benefits:**
- Immediately know what screenshot shows without opening it
- Easy to find specific events
- Sorted chronologically by both counter and timestamp
- Searchable by event type

---

### **3. Screenshot Capture Integration**

**A. Death Detection** ([mob_hunter.py:1182-1184](mob_hunter.py#L1182-L1184))
```python
# Save death screenshot
if Config.SAVE_DEATH_SCREENSHOTS:
    self.save_screenshot(screenshot, "DEATH", f"death_{self.death_detector.death_count + 1}")
```

**When Triggered:**
- Immediately when death popup detected
- Before revive sequence executes
- Filename includes death number (death_1, death_2, etc.)

**Example Output:**
```
💀 DEATH DETECTED - Player is dead!
📸 Screenshot saved: 0005_142030_DEATH_death_1.png
⚠️  Player is dead - pausing hunting
```

---

**B. Fatal Errors** ([mob_hunter.py:1158-1163](mob_hunter.py#L1158-L1163))
```python
# Save error screenshot if possible
if Config.SAVE_ERROR_SCREENSHOTS:
    try:
        error_screenshot = self.screen_capture.capture()
        self.save_screenshot(error_screenshot, "ERROR", "fatal_error")
    except:
        pass  # Don't crash while trying to save error screenshot
```

**When Triggered:**
- Unhandled exception in main loop
- Fatal errors that stop the bot
- Safe error handling (won't crash if screenshot fails)

---

**C. Periodic Cycles** ([mob_hunter.py:1290-1293](mob_hunter.py#L1290-L1293))
```python
# Save periodic screenshot if enabled
if Config.SAVE_PERIODIC_SCREENSHOTS and self.cycle % Config.PERIODIC_SCREENSHOT_INTERVAL == 0:
    self.save_screenshot(screenshot, "CYCLE")
```

**When Triggered:**
- Every N cycles (default: 50)
- Only if `SAVE_PERIODIC_SCREENSHOTS = True`
- Disabled by default to save disk space

---

### **4. Enhanced Statistics** ([mob_hunter.py:1312-1366](mob_hunter.py#L1312-L1366))

**Complete Rewrite:**

**Before:**
```python
# Old statistics (basic)
self.logger.info(f"Total cycles: {self.cycle}")
self.logger.info(f"Total kills: {self.combat.total_kills}")
self.logger.info(f"Deaths: {self.death_detector.death_count}")
# ... simple list
```

**After (Categorized):**
```python
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
```

**Categories:**

**1. 📁 Session Info**
- Log directory path (for finding screenshots/logs)
- Uptime in seconds and formatted (Xm Ys)
- Total cycles completed
- Screenshots saved count

**2. 🔍 Detection**
- Total clicks on nameplates
- Verified mobs (passed pet filter)
- Filtered pets (prevented from clicking)
- Pet filter rate percentage

**3. ⚔️ Combat**
- Total kills
- Deaths
- Early stops (left combat early)
- Skills used
- Average skills per kill
- **Kills per hour** (efficiency metric)

**4. ⚙️ System**
- Buffer sequences executed
- Cache hit rate percentage
- Cache size (number of entries)

**5. 📈 Efficiency**
- Average cycle time
- Average clicks per cycle
- Average kills per cycle

---

### **5. Configuration Logging at Startup** ([mob_hunter.py:1096-1106](mob_hunter.py#L1096-L1106))

**New Startup Message:**
```python
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
```

**Example Output:**
```
🚀 Bot started! Press Ctrl+C to stop.

💡 Controls: CapsLock = Pause/Resume | O = Toggle Overlay

⌨️  Global keyboard listener active (works in any window)

📋 Configuration:
   Death Detection: ✅ Enabled
   Death Screenshots: ✅ Enabled
   Error Screenshots: ✅ Enabled
   Periodic Screenshots: ❌ Disabled
   Buffer Interval: 60s
   Overlay: ✅ Enabled
```

**Benefits:**
- Immediately see what features are active
- Verify configuration without checking code
- Easy troubleshooting (check if feature is enabled)
- Visual checkmarks/X marks for quick scanning

---

## Screenshot Comparison

### **Before (Old System):**
```
Folder: screenshots/
├── 0001.png  (cycle 10 - nothing interesting)
├── 0002.png  (cycle 20 - nothing interesting)
├── 0003.png  (cycle 30 - nothing interesting)
├── 0004.png  (cycle 40 - nothing interesting)
├── 0005.png  (cycle 50 - maybe has death?)
├── 0006.png  (cycle 60 - nothing interesting)
├── ...
└── 0100.png  (1000 cycles = 100 screenshots!)
```

**Problems:**
- ❌ Tons of useless screenshots
- ❌ Can't tell what each screenshot shows
- ❌ Have to open each one to find relevant events
- ❌ Wastes disk space
- ❌ Cluttered folder

---

### **After (New System):**
```
Folder: screenshots/
├── 0001_142030_DEATH_death_1.png       (Death event #1)
├── 0002_142545_ERROR_fatal_error.png   (Fatal error)
├── 0003_143215_DEATH_death_2.png       (Death event #2)
├── 0004_144802_ERROR_fatal_error.png   (Fatal error)
└── 0005_145930_DEATH_death_3.png       (Death event #3)
```

**Benefits:**
- ✅ Only important events captured
- ✅ Filename tells you exactly what it is
- ✅ Easy to find specific event types
- ✅ Saves disk space (5 vs 100 screenshots)
- ✅ Clean, organized folder

---

## Usage Examples

### **Example 1: Death Event**

**Console Output:**
```
======================================================================
CYCLE #47
======================================================================
Detected: 3 floating names
Death detection: Gold=1234, Dark=12500, Brown=5200, White=750
💀 DEATH DETECTED - Player is dead!
   Indicators: Gold=True, Dark=True, Brown=True, Text=True
📸 Screenshot saved: 0001_142030_DEATH_death_1.png
⚠️  Player is dead - pausing hunting

======================================================================
💀 DEATH HANDLER ACTIVATED
======================================================================
Death #1
Waiting 2.0s before reviving...
Pressing F4 (open revive menu)...
Pressing 0 (resurrect at specified point)...
Waiting for respawn (3s)...
✅ Revive sequence completed!
======================================================================

🔄 Running buffer sequence after revive...
[Buffer sequence runs]
✅ Ready to resume hunting!
```

**Screenshot Saved:**
- Filename: `0001_142030_DEATH_death_1.png`
- Shows exact moment death popup was detected
- Useful for adjusting detection thresholds

---

### **Example 2: Final Statistics**

**Console Output:**
```
======================================================================
📊 FINAL STATISTICS
======================================================================
📁 Log Directory: logs/session_20251205_142000
⏱️  Uptime: 3625s (60m 25s)
🔄 Total Cycles: 150
📸 Screenshots Saved: 5

🔍 Detection:
   Total Clicks: 450
   Verified Mobs: 420
   Filtered Pets: 30
   Pet Filter Rate: 6.7%

⚔️  Combat:
   Total Kills: 138
   Deaths: 3
   Early Stops: 12
   Skills Used: 276
   Avg Skills/Kill: 2.0
   Kills/Hour: 137.1

⚙️  System:
   Buffer Sequences: 61
   Cache Hit Rate: 94.2%
   Cache Size: 1247 entries

📈 Efficiency:
   Avg Cycle Time: 24.17s
   Avg Clicks/Cycle: 3.0
   Avg Kills/Cycle: 0.92

======================================================================
```

**Information Provided:**
- Session lasted 60 minutes
- Killed 138 mobs (137/hour rate)
- Died 3 times (auto-revived each time)
- Pet filter working (6.7% pets filtered)
- Cache efficient (94% hit rate)
- Average 3 clicks per cycle (good targeting)
- Only saved 5 screenshots (deaths + errors)

---

## Configuration Options

### **Enable All Screenshots:**
```python
SAVE_DEATH_SCREENSHOTS = True
SAVE_ERROR_SCREENSHOTS = True
SAVE_PERIODIC_SCREENSHOTS = True
PERIODIC_SCREENSHOT_INTERVAL = 50
```

### **Disable All Screenshots:**
```python
SAVE_DEATH_SCREENSHOTS = False
SAVE_ERROR_SCREENSHOTS = False
SAVE_PERIODIC_SCREENSHOTS = False
```

### **Only Death Screenshots:**
```python
SAVE_DEATH_SCREENSHOTS = True
SAVE_ERROR_SCREENSHOTS = False
SAVE_PERIODIC_SCREENSHOTS = False
```

### **More Frequent Periodic:**
```python
SAVE_PERIODIC_SCREENSHOTS = True
PERIODIC_SCREENSHOT_INTERVAL = 10  # Every 10 cycles
```

---

## Benefits Summary

### **✅ Better Tracking:**
- Categorized statistics (Session, Detection, Combat, System, Efficiency)
- Kills per hour metric
- Pet filter rate
- Cache efficiency
- Average cycle time
- Configuration display at startup

### **✅ Relevant Screenshots:**
- Only important events captured
- Context-aware filenames
- Easy to find specific events
- Saves disk space
- Clean folder organization

### **✅ Improved Debugging:**
- Screenshots show exact moment of events
- Filename tells you what happened
- Error screenshots capture crash state
- Death screenshots show detection conditions
- Configuration logging verifies settings

### **✅ Efficiency Metrics:**
- Kills per hour rate
- Average cycle time
- Clicks per cycle
- Kills per cycle
- Cache hit rate
- Skills per kill

---

## File Locations

### **Configuration:**
- [mob_hunter.py:142-155](mob_hunter.py#L142-L155) - Death detection & screenshot settings

### **Screenshot Method:**
- [mob_hunter.py:1064-1088](mob_hunter.py#L1064-L1088) - `save_screenshot()` helper

### **Screenshot Calls:**
- [mob_hunter.py:1182-1184](mob_hunter.py#L1182-L1184) - Death detection
- [mob_hunter.py:1158-1163](mob_hunter.py#L1158-L1163) - Fatal errors
- [mob_hunter.py:1290-1293](mob_hunter.py#L1290-L1293) - Periodic cycles

### **Statistics:**
- [mob_hunter.py:1312-1366](mob_hunter.py#L1312-L1366) - `print_statistics()` method

### **Configuration Logging:**
- [mob_hunter.py:1096-1106](mob_hunter.py#L1096-L1106) - Startup configuration display

---

## Performance Impact

- **CPU:** Negligible (screenshots only on events)
- **Disk Space:** Significantly reduced (5 vs 100+ screenshots)
- **Memory:** Same (screenshot method reuses existing captures)
- **Logging:** Minimal overhead (formatted strings)

---

## Troubleshooting

### **No screenshots being saved:**
1. Check configuration:
   ```python
   SAVE_DEATH_SCREENSHOTS = True
   SAVE_ERROR_SCREENSHOTS = True
   ```
2. Verify screenshots folder exists: `logs/session_YYYYMMDD_HHMMSS/screenshots/`
3. Check console for "📸 Screenshot saved:" messages
4. Check for write permission errors

### **Too many screenshots:**
- Disable periodic: `SAVE_PERIODIC_SCREENSHOTS = False`
- Increase interval: `PERIODIC_SCREENSHOT_INTERVAL = 100`

### **Missing death screenshots:**
- Verify death detection is working (check console for death messages)
- Enable debug mode to see detection values
- Check if `SAVE_DEATH_SCREENSHOTS = True`

### **Statistics not showing:**
- Statistics print when bot stops (Ctrl+C)
- Check final console output
- Look for "📊 FINAL STATISTICS" section

---

## Conclusion

The logging system now provides **much better tracking** with:

1. ✅ **Selective screenshots** - Only deaths, errors, or optional periodic
2. ✅ **Context-aware filenames** - Know what screenshot shows without opening
3. ✅ **Enhanced statistics** - Categorized metrics with efficiency calculations
4. ✅ **Configuration logging** - See enabled features at startup
5. ✅ **Better organization** - Clean folders, meaningful names
6. ✅ **Useful debugging** - Screenshots capture actual events

**The screenshots folder now contains only relevant images that help with debugging and tracking bot performance!** 📊📸✅
