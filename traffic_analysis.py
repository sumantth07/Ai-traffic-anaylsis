"""
HỆ THỐNG PHÂN TÍCH VIDEO GIAO THÔNG THÔNG MINH (ITS)
Sử dụng: YOLOv8 + ByteTrack + Speed Estimation

Tác giả: ITS Research Team
Ngày tạo: 2024
Phiên bản: 1.0

Chức năng:
- Phát hiện phương tiện (YOLO)
- Theo dõi phương tiện (ByteTrack)
- Đếm xe qua line
- Tính tốc độ
- Xuất video + CSV thống kê
"""

import os
import csv
import json
import logging
import subprocess
import tempfile
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Callable
from pathlib import Path

import cv2
import numpy as np

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Thử import YOLO, nếu không có thì hướng dẫn cài
try:
    from ultralytics import YOLO
    logger.info("✓ YOLO library loaded successfully")
except ImportError:
    logger.error("✗ YOLOv8 not installed. Install: pip install ultralytics")
    exit(1)

# ==================== DATA CLASSES ====================

@dataclass
class BoundingBox:
    """Lớp đại diện cho bounding box"""
    x1: float  # Tọa độ góc trên trái X
    y1: float  # Tọa độ góc trên trái Y
    x2: float  # Tọa độ góc dưới phải X
    y2: float  # Tọa độ góc dưới phải Y
    
    @property
    def width(self) -> float:
        """Chiều rộng"""
        return self.x2 - self.x1
    
    @property
    def height(self) -> float:
        """Chiều cao"""
        return self.y2 - self.y1
    
    @property
    def center(self) -> Tuple[float, float]:
        """Điểm trung tâm (centroid)"""
        cx = (self.x1 + self.x2) / 2
        cy = (self.y1 + self.y2) / 2
        return (cx, cy)
    
    def iou(self, other: 'BoundingBox') -> float:
        """
        Tính Intersection over Union (IoU) - độ chồng lấp
        
        Args:
            other: BoundingBox khác
            
        Returns:
            float: IoU từ 0 đến 1 (1 = hoàn toàn trùng)
        """
        # Tính tọa độ giao nhau
        x1_inter = max(self.x1, other.x1)
        y1_inter = max(self.y1, other.y1)
        x2_inter = min(self.x2, other.x2)
        y2_inter = min(self.y2, other.y2)
        
        # Nếu không giao nhau
        if x2_inter < x1_inter or y2_inter < y1_inter:
            return 0.0
        
        # Tính diện tích giao nhau
        inter_area = (x2_inter - x1_inter) * (y2_inter - y1_inter)
        
        # Tính diện tích hợp
        box1_area = self.width * self.height
        box2_area = other.width * other.height
        union_area = box1_area + box2_area - inter_area
        
        # Tránh chia cho 0
        if union_area == 0:
            return 0.0
        
        return inter_area / union_area


@dataclass
class Detection:
    """Lớp đại diện cho 1 detection từ YOLO"""
    bbox: BoundingBox    # Bounding box
    class_id: int        # ID class (0=person, 1=car, 2=bike, ...)
    class_name: str      # Tên class ("car", "bike", ...)
    confidence: float    # Confidence score (0-1)
    frame_id: int        # Frame ID (frame nào)


class VehicleTrack:
    """
    Lớp đại diện cho 1 phương tiện đang được tracking
    
    Attributes:
        track_id: ID duy nhất của phương tiện
        class_name: Loại xe (car, bike, bus, truck, ...)
        positions: Lịch sử vị trí centroid qua các frame
        bboxes: Lịch sử bounding boxes
        ages: Tuổi track (số frame tồn tại)
        hits: Số frame liên tiếp được match (detection)
        time_since_update: Số frame chưa được update
        crossed_line: Đã cắt qua counting line chưa?
        speed_history: Lịch sử tốc độ
    """
    
    def __init__(self, track_id: int, class_name: str, 
                 initial_bbox: BoundingBox, frame_id: int):
        """
        Khởi tạo track mới
        
        Args:
            track_id: ID duy nhất
            class_name: Tên loại xe
            initial_bbox: Bounding box ban đầu
            frame_id: Frame ID
        """
        self.track_id = track_id
        self.class_name = class_name
        self.positions = deque(maxlen=100)  # Lưu 100 vị trí gần nhất
        self.bboxes = deque(maxlen=100)
        self.positions.append(initial_bbox.center)
        self.bboxes.append(initial_bbox)
        
        self.age = 1  # Số frame từ lúc bắt đầu
        self.hits = 1  # Số frame liên tiếp được match
        self.time_since_update = 0
        
        self.crossed_line = False  # Chưa cắt qua counting line
        self.speed_history = []  # Lịch sử tốc độ
        self.frame_started = frame_id
        self.last_frame_id = frame_id
        
    def update(self, bbox: BoundingBox, frame_id: int):
        """
        Cập nhật track khi có detection match
        
        Args:
            bbox: Bounding box mới
            frame_id: Frame ID hiện tại
        """
        self.positions.append(bbox.center)
        self.bboxes.append(bbox)
        self.age += 1
        self.hits += 1
        self.time_since_update = 0
        self.last_frame_id = frame_id
        
    def predict(self):
        """Dự đoán vị trí tiếp theo (nếu không có detection)"""
        self.age += 1
        self.time_since_update += 1
        # Trong thực tế, có thể dùng Kalman Filter
        # Tạm thời dùng vị trí cuối cùng
        
    def get_current_position(self) -> Tuple[float, float]:
        """Lấy vị trí hiện tại"""
        return self.positions[-1] if self.positions else (0, 0)
    
    def get_current_bbox(self) -> BoundingBox:
        """Lấy bbox hiện tại"""
        return self.bboxes[-1] if self.bboxes else None
    
    def add_speed(self, speed: float):
        """Thêm tốc độ vào lịch sử"""
        self.speed_history.append(speed)
    
    def get_average_speed(self) -> float:
        """Tính tốc độ trung bình"""
        if not self.speed_history:
            return 0.0
        return sum(self.speed_history) / len(self.speed_history)
    
    def get_max_speed(self) -> float:
        """Lấy tốc độ cao nhất"""
        return max(self.speed_history) if self.speed_history else 0.0


# ==================== MAIN TRAFFIC ANALYZER ====================

class TrafficAnalyzer:
    """
    Lớp chính để phân tích video giao thông
    
    Pipeline:
    1. Load frame từ video
    2. Detect vehicles bằng YOLO
    3. Track vehicles qua frames
    4. Detect line crossing
    5. Tính tốc độ
    6. Vẽ kết quả
    7. Xuất CSV
    """
    
    def __init__(self, 
                 video_path: str,
                 model_path: str = 'yolov8n.pt',
                 output_video_path: str = None,  # Sẽ tự động tạo nếu None
                 output_csv_path: str = 'traffic_statistics.csv',
                 output_json_path: str = 'traffic_statistics_frames.json',
                 conf_threshold: float = 0.5,
                 iou_threshold: float = 0.5,
                 track_iou_threshold: float = 0.3,
                 reid_iou_threshold: float = 0.25,
                 max_age: int = 60,
                 reid_max_age: int = 150,
                 min_track_frames: int = 10):
        """
        Khởi tạo Traffic Analyzer
        
        Args:
            video_path: Đường dẫn video đầu vào
            model_path: Đường dẫn model YOLO (hoặc 'yolov8n.pt', 'yolov8s.pt', ...)
            output_video_path: Đường dẫn video đầu ra (None = tự động tạo theo timestamp)
            output_csv_path: Đường dẫn CSV thống kê
            output_json_path: Đường dẫn JSON kết quả theo frame
            conf_threshold: Confidence threshold cho YOLO
            iou_threshold: IoU threshold cho NMS
        """
        self.video_path = video_path
        
        # Tạo thư mục output_video nếu chưa có
        output_dir = Path("output_video")
        output_dir.mkdir(exist_ok=True)
        
        # Tự động tạo tên file theo timestamp nếu không được chỉ định
        if output_video_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_video_path = str(output_dir / f"{timestamp}.mp4")
        
        self.output_video_path = output_video_path
        self.output_csv_path = output_csv_path
        self.output_json_path = output_json_path
        
        # Cấu hình YOLO
        logger.info(f"📥 Loading YOLO model from {model_path}...")
        self.model = YOLO(model_path)
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.track_iou_threshold = track_iou_threshold
        self.reid_iou_threshold = reid_iou_threshold
        self.max_age = max_age
        self.reid_max_age = reid_max_age
        self.min_track_frames = min_track_frames
        
        # Theo dõi phương tiện
        self.tracks: Dict[int, VehicleTrack] = {}  # {track_id: VehicleTrack}
        self.next_track_id = 1
        self.dead_tracks: List[VehicleTrack] = []  # Lưu track đã chết (để thống kê)
        self.lost_tracks: Dict[int, VehicleTrack] = {}
        self.lost_track_frames: Dict[int, int] = {}
        
        # Cấu hình đếm xe
        self.counting_line_y = None  # Y-coordinate của line đếm
        self.counting_line_type = 'horizontal'  # 'horizontal' hoặc 'vertical'
        self.vehicle_count = 0  # Tổng số xe cắt qua line
        
        # Cấu hình tốc độ
        self.fps = 30  # Frame per second (sẽ được update từ video)
        self.pixels_per_meter = 1.0  # Tỷ lệ calibration (cần tính toán)
        
        # Lưu trữ dữ liệu thống kê
        self.statistics = []  # List of dicts: {frame_id, vehicle_id, class_name, speed, ...}
        self.frame_data = {}  # Dict: {frame_id: [track_data_list]} - Lưu kết quả theo frame
        
        # Video reader/writer
        self.cap = None
        self.out = None

    def filter_valid_tracks(self, tracks: List[VehicleTrack]) -> List[VehicleTrack]:
        """Lọc track quá ngắn để giảm đếm ảo."""
        if self.min_track_frames <= 1:
            return tracks
        return [t for t in tracks if len(t.positions) >= self.min_track_frames]
        
    def load_video(self) -> bool:
        """
        Tải video và lấy thông tin
        
        Returns:
            bool: True nếu thành công
        """
        try:
            self.cap = cv2.VideoCapture(self.video_path)
            if not self.cap.isOpened():
                logger.error(f"❌ Cannot open video: {self.video_path}")
                return False
            
            # Lấy thông tin video
            self.fps = self.cap.get(cv2.CAP_PROP_FPS)
            self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            logger.info(f"✓ Video loaded successfully")
            logger.info(f"  Resolution: {self.frame_width}x{self.frame_height}")
            logger.info(f"  FPS: {self.fps}")
            logger.info(f"  Total frames: {self.total_frames}")
            logger.info(f"  Duration: {self.total_frames / self.fps:.1f} seconds")
            
            # Setup video writer
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # Codec MP4
            self.out = cv2.VideoWriter(
                self.output_video_path, fourcc, self.fps,
                (self.frame_width, self.frame_height)
            )
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error loading video: {e}")
            return False
    
    def set_counting_line(self, y: Optional[int] = None):
        """
        Thiết lập đường đếm
        
        Args:
            y: Y-coordinate của line (nếu horizontal)
               Nếu None, dùng 2/3 chiều cao video
        """
        if y is None:
            # If frame_height is not set yet, we'll set it later in load_video
            if hasattr(self, 'frame_height') and self.frame_height > 0:
                y = int(self.frame_height * 2 / 3)
            else:
                # Placeholder - will be set in load_video or process_video
                y = None
        
        if y is not None:
            self.counting_line_y = y
            logger.info(f"📍 Counting line set at Y={y}")
        else:
            self.counting_line_y = None
            logger.info(f"📍 Counting line will be auto-set based on video resolution")
    
    def set_calibration(self, reference_object_pixels: int, 
                       reference_object_meters: float = 4.5):
        """
        Calibrate tỷ lệ pixel → mét
        
        Ví dụ: Xe dài ~4.5m, trong video dài 150 pixels
               → pixels_per_meter = 150 / 4.5 = 33.33
        
        Args:
            reference_object_pixels: Chiều dài object trong video (pixels)
            reference_object_meters: Chiều dài thực tế (meters)
        """
        if reference_object_pixels <= 0:
            logger.error("❌ Invalid reference object size")
            return
        
        self.pixels_per_meter = reference_object_pixels / reference_object_meters
        logger.info(f"📏 Calibration set: {self.pixels_per_meter:.2f} pixels/meter")
    
    def detect_vehicles(self, frame: np.ndarray) -> List[Detection]:
        """
        Phát hiện phương tiện trong frame bằng YOLO
        
        Args:
            frame: Input frame (H x W x 3)
            
        Returns:
            List[Detection]: Danh sách detections
        """
        # Chạy YOLO inference
        results = self.model(frame, conf=self.conf_threshold, 
                           iou=self.iou_threshold, verbose=False)
        
        detections = []
        
        # Parse kết quả
        for result in results:
            for box in result.boxes:
                # Lấy thông tin
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                class_id = int(box.cls[0])
                class_name = result.names[class_id]
                confidence = float(box.conf[0])
                
                # Filter: chỉ lấy các class liên quan đến xe
                vehicle_classes = ['car', 'motorbike', 'bicycle', 'bus', 'truck', 'motorcycle']
                if class_name.lower() not in vehicle_classes:
                    continue
                
                # Tạo Detection object
                bbox = BoundingBox(x1, y1, x2, y2)
                det = Detection(
                    bbox=bbox,
                    class_id=class_id,
                    class_name=class_name,
                    confidence=confidence,
                    frame_id=0  # Sẽ được set ngoài
                )
                detections.append(det)
        
        return detections
    
    def match_detections_to_tracks(self, detections: List[Detection]) -> Tuple[Dict, List]:
        """
        Gán detections tới tracks hiện tại bằng Hungarian Algorithm (tối ưu)
        
        Args:
            detections: Danh sách detections
            
        Returns:
            Tuple: (matched_dict: {track_id: detection}, unmatched_detections: [])
        """
        matched = {}
        unmatched_dets = list(range(len(detections)))
        
        if not self.tracks or not detections:
            return matched, unmatched_dets
        
        track_ids = list(self.tracks.keys())
        if not track_ids:
            return matched, unmatched_dets

        # Hungarian Algorithm (simple greedy version)
        # Trong thực tế, dùng scipy.optimize.linear_sum_assignment
        matched_indices = []
        used_dets = set()
        
        for i in range(len(track_ids)):
            # Tìm detection có cost nhỏ nhất
            best_j = -1
            best_iou = 0.0
            
            for j in range(len(detections)):
                if j in used_dets:
                    continue
                det = detections[j]
                track = self.tracks[track_ids[i]]
                if det.class_name != track.class_name:
                    continue
                current_bbox = track.get_current_bbox()
                if current_bbox is None:
                    continue
                iou = current_bbox.iou(det.bbox)
                if iou >= self.track_iou_threshold and iou > best_iou:
                    best_j = j
                    best_iou = iou
            
            if best_j >= 0:
                track_id = track_ids[i]
                matched[track_id] = detections[best_j]
                used_dets.add(best_j)
                if best_j in unmatched_dets:
                    unmatched_dets.remove(best_j)
        
        return matched, unmatched_dets

    def reidentify_lost_tracks(self, detections: List[Detection], 
                               unmatched_dets: List[int], frame_id: int) -> Tuple[Dict, List[int]]:
        """
        Gán lại ID cho detections dựa trên lost tracks (re-identification đơn giản bằng IoU).
        """
        matched = {}
        if not self.lost_tracks or not unmatched_dets:
            return matched, unmatched_dets

        used_lost = set()
        remaining = list(unmatched_dets)

        for det_idx in list(remaining):
            det = detections[det_idx]
            best_track_id = None
            best_iou = 0.0

            for track_id, track in self.lost_tracks.items():
                if track_id in used_lost:
                    continue
                lost_frame = self.lost_track_frames.get(track_id, frame_id)
                if frame_id - lost_frame > self.reid_max_age:
                    continue
                if det.class_name != track.class_name:
                    continue
                current_bbox = track.get_current_bbox()
                if current_bbox is None:
                    continue
                iou = current_bbox.iou(det.bbox)
                if iou >= self.reid_iou_threshold and iou > best_iou:
                    best_iou = iou
                    best_track_id = track_id

            if best_track_id is not None:
                matched[best_track_id] = det
                used_lost.add(best_track_id)
                remaining.remove(det_idx)

        return matched, remaining
    
    def update_tracks(self, matched: Dict, unmatched_dets: List, 
                     detections: List[Detection], frame_id: int):
        """
        Update tracks với matched detections, xóa old tracks, tạo track mới
        
        Args:
            matched: Dict {track_id: detection}
            unmatched_dets: List indices của unmatched detections
            detections: Toàn bộ detections
            frame_id: Frame ID hiện tại
        """
        # Update matched tracks
        for track_id, det in matched.items():
            self.tracks[track_id].update(det.bbox, frame_id)
        
        # Predict cho unmatched tracks
        unmatched_tracks = [tid for tid in self.tracks if tid not in matched]
        for track_id in unmatched_tracks:
            self.tracks[track_id].predict()
        
        # Chuyển tracks quá hạn sang lost để chờ re-ID
        dead_ids = []
        for track_id, track in self.tracks.items():
            if track.time_since_update > self.max_age:
                dead_ids.append(track_id)
                self.lost_tracks[track_id] = track
                self.lost_track_frames[track_id] = frame_id
        
        for track_id in dead_ids:
            del self.tracks[track_id]

        # Re-ID bằng lost tracks trước khi tạo ID mới
        reid_matched, unmatched_dets = self.reidentify_lost_tracks(
            detections, unmatched_dets, frame_id
        )
        for track_id, det in reid_matched.items():
            track = self.lost_tracks.pop(track_id)
            self.lost_track_frames.pop(track_id, None)
            track.update(det.bbox, frame_id)
            self.tracks[track_id] = track

        # Loại bỏ lost quá lâu -> dead
        expired_lost = []
        for track_id, lost_frame in self.lost_track_frames.items():
            if frame_id - lost_frame > self.reid_max_age:
                expired_lost.append(track_id)
                self.dead_tracks.append(self.lost_tracks[track_id])
        for track_id in expired_lost:
            del self.lost_tracks[track_id]
            del self.lost_track_frames[track_id]
        
        # Tạo track mới cho unmatched detections
        for det_idx in unmatched_dets:
            det = detections[det_idx]
            track = VehicleTrack(
                track_id=self.next_track_id,
                class_name=det.class_name,
                initial_bbox=det.bbox,
                frame_id=frame_id
            )
            self.tracks[self.next_track_id] = track
            self.next_track_id += 1
    
    def detect_line_crossing(self):
        """
        Kiểm tra phương tiện nào vừa cắt qua counting line
        
        Returns:
            List[int]: Danh sách track_id của xe vừa cắt qua
        """
        crossed_ids = []
        
        if self.counting_line_y is None:
            return crossed_ids
        
        for track_id, track in self.tracks.items():
            if len(track.positions) < 2:
                continue
            
            prev_pos = track.positions[-2]
            curr_pos = track.positions[-1]
            
            # Nếu chưa qua line mà bây giờ qua rồi
            if not track.crossed_line:
                if self.counting_line_type == 'horizontal':
                    # Line ngang: kiểm tra Y-coordinate
                    if prev_pos[1] < self.counting_line_y <= curr_pos[1]:
                        track.crossed_line = True
                        crossed_ids.append(track_id)
        
        return crossed_ids
    
    def calculate_speed(self, track_id: int) -> float:
        """
        Tính tốc độ của phương tiện
        
        Args:
            track_id: ID của track
            
        Returns:
            float: Tốc độ (km/h)
        """
        track = self.tracks.get(track_id)
        if not track or len(track.positions) < 2:
            return 0.0
        
        # Lấy 2 vị trí cách nhau 5 frame
        if len(track.positions) < 6:
            interval = 1
        else:
            interval = 5
        
        prev_pos = track.positions[-interval - 1]
        curr_pos = track.positions[-1]
        
        # Tính khoảng cách pixel
        delta_x = curr_pos[0] - prev_pos[0]
        delta_y = curr_pos[1] - prev_pos[1]
        delta_pixels = np.sqrt(delta_x**2 + delta_y**2)
        
        # Tính thời gian
        delta_time = interval / self.fps  # giây
        
        if delta_time == 0:
            return 0.0
        
        # Tính vận tốc
        velocity_pixels_per_sec = delta_pixels / delta_time
        velocity_meters_per_sec = velocity_pixels_per_sec / self.pixels_per_meter
        velocity_kmh = velocity_meters_per_sec * 3.6
        
        # Bộ lọc: tốc độ thực tế nên < 150 km/h
        if velocity_kmh > 150:
            velocity_kmh = 0.0
        
        return velocity_kmh
    
    def draw_results(self, frame: np.ndarray, frame_id: int) -> np.ndarray:
        """
        Vẽ bounding box, ID, tốc độ, trajectory, line lên frame
        
        Args:
            frame: Input frame
            frame_id: Frame ID
            
        Returns:
            np.ndarray: Frame với kết quả vẽ
        """
        result_frame = frame.copy()
        
        # Lưu tracking data cho frame này
        frame_tracks = []
        
        # Vẽ counting line
        if self.counting_line_y:
            cv2.line(result_frame, (0, self.counting_line_y), 
                    (self.frame_width, self.counting_line_y),
                    (0, 255, 255), 2)  # Vàng
            cv2.putText(result_frame, 'Counting Line', (10, self.counting_line_y - 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        
        # Vẽ từng track
        colors = {}  # {track_id: (B, G, R)}
        
        for track_id, track in self.tracks.items():
            bbox = track.get_current_bbox()
            if not bbox:
                continue
            
            # Màu dựa trên track_id (xác định duy nhất)
            if track_id not in colors:
                np.random.seed(track_id)  # Seed để màu nhất quán
                colors[track_id] = tuple(np.random.randint(0, 256, 3).tolist())
            
            color = colors[track_id]
            
            # Vẽ bounding box
            cv2.rectangle(result_frame, (int(bbox.x1), int(bbox.y1)), 
                         (int(bbox.x2), int(bbox.y2)), color, 2)
            
            # Tính tốc độ
            speed = self.calculate_speed(track_id)
            if speed > 0:
                track.add_speed(speed)
            
            # Viết ID và tốc độ
            label = f"ID:{track_id} {track.class_name.upper()} {speed:.1f}km/h"
            cv2.putText(result_frame, label, 
                       (int(bbox.x1), int(bbox.y1) - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            
            # Vẽ trajectory (đường di chuyển)
            if len(track.positions) > 2:
                points = [tuple(map(int, pos)) for pos in track.positions]
                for i in range(1, len(points)):
                    cv2.line(result_frame, points[i-1], points[i], color, 1)
                    if i % 5 == 0:  # Vẽ dấu chấm mỗi 5 frame
                        cv2.circle(result_frame, points[i], 3, color, -1)
            
            # Lưu tracking data cho frame này
            frame_tracks.append({
                'track_id': track_id,
                'class_name': track.class_name,
                'bbox': {
                    'x1': float(bbox.x1),
                    'y1': float(bbox.y1),
                    'x2': float(bbox.x2),
                    'y2': float(bbox.y2)
                },
                'center': {
                    'x': float(bbox.center[0]),
                    'y': float(bbox.center[1])
                },
                'speed': float(speed),
                'crossed_line': track.crossed_line
            })
        
        # Lưu vào frame_data
        self.frame_data[frame_id] = frame_tracks
        
        # Vẽ info bar (góc trên trái)
        info_text = [
            f"Frame: {frame_id}/{self.total_frames}",
            f"FPS: {self.fps:.1f}",
            f"Active Tracks: {len(self.tracks)}",
            f"Total Passed: {self.vehicle_count}"
        ]
        
        y_offset = 30
        for text in info_text:
            cv2.putText(result_frame, text, (10, y_offset),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            y_offset += 30
        
        return result_frame
    
    def _continue_processing(self, progress_callback: Optional[Callable[[float, int, int], None]] = None) -> bool:
        """
        Tiếp tục xử lý video sau khi load_video() đã được gọi
        (Dùng để tách initialization ra khỏi processing)
        
        Returns:
            bool: True nếu thành công
        """
        if self.cap is None or self.out is None:
            logger.error("❌ Video not loaded. Call load_video() first")
            return False
        
        if self.counting_line_y is None:
            self.set_counting_line()
        
        # Nếu chưa calibrate, dùng giá trị mặc định
        if self.pixels_per_meter == 1.0:
            logger.warning("⚠ Calibration not set, using default value (1.0 pixels/meter)")
            self.set_calibration(reference_object_pixels=150, reference_object_meters=4.5)
        
        # DEBUG: In thông tin video input
        logger.info("🎬 Processing video...")
        logger.info(f"📊 INPUT VIDEO INFO:")
        logger.info(f"  - FPS: {self.fps}")
        logger.info(f"  - Total frames: {self.total_frames}")
        logger.info(f"  - Resolution: {self.frame_width}x{self.frame_height}")
        logger.info(f"  - Duration: {self.total_frames / self.fps:.2f} seconds")
        
        frame_id = 0
        frames_written = 0  # Đếm số frame đã ghi
        
        try:
            while True:
                ret, frame = self.cap.read()
                if not ret:
                    break
                
                # Kiểm tra kích thước frame
                if frame.shape[1] != self.frame_width or frame.shape[0] != self.frame_height:
                    logger.warning(f"⚠ Frame {frame_id} size mismatch: {frame.shape[1]}x{frame.shape[0]} vs {self.frame_width}x{self.frame_height}")
                    # Resize nếu cần
                    frame = cv2.resize(frame, (self.frame_width, self.frame_height))
                
                # Detect vehicles
                detections = self.detect_vehicles(frame)
                
                # Match và update tracks
                matched, unmatched_dets = self.match_detections_to_tracks(detections)
                self.update_tracks(matched, unmatched_dets, detections, frame_id)
                
                # Check line crossing
                crossed = self.detect_line_crossing()
                self.vehicle_count += len(crossed)
                
                # Draw results
                result_frame = self.draw_results(frame, frame_id)
                
                # Kiểm tra kích thước result_frame trước khi ghi
                if result_frame.shape[1] != self.frame_width or result_frame.shape[0] != self.frame_height:
                    logger.warning(f"⚠ Result frame {frame_id} size mismatch: {result_frame.shape[1]}x{result_frame.shape[0]}")
                    result_frame = cv2.resize(result_frame, (self.frame_width, self.frame_height))
                
                # Write to output video
                self.out.write(result_frame)
                frames_written += 1
                
                # Progress
                if progress_callback:
                    try:
                        frac = min(max((frame_id + 1) / max(1, self.total_frames), 0.0), 1.0)
                        progress_callback(frac, frame_id + 1, self.total_frames)
                    except Exception:
                        pass
                elif frame_id % 30 == 0:
                    progress = (frame_id / self.total_frames) * 100
                    logger.info(f"Progress: {progress:.1f}% (Frame {frame_id}/{self.total_frames})")
                
                frame_id += 1
            
            # DEBUG: In thông tin output
            logger.info("✓ Video processing completed")
            logger.info(f"📊 OUTPUT VIDEO INFO:")
            logger.info(f"  - Frames read: {frame_id}")
            logger.info(f"  - Frames written: {frames_written}")
            logger.info(f"  - Expected duration: {frames_written / self.fps:.2f} seconds")
            
            if frames_written != frame_id:
                logger.warning(f"⚠ Frame count mismatch! Read: {frame_id}, Written: {frames_written}")
            
            if progress_callback:
                try:
                    progress_callback(1.0, self.total_frames, self.total_frames)
                except Exception:
                    pass
            
        except Exception as e:
            logger.error(f"❌ Error during processing: {e}")
            return False
        
        finally:
            self.cap.release()
            self.out.release()
            cv2.destroyAllWindows()
        
        # Save statistics
        self.save_statistics()
        self.save_frame_data()
        self.print_summary()
        self._reencode_h264()

        logger.info(f"✓ Output video saved to {self.output_video_path}")
        logger.info(f"✓ Statistics saved to {self.output_csv_path}")
        logger.info(f"✓ Frame data saved to {self.output_json_path}")

        return True
    
    def _continue_processing_with_frame(self, progress_callback: Optional[Callable[[float, int, int, np.ndarray], None]] = None) -> bool:
        """
        Tiếp tục xử lý video với callback trả về frame để hiển thị real-time
        
        Args:
            progress_callback: Callback nhận (progress_fraction, frame_idx, total_frames, result_frame_rgb)
        
        Returns:
            bool: True nếu thành công
        """
        if self.cap is None or self.out is None:
            logger.error("❌ Video not loaded. Call load_video() first")
            return False
        
        if self.counting_line_y is None:
            self.set_counting_line()
        
        # Nếu chưa calibrate, dùng giá trị mặc định
        if self.pixels_per_meter == 1.0:
            logger.warning("⚠ Calibration not set, using default value (1.0 pixels/meter)")
            self.set_calibration(reference_object_pixels=150, reference_object_meters=4.5)
        
        # DEBUG: In thông tin video input
        logger.info("🎬 Processing video...")
        logger.info(f"📊 INPUT VIDEO INFO:")
        logger.info(f"  - FPS: {self.fps}")
        logger.info(f"  - Total frames: {self.total_frames}")
        logger.info(f"  - Resolution: {self.frame_width}x{self.frame_height}")
        logger.info(f"  - Duration: {self.total_frames / self.fps:.2f} seconds")
        
        frame_id = 0
        frames_written = 0
        
        try:
            while True:
                ret, frame = self.cap.read()
                if not ret:
                    break
                
                # Kiểm tra kích thước frame
                if frame.shape[1] != self.frame_width or frame.shape[0] != self.frame_height:
                    frame = cv2.resize(frame, (self.frame_width, self.frame_height))
                
                # Detect vehicles
                detections = self.detect_vehicles(frame)
                
                # Match và update tracks
                matched, unmatched_dets = self.match_detections_to_tracks(detections)
                self.update_tracks(matched, unmatched_dets, detections, frame_id)
                
                # Check line crossing
                crossed = self.detect_line_crossing()
                self.vehicle_count += len(crossed)
                
                # Draw results
                result_frame = self.draw_results(frame, frame_id)
                
                # Kiểm tra kích thước result_frame trước khi ghi
                if result_frame.shape[1] != self.frame_width or result_frame.shape[0] != self.frame_height:
                    result_frame = cv2.resize(result_frame, (self.frame_width, self.frame_height))
                
                # Write to output video
                self.out.write(result_frame)
                frames_written += 1
                
                # Progress với frame
                if progress_callback:
                    try:
                        frac = min(max((frame_id + 1) / max(1, self.total_frames), 0.0), 1.0)
                        # Chuyển BGR sang RGB cho Streamlit
                        result_frame_rgb = cv2.cvtColor(result_frame, cv2.COLOR_BGR2RGB)
                        progress_callback(frac, frame_id + 1, self.total_frames, result_frame_rgb)
                    except Exception:
                        pass
                elif frame_id % 30 == 0:
                    progress = (frame_id / self.total_frames) * 100
                    logger.info(f"Progress: {progress:.1f}% (Frame {frame_id}/{self.total_frames})")
                
                frame_id += 1
            
            # DEBUG: In thông tin output
            logger.info("✓ Video processing completed")
            logger.info(f"📊 OUTPUT VIDEO INFO:")
            logger.info(f"  - Frames read: {frame_id}")
            logger.info(f"  - Frames written: {frames_written}")
            logger.info(f"  - Expected duration: {frames_written / self.fps:.2f} seconds")
            
            if frames_written != frame_id:
                logger.warning(f"⚠ Frame count mismatch! Read: {frame_id}, Written: {frames_written}")
            
            if progress_callback:
                try:
                    progress_callback(1.0, self.total_frames, self.total_frames, None)
                except Exception:
                    pass
            
        except Exception as e:
            logger.error(f"❌ Error during processing: {e}")
            return False
        
        finally:
            self.cap.release()
            self.out.release()
            cv2.destroyAllWindows()
        
        # Save statistics
        self.save_statistics()
        self.save_frame_data()
        self.print_summary()
        self._reencode_h264()

        logger.info(f"✓ Output video saved to {self.output_video_path}")
        logger.info(f"✓ Statistics saved to {self.output_csv_path}")
        logger.info(f"✓ Frame data saved to {self.output_json_path}")

        return True

    def save_statistics(self):
        """Lưu thống kê ra CSV"""
        try:
            with open(self.output_csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['vehicle_id', 'class_name', 'frame_started', 
                            'num_frames', 'avg_speed', 'max_speed', 'distance_pixels']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                
                # Viết thống kê từ dead tracks
                all_tracks = self.dead_tracks + list(self.tracks.values())
                all_tracks = self.filter_valid_tracks(all_tracks)
                
                for track in all_tracks:
                    avg_speed = track.get_average_speed()
                    max_speed = track.get_max_speed()
                    num_frames = len(track.positions)
                    distance = 0.0
                    
                    if len(track.positions) > 1:
                        first_pos = track.positions[0]
                        last_pos = track.positions[-1]
                        distance = np.sqrt(
                            (last_pos[0] - first_pos[0])**2 + 
                            (last_pos[1] - first_pos[1])**2
                        )
                    
                    writer.writerow({
                        'vehicle_id': track.track_id,
                        'class_name': track.class_name,
                        'frame_started': track.frame_started,
                        'num_frames': num_frames,
                        'avg_speed': f"{avg_speed:.2f}",
                        'max_speed': f"{max_speed:.2f}",
                        'distance_pixels': f"{distance:.2f}"
                    })
            
            logger.info(f"✓ Statistics saved to {self.output_csv_path}")
            
        except Exception as e:
            logger.error(f"❌ Error saving statistics: {e}")

    def save_frame_data(self):
        """Lưu tracking data theo từng frame ra JSON"""
        try:
            # Chuyển đổi frame_data sang format dễ đọc
            output_data = {
                'metadata': {
                    'video_path': self.video_path,
                    'total_frames': self.total_frames,
                    'fps': self.fps,
                    'resolution': {
                        'width': self.frame_width,
                        'height': self.frame_height
                    },
                    'counting_line_y': self.counting_line_y,
                    'total_vehicles': len(self.dead_tracks) + len(self.tracks),
                    'vehicles_passed': self.vehicle_count
                },
                'frames': {}
            }
            
            # Lưu data từng frame
            for frame_id, tracks in self.frame_data.items():
                output_data['frames'][str(frame_id)] = tracks
            
            # Ghi ra file JSON
            with open(self.output_json_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"✓ Frame data saved to {self.output_json_path}")
            
        except Exception as e:
            logger.error(f"❌ Error saving frame data: {e}")

    def _reencode_h264(self) -> bool:
        """Re-encode output video to H.264 for browser playback. Returns True if successful."""
        tmp_path = None
        try:
            # Lấy thông tin video gốc
            cap_check = cv2.VideoCapture(self.output_video_path)
            original_fps = cap_check.get(cv2.CAP_PROP_FPS)
            original_frames = int(cap_check.get(cv2.CAP_PROP_FRAME_COUNT))
            cap_check.release()
            
            logger.info(f"🔄 Re-encoding to H.264...")
            logger.info(f"  Original: {original_frames} frames @ {original_fps} FPS")
            
            tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            tmp_path = tmp.name
            tmp.close()
            
            # Re-encode với FPS cố định từ video gốc
            rc = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    self.output_video_path,
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-r", str(original_fps),  # Giữ nguyên FPS
                    "-movflags",
                    "+faststart",
                    tmp_path,
                ],
                capture_output=True,
                timeout=3600,
            )
            if rc.returncode != 0:
                err = rc.stderr.decode(errors="ignore") if rc.stderr else "ffmpeg failed"
                raise RuntimeError(err)
            
            # Kiểm tra video sau khi re-encode
            cap_check = cv2.VideoCapture(tmp_path)
            reencoded_fps = cap_check.get(cv2.CAP_PROP_FPS)
            reencoded_frames = int(cap_check.get(cv2.CAP_PROP_FRAME_COUNT))
            cap_check.release()
            
            logger.info(f"  Re-encoded: {reencoded_frames} frames @ {reencoded_fps} FPS")
            
            if reencoded_frames != original_frames:
                logger.warning(f"⚠ Frame count changed after re-encode! {original_frames} → {reencoded_frames}")
            
            os.replace(tmp_path, self.output_video_path)
            logger.info("✓ Re-encoded to H.264 for browser playback")
            return True
        except FileNotFoundError:
            logger.warning("⚠ ffmpeg not found; output is mp4v (may not play in browser)")
            return False
        except Exception as e:
            logger.warning(f"⚠ H.264 re-encode failed: {e}; output is mp4v")
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            return False

    def print_summary(self):
        """In tóm tắt thống kê"""
        print("\n" + "="*60)
        print("TRAFFIC ANALYSIS SUMMARY")
        print("="*60)
        
        all_tracks = self.dead_tracks + list(self.tracks.values())
        all_tracks = self.filter_valid_tracks(all_tracks)
        
        print(f"\nTotal Vehicles Detected: {len(all_tracks)}")
        print(f"Vehicles Passed Counting Line: {self.vehicle_count}")
        
        # Thống kê theo loại xe
        class_count = defaultdict(int)
        for track in all_tracks:
            class_count[track.class_name] += 1
        
        print(f"\nVehicle Breakdown:")
        for class_name, count in sorted(class_count.items()):
            percentage = (count / len(all_tracks)) * 100 if all_tracks else 0
            print(f"  - {class_name}: {count} ({percentage:.1f}%)")
        
        # Thống kê tốc độ
        all_speeds = []
        for track in all_tracks:
            all_speeds.extend(track.speed_history)
        
        if all_speeds:
            avg_speed = np.mean(all_speeds)
            max_speed = np.max(all_speeds)
            min_speed = np.min(all_speeds)
            
            print(f"\nSpeed Statistics:")
            print(f"  - Average Speed: {avg_speed:.2f} km/h")
            print(f"  - Max Speed: {max_speed:.2f} km/h")
            print(f"  - Min Speed: {min_speed:.2f} km/h")
            
            # Đếm vi phạm quá tốc độ (ví dụ: giới hạn 50 km/h)
            speed_limit = 50
            violations = sum(1 for s in all_speeds if s > speed_limit)
            print(f"  - Speed > {speed_limit} km/h: {violations} ({violations/len(all_speeds)*100:.1f}%)")
        
        print("\n" + "="*60)
    
    def process_video(self) -> bool:
        """
        Xử lý toàn bộ video
        
        Returns:
            bool: True nếu thành công
        """
        if not self.load_video():
            return False
        
        if self.counting_line_y is None:
            self.set_counting_line()
        
        # Nếu chưa calibrate, dùng giá trị mặc định
        if self.pixels_per_meter == 1.0:
            logger.warning("⚠ Calibration not set, using default value (1.0 pixels/meter)")
            # Ví dụ: nếu video 720p, xe ~150 pixels, dài 4.5m
            self.set_calibration(reference_object_pixels=150, reference_object_meters=4.5)
        
        logger.info("🎬 Processing video...")
        frame_id = 0
        
        try:
            while True:
                ret, frame = self.cap.read()
                if not ret:
                    break
                
                # Detect vehicles
                detections = self.detect_vehicles(frame)
                
                # Match và update tracks
                matched, unmatched_dets = self.match_detections_to_tracks(detections)
                self.update_tracks(matched, unmatched_dets, detections, frame_id)
                
                # Check line crossing
                crossed = self.detect_line_crossing()
                self.vehicle_count += len(crossed)
                
                # Draw results
                result_frame = self.draw_results(frame, frame_id)
                
                # Write to output video
                self.out.write(result_frame)
                
                # Progress
                if frame_id % 30 == 0:
                    progress = (frame_id / self.total_frames) * 100
                    logger.info(f"Progress: {progress:.1f}% (Frame {frame_id}/{self.total_frames})")
                
                frame_id += 1
            
            logger.info("✓ Video processing completed")
            
        except Exception as e:
            logger.error(f"❌ Error during processing: {e}")
            return False
        
        finally:
            self.cap.release()
            self.out.release()
            cv2.destroyAllWindows()

        # Save statistics
        self.save_statistics()
        self.save_frame_data()
        self.print_summary()
        self._reencode_h264()

        logger.info(f"✓ Output video saved to {self.output_video_path}")
        logger.info(f"✓ Statistics saved to {self.output_csv_path}")
        logger.info(f"✓ Frame data saved to {self.output_json_path}")

        return True


# ==================== MAIN ENTRY POINT ====================

def main():
    """Hàm main - điểm bắt đầu chương trình"""
    
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║   INTELLIGENT TRAFFIC ANALYSIS SYSTEM (ITS)              ║
    ║   Vehicle Detection + Tracking + Speed Estimation        ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    # Cấu hình
    VIDEO_PATH = "test_traffic.mp4"  # Sử dụng video test có sẵn
    OUTPUT_VIDEO = "output_traffic.mp4"
    OUTPUT_CSV = "traffic_statistics.csv"
    MODEL = "yolov8n.pt"  # n=nano, s=small, m=medium, l=large, x=extra large
    
    # Kiểm tra video tồn tại
    import os
    if not os.path.exists(VIDEO_PATH):
        print(f"❌ Video not found: {VIDEO_PATH}")
        print("💡 Hãy thay đường dẫn video hoặc tạo video test")
        return
    
    # Khởi tạo analyzer
    analyzer = TrafficAnalyzer(
        video_path=VIDEO_PATH,
        model_path=MODEL,
        output_video_path=OUTPUT_VIDEO,
        output_csv_path=OUTPUT_CSV,
        conf_threshold=0.5,
        iou_threshold=0.5
    )
    
    # Cấu hình
    # analyzer.set_counting_line(y=400)  # Đặt line ở y=400 (nếu muốn custom)
    analyzer.set_calibration(
        reference_object_pixels=150,  # Chiều dài xe trong video (pixels)
        reference_object_meters=4.5   # Chiều dài thực tế (meters)
    )
    
    # Xử lý video
    success = analyzer.process_video()
    
    if success:
        print("\n✅ Processing complete!")
        print(f"📹 Output video: {OUTPUT_VIDEO}")
        print(f"📊 Statistics: {OUTPUT_CSV}")
    else:
        print("\n❌ Processing failed!")


if __name__ == "__main__":
    main()
