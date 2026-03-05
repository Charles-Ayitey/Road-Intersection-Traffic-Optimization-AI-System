"""
calibrate_zones.py  —  Interactive zone-polygon calibration tool
================================================================
Click 4+ points on the camera frame to define each traffic arm's
detection zone.  The tool saves normalised (0-1) coordinates that
can be pasted directly into config.json.

Usage
-----
  python vision/calibrate_zones.py                          # uses active_scenario from config.json
  python vision/calibrate_zones.py --scenario live_camera   # use a specific scenario
  python vision/calibrate_zones.py --source path/to/video.mp4
  python vision/calibrate_zones.py --source 0               # webcam index

Controls (shown in window title)
---------------------------------
  Left-click        Add point to current zone
  Right-click       Undo last point in current zone
  ENTER / N         Close current polygon and move to next arm
  R                 Reset current zone (clear all points)
  S                 Save all zones and exit
  Q / ESC           Quit without saving
"""

import cv2
import json
import os
import sys
import argparse
import logging
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# Default arms to calibrate (in order)
DEFAULT_ARMS = ["North", "South", "East", "West"]

# Colours per arm
ARM_COLORS = {
    "North": (0, 255, 0),    # green
    "South": (0, 0, 255),    # red
    "East": (255, 128, 0),   # orange
    "West": (255, 0, 255),   # magenta
}

WINDOW = "Zone Calibration  |  L-click=add  R-click=undo  ENTER=next arm  S=save  Q=quit"


def load_first_frame(source):
    """Open *source* (path string or integer webcam index) and return the first frame."""
    if isinstance(source, str) and source.isdigit():
        source = int(source)
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        log.error(f"Cannot open source: {source}")
        return None, None
    ret, frame = cap.read()
    cap.release()
    if not ret:
        log.error("Could not read first frame.")
        return None, None
    return frame, (frame.shape[1], frame.shape[0])  # (width, height)


def draw_state(base_frame, completed_zones, current_arm, current_pts, frame_wh):
    """Render all completed zones + the in-progress zone onto a copy of *base_frame*."""
    viz = base_frame.copy()
    w, h = frame_wh

    # Draw completed zones
    for arm, pts in completed_zones.items():
        color = ARM_COLORS.get(arm, (255, 255, 255))
        poly = np.array(pts, np.int32)
        cv2.polylines(viz, [poly], True, color, 2)
        cx, cy = poly.mean(axis=0).astype(int)
        cv2.putText(viz, arm, (cx - 20, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)

    # Draw current in-progress zone
    if current_pts:
        color = ARM_COLORS.get(current_arm, (0, 255, 255))
        pts_arr = np.array(current_pts, np.int32)
        cv2.polylines(viz, [pts_arr], False, color, 2)
        for pt in current_pts:
            cv2.circle(viz, pt, 5, color, -1)

    # HUD overlay
    instructions = [
        f"Arm: {current_arm}  ({len(current_pts)} pts)",
        "L-click=add  R-click=undo  ENTER=next arm",
        "R=reset arm  S=save  Q=quit",
    ]
    for i, line in enumerate(instructions):
        cv2.putText(viz, line, (10, 25 + i * 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(viz, line, (10, 25 + i * 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)

    return viz


def normalise(pts, frame_wh):
    """Convert pixel (x, y) tuples to normalised [0-1] pairs."""
    w, h = frame_wh
    return [[round(x / w, 6), round(y / h, 6)] for x, y in pts]


def run_calibration(base_frame, frame_wh, arms):
    """Run the interactive OpenCV loop.  Returns dict arm→pixel_pts or None on quit."""
    completed = {}     # arm_name → list of pixel (x,y)
    arm_idx = 0
    current_pts = []
    done = False
    save = False

    def on_mouse(event, x, y, flags, param):
        nonlocal current_pts
        if event == cv2.EVENT_LBUTTONDOWN:
            current_pts.append((x, y))
        elif event == cv2.EVENT_RBUTTONDOWN:
            if current_pts:
                current_pts.pop()

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW, min(frame_wh[0], 1280), min(frame_wh[1], 720))
    cv2.setMouseCallback(WINDOW, on_mouse)

    while not done:
        current_arm = arms[arm_idx]
        viz = draw_state(base_frame, completed, current_arm, current_pts, frame_wh)
        cv2.imshow(WINDOW, viz)
        key = cv2.waitKey(30) & 0xFF

        if key in (13, ord('n')):          # ENTER or N → close arm
            if len(current_pts) < 3:
                log.warning(f"{current_arm}: need at least 3 points to close polygon.")
            else:
                completed[current_arm] = list(current_pts)
                log.info(f"{current_arm}: {len(current_pts)} points saved.")
                current_pts = []
                arm_idx += 1
                if arm_idx >= len(arms):
                    log.info("All arms calibrated.")
                    done = True
                    save = True

        elif key == ord('r'):              # R → reset current arm
            current_pts = []
            log.info(f"{current_arm}: reset.")

        elif key == ord('s'):              # S → save whatever we have and exit
            if len(current_pts) >= 3:
                completed[current_arm] = list(current_pts)
            done = True
            save = True

        elif key in (ord('q'), 27):        # Q or ESC → quit without saving
            done = True
            save = False

    cv2.destroyAllWindows()
    return completed if save else None


def build_zone_config(completed_pixel_pts, frame_wh):
    """Convert pixel coordinates to the config.json zones array."""
    zones = []
    for arm, pts in completed_pixel_pts.items():
        normalised = normalise(pts, frame_wh)
        zones.append({
            "name": f"{arm} Arm",
            "map_to": arm,
            "polygon": normalised,
        })
    return zones


def main():
    parser = argparse.ArgumentParser(description="Interactive zone calibration tool")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    parser.add_argument("--scenario", default=None,
                        help="Scenario name to calibrate (overrides active_scenario)")
    parser.add_argument("--source", default=None,
                        help="Video file or RTSP URL or webcam index (overrides config source)")
    parser.add_argument("--arms", nargs="+", default=DEFAULT_ARMS,
                        help="Arm names to calibrate in order (default: North South East West)")
    parser.add_argument("--output", default="vision/zones_calibrated.json",
                        help="Where to write calibrated zones JSON")
    args = parser.parse_args()

    # --- Resolve source ---
    source = args.source
    if source is None:
        config_path = args.config
        if not os.path.isfile(config_path):
            # Try one level up (running from vision/ subfolder)
            config_path = os.path.join(os.path.dirname(__file__), "..", args.config)
        with open(config_path) as f:
            cfg = json.load(f)
        scenario_name = args.scenario or cfg.get("active_scenario", "traffic_test")
        scenario = cfg["scenarios"].get(scenario_name)
        if not scenario:
            log.error(f"Scenario '{scenario_name}' not found in config.")
            sys.exit(1)
        # Prefer first video_list entry, then source
        video_list = scenario.get("video_list", [])
        if video_list:
            root = os.path.dirname(os.path.dirname(os.path.abspath(config_path)))
            source = os.path.join(root, video_list[0].replace("/", os.sep))
        else:
            source = scenario.get("source")
        if not source:
            log.error("No video source found in scenario config.  Pass --source explicitly.")
            sys.exit(1)
        log.info(f"Using source from scenario '{scenario_name}': {source}")

    # --- Load first frame ---
    frame, frame_wh = load_first_frame(source)
    if frame is None:
        sys.exit(1)
    log.info(f"Frame size: {frame_wh[0]}×{frame_wh[1]}  |  Arms to calibrate: {args.arms}")

    # --- Interactive calibration ---
    print("\n" + "="*60)
    print("  ZONE CALIBRATION TOOL")
    print("="*60)
    print(f"  Source : {source}")
    print(f"  Arms   : {args.arms}")
    print(f"  Click points on the frame to define each zone polygon.")
    print(f"  Press ENTER when each arm is done.  S to save early.  Q to quit.")
    print("="*60 + "\n")

    result = run_calibration(frame, frame_wh, args.arms)
    if result is None:
        log.info("Calibration cancelled — nothing saved.")
        sys.exit(0)

    # --- Build output ---
    zones = build_zone_config(result, frame_wh)

    output_data = {
        "scenario": args.scenario or "calibrated",
        "source_used": str(source),
        "frame_size": {"width": frame_wh[0], "height": frame_wh[1]},
        "zones": zones,
    }

    output_path = args.output
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)
    log.info(f"Zones saved to: {os.path.abspath(output_path)}")

    # --- Print paste-ready snippet ---
    print("\n" + "="*60)
    print("  PASTE INTO config.json  →  scenarios.<name>.zones")
    print("="*60)
    print(json.dumps(zones, indent=4))
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
