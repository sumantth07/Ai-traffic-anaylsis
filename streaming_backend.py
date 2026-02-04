"""
STREAMING BACKEND - FastAPI + MJPEG
Real-time video streaming với YOLO + ByteTrack
Không ghi file video ra disk
"""

import asyncio
import cv2
import numpy as np
from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from threading import Thread, Lock
import time
from collections import deque
from typing import Optional

# Import traffic analyzer
from traffic_analysis import TrafficAnalyzer, VehicleTrack, BoundingBox

app = FastAPI()

# CORS để Streamlit có thể gọi
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== GLOBAL STATE ====================
class StreamState:
    def __init__(self):
        self.is_streaming = False
        self.analyzer: Optional[TrafficAnalyzer] = None
        self.current_frame: Optional[np.ndarray] = None
        self.frame_lock = Lock()
        self.fps_counter = deque(maxlen=30)
        self.stats = {
            "total_vehicles": 0,
            "vehicle_count": 0,
            "avg_speed": 0.0,
            "max_speed": 0.0,
            "breakdown": {},
            "fps": 0.0
        }
        self.video_path: Optional[str] = None
        self.config = {}
        
stream_state = StreamState()


# ==================== VIDEO PROCESSING THREAD ====================
def process_video_stream():
    """Thread xử lý video và tracking"""
    global stream_state
    
    try:
        # Khởi tạo analyzer
        analyzer = TrafficAnalyzer(
            video_path=stream_state.video_path,
            model_path=stream_state.config.get("model_path", "yolov8n.pt"),
            output_video_path=None,  # KHÔNG GHI FILE
            output_csv_path=None,    # KHÔNG GHI FILE
            output_json_path=None,   # KHÔNG GHI FILE
            conf_threshold=stream_state.config.get("conf_threshold", 0.5),
            iou_threshold=stream_state.config.get("iou_threshold", 0.5),
            track_iou_threshold=stream_state.config.get("track_iou_threshold", 0.3),
            reid_iou_threshold=stream_state.config.get("reid_iou_threshold", 0.25),
            max_age=stream_state.config.get("max_age", 60),
            reid_max_age=stream_state.config.get("reid_max_age", 150),
            min_track_frames=stream_state.config.get("min_track_frames", 10),
        )
        
        # Load video
        if not analyzer.load_video():
            print("❌ Không thể load video!")
            stream_state.is_streaming = False
            return
        
        # Set counting line
        counting_line_y = stream_state.config.get("counting_line_y", 0)
        if counting_line_y > 0:
            analyzer.set_counting_line(y=int(counting_line_y))
        else:
            analyzer.set_counting_line()
        
        # Calibration
        analyzer.set_calibration(
            reference_object_pixels=stream_state.config.get("car_length_pixels", 150),
            reference_object_meters=stream_state.config.get("car_length_meters", 4.5)
        )
        
        stream_state.analyzer = analyzer
        cap = analyzer.cap
        frame_count = 0
        
        # Vehicle classes để filter
        VEHICLE_CLASSES = ['car', 'motorbike', 'bicycle', 'bus', 'truck', 'motorcycle']
        
        print("✅ Bắt đầu streaming...")
        
        # Main processing loop
        while stream_state.is_streaming:
            start_time = time.time()
            
            ret, frame = cap.read()
            if not ret:
                # Video ended, loop lại
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                frame_count = 0
                continue
            
            frame_count += 1
            
            # ===== YOLO DETECTION + BYTETRACK =====
            results = analyzer.model.track(
                frame,
                conf=analyzer.conf_threshold,
                iou=analyzer.iou_threshold,
                persist=True,
                tracker='bytetrack.yaml',
                verbose=False
            )
            
            # Process detections
            if results and len(results) > 0:
                result = results[0]
                
                if hasattr(result, 'boxes') and result.boxes is not None:
                    boxes = result.boxes
                    
                    for box in boxes:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        conf = float(box.conf[0])
                        cls = int(box.cls[0])
                        class_name = analyzer.model.names[cls]
                        
                        # Only vehicles
                        if class_name not in VEHICLE_CLASSES:
                            continue
                        
                        # Get track ID
                        track_id = int(box.id[0]) if hasattr(box, 'id') and box.id is not None else None
                        if track_id is None:
                            continue
                        
                        # Update track
                        bbox = BoundingBox(x1, y1, x2, y2)
                        
                        if track_id not in analyzer.tracks:
                            analyzer.tracks[track_id] = VehicleTrack(
                                track_id=track_id,
                                class_name=class_name,
                                bbox=bbox,
                                confidence=conf,
                                frame_id=frame_count,
                                pixels_per_meter=analyzer.pixels_per_meter
                            )
                        else:
                            analyzer.tracks[track_id].update(bbox, conf, frame_count)
                        
                        track = analyzer.tracks[track_id]
                        
                        # Check counting line
                        center_x, center_y = bbox.center
                        if not track.has_crossed and center_y > analyzer.counting_line_y:
                            track.has_crossed = True
                            analyzer.vehicle_count += 1
                        
                        # ===== DRAW ON FRAME =====
                        # Color theo class
                        if class_name == "car":
                            color = (0, 255, 0)  # Green
                        elif class_name == "motorcycle":
                            color = (255, 0, 0)  # Blue
                        elif class_name == "truck":
                            color = (0, 0, 255)  # Red
                        elif class_name == "bus":
                            color = (255, 255, 0)  # Cyan
                        else:
                            color = (255, 255, 255)  # White
                        
                        # Bounding box
                        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                        
                        # Track info
                        speed = track.get_average_speed()
                        label = f"ID:{track_id} {class_name.upper()} {speed:.1f}km/h"
                        
                        # Background cho text
                        (text_w, text_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
                        cv2.rectangle(frame, (int(x1), int(y1) - text_h - 10), 
                                    (int(x1) + text_w, int(y1)), color, -1)
                        cv2.putText(frame, label, (int(x1), int(y1) - 5),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
                        
                        # Trajectory
                        if len(track.positions) > 1:
                            pts = np.array(track.positions[-30:], dtype=np.int32)  # Last 30 points
                            cv2.polylines(frame, [pts], False, color, 2)
            
            # ===== DRAW COUNTING LINE =====
            cv2.line(frame, (0, analyzer.counting_line_y), 
                    (analyzer.frame_width, analyzer.counting_line_y), 
                    (0, 255, 255), 3)
            cv2.putText(frame, "COUNTING LINE", (10, analyzer.counting_line_y - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            
            # ===== CALCULATE STATS =====
            from collections import defaultdict
            breakdown = defaultdict(int)
            all_speeds = []
            
            for track in analyzer.tracks.values():
                if len(track.positions) >= analyzer.min_track_frames:
                    breakdown[track.class_name] += 1
                    spd = track.get_average_speed()
                    all_speeds.append(spd)
            
            avg_speed = sum(all_speeds) / len(all_speeds) if all_speeds else 0.0
            max_speed = max(all_speeds) if all_speeds else 0.0
            
            # Calculate FPS
            elapsed = time.time() - start_time
            stream_state.fps_counter.append(1.0 / elapsed if elapsed > 0 else 0)
            current_fps = sum(stream_state.fps_counter) / len(stream_state.fps_counter)
            
            # ===== DRAW STATS ON FRAME =====
            stats_y = 30
            cv2.rectangle(frame, (0, 0), (350, 180), (0, 0, 0), -1)  # Black background
            
            cv2.putText(frame, f"FPS: {current_fps:.1f}", (10, stats_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            stats_y += 30
            
            cv2.putText(frame, f"Frame: {frame_count}/{analyzer.total_frames}", (10, stats_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            stats_y += 25
            
            cv2.putText(frame, f"Vehicles: {len(breakdown)}", (10, stats_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            stats_y += 25
            
            cv2.putText(frame, f"Passed: {analyzer.vehicle_count}", (10, stats_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            stats_y += 25
            
            cv2.putText(frame, f"Avg Speed: {avg_speed:.1f} km/h", (10, stats_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            stats_y += 25
            
            cv2.putText(frame, f"Max Speed: {max_speed:.1f} km/h", (10, stats_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            # Update global state
            with stream_state.frame_lock:
                stream_state.current_frame = frame.copy()
                stream_state.stats = {
                    "total_vehicles": len(breakdown),
                    "vehicle_count": analyzer.vehicle_count,
                    "avg_speed": avg_speed,
                    "max_speed": max_speed,
                    "breakdown": dict(breakdown),
                    "fps": current_fps
                }
            
            # Small delay to control FPS
            time.sleep(0.01)
        
        # Cleanup
        cap.release()
        print("✅ Streaming stopped")
        
    except Exception as e:
        print(f"❌ Error in processing thread: {str(e)}")
        stream_state.is_streaming = False


# ==================== VIDEO FEED GENERATOR ====================
def generate_frames():
    """Generator cho MJPEG stream"""
    while stream_state.is_streaming:
        with stream_state.frame_lock:
            if stream_state.current_frame is not None:
                frame = stream_state.current_frame.copy()
            else:
                # Empty frame
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(frame, "Waiting for video...", (50, 240),
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        # Encode frame as JPEG
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ret:
            continue
        
        frame_bytes = buffer.tobytes()
        
        # MJPEG format
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        # Small delay
        time.sleep(0.01)


# ==================== API ENDPOINTS ====================

@app.post("/start")
async def start_streaming(
    video_path: str,
    model_path: str = "yolov8n.pt",
    conf_threshold: float = 0.5,
    iou_threshold: float = 0.5,
    track_iou_threshold: float = 0.3,
    reid_iou_threshold: float = 0.25,
    max_age: int = 60,
    reid_max_age: int = 150,
    min_track_frames: int = 10,
    car_length_pixels: int = 150,
    car_length_meters: float = 4.5,
    counting_line_y: int = 0
):
    """Bắt đầu streaming"""
    if stream_state.is_streaming:
        return {"status": "error", "message": "Already streaming"}
    
    # Set config
    stream_state.video_path = video_path
    stream_state.config = {
        "model_path": model_path,
        "conf_threshold": conf_threshold,
        "iou_threshold": iou_threshold,
        "track_iou_threshold": track_iou_threshold,
        "reid_iou_threshold": reid_iou_threshold,
        "max_age": max_age,
        "reid_max_age": reid_max_age,
        "min_track_frames": min_track_frames,
        "car_length_pixels": car_length_pixels,
        "car_length_meters": car_length_meters,
        "counting_line_y": counting_line_y
    }
    
    # Start processing thread
    stream_state.is_streaming = True
    thread = Thread(target=process_video_stream, daemon=True)
    thread.start()
    
    return {"status": "success", "message": "Streaming started"}


@app.post("/stop")
async def stop_streaming():
    """Dừng streaming"""
    if not stream_state.is_streaming:
        return {"status": "error", "message": "Not streaming"}
    
    stream_state.is_streaming = False
    
    # Cleanup
    if stream_state.analyzer and stream_state.analyzer.cap:
        stream_state.analyzer.cap.release()
    
    stream_state.analyzer = None
    stream_state.current_frame = None
    
    return {"status": "success", "message": "Streaming stopped"}


@app.get("/video_feed")
async def video_feed():
    """MJPEG video stream"""
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.get("/stats")
async def get_stats():
    """Lấy thống kê real-time"""
    return stream_state.stats


@app.get("/status")
async def get_status():
    """Kiểm tra trạng thái streaming"""
    return {
        "is_streaming": stream_state.is_streaming,
        "video_path": stream_state.video_path
    }


@app.get("/")
async def root():
    return {"message": "ITS Traffic Streaming Backend", "status": "running"}


# ==================== RUN SERVER ====================
if __name__ == "__main__":
    print("🚀 Starting FastAPI Streaming Backend...")
    print("📡 Video stream: http://localhost:8002/video_feed")
    print("📊 Stats API: http://localhost:8002/stats")
    
    uvicorn.run(app, host="0.0.0.0", port=8002, log_level="error")
