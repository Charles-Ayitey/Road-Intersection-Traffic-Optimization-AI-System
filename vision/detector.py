import cv2
import numpy as np
import json
import os
import time
import logging
import requests
from ultralytics import YOLO

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

class ZoneCounter:
    def __init__(self, name, normalized_polygon, map_to):
        self.name = name
        self.normalized_polygon = np.array(normalized_polygon, np.float32)
        self.polygon = None # To be scaled later
        self.map_to = map_to
        self.count = 0

    def scale_polygon(self, width, height):
        self.polygon = (self.normalized_polygon * [width, height]).astype(np.int32)

    def is_inside(self, point):
        if self.polygon is None: return False
        return cv2.pointPolygonTest(self.polygon, (point[0], point[1]), False) >= 0

class VehicleDetector:
    # Supported video extensions to auto-discover in data/
    VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}

    def __init__(self, config_path='config.json'):
        with open(config_path, 'r') as f:
            self.config = json.load(f)

        self.model = YOLO(self.config.get('yolo_model', 'yolov8n.pt'))
        self.vehicle_classes = [2, 3, 5, 7]
        self.zones = []

        active_name = self.config.get('active_scenario', 'traffic_test')
        self.scenario = self.config['scenarios'].get(active_name)
        if not self.scenario:
            raise ValueError(f"Scenario '{active_name}' not found in config.")

        for z in self.scenario.get('zones', []):
            self.zones.append(ZoneCounter(z['name'], z['polygon'], z.get('map_to', 'North')))

        self.api_url = self.config.get('api_url', 'http://localhost:8000/update_counts')
        self.polygons_scaled = False

        # Build video playlist: all .mp4/.avi/etc in data/ folder
        self._playlist = self._discover_videos()
        self._playlist_index = 0
        log.info(f"Video playlist ({len(self._playlist)} video(s)): {self._playlist}")

    def _discover_videos(self):
        """Build the video playlist for this scenario.

        Priority order:
          1. scenario['video_list'] — explicit allowlist of geometrically
             compatible videos for this camera perspective.  Paths are relative
             to the project root.
          2. Auto-discover all video files in data/ — used only when no
             video_list is specified (e.g. simple single-camera scenarios).
          3. Fall back to scenario['source'] if neither produces results.

        The 34 Ghanaian training videos in data/ are SUMO training data, not
        vision-pipeline sources.  Street-level footage cannot produce correct
        N/S/E/W counts from top-down zone polygons, so they must not be
        included in the playlist for top-down scenarios.
        """
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # 1. Explicit video_list in scenario config
        explicit = self.scenario.get('video_list')
        if explicit:
            videos = []
            for rel_path in explicit:
                abs_path = os.path.join(root, rel_path.replace('/', os.sep))
                if os.path.isfile(abs_path):
                    videos.append(abs_path)
                else:
                    log.warning(f"video_list entry not found, skipping: {rel_path}")
            if videos:
                return videos
            log.warning("video_list specified but no files found; falling back to auto-discover.")

        # 2. Auto-discover data/ (no video_list configured)
        data_dir = os.path.join(root, "data")
        videos = []
        if os.path.isdir(data_dir):
            for fname in sorted(os.listdir(data_dir)):
                if os.path.splitext(fname)[1].lower() in self.VIDEO_EXTENSIONS:
                    videos.append(os.path.join(data_dir, fname))
        if videos:
            return videos

        # 3. Fallback to config source
        fallback = self.scenario.get('source')
        if fallback:
            log.warning(f"No videos found in data/. Falling back to config source: {fallback}")
            return [fallback]
        return []

    def detect_and_count(self, frame):
        h, w = frame.shape[:2]
        if not self.polygons_scaled:
            for zone in self.zones:
                zone.scale_polygon(w, h)
            self.polygons_scaled = True

        conf_thresh = self.config.get('confidence_threshold', 0.25)
        results = self.model(frame, classes=self.vehicle_classes, conf=conf_thresh, verbose=False)
        
        detections = []
        for zone in self.zones: zone.count = 0

        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                center_bottom = [int((x1 + x2) / 2), int(y2)]
                
                detections.append({'bbox': [int(x1), int(y1), int(x2), int(y2)], 'center_bottom': center_bottom})

                for zone in self.zones:
                    if zone.is_inside(center_bottom):
                        zone.count += 1
                        
        return detections, {zone.name: zone.count for zone in self.zones}

    def report_to_api(self, counts_dict):
        """Aggregate counts by their 'map_to' direction and send to API"""
        api_counts = {"North": 0, "South": 0, "East": 0, "West": 0}
        for zone in self.zones:
            if zone.map_to in api_counts:
                api_counts[zone.map_to] += zone.count

        try:
            payload = {"counts": api_counts, "timestamp": time.time()}
            requests.post(self.api_url, json=payload, timeout=0.1)
        except requests.RequestException as e:
            log.warning(f"Failed to report counts to API: {e}")

    def _is_live_source(self, source) -> bool:
        """Return True if source is a live stream (not a local file)."""
        if isinstance(source, int):
            return True  # webcam index
        s = str(source)
        return s.startswith("rtsp://") or s.startswith("http://") or s.startswith("https://")

    def process_video(self, show=True):
        live = self.scenario.get("reconnect_on_drop", False) or (
            not self._playlist and self._is_live_source(self.scenario.get("source", ""))
        )

        if live:
            self._process_live_stream(show)
        else:
            self._process_playlist(show)

    def _process_live_stream(self, show=True):
        """Continuously read from a live camera, reconnecting on drop."""
        source = self.scenario.get("source")
        # Allow integer webcam index stored as string in JSON
        try:
            source = int(source)
        except (ValueError, TypeError):
            pass

        log.info(f"Opening live stream: {source}")
        RECONNECT_DELAY = 3  # seconds between reconnect attempts

        while True:
            cap = cv2.VideoCapture(source)
            if not cap.isOpened():
                log.error(f"Cannot open stream '{source}'. Retrying in {RECONNECT_DELAY}s...")
                time.sleep(RECONNECT_DELAY)
                continue

            log.info("Live stream connected.")
            self.polygons_scaled = False
            frame_idx = 0

            while True:
                ret, frame = cap.read()
                if not ret:
                    log.warning("Stream dropped. Reconnecting...")
                    cap.release()
                    time.sleep(RECONNECT_DELAY)
                    break  # break inner loop → reconnect outer loop

                if frame_idx % 5 == 0:
                    detections, counts = self.detect_and_count(frame)
                    self.report_to_api(counts)

                    if show:
                        for zone in self.zones:
                            cv2.polylines(frame, [zone.polygon], True, (0, 255, 255), 2)
                            cv2.putText(frame, f"{zone.map_to}: {zone.count}",
                                        (zone.polygon[0][0], zone.polygon[0][1] - 10),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                        cv2.imshow("Traffic Vision Pipeline (LIVE)", frame)
                        if cv2.waitKey(1) & 0xFF == ord('q'):
                            cap.release()
                            cv2.destroyAllWindows()
                            return
                frame_idx += 1

    def _process_playlist(self, show=True):
        if not self._playlist:
            log.error("Playlist is empty — no videos to process.")
            return

        source = self._playlist[self._playlist_index]
        log.info(f"Starting playlist at video {self._playlist_index + 1}/{len(self._playlist)}: {os.path.basename(source)}")
        cap = cv2.VideoCapture(source)

        frame_idx = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                # End of this video — advance to next in playlist
                cap.release()
                self._playlist_index = (self._playlist_index + 1) % len(self._playlist)
                source = self._playlist[self._playlist_index]
                log.info(f"Switching to video {self._playlist_index + 1}/{len(self._playlist)}: {os.path.basename(source)}")
                cap = cv2.VideoCapture(source)
                self.polygons_scaled = False  # rescale zones for new video resolution
                frame_idx = 0
                continue

            if frame_idx % 5 == 0:
                detections, counts = self.detect_and_count(frame)
                self.report_to_api(counts)

                if show:
                    for zone in self.zones:
                        cv2.polylines(frame, [zone.polygon], True, (255, 255, 0), 2)
                        cv2.putText(frame, f"{zone.name}: {zone.count}",
                                    (zone.polygon[0][0], zone.polygon[0][1] - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                    cv2.imshow('Traffic Vision Pipeline', frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
            frame_idx += 1

        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    detector = VehicleDetector()
    detector.process_video(show=False)
