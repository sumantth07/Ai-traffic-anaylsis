"""
Hệ thống xử lý video TRỰC TIẾP với YOLO + ByteTrack
Hiển thị real-time + Lưu video output để xem lại
"""

import os
import cv2
import time
import numpy as np
import streamlit as st
from collections import defaultdict, deque
from ultralytics import YOLO
from datetime import datetime

# ==================== CONFIG ====================
st.set_page_config(
    page_title="Xử Lý Video Trực Tiếp - YOLO + ByteTrack",
    page_icon="🚦",
    layout="wide"
)

# ==================== SESSION STATE ====================
if "is_processing" not in st.session_state:
    st.session_state.is_processing = False
if "stop_requested" not in st.session_state:
    st.session_state.stop_requested = False
if "stats" not in st.session_state:
    st.session_state.stats = {
        "frame_count": 0,
        "total_vehicles": 0,
        "vehicle_passed": 0,
        "fps": 0.0,
        "breakdown": {}
    }
if "output_video_path" not in st.session_state:
    st.session_state.output_video_path = None
if "processing_complete" not in st.session_state:
    st.session_state.processing_complete = False

# ==================== SIDEBAR ====================
with st.sidebar:
    st.markdown("## ⚙️ Cấu Hình")
    
    model_choice = st.selectbox(
        "Model YOLO",
        options=["yolov8n.pt", "yolov8s.pt"],
        index=0,
        disabled=st.session_state.is_processing
    )
    
    conf_threshold = st.slider(
        "Confidence", 0.1, 0.9, 0.5, 0.05,
        disabled=st.session_state.is_processing
    )
    
    st.markdown("---")
    st.markdown("### 📏 Calibration")
    car_length_px = st.number_input(
        "Xe (pixels)", 10, 2000, 150,
        disabled=st.session_state.is_processing
    )
    car_length_m = st.number_input(
        "Xe (meters)", 1.0, 20.0, 4.5,
        disabled=st.session_state.is_processing
    )

# ==================== HEADER ====================
st.markdown("# 🚦 Xử Lý Video Trực Tiếp")
st.markdown("### YOLO + ByteTrack - Real-time Processing + Video Output")
st.markdown("---")

# ==================== MAIN LAYOUT ====================
col_video, col_stats = st.columns([2, 1], gap="large")

with col_video:
    st.markdown("### 📹 Video Processing")
    
    # Video source
    uploaded_video = st.file_uploader(
        "Tải Video",
        type=["mp4", "avi", "mov", "mkv"],
        disabled=st.session_state.is_processing
    )
    
    video_path_text = st.text_input(
        "Hoặc đường dẫn video",
        value="video_giao_thong.mp4",
        disabled=st.session_state.is_processing
    )
    
    # Determine video source
    if uploaded_video is not None:
        tmp_path = "uploaded_temp.mp4"
        if not st.session_state.is_processing:
            with open(tmp_path, "wb") as f:
                f.write(uploaded_video.read())
        video_source = tmp_path
    else:
        video_source = video_path_text
    
    # Control buttons
    col_btn1, col_btn2 = st.columns(2)
    
    with col_btn1:
        start_btn = st.button(
            "🚀 Bắt Đầu Xử Lý",
            type="primary",
            use_container_width=True,
            disabled=st.session_state.is_processing
        )
    
    with col_btn2:
        stop_btn = st.button(
            "⏹ Dừng",
            use_container_width=True,
            disabled=not st.session_state.is_processing
        )
    
    # Video display
    video_placeholder = st.empty()
    progress_placeholder = st.empty()
    info_placeholder = st.empty()

with col_stats:
    st.markdown("### 📊 Thống Kê Real-time")
    
    metric_col1, metric_col2 = st.columns(2)
    with metric_col1:
        st.metric("Frame", st.session_state.stats["frame_count"])
    with metric_col2:
        st.metric("FPS", f"{st.session_state.stats['fps']:.1f}")
    
    metric_col3, metric_col4 = st.columns(2)
    with metric_col3:
        st.metric("Xe", st.session_state.stats["total_vehicles"])
    with metric_col4:
        st.metric("Qua Line", st.session_state.stats["vehicle_passed"])
    
    st.markdown("---")
    st.markdown("### 🚗 Phân Loại")
    
    breakdown = st.session_state.stats.get("breakdown", {})
    if breakdown:
        for class_name, count in sorted(breakdown.items(), key=lambda x: x[1], reverse=True):
            st.write(f"• **{class_name.upper()}**: {count}")
    else:
        st.write("_(chưa có dữ liệu)_")

# ==================== PROCESSING FUNCTION ====================
def process_video_realtime(video_path, model_path, conf_threshold, pixels_per_meter):
    """Xử lý video real-time với YOLO + ByteTrack"""
    
    # Vehicle classes
    VEHICLE_CLASSES = ['car', 'motorbike', 'bicycle', 'bus', 'truck', 'motorcycle']
    
    # Load YOLO model
    with st.spinner("⏳ Đang load YOLO model..."):
        model = YOLO(model_path)
    
    # Open video
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        st.error("❌ Không thể mở video!")
        return
    
    # Get video info
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # Create output video writer
    os.makedirs("output_video", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = f"output_video/processed_{timestamp}.mp4"
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    
    st.session_state.output_video_path = output_path
    
    # Counting line
    counting_line_y = int(height * 2 / 3)
    
    # Tracking
    tracks = {}
    vehicle_count = 0
    crossed_ids = set()
    
    # FPS counter
    fps_counter = deque(maxlen=30)
    
    frame_idx = 0
    
    st.session_state.is_processing = True
    st.session_state.stop_requested = False
    
    info_placeholder.info(f"📹 Video: {width}x{height}, {total_frames} frames, {fps:.1f} FPS")
    
    try:
        while cap.isOpened() and not st.session_state.stop_requested:
            start_time = time.time()
            
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_idx += 1
            
            # ===== YOLO DETECTION + BYTETRACK =====
            results = model.track(
                frame,
                conf=conf_threshold,
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
                        class_name = model.names[cls]
                        
                        # Only vehicles
                        if class_name not in VEHICLE_CLASSES:
                            continue
                        
                        # Get track ID
                        track_id = int(box.id[0]) if hasattr(box, 'id') and box.id is not None else None
                        if track_id is None:
                            continue
                        
                        # Update tracks
                        if track_id not in tracks:
                            tracks[track_id] = {
                                'class': class_name,
                                'positions': [],
                                'crossed': False
                            }
                        
                        center_x = (x1 + x2) / 2
                        center_y = (y1 + y2) / 2
                        tracks[track_id]['positions'].append((int(center_x), int(center_y)))
                        
                        # Check counting line
                        if not tracks[track_id]['crossed'] and center_y > counting_line_y:
                            tracks[track_id]['crossed'] = True
                            if track_id not in crossed_ids:
                                crossed_ids.add(track_id)
                                vehicle_count += 1
                        
                        # Calculate speed (simple)
                        speed = 0.0
                        if len(tracks[track_id]['positions']) > 5:
                            pos_history = tracks[track_id]['positions'][-10:]
                            if len(pos_history) >= 2:
                                dx = pos_history[-1][0] - pos_history[0][0]
                                dy = pos_history[-1][1] - pos_history[0][1]
                                distance_px = (dx**2 + dy**2)**0.5
                                distance_m = distance_px / pixels_per_meter
                                time_s = len(pos_history) / fps
                                speed = (distance_m / time_s) * 3.6  # km/h
                        
                        # ===== DRAW ON FRAME =====
                        # Color by class
                        if class_name == "car":
                            color = (0, 255, 0)
                        elif class_name == "motorcycle" or class_name == "motorbike":
                            color = (255, 0, 0)
                        elif class_name == "truck":
                            color = (0, 0, 255)
                        elif class_name == "bus":
                            color = (255, 255, 0)
                        else:
                            color = (255, 255, 255)
                        
                        # Bounding box
                        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                        
                        # Label
                        label = f"ID:{track_id} {class_name.upper()}"
                        if speed > 0:
                            label += f" {speed:.0f}km/h"
                        
                        # Background for text
                        (text_w, text_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                        cv2.rectangle(frame, (int(x1), int(y1) - text_h - 8),
                                    (int(x1) + text_w, int(y1)), color, -1)
                        cv2.putText(frame, label, (int(x1), int(y1) - 5),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
                        
                        # Trajectory
                        if len(tracks[track_id]['positions']) > 1:
                            pts = np.array(tracks[track_id]['positions'][-20:], dtype=np.int32)
                            cv2.polylines(frame, [pts], False, color, 2)
            
            # ===== DRAW COUNTING LINE =====
            cv2.line(frame, (0, counting_line_y), (width, counting_line_y), (0, 255, 255), 2)
            cv2.putText(frame, "COUNTING LINE", (10, counting_line_y - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            
            # ===== DRAW INFO =====
            # Calculate FPS
            elapsed = time.time() - start_time
            fps_counter.append(1.0 / elapsed if elapsed > 0 else 0)
            current_fps = sum(fps_counter) / len(fps_counter)
            
            # Breakdown by class
            breakdown = defaultdict(int)
            for track in tracks.values():
                breakdown[track['class']] += 1
            
            # Draw stats on frame
            cv2.putText(frame, f"Frame: {frame_idx}/{total_frames}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, f"FPS: {current_fps:.1f}", (10, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, f"Vehicles: {len(tracks)}", (10, 90),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, f"Passed: {vehicle_count}", (10, 120),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # Write frame to output video
            out.write(frame)
            
            # ===== UPDATE UI =====
            # Convert to RGB for Streamlit
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            video_placeholder.image(frame_rgb, channels="RGB", use_container_width=True)
            
            # Update progress
            progress = frame_idx / total_frames
            progress_placeholder.progress(progress, f"Frame {frame_idx}/{total_frames}")
            
            # Update stats
            st.session_state.stats = {
                "frame_count": frame_idx,
                "total_vehicles": len(tracks),
                "vehicle_passed": vehicle_count,
                "fps": current_fps,
                "breakdown": dict(breakdown)
            }
    
    except Exception as e:
        st.error(f"❌ Lỗi xử lý: {str(e)}")
    finally:
        cap.release()
        out.release()
        st.session_state.is_processing = False
        st.session_state.processing_complete = True
        info_placeholder.success(f"✅ Hoàn tất! Video đã lưu: {output_path}")

# ==================== BUTTON ACTIONS ====================
if start_btn:
    if not os.path.exists(video_source):
        st.error(f"❌ Không tìm thấy video: {video_source}")
    else:
        # Calculate pixels_per_meter
        pixels_per_meter = car_length_px / car_length_m
        
        # Start processing
        process_video_realtime(
            video_path=video_source,
            model_path=model_choice,
            conf_threshold=conf_threshold,
            pixels_per_meter=pixels_per_meter
        )
        
        st.rerun()

if stop_btn:
    st.session_state.stop_requested = True
    st.session_state.is_processing = False
    st.warning("⏹ Đã dừng xử lý")
    st.rerun()

# ==================== PLAYBACK VIDEO ====================
st.markdown("---")
st.markdown("## 🎬 Video Đã Xử Lý")

if st.session_state.processing_complete and st.session_state.output_video_path:
    output_path = st.session_state.output_video_path
    
    if os.path.exists(output_path):
        st.success(f"✅ Video đã xử lý: `{output_path}`")
        
        # Display video
        st.video(output_path)
        
        # Download button
        with open(output_path, "rb") as f:
            st.download_button(
                label="⬇️ Tải Video",
                data=f,
                file_name=os.path.basename(output_path),
                mime="video/mp4"
            )
    else:
        st.warning("⚠️ Không tìm thấy video output")
else:
    st.info("ℹ️ Xử lý video để xem kết quả")

# ==================== FOOTER ====================
st.markdown("---")
st.caption("🚀 YOLO + ByteTrack + OpenCV | Xử lý real-time + Lưu video output")
