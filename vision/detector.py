import cv2
import numpy as np
import json
import os
import time
import requests
from ultralytics import YOLO

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
    def __init__(self, config_path='config.json'):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
            
        self.model = YOLO(self.config.get('yolo_model', 'yolov8n.pt'))
        self.vehicle_classes = [2, 3, 5, 7]
        self.zones = []
        
        # Load the active scenario
        active_name = self.config.get('active_scenario', 'traffic_test')
        self.scenario = self.config['scenarios'].get(active_name)
        if not self.scenario:
            raise ValueError(f"Scenario '{active_name}' not found in config.")
            
        for z in self.scenario.get('zones', []):
            self.zones.append(ZoneCounter(z['name'], z['polygon'], z.get('map_to', 'North')))
            
        self.api_url = self.config.get('api_url', 'http://localhost:8000/update_counts')
        self.polygons_scaled = False

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
        except Exception: pass

    def process_video(self, show=True):
        source = self.scenario.get('source')
        cap = cv2.VideoCapture(source)
        
        print(f"🎬 Scenario: {self.config['active_scenario']} | Source: {source}")
        
        frame_idx = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0) # Loop video
                continue
            
            if frame_idx % 5 == 0:
                detections, counts = self.detect_and_count(frame)
                self.report_to_api(counts)
                
                if show:
                    for zone in self.zones:
                        cv2.polylines(frame, [zone.polygon], True, (255, 255, 0), 2)
                        cv2.putText(frame, f"{zone.name}: {zone.count}", (zone.polygon[0][0], zone.polygon[0][1]-10), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                    cv2.imshow('Traffic Vision Pipeline', frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'): break
            frame_idx += 1
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    detector = VehicleDetector()
    detector.process_video(show=False)
