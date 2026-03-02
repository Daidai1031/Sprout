# 🌱 Sprout

**A Calm Computing Wearable for Posture Awareness and Focus
Cultivation**

------------------------------------------------------------------------

## Introduction

Sprout is a wearable posture-awareness device built using the **ESP32-S2
Feather with TFT display** and the **ICM-20948 9-DoF IMU sensor**.

The project explores how motion sensing, real-time data processing, and
visual feedback can be combined into a calm computing wearable that
supports children in developing healthy sitting posture and sustained
focus.

Rather than using sound, vibration, or disruptive alerts, Sprout
translates posture data into an evolving visual ecosystem --- a
collection of colored bubbles that grow, drift, and respond to body
movement over time.

------------------------------------------------------------------------

## Concept

Sprout is designed around a simple metaphor:

-   **Upright posture = healthy growth**
-   **Tilted posture = directional drift**

Instead of punishing incorrect posture, the device visualizes posture
behavior over time. The longer a posture is held, the larger its bubble
becomes.

The goal is to cultivate awareness rather than enforce correction.

------------------------------------------------------------------------

## Hardware Components

-   ESP32-S2 Feather with TFT display\
-   InvenSense ICM-20948 9-DoF IMU\
-   APDS-9960 proximity sensor\
-   LiPo battery\
-   STEMMA-QT cable

------------------------------------------------------------------------

## Wearable Placement

Sprout is designed as a chest-mounted clip.

Why chest placement?

-   Gravity vector accurately reflects torso tilt
-   Roll and pitch angles correspond to real posture
-   Less noise than wrist-mounted sensing
-   Stable baseline calibration

------------------------------------------------------------------------

## Interaction Flow

### 1. Idle Mode

-   Screen off
-   Proximity sensor wakes device

### 2. Ready Screen

Educator selects session duration: - 10 minutes - 20 minutes - 30
minutes

### 3. Upright Calibration (5 Seconds)

After button press: 1. Ready screen disappears 2. "Sit up straight"
screen appears 3. 5-second countdown begins 4. IMU data averaged during
countdown

This establishes a personalized upright baseline.

------------------------------------------------------------------------

## IMU Processing Pipeline

roll = atan2(ay, az)\
pitch = atan2(-ax, sqrt(ay² + az²))

roll_offset = roll - roll_reference\
pitch_offset = pitch - pitch_reference

------------------------------------------------------------------------

## Visualization System

Bubble radius is proportional to posture duration.

r = R_MIN + (hold_time / 10s) \* (R_MAX - R_MIN)\
r \*= 0.6

Spatial Anchors: - UPRIGHT → Center - FORWARD → Top - BACKWARD →
Bottom - LEFT → Left side - RIGHT → Right side

------------------------------------------------------------------------

## Summary Screen

After session completion:

-   All bubbles remain
-   Colors dimmed for background effect
-   Title color reflects dominant tilt posture
-   Encouragement message depends on upright percentage
-   Screen remains active for 90 seconds

------------------------------------------------------------------------

## Software Structure

READY\
CALIB\
SESSION\
SUMMARY

------------------------------------------------------------------------

## Insights

-   Behavior change works better through awareness than punishment.
-   Temporal filtering is critical in wearable sensing.
-   Calibration is essential for human-centered wearables.
-   Calm computing requires restraint in feedback intensity.

Sprout does not correct posture.\
It reflects it.

------------------------------------------------------------------------

## Future Improvements

-   WiFi data logging
-   Parent dashboard
-   Long-term growth visualization
-   Multi-device syncing

------------------------------------------------------------------------

## Demo

(Insert video link here)
