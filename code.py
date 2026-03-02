# code.py (CircuitPython 9.x)
# ESP32-S2 Feather Reverse TFT + ICM20948 + APDS-9960
# Silent posture focus clip: ready screen + focus session + non-overlap bubbles + IMU tilt dynamics
#
# Updates in this version:
# - READY: press_group blinks (non-blocking) while waiting for D0/D1/D2
# - READY spacing matches user-provided parameters (Y1/Y2/SUB_Y, right_x)
# - Posture thresholds: LEFT/RIGHT easier to trigger than FORWARD/BACKWARD
# - Bubbles: generated with anchor-biased distribution but can occupy full screen
# - Bubble motion: per-bubble physics with spring + IMU tilt + collision repulsion (no overlaps)

import time
import math
import random
import board
import digitalio
import displayio
import terminalio

from adafruit_icm20x import ICM20948
from adafruit_apds9960.apds9960 import APDS9960
from adafruit_display_text import label
from adafruit_display_shapes.circle import Circle
from adafruit_bitmap_font import bitmap_font
import adafruit_imageload

# -----------------------------
# CONFIG
# -----------------------------
PROX_THRESHOLD = 70
PROX_HYST = 10

BASELINE_SEC = 4.0
SAMPLE_DT = 0.2            # 5 Hz (sensor + UI refresh)
PHYSICS_DT = 0.05          # 20 Hz physics for bubble motion
SUSTAIN_SEC = 3.0          # posture change must persist this long
MAJOR_WINDOW_SEC = 30.0    # 30s majority window (optional)

# angle thresholds (deg) after baseline compensation
# Make LEFT/RIGHT easier than FORWARD/BACKWARD
TH_CENTER = 6.0
TH_FORWARD = -9.0
TH_BACK = 9.0
TH_LEFT = -6.0
TH_RIGHT = 6.0

# bubble sizing (then shrink 40%)
R_MIN = 5
R_MAX = 22
R_MAP_MAX_SEC = 10.0
BUBBLE_SHRINK = 0.6

MAX_BUBBLES = 20
NON_OVERLAP_PAD = 2

# IMU tilt -> external force on bubbles (visual "tilt")
TILT_FORCE = 0.35       # acceleration-ish per deg
TILT_CLAMP_DEG = 20.0

# Bubble physics parameters
SPRING_K = 0.010        # pull toward anchor
DAMPING = 0.86          # velocity damping per physics step
REPULSE_K = 0.6         # collision repulsion strength

SUMMARY_DURATION = 90.0   # seconds to show summary screen with drifting bubbles
# -----------------------------
# HARDWARE INIT
# -----------------------------
i2c = board.I2C()

imu = ICM20948(i2c)

apds = APDS9960(i2c)
apds.enable_proximity = True

display = board.DISPLAY
W, H = display.width, display.height
CX, CY = W // 2, H // 2

# Buttons D0/D1/D2
def make_button(pin):
    b = digitalio.DigitalInOut(pin)
    b.switch_to_input(pull=digitalio.Pull.UP)
    return b

btn10 = make_button(board.D0)
btn20 = make_button(board.D1)
btn30 = make_button(board.D2)

def set_brightness(v):
    try:
        display.brightness = v
    except Exception:
        pass

# -----------------------------
# FONTS
# -----------------------------
FONT_UI = bitmap_font.load_font("/fonts/Schoolbell-16-UIsubset.bdf")

# -----------------------------
# HELPERS
# -----------------------------
def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v

def read_proximity():
    try:
        return apds.proximity
    except Exception:
        return None

def accel_to_roll_pitch(ax, ay, az):
    roll = math.degrees(math.atan2(ay, az))
    pitch = math.degrees(math.atan2(-ax, math.sqrt(ay * ay + az * az)))
    return roll, pitch

STATES = ["UPRIGHT", "FORWARD", "BACKWARD", "LEFT", "RIGHT"]

def classify(roll_off, pitch_off):
    if abs(roll_off) < TH_CENTER and abs(pitch_off) < TH_CENTER:
        return "UPRIGHT"
    if roll_off < TH_FORWARD:
        return "FORWARD"
    if roll_off > TH_BACK:
        return "BACKWARD"
    if pitch_off < TH_LEFT:
        return "LEFT"
    if pitch_off > TH_RIGHT:
        return "RIGHT"
    return "UPRIGHT"

def hold_to_radius(hold_sec):
    t = clamp(hold_sec, 0.0, R_MAP_MAX_SEC)
    r = R_MIN + int((t / R_MAP_MAX_SEC) * (R_MAX - R_MIN))
    r = clamp(r, R_MIN, R_MAX)
    r = max(2, int(r * BUBBLE_SHRINK))  # shrink 40%
    return r

def add_icon_scaled(path, x, y, scale, group):
    bmp, pal = adafruit_imageload.load(
        path,
        bitmap=displayio.Bitmap,
        palette=displayio.Palette
    )

    icon_group = displayio.Group(scale=scale, x=x, y=y)
    icon_group.append(displayio.TileGrid(bmp, pixel_shader=pal))

    group.append(icon_group)
    return icon_group

# -----------------------------
# UI GROUPS
# -----------------------------
BLACK = displayio.Group()

def make_bg_group():
    g = displayio.Group()
    bmp = displayio.Bitmap(W, H, 1)
    pal = displayio.Palette(1)
    pal[0] = 0x000000
    g.append(displayio.TileGrid(bmp, pixel_shader=pal))
    return g

def enter_black():
    set_brightness(0.02)
    display.root_group = BLACK
    display.refresh()

def show_group(g):
    set_brightness(0.8)
    display.root_group = g
    display.refresh()

# READY screen
READY = make_bg_group()

# Left time options (no D0/D1/D2) — keep exactly as user parameters
margin_left = 8
READY.append(label.Label(terminalio.FONT, text="10 min", color=0x00FF88, x=margin_left, y=16))
READY.append(label.Label(terminalio.FONT, text="20 min", color=0xFFAA00, x=margin_left, y=CY))
READY.append(label.Label(terminalio.FONT, text="30 min", color=0xFF4444, x=margin_left, y=H - 18))

# Title area (shift right to avoid left column) — keep user spacing
TITLE_X = int(W * 0.64)
Y1 = int(H * 0.32)
Y2 = int(H * 0.60)

# Title group (static)
ready_title_group = displayio.Group()
READY.append(ready_title_group)

t_hi = label.Label(
    FONT_UI, text="Hi ", color=0xFFFFFF,
    anchor_point=(1.0, 0.5), anchored_position=(TITLE_X - 38, Y1),
    scale=2
)
ready_title_group.append(t_hi)

t_name = label.Label(
    FONT_UI, text="Daisy", color=0xFFFFFF,
    anchor_point=(0.0, 0.5), anchored_position=(TITLE_X - 36, Y1),
    scale=2
)
ready_title_group.append(t_name)

t_comma = label.Label(
    FONT_UI, text=",", color=0xFFFFFF,
    anchor_point=(0.0, 0.5), anchored_position=(TITLE_X + 50, Y1),
    scale=2
)
ready_title_group.append(t_comma)

t_ready = label.Label(
    FONT_UI, text="ready?", color=0x00FF00,
    anchor_point=(0.5, 0.5), anchored_position=(TITLE_X, Y2),
    scale=2
)
ready_title_group.append(t_ready)

# Subtitle (blink only this): keep user spacing
SUB_Y = int(H * 0.87)
press_group = displayio.Group()
READY.append(press_group)

t_sub = label.Label(
    FONT_UI, text="press the button",
    color=0x808080,
    anchor_point=(0.5, 0.5), anchored_position=(TITLE_X - 8, SUB_Y),
    scale=1
)
press_group.append(t_sub)

# Color icons on both sides (stay visible)
def add_icon(path, x, y, group):
    bmp, pal = adafruit_imageload.load(path, bitmap=displayio.Bitmap, palette=displayio.Palette)
    tile = displayio.TileGrid(bmp, pixel_shader=pal, x=x, y=y)
    group.append(tile)
    return tile

ICON_Y = SUB_Y - 8
left_x = TITLE_X - 92
right_x = TITLE_X + 58
add_icon("/images/sparkle.bmp", left_x, ICON_Y, READY)
add_icon("/images/seedling.bmp", right_x, ICON_Y, READY)

# --- Calibration prompt (hidden by default) ---
calib_lbl = label.Label(
    FONT_UI,
    text="",
    color=0xCCCCCC,
    anchor_point=(0.5, 0.5),
    anchored_position=(TITLE_X, int(H * 0.74)),  # 介于 ready? 和 press 之间
    scale=1
)
calib_lbl.hidden = True
READY.append(calib_lbl)

# -----------------------------
# CALIB screen (Upright setup)
# -----------------------------
CALIB = make_bg_group()

calib_title = label.Label(
    FONT_UI,
    text="Sit up straight",
    color=0xFFFFFF,
    anchor_point=(0.5, 0.5),
    anchored_position=(CX, int(H * 0.35)),
    scale=2
)
CALIB.append(calib_title)

calib_count = label.Label(
    FONT_UI,
    text="5",
    color=0x00FF00,
    anchor_point=(0.5, 0.5),
    anchored_position=(CX, int(H * 0.75)),
    scale=2
)
CALIB.append(calib_count)

add_icon_scaled("/images/tree.bmp", int(CX + 45), int(H * 0.60), 2, CALIB)

# SESSION screen
SESSION = make_bg_group()
bubble_layer = displayio.Group()
SESSION.append(bubble_layer)

# Center labels: line1 scale=2, line2 scale=1 (Schoolbell)
current_lbl = label.Label(
    FONT_UI, text="UPRIGHT", color=0xFFFFFF,
    anchor_point=(0.5, 0.5), anchored_position=(CX, CY - 10),
    scale=2
)
SESSION.append(current_lbl)

info_lbl = label.Label(
    FONT_UI, text="Started: 0 min", color=0xCCCCCC,
    anchor_point=(0.5, 0.5), anchored_position=(CX, CY + 24),
    scale=1
)
SESSION.append(info_lbl)

# SUMMARY screen (kept minimal)
SUMMARY = make_bg_group()
summary_bubble_layer = displayio.Group()
SUMMARY.append(summary_bubble_layer)

sum_title = label.Label(
    FONT_UI,
    text="Summary",
    color=0xFFFFFF,
    anchor_point=(0.5, 0.5),
    anchored_position=(CX, int(H * 0.30)),   # 你也可以用 CY-28，但用比例更稳
    scale=2
)
SUMMARY.append(sum_title)

sum_msg = label.Label(
    FONT_UI,
    text="",
    color=0xFFFFFF,
    anchor_point=(0.5, 0.5),
    anchored_position=(CX, int(H * 0.62)),   # ✅ 往下挪（原来如果是 CY+14，改到这里会明显下移）
    scale=1
)
SUMMARY.append(sum_msg)
# -----------------------------
# BUBBLES: anchor-biased distribution + full-screen reach + physics + collisions
# -----------------------------
def dim_color(rgb, factor=0.35):
    r = (rgb >> 16) & 0xFF
    g = (rgb >> 8) & 0xFF
    b = rgb & 0xFF
    r = int(r * factor)
    g = int(g * factor)
    b = int(b * factor)
    return (r << 16) | (g << 8) | b

COLORS = {
    "UPRIGHT":  0x00FF00,
    "BACKWARD": 0x808080,
    "LEFT":     0xFF8800,
    "RIGHT":    0xFFFF00,
    "FORWARD":  0xFF0000,
}

ANCHOR = {
    "UPRIGHT":  (CX, CY + 30),
    "FORWARD":  (CX, CY - int(H * 0.24)),
    "BACKWARD": (CX, CY + int(H * 0.24)),
    "LEFT":     (CX - int(W * 0.30), CY),
    "RIGHT":    (CX + int(W * 0.30), CY),
}

# each bubble: dict with {circle, x, y, r, vx, vy, state}
bubbles = []

def clear_bubbles():
    bubbles.clear()
    while len(bubble_layer) > 0:
        bubble_layer.pop()

def inside_bounds(x, y, r):
    x = clamp(x, r + 1, W - r - 2)
    y = clamp(y, r + 1, H - r - 2)
    return x, y

def overlaps_any(x, y, r):
    for b in bubbles:
        dx = x - b["x"]
        dy = y - b["y"]
        min_d = r + b["r"] + NON_OVERLAP_PAD
        if (dx*dx + dy*dy) < (min_d * min_d):
            return True
    return False

def pick_position_biased(state, r, tries=80):
    ax, ay = ANCHOR[state]

    # Start near anchor; if crowded, gradually expand to full-screen
    for i in range(tries):
        # expansion factor 0..1
        t = i / (tries - 1)
        # sigma grows from small -> large (full screen)
        sigma_x = 14 + t * (W * 0.45)
        sigma_y = 14 + t * (H * 0.45)

        # Box-Muller gaussian-ish
        u1 = max(1e-6, random.random())
        u2 = random.random()
        z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
        u3 = max(1e-6, random.random())
        u4 = random.random()
        z2 = math.sqrt(-2.0 * math.log(u3)) * math.sin(2.0 * math.pi * u4)

        x = int(ax + z * sigma_x)
        y = int(ay + z2 * sigma_y)
        x, y = inside_bounds(x, y, r)

        if not overlaps_any(x, y, r):
            return x, y

    # fallback random anywhere
    for _ in range(60):
        x = random.randint(r + 1, W - r - 2)
        y = random.randint(r + 1, H - r - 2)
        if not overlaps_any(x, y, r):
            return x, y

    return inside_bounds(ax, ay, r)

def add_bubble(state, hold_sec):
    r = hold_to_radius(hold_sec)
    x, y = pick_position_biased(state, r)

    c = Circle(int(x), int(y), int(r), outline=COLORS[state], fill=COLORS[state])
    bubble_layer.append(c)

    bubbles.append({
        "circle": c,
        "x": float(x),
        "y": float(y),
        "r": float(r),
        "vx": 0.0,
        "vy": 0.0,
        "state": state,
    })

    # trim oldest
    while len(bubbles) > MAX_BUBBLES:
        old = bubbles.pop(0)
        # also remove from display
        try:
            bubble_layer.pop(0)
        except Exception:
            pass

def step_bubble_physics(pitch_off, roll_off):
    # Convert IMU offsets to small external acceleration (tilt)
    pitch_off = clamp(pitch_off, -TILT_CLAMP_DEG, TILT_CLAMP_DEG)
    roll_off = clamp(roll_off, -TILT_CLAMP_DEG, TILT_CLAMP_DEG)
    ax_tilt = pitch_off * TILT_FORCE
    ay_tilt = roll_off * TILT_FORCE

    # 1) spring to anchor + tilt
    for b in bubbles:
        ax, ay = ANCHOR[b["state"]]
        fx = (ax - b["x"]) * SPRING_K + ax_tilt
        fy = (ay - b["y"]) * SPRING_K + ay_tilt

        b["vx"] = (b["vx"] + fx) * DAMPING
        b["vy"] = (b["vy"] + fy) * DAMPING

    # 2) repulsion to avoid overlaps (pairwise)
    n = len(bubbles)
    for i in range(n):
        bi = bubbles[i]
        for j in range(i + 1, n):
            bj = bubbles[j]
            dx = bj["x"] - bi["x"]
            dy = bj["y"] - bi["y"]
            dist2 = dx*dx + dy*dy
            min_d = bi["r"] + bj["r"] + NON_OVERLAP_PAD
            if dist2 < (min_d * min_d) and dist2 > 1e-6:
                dist = math.sqrt(dist2)
                # push away proportional to penetration
                pen = (min_d - dist)
                nx = dx / dist
                ny = dy / dist
                push = pen * REPULSE_K
                bi["vx"] -= nx * push
                bi["vy"] -= ny * push
                bj["vx"] += nx * push
                bj["vy"] += ny * push

    # 3) integrate + bounds + apply to Circle
    for b in bubbles:
        b["x"] += b["vx"]
        b["y"] += b["vy"]

        # bounce off edges softly
        if b["x"] < b["r"] + 1:
            b["x"] = b["r"] + 1
            b["vx"] *= -0.4
        if b["x"] > W - b["r"] - 2:
            b["x"] = W - b["r"] - 2
            b["vx"] *= -0.4
        if b["y"] < b["r"] + 1:
            b["y"] = b["r"] + 1
            b["vy"] *= -0.4
        if b["y"] > H - b["r"] - 2:
            b["y"] = H - b["r"] - 2
            b["vy"] *= -0.4

        # update display object (Circle uses x0/y0)
        c = b["circle"]
        try:
            c.x0 = int(b["x"])
            c.y0 = int(b["y"])
        except Exception:
            # fallback: if Circle implementation differs, skip silently
            pass

# -----------------------------
# BASELINE CALIBRATION
# -----------------------------

def calibrate_baseline(seconds=BASELINE_SEC):
    t0 = time.monotonic()
    rs = 0.0
    ps = 0.0
    n = 0
    while time.monotonic() - t0 < seconds:
        ax, ay, az = imu.acceleration
        r, p = accel_to_roll_pitch(ax, ay, az)
        rs += r
        ps += p
        n += 1
        time.sleep(0.05)
    return (rs / max(1, n)), (ps / max(1, n))

def calibrate_upright_with_countdown(seconds=5):
    """
    Show CALIB screen, countdown seconds, and compute average roll/pitch as upright baseline.
    READY will disappear immediately because we switch root_group to CALIB.
    """
    show_group(CALIB)

    t0 = time.monotonic()
    last_shown = None

    rs = 0.0
    ps = 0.0
    n = 0

    # sample at ~20Hz for smoother average during countdown
    while True:
        now = time.monotonic()
        elapsed = now - t0
        remaining = int(seconds - elapsed)

        if remaining < 0:
            break

        # update countdown text once per second
        if remaining != last_shown:
            calib_count.text = str(remaining)
            display.refresh()
            last_shown = remaining

        # accumulate baseline samples
        ax, ay, az = imu.acceleration
        r, p = accel_to_roll_pitch(ax, ay, az)
        rs += r
        ps += p
        n += 1

        time.sleep(0.05)

    roll_ref = rs / max(1, n)
    pitch_ref = ps / max(1, n)
    return roll_ref, pitch_ref

# -----------------------------
# SESSION
# -----------------------------
def run_focus_session(minutes, roll_ref, pitch_ref):
    total_sec = minutes * 60
    start = time.monotonic()

    dur = {s: 0.0 for s in STATES}
    win_counts = {s: 0 for s in STATES}
    win_t0 = time.monotonic()

    confirmed_state = "UPRIGHT"
    candidate_state = confirmed_state
    candidate_t0 = time.monotonic()

    seg_state = confirmed_state
    seg_t0 = time.monotonic()

    clear_bubbles()
    current_lbl.text = confirmed_state
    current_lbl.color = COLORS[confirmed_state]
    info_lbl.text = "Started: 0 min"

    show_group(SESSION)

    last_sample = time.monotonic()
    last_phys = time.monotonic()

    # use last measured offsets for physics in between sensor samples
    last_roll_off = 0.0
    last_pitch_off = 0.0

    while True:
        now = time.monotonic()
        elapsed = now - start
        if elapsed >= total_sec:
            break

        # sensor + state machine at SAMPLE_DT
        if (now - last_sample) >= SAMPLE_DT:
            last_sample = now

            ax, ay, az = imu.acceleration
            roll, pitch = accel_to_roll_pitch(ax, ay, az)
            roll_off = roll - roll_ref
            pitch_off = pitch - pitch_ref
            last_roll_off = roll_off
            last_pitch_off = pitch_off

            raw_state = classify(roll_off, pitch_off)
            dur[raw_state] += SAMPLE_DT
            win_counts[raw_state] += 1

            # sustain filter
            if raw_state != candidate_state:
                candidate_state = raw_state
                candidate_t0 = now
            else:
                if (candidate_state != confirmed_state) and ((now - candidate_t0) >= SUSTAIN_SEC):
                    prev_hold = now - seg_t0
                    add_bubble(seg_state, prev_hold)

                    confirmed_state = candidate_state
                    seg_state = confirmed_state
                    seg_t0 = now

                    current_lbl.text = confirmed_state
                    current_lbl.color = COLORS[confirmed_state]

            # second line info (scale=1)
            info_lbl.text = f"Started: {int(elapsed // 60)} min"

            # optional 30s majority (currently not displayed separately)
            if (now - win_t0) >= MAJOR_WINDOW_SEC:
                win_t0 = now
                win_counts = {s: 0 for s in STATES}

        # physics at PHYSICS_DT for smooth motion + collisions
        if (now - last_phys) >= PHYSICS_DT:
            last_phys = now
            step_bubble_physics(last_pitch_off, last_roll_off)

        display.refresh()
        time.sleep(0.01)

    # close final segment bubble
    end_now = time.monotonic()
    add_bubble(seg_state, end_now - seg_t0)
    display.refresh()

    return dur, total_sec

def show_summary(dur, total_sec):
    tilt_states = ["FORWARD", "BACKWARD", "LEFT", "RIGHT"]
    major_tilt = max(tilt_states, key=lambda s: dur.get(s, 0.0))
    tilt_total = sum(dur.get(s, 0.0) for s in tilt_states)
    if total_sec > 0 and (tilt_total / total_sec) < 0.10:
        major_tilt = "UPRIGHT"

    sum_title.color = COLORS.get(major_tilt, 0xFFFFFF)
    # 1) build message
    upright = dur["UPRIGHT"]
    pct = 0.0 if total_sec <= 0 else (upright / total_sec) * 100.0

    if pct < 10:
        sum_msg.text = "Next time, sit tall\nso the little tree grows."
    elif pct < 30:
        sum_msg.text = "Not bad.\nKeep helping the tree grow."
    else:
        sum_msg.text = "Awesome!\nYour little tree is strong."

    # 2) copy current bubbles into SUMMARY background with reduced contrast
    while len(summary_bubble_layer) > 0:
        summary_bubble_layer.pop()

    # recreate circles with dim colors so they sit behind text
    for b in bubbles:
        col = COLORS.get(b["state"], 0x666666)
        col_dim = dim_color(col, factor=0.32)
        c = Circle(int(b["x"]), int(b["y"]), int(b["r"]), outline=col_dim, fill=col_dim)
        summary_bubble_layer.append(c)

    show_group(SUMMARY)

    # 3) animate background gently for 4 seconds (dynamic background)
    t0 = time.monotonic()
    # small fake tilt so background drifts slowly even if user is still
    fake_pitch = 2.0
    fake_roll = -1.5

    # We need a lightweight physics step for these summary circles (no state anchors needed)
    # We'll just do a soft drift + collision by reusing the existing bubbles velocities.
    while time.monotonic() - t0 < SUMMARY_DURATION:
        # reuse your physics but with small constant tilt (keeps it alive)
        step_bubble_physics(fake_pitch, fake_roll)

        # mirror positions into summary circles
        for i, b in enumerate(bubbles):
            try:
                sc = summary_bubble_layer[i]
                sc.x0 = int(b["x"])
                sc.y0 = int(b["y"])
            except Exception:
                pass

        display.refresh()
        time.sleep(0.05)

# -----------------------------
# READY press blink (non-blocking)
# -----------------------------
def wait_for_button_with_press_blink():
    blink_on = True
    last_toggle = time.monotonic()
    ON_TIME = 0.55
    OFF_TIME = 0.25

    while True:
        now = time.monotonic()

        # blink press line only
        if blink_on and (now - last_toggle) >= ON_TIME:
            blink_on = False
            press_group.hidden = True
            display.refresh()
            last_toggle = now
        elif (not blink_on) and (now - last_toggle) >= OFF_TIME:
            blink_on = True
            press_group.hidden = False
            display.refresh()
            last_toggle = now

        # read buttons frequently (no missed short presses)
        if not btn10.value:
            time.sleep(0.08)
            press_group.hidden = False
            return 10
        if not btn20.value:
            time.sleep(0.08)
            press_group.hidden = False
            return 20
        if not btn30.value:
            time.sleep(0.08)
            press_group.hidden = False
            return 30

        time.sleep(0.02)

def upright_setup_countdown(seconds=5):
    # Hide press blink, show calibration text
    press_group.hidden = True
    calib_lbl.hidden = False

    # Simple countdown
    t0 = time.monotonic()
    last_sec = None
    while True:
        remaining = int(seconds - (time.monotonic() - t0))
        if remaining < 0:
            break
        if remaining != last_sec:
            calib_lbl.text = f"Set upright... {remaining}s"
            display.refresh()
            last_sec = remaining
        time.sleep(0.05)

    calib_lbl.hidden = True
    press_group.hidden = False
    display.refresh()

# -----------------------------
# MAIN LOOP
# -----------------------------
enter_black()

while True:
    # 1) Wait for proximity wake
    while True:
        p = read_proximity()
        if (p is not None) and (p > PROX_THRESHOLD):
            show_group(READY)
            break
        time.sleep(0.12)

    # 2) Wait for educator button (with press blink)
    minutes = wait_for_button_with_press_blink()

    # NEW: READY disappears immediately → CALIB (5s) → baseline returned
    roll_ref, pitch_ref = calibrate_upright_with_countdown(seconds=5)

    # session starts immediately after calibration
    dur, total_sec = run_focus_session(minutes, roll_ref, pitch_ref)

    # 5) Summary + back to black
    show_summary(dur, total_sec)
    enter_black()
 