"""
ITS Traffic Video Analytics - REAL-TIME DISPLAY
Hiển thị video xử lý REAL-TIME lên web app

Run:
  streamlit run traffic_web_app_realtime.py --server.port 5173
"""

import os
import time
import cv2
import numpy as np
import streamlit as st
from collections import defaultdict
import logging

# SUPPRESS ALL CONSOLE OUTPUT
logging.disable(logging.CRITICAL)
os.environ['STREAMLIT_CLIENT_LOGGING_LEVEL'] = 'critical'
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

from traffic_analysis import TrafficAnalyzer

# ---------------------- CONFIG ----------------------
st.set_page_config(
    page_title="Hệ Thống Giám Sát Giao Thông - Real-time", 
    page_icon="🚦", 
    layout="wide"
)

# ---------------------- SESSION STATE ----------------------
if "analyzer" not in st.session_state:
    st.session_state.analyzer = None
if "is_running" not in st.session_state:
    st.session_state.is_running = False
if "frame_count" not in st.session_state:
    st.session_state.frame_count = 0
if "stats" not in st.session_state:
    st.session_state.stats = {
        "total_vehicles": 0,
        "vehicle_count": 0,
        "avg_speed": 0.0,
        "max_speed": 0.0,
        "breakdown": {}
    }
if "video_path" not in st.session_state:
    st.session_state.video_path = None
if "output_video_path" not in st.session_state:
    st.session_state.output_video_path = None

# ---------------------- SIDEBAR ----------------------
with st.sidebar:
    st.markdown("## ⚙️ Cấu Hình")
    
    model_choice = st.selectbox(
        "Model YOLO",
        options=["yolov8n.pt", "yolov8s.pt"],
        index=0
    )

    conf_threshold = st.slider("Confidence", 0.1, 0.9, 0.5, 0.1)
    iou_threshold = st.slider("IoU NMS", 0.3, 0.9, 0.5, 0.1)

    st.markdown("---")
    st.markdown("### 🔄 Tracking")
    track_iou_threshold = st.slider("Track IoU", 0.1, 0.9, 0.3, 0.05)
    reid_iou_threshold = st.slider("ReID IoU", 0.1, 0.9, 0.25, 0.05)
    max_age = st.slider("Max Age", 5, 300, 60, 5)
    reid_max_age = st.slider("ReID Max Age", 10, 600, 150, 10)
    min_track_frames = st.slider("Min Frames", 1, 120, 10, 1)

    st.markdown("---")
    st.markdown("### 📏 Calibration")
    car_length_pixels = st.number_input("Xe (px)", 10, 2000, 150)
    car_length_meters = st.number_input("Xe (m)", 1.0, 20.0, 4.5)

    st.markdown("---")
    counting_line_y = st.number_input("Counting Line Y", 0, 4000, 0)

# ---------------------- HEADER ----------------------
st.markdown("# 🚦 Hệ Thống Giám Sát Giao Thông - Real-time")
st.markdown("**Hiển thị video xử lý trực tiếp trên web app**")
st.markdown("---")

# ---------------------- MAIN LAYOUT ----------------------
col_video, col_stats = st.columns([2, 1], gap="large")

with col_video:
    st.markdown("### 📹 Video Real-time")
    
    # Video source
    uploaded_video = st.file_uploader(
        "Tải Video", 
        type=["mp4", "avi", "mov", "mkv"],
        disabled=st.session_state.is_running
    )
    video_path_text = st.text_input(
        "Hoặc đường dẫn video", 
        value="video_giao_thong.mp4",
        disabled=st.session_state.is_running
    )

    # Determine video source
    if uploaded_video is not None:
        tmp_path = "uploaded_video_temp.mp4"
        with open(tmp_path, "wb") as f:
            f.write(uploaded_video.read())
        video_source = tmp_path
    else:
        video_source = video_path_text

    # Start/Stop buttons
    col_btn1, col_btn2 = st.columns(2)
    
    with col_btn1:
        start_btn = st.button(
            "🚀 Bắt Đầu Real-time", 
            type="primary", 
            use_container_width=True,
            disabled=st.session_state.is_running
        )
    
    with col_btn2:
        stop_btn = st.button(
            "⏹ Dừng", 
            use_container_width=True,
            disabled=not st.session_state.is_running
        )

    # Video display
    video_frame = st.empty()
    progress_bar = st.progress(0.0)
    frame_info = st.empty()

with col_stats:
    st.markdown("### 📊 Thống Kê Real-time")
    
    metric_col1, metric_col2 = st.columns(2)
    with metric_col1:
        st.metric("Xe Phát Hiện", st.session_state.stats["total_vehicles"])
    with metric_col2:
        st.metric("Qua Line", st.session_state.stats["vehicle_count"])
    
    metric_col3, metric_col4 = st.columns(2)
    with metric_col3:
        st.metric("TB Speed", f"{st.session_state.stats['avg_speed']:.1f} km/h")
    with metric_col4:
        st.metric("Max Speed", f"{st.session_state.stats['max_speed']:.1f} km/h")
    
    st.markdown("---")
    st.markdown("### 🚗 Phân Loại")
    
    breakdown = st.session_state.stats.get("breakdown", {})
    if breakdown:
        for class_name, count in sorted(breakdown.items(), key=lambda x: x[1], reverse=True):
            st.write(f"• **{class_name.upper()}**: {count}")
    else:
        st.write("_(chưa có dữ liệu)_")

# ---------------------- START PROCESSING ----------------------
if start_btn:
    if not video_source or not os.path.exists(video_source):
        st.error("❌ Video không tồn tại!")
    else:
        st.session_state.video_path = video_source
        st.session_state.is_running = True
        st.session_state.frame_count = 0
        st.rerun()

# ---------------------- STOP PROCESSING ----------------------
if stop_btn:
    st.session_state.is_running = False
    if st.session_state.analyzer:
        st.session_state.analyzer = None
    st.info("Đã dừng xử lý!")
    time.sleep(0.5)
    st.rerun()

# ---------------------- MAIN PROCESSING LOOP ----------------------
if st.session_state.is_running:
    try:
        # Initialize analyzer if not exists
        if st.session_state.analyzer is None:
            with st.spinner("⏳ Đang khởi tạo YOLO + ByteTrack..."):
                st.session_state.analyzer = TrafficAnalyzer(
                    video_path=st.session_state.video_path,
                    model_path=model_choice,
                    output_video_path=None,
                    output_csv_path="traffic_statistics.csv",
                    output_json_path="traffic_statistics_frames.json",
                    conf_threshold=conf_threshold,
                    iou_threshold=iou_threshold,
                    track_iou_threshold=track_iou_threshold,
                    reid_iou_threshold=reid_iou_threshold,
                    max_age=max_age,
                    reid_max_age=reid_max_age,
                    min_track_frames=min_track_frames,
                )
                
                # Load video
                if not st.session_state.analyzer.load_video():
                    st.error("❌ Không thể load video!")
                    st.session_state.is_running = False
                    st.stop()
                
                # Save output path
                st.session_state.output_video_path = st.session_state.analyzer.output_video_path
                
                # Set counting line
                if counting_line_y > 0:
                    st.session_state.analyzer.set_counting_line(y=int(counting_line_y))
                else:
                    st.session_state.analyzer.set_counting_line()
                
                # Calibration
                st.session_state.analyzer.set_calibration(
                    reference_object_pixels=int(car_length_pixels),
                    reference_object_meters=float(car_length_meters)
                )
                
                st.success("✅ Khởi tạo thành công!")
        
        # Process video frame by frame
        analyzer = st.session_state.analyzer
        cap = analyzer.cap
        out = analyzer.out
        
        # Read frame
        ret, frame = cap.read()
        
        if not ret:
            # Video ended
            st.session_state.is_running = False
            st.success("✅ Xử lý hoàn tất!")
            
            # Close video writer
            if out:
                out.release()
            if cap:
                cap.release()
            
            # Update final stats
            tracks = analyzer.dead_tracks + list(analyzer.tracks.values())
            tracks = analyzer.filter_valid_tracks(tracks)
            
            all_speeds = []
            breakdown = defaultdict(int)
            
            for track in tracks:
                spd = track.get_average_speed()
                all_speeds.append(spd)
                breakdown[track.class_name] += 1
            
            avg_speed = sum(all_speeds) / len(all_speeds) if all_speeds else 0.0
            max_speed = max(all_speeds) if all_speeds else 0.0
            
            st.session_state.stats = {
                "total_vehicles": len(tracks),
                "vehicle_count": analyzer.vehicle_count,
                "avg_speed": avg_speed,
                "max_speed": max_speed,
                "breakdown": dict(breakdown)
            }
            
            st.balloons()
            time.sleep(1)
            st.rerun()
        
        else:
            # Process this frame
            st.session_state.frame_count += 1
            frame_idx = st.session_state.frame_count
            
            # Run YOLO detection
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
                        # Get detection info
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        conf = float(box.conf[0])
                        cls = int(box.cls[0])
                        class_name = analyzer.model.names[cls]
                        
                        # Only process vehicles
                        if class_name not in analyzer.VEHICLE_CLASSES:
                            continue
                        
                        # Get track ID
                        track_id = int(box.id[0]) if hasattr(box, 'id') and box.id is not None else None
                        
                        if track_id is None:
                            continue
                        
                        # Update or create track
                        from traffic_analysis import Track, BoundingBox
                        bbox = BoundingBox(x1, y1, x2, y2)
                        
                        if track_id not in analyzer.tracks:
                            # New track
                            analyzer.tracks[track_id] = Track(
                                track_id=track_id,
                                class_name=class_name,
                                bbox=bbox,
                                confidence=conf,
                                frame_id=frame_idx,
                                pixels_to_meters=analyzer.pixels_to_meters
                            )
                        else:
                            # Update existing track
                            analyzer.tracks[track_id].update(bbox, conf, frame_idx)
                        
                        # Check counting line
                        center_x, center_y = bbox.center
                        track = analyzer.tracks[track_id]
                        
                        if not track.has_crossed and center_y > analyzer.counting_line_y:
                            track.has_crossed = True
                            analyzer.vehicle_count += 1
                        
                        # Draw on frame
                        color = (0, 255, 0)
                        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                        
                        # Draw track info
                        speed = track.get_average_speed()
                        label = f"ID:{track_id} {class_name} {speed:.1f}km/h"
                        cv2.putText(frame, label, (int(x1), int(y1) - 10),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                        
                        # Draw trajectory
                        if len(track.positions) > 1:
                            pts = np.array(track.positions, dtype=np.int32)
                            cv2.polylines(frame, [pts], False, (255, 0, 255), 2)
            
            # Draw counting line
            cv2.line(frame, (0, analyzer.counting_line_y), 
                    (analyzer.frame_width, analyzer.counting_line_y), 
                    (0, 255, 255), 3)
            cv2.putText(frame, "COUNTING LINE", (10, analyzer.counting_line_y - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            
            # Draw stats on frame
            cv2.putText(frame, f"Frame: {frame_idx}/{analyzer.total_frames}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(frame, f"Vehicles: {len(analyzer.tracks)}", (10, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(frame, f"Passed: {analyzer.vehicle_count}", (10, 90),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # Write to output video
            if out:
                out.write(frame)
            
            # Display frame in Streamlit
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            video_frame.image(frame_rgb, channels="RGB", use_container_width=True)
            
            # Update progress
            progress = frame_idx / analyzer.total_frames
            progress_bar.progress(progress)
            frame_info.caption(f"Frame {frame_idx}/{analyzer.total_frames} ({progress*100:.1f}%)")
            
            # Update stats
            tracks_now = list(analyzer.tracks.values())
            all_speeds = []
            breakdown = defaultdict(int)
            
            for track in tracks_now:
                if len(track.positions) >= min_track_frames:
                    spd = track.get_average_speed()
                    all_speeds.append(spd)
                    breakdown[track.class_name] += 1
            
            avg_speed = sum(all_speeds) / len(all_speeds) if all_speeds else 0.0
            max_speed = max(all_speeds) if all_speeds else 0.0
            
            st.session_state.stats = {
                "total_vehicles": len(breakdown),
                "vehicle_count": analyzer.vehicle_count,
                "avg_speed": avg_speed,
                "max_speed": max_speed,
                "breakdown": dict(breakdown)
            }
            
            # Small delay for real-time feel
            time.sleep(0.01)
            
            # Rerun to process next frame
            st.rerun()
    
    except Exception as e:
        st.error(f"❌ Lỗi: {str(e)}")
        st.session_state.is_running = False
        st.stop()

# ---------------------- RESULTS SECTION ----------------------
if not st.session_state.is_running and st.session_state.stats["total_vehicles"] > 0:
    st.markdown("---")
    st.markdown("## 📊 KẾT QUẢ CUỐI CÙNG")
    
    col_result1, col_result2, col_result3, col_result4 = st.columns(4)
    
    with col_result1:
        st.metric("🚗 Tổng Xe", st.session_state.stats["total_vehicles"])
    
    with col_result2:
        st.metric("✅ Qua Line", st.session_state.stats["vehicle_count"])
    
    with col_result3:
        st.metric("📊 TB Speed", f"{st.session_state.stats['avg_speed']:.2f} km/h")
    
    with col_result4:
        st.metric("⚡ Max Speed", f"{st.session_state.stats['max_speed']:.2f} km/h")
    
    # Breakdown
    st.markdown("### 🚙 Phân Loại Xe")
    breakdown = st.session_state.stats.get("breakdown", {})
    
    if breakdown:
        for class_name, count in sorted(breakdown.items(), key=lambda x: x[1], reverse=True):
            pct = (count / st.session_state.stats["total_vehicles"] * 100)
            st.write(f"• **{class_name.upper()}**: {count} ({pct:.1f}%)")
    
    # Output files
    st.markdown("### 💾 Files Output")
    
    if st.session_state.output_video_path and os.path.exists(st.session_state.output_video_path):
        file_size = os.path.getsize(st.session_state.output_video_path) / (1024*1024)
        st.success(f"✅ Video: `{st.session_state.output_video_path}` ({file_size:.2f} MB)")
        
        st.markdown("### ▶️ Playback Video")
        st.video(st.session_state.output_video_path)
    
    if os.path.exists("traffic_statistics.csv"):
        file_size = os.path.getsize("traffic_statistics.csv") / 1024
        st.success(f"✅ CSV: `traffic_statistics.csv` ({file_size:.1f} KB)")

st.markdown("---")
st.caption("Powered by YOLOv8 + ByteTrack + OpenCV | Real-time Display")
