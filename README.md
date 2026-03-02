from pypandoc import convert_text

readme_full = """
# 🌱 Sprout  
### A Calm Computing Wearable for Posture Awareness & Focus Cultivation

---

## 1. Project Vision

Sprout is a calm-computing wearable that transforms posture sensing into a living visual metaphor.

Instead of correcting posture through vibration or sound alerts, Sprout reflects behavior through motion, color, and accumulation. It is designed for children developing sitting habits and sustained attention.

The core idea:

- Upright posture → Growth
- Tilt → Drift
- Time → Memory

Sprout does not interrupt.  
Sprout visualizes.

---

## 2. Design Motivation

Traditional posture devices rely on:

- Vibration alerts
- Audio warnings
- Threshold-triggered correction

These approaches interrupt focus and can create negative feedback loops.

Sprout explores:

- Embodied visualization
- Calm computing principles
- Behavior reflection instead of correction
- Habit formation through accumulated visual memory

---

## 3. System Overview

### Hardware

- ESP32-S2 Feather with TFT display  
- ICM-20948 9-DoF IMU  
- APDS-9960 proximity sensor  
- LiPo battery  
- STEMMA-QT cable  

### Wearable Placement

Chest-mounted clip to capture torso orientation.

Why chest placement?

- Gravity vector reflects spinal alignment
- Stable roll/pitch reference
- Less noise than wrist-mounted sensing

---

## 4. Interaction Flow

### Idle
- Screen off
- Proximity wake

### Ready Screen
Educator selects duration:

- 10 min – habit formation
- 20 min – elementary focus window
- 30 min – Pomodoro duration

Blinking prompt encourages button press.

---

### Upright Calibration (5 Seconds)

After button press:

1. READY screen disappears
2. Calibration screen appears
3. “Sit up straight” displayed (scale=2)
4. Tree icon shown (scale=2)
5. 5-second countdown
6. IMU roll/pitch averaged

This establishes personalized upright baseline.

---

## 5. Technical Pipeline

### Step 1 – IMU Processing

Acceleration → Roll & Pitch

roll  = atan2(ay, az)  
pitch = atan2(-ax, sqrt(ay² + az²))

Converted to degrees.

---

### Step 2 – Baseline Compensation

roll_offset  = roll  - roll_reference  
pitch_offset = pitch - pitch_reference

---

### Step 3 – Posture Classification

| State | Threshold | Color |
|--------|-----------|--------|
| UPRIGHT | ±6° | Green |
| FORWARD | roll < -9° | Red |
| BACKWARD | roll > 9° | Gray |
| LEFT | pitch < -6° | Orange |
| RIGHT | pitch > 6° | Yellow |

Left/right are intentionally more sensitive.

---

### Step 4 – Temporal Filtering

Posture must persist for 3 seconds before becoming confirmed.

Prevents noise from creating unstable visual feedback.

---

## 6. Visualization Engine

### Bubble Generation

Each confirmed posture segment generates a bubble.

Bubble size ∝ posture duration.

r = R_MIN + (hold_time / 10s) * (R_MAX - R_MIN)  
r *= 0.6

Bubbles globally reduced by 40% for density balance.

---

### Spatial Anchoring

Each posture has an anchor region:

- UPRIGHT → Center
- FORWARD → Top
- BACKWARD → Bottom
- LEFT → Left
- RIGHT → Right

Placement logic:

- Gaussian bias around anchor
- Expands to full screen if crowded
- Never overlaps on spawn

---

## 7. Physics Engine

Each bubble stores:

- x, y
- vx, vy
- radius
- state

Forces applied:

1. Spring toward anchor
2. IMU-based tilt force
3. Inter-bubble repulsion
4. Boundary collision
5. Damping

Physics runs at 20Hz for smooth motion.

---

## 8. Embodied Tilt Mapping

Live IMU offsets produce subtle drift:

ax_tilt = pitch_offset * TILT_FORCE  
ay_tilt = roll_offset  * TILT_FORCE

This creates a direct embodied mapping between posture and motion.

---

## 9. Session Logic

- IMU sampling: 5Hz
- Physics update: 20Hz
- State duration accumulation
- 30-second majority window

Display Layout:

Line 1: Current posture (Schoolbell, scale=2)  
Line 2: Elapsed time (scale=1)

---

## 10. Summary Screen

After session ends:

- All bubbles retained
- Colors dimmed (~30% brightness)
- Rendered behind text
- Continue drifting

Title color reflects dominant tilt posture.

Encouragement based on upright percentage.

Screen remains active for 90 seconds.

---

## 11. Code Architecture

READY  
CALIB  
SESSION  
SUMMARY  

Core Functions:

- wait_for_button_with_press_blink()
- calibrate_upright_with_countdown()
- run_focus_session()
- step_bubble_physics()
- show_summary()

Non-blocking timing using time.monotonic().

---

## 12. Coding Challenges

### IMU Noise
Solved using:
- Baseline averaging
- Sustained state confirmation
- Separate sensor & physics loops

### Display Limitations
- No alpha blending
- No rotation for shapes
- Memory constraints for fonts

Solutions:
- RGB dimming for background
- Layer reordering
- Lightweight physics model

---

## 13. Insights

- Reflection is stronger than interruption.
- Calibration is essential for wearable sensing.
- Temporal filtering dramatically improves UX.
- Calm computing requires reducing feedback intensity.
- Visualization can encode behavioral memory.

Sprout does not correct posture.

It makes posture visible.

---

## 14. User Roadmap

### Short-Term
- Add WiFi logging
- Session statistics export
- Adjustable sensitivity presets

### Mid-Term
- Parent dashboard visualization
- Weekly posture analytics
- Growth-based tree animation

### Long-Term
- Multi-device syncing
- Classroom mesh interaction
- AI-based posture pattern modeling

---

## 15. Future Directions

- Longitudinal growth narrative
- Biofeedback personalization
- Hardware enclosure refinement
- Lower power optimization

---

## Demo

(Insert video link)

---

Developed as part of an IMU wearable systems exploration focusing on embodied sensing and calm computing.
"""

output_path = "/mnt/data/README_full.md"
convert_text(readme_full, 'md', format='md', outputfile=output_path, extra_args=['--standalone'])

output_path
