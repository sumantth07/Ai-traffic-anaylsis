"""
ITS Traffic Video Analytics - Streamlit Web App
UI/UX: Upload/Select video, start detection, live metrics (counts, avg/max speed), recent detections

Run:
  streamlit run traffic_web_app.py --server.port 5173
"""

import os
import time
import threading
import cv2
import pandas as pd
from typing import Dict, Any
from collections import defaultdict
import logging
import sys

# SUPPRESS ALL CONSOLE OUTPUT ASAP
logging.disable(logging.CRITICAL)

# Set environment variables BEFORE importing heavy libs to reduce logs
os.environ['STREAMLIT_CLIENT_LOGGING_LEVEL'] = 'critical'
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # Suppress TensorFlow logging

import streamlit as st
from traffic_analysis import TrafficAnalyzer

# Suppress Streamlit telemetry and error details in UI
st.set_option("client.showErrorDetails", False)


# ---------------------- GLOBAL STATE ----------------------
class AppState:
    def __init__(self):
        self.analyzer: TrafficAnalyzer | None = None
        self.is_running: bool = False
        self.last_summary: Dict[str, Any] = {}
        self.output_video_path: str = None  # Sẽ được set sau khi xử lý
        self.output_csv_path: str = "traffic_statistics.csv"
        self.log_lines: list[str] = []
        self.processing_progress: float = 0.0  # 0.0 to 1.0
        self.current_frame_display: int = 0
        self.total_frames_expected: int = 0
        self.current_frame: np.ndarray | None = None  # Frame hiện tại để hiển thị

    def log(self, msg: str):
        self.log_lines.append(msg)
        if len(self.log_lines) > 200:
            self.log_lines = self.log_lines[-200:]


if "app_state" not in st.session_state:
    st.session_state.app_state = AppState()

app = st.session_state.app_state


# ---------------------- SIDEBAR (Controls) ----------------------
st.set_page_config(page_title="Hệ Thống Giám Sát Giao Thông", page_icon="🚦", layout="wide")

with st.sidebar:
    st.markdown("## Cấu Hình")
    model_choice = st.selectbox(
        "Model YOLO",
        options=["yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt"],
        index=0,
        help="nano/small/medium/large: chọn theo tốc độ và độ chính xác"
    )

    conf_threshold = st.slider("Confidence Threshold", 0.1, 0.9, 0.5, 0.1)
    iou_threshold = st.slider("IoU Threshold", 0.3, 0.9, 0.5, 0.1)

    st.markdown("---")
    st.markdown("### Tracking (ID ổn định)")
    track_iou_threshold = st.slider("Track IoU Threshold", 0.1, 0.9, 0.3, 0.05)
    reid_iou_threshold = st.slider("ReID IoU Threshold", 0.1, 0.9, 0.25, 0.05)
    max_age = st.slider("Max Age (frames)", 5, 300, 60, 5)
    reid_max_age = st.slider("ReID Max Age (frames)", 10, 600, 150, 10)
    min_track_frames = st.slider("Min Track Frames", 1, 120, 10, 1)

    st.markdown("---")
    st.markdown("### Calibration (Pixels → Meters)")
    car_length_pixels = st.number_input("Chiều dài xe (pixels)", min_value=10, max_value=2000, value=150)
    car_length_meters = st.number_input("Chiều dài thực (m)", min_value=1.0, max_value=20.0, value=4.5)

    st.markdown("---")
    st.markdown("### Counting Line")
    counting_line_y = st.number_input("Y-coordinate (0 = mặc định)", min_value=0, max_value=4000, value=0)


# ---------------------- HEADER ----------------------
st.markdown("""
<div style="display:flex; align-items:center; gap:12px;">
  <div style="font-size:28px; font-weight:700;">Hệ Thống Giám Sát Giao Thông</div>
  <div style="background:#eef2ff; color:#3b82f6; padding:4px 10px; border-radius:999px; font-size:14px;">Real-time Vehicle Detection System</div>
</div>
""", unsafe_allow_html=True)

st.markdown("<hr style='opacity:0.2;' />", unsafe_allow_html=True)


# ---------------------- MAIN LAYOUT ----------------------
col_video, col_stats = st.columns([2, 1], gap="large")

with col_video:
    st.markdown("### Nguồn Video")

    # Upload video or use path
    uploaded_video = st.file_uploader("Tải Video", type=["mp4", "avi", "mov", "mkv"], help="Chọn file video từ máy")
    video_path_text = st.text_input("Hoặc nhập đường dẫn video", value="video_giao_thong.mp4")

    # Determine video source
    if uploaded_video is not None:
        tmp_path = os.path.join(st.session_state.get("tmp_dir", os.getcwd()), "uploaded_video.mp4")
        with open(tmp_path, "wb") as f:
            f.write(uploaded_video.read())
        video_source = tmp_path
    else:
        video_source = video_path_text

    # Start/Stop buttons
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        start_btn = st.button("🚀 Bắt Đầu Nhận Diện", type="primary", use_container_width=True, disabled=app.is_running)
    with col_btn2:
        stop_btn = st.button("⏹ Dừng", use_container_width=True, disabled=not app.is_running)

    # Video display placeholder
    video_placeholder = st.empty()
    progress_placeholder = st.empty()
    frame_info_placeholder = st.empty()
    
    # Hiển thị video real-time khi đang xử lý
    if app.is_running and app.current_frame is not None:
        video_placeholder.image(app.current_frame, channels="RGB", caption="Đang xử lý...", use_container_width=True)
        frame_info_placeholder.text(f"Frame: {app.current_frame_display}/{app.total_frames_expected}")

    # Logs
    st.markdown("### Lịch Sử Phiên")
    st.caption("Các bản ghi mới nhất")
    st.code("\n".join(app.log_lines[-15:]) or "(trống)", language="text")


with col_stats:
    st.markdown("### Thống Kê Nhanh")
    k1, k2, k3 = st.columns(3)
    total_vehicles = app.last_summary.get("total_vehicles", 0)
    vehicles_passed = app.last_summary.get("vehicle_count", 0)
    avg_speed = app.last_summary.get("avg_speed", 0.0)
    max_speed = app.last_summary.get("max_speed", 0.0)
    
    with k1:
        st.metric(label="Xe Đã Quét (hợp lệ)", value=total_vehicles)
    with k2:
        st.metric(label="Tốc Độ TB", value=f"{avg_speed:.1f} km/h")
    with k3:
        st.metric(label="Tốc Độ Max", value=f"{max_speed:.1f} km/h")
    st.caption(f"Xe qua line: {vehicles_passed}")

    st.markdown("---")
    st.markdown("### Phân Loại Xe")
    breakdown = app.last_summary.get("breakdown", {})
    
    if breakdown:
        for class_name, count in sorted(breakdown.items(), key=lambda x: x[1], reverse=True):
            st.write(f"• {class_name.upper()}: **{count}**")
    else:
        st.write("_(chưa có dữ liệu)_")

    st.markdown("---")
    st.markdown("### Top Tốc Độ")
    recent = app.last_summary.get("recent", [])
    if recent:
        for i, item in enumerate(recent[-5:], 1):
            st.write(f"{i}. ID:{item['id']} {item['class']} - {item['speed']:.1f} km/h")
    else:
        st.write("_(chưa có dữ liệu)_")


# ---------------------- DETAILED RESULTS TABLE ----------------------
if app.last_summary.get("detailed_stats"):
    st.markdown("---")
    st.markdown("### Bảng Thống Kê Chi Tiết")
    
    detailed_stats = app.last_summary.get("detailed_stats", [])
    if detailed_stats:
        df = pd.DataFrame(detailed_stats)
        
        # Reorder and rename columns for display
        display_cols = {
            'vehicle_id': 'ID Xe',
            'class_name': 'Loại Xe',
            'avg_speed': 'Tốc Độ TB (km/h)',
            'max_speed': 'Tốc Độ Max (km/h)',
            'num_frames': 'Số Frame',
            'distance_pixels': 'Khoảng Cách (px)'
        }
        
        if 'avg_speed' in df.columns:
            df['avg_speed'] = df['avg_speed'].astype(float)
            df['max_speed'] = df['max_speed'].astype(float)
            df = df.sort_values('avg_speed', ascending=False)
        
        # Display as table
        st.dataframe(
            df[list(display_cols.keys())].rename(columns=display_cols),
            use_container_width=True,
            hide_index=True
        )
    
    # Summary by vehicle type
    st.markdown("### Thống Kê Theo Loại Xe")
    summary_by_type = app.last_summary.get("summary_by_type", {})
    
    if summary_by_type:
        type_data = []
        for class_name, stats in sorted(summary_by_type.items()):
            type_data.append({
                'Loại Xe': class_name.upper(),
                'Số Lượng': stats['count'],
                'Tốc Độ TB (km/h)': f"{stats['avg_speed']:.2f}",
                'Tốc Độ Max (km/h)': f"{stats['max_speed']:.2f}"
            })
        
        df_summary = pd.DataFrame(type_data)
        st.dataframe(df_summary, use_container_width=True, hide_index=True)


# ======================== SUMMARY RESULTS SECTION ========================
if app.last_summary:
    st.markdown("---")
    st.markdown("## 📊 TÓM TẮT KẾT QUẢ PHÂN TÍCH")
    
    # Extract summary data
    total_vehicles = app.last_summary.get("total_vehicles", 0)
    vehicles_passed = app.last_summary.get("vehicle_count", 0)
    breakdown = app.last_summary.get("breakdown", {})
    avg_speed = app.last_summary.get("avg_speed", 0.0)
    max_speed = app.last_summary.get("max_speed", 0.0)
    detailed_stats = app.last_summary.get("detailed_stats", [])
    summary_by_type = app.last_summary.get("summary_by_type", {})
    
    # Calculate additional metrics
    all_speeds = []
    speed_over_50 = 0
    if detailed_stats:
        for item in detailed_stats:
            try:
                spd = float(item['avg_speed'])
                all_speeds.append(spd)
                if spd > 50:
                    speed_over_50 += 1
            except:
                pass
    
    speed_over_50_pct = (speed_over_50 / len(all_speeds) * 100) if all_speeds else 0.0
    
    # Display comprehensive summary
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🚗 Phương Tiện Phát Hiện")
        st.markdown(f"""
        **Vehicles Detected (valid):** {total_vehicles}
        
        **Vehicles Passed Counting Line:** {vehicles_passed}
        """)
    
    with col2:
        st.markdown("### 📊 Tốc Độ Thống Kê")
        st.markdown(f"""
        **Average Speed:** {avg_speed:.2f} km/h
        
        **Max Speed:** {max_speed:.2f} km/h
        
        **Speed > 50 km/h:** {speed_over_50} ({speed_over_50_pct:.1f}%)
        """)
    
    # Vehicle Breakdown
    st.markdown("### 🚙 Vehicle Breakdown")
    
    if breakdown:
        breakdown_text = ""
        for class_name, count in sorted(breakdown.items(), key=lambda x: x[1], reverse=True):
            pct = (count / total_vehicles * 100) if total_vehicles > 0 else 0
            breakdown_text += f"  - **{class_name}**: {count} ({pct:.1f}%)\n"
        
        st.markdown(breakdown_text)
    
    # Speed Statistics by Type
    st.markdown("### ⚡ Speed Statistics by Vehicle Type")
    
    if summary_by_type:
        speed_breakdown_text = ""
        for class_name, stats in sorted(summary_by_type.items(), key=lambda x: x[1]['count'], reverse=True):
            count = stats['count']
            avg = stats['avg_speed']
            max_s = stats['max_speed']
            speed_breakdown_text += f"**{class_name.upper()}:**\n"
            speed_breakdown_text += f"  - Count: {count}\n"
            speed_breakdown_text += f"  - Average Speed: {avg:.2f} km/h\n"
            speed_breakdown_text += f"  - Max Speed: {max_s:.2f} km/h\n"
            speed_breakdown_text += "\n"
        
        st.markdown(speed_breakdown_text)
    
    # Export summary as text
    st.markdown("---")
    st.markdown("### 💾 Dữ Liệu Đầu Ra")
    
    col_export1, col_export2 = st.columns(2)
    
    with col_export1:
        st.markdown(f"✅ **Video:** `{app.output_video_path}`")
        if os.path.exists(app.output_video_path):
            file_size = os.path.getsize(app.output_video_path) / (1024*1024)
            st.caption(f"Kích thước: {file_size:.2f} MB")
    
    with col_export2:
        st.markdown(f"✅ **CSV:** `{app.output_csv_path}`")
        if os.path.exists(app.output_csv_path):
            file_size = os.path.getsize(app.output_csv_path) / 1024
            st.caption(f"Kích thước: {file_size:.1f} KB")


# ---------------------- BACKGROUND PROCESS ----------------------
def run_analysis_thread(video_path: str):
    """Run analysis in background and build comprehensive statistics"""
    ok = False
    try:
        app.is_running = True
        app.log("🚀 Bắt đầu phân tích...")
        
        # Redirect stdout/stderr to suppress print statements
        import io
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        
        analyzer = TrafficAnalyzer(
            video_path=video_path,
            model_path=model_choice,
            output_video_path=None,  # Tự động tạo theo timestamp
            output_csv_path=app.output_csv_path,
            output_json_path="traffic_statistics_frames.json",
            conf_threshold=conf_threshold,
            iou_threshold=iou_threshold,
            track_iou_threshold=track_iou_threshold,
            reid_iou_threshold=reid_iou_threshold,
            max_age=max_age,
            reid_max_age=reid_max_age,
            min_track_frames=min_track_frames,
        )

        # Load video first to initialize frame dimensions
        if not analyzer.load_video():
            app.log("❌ Không thể mở video")
            app.is_running = False
            return

        # Lưu output path để hiển thị sau
        app.output_video_path = analyzer.output_video_path

        app.total_frames_expected = analyzer.total_frames
        app.log(f"📹 Video: {analyzer.frame_width}x{analyzer.frame_height}, {analyzer.total_frames} frames, {analyzer.fps:.1f} fps")

        # Configure counting line (after video is loaded)
        if counting_line_y > 0:
            analyzer.set_counting_line(y=int(counting_line_y))
            app.log(f"📍 Counting line Y = {counting_line_y}")
        else:
            analyzer.set_counting_line()
            app.log("📍 Counting line mặc định")

        # Calibration
        analyzer.set_calibration(
            reference_object_pixels=int(car_length_pixels), 
            reference_object_meters=float(car_length_meters)
        )
        app.log(f"📏 Calibration: {car_length_pixels} px = {car_length_meters} m")

        # Process video
        app.log("⏳ Đang xử lý video...")
        app.processing_progress = 0.0

        def on_progress(frac: float, frame_idx: int, total_frames: int, frame_rgb: np.ndarray = None):
            # Update progress fraction 0.0-1.0
            app.processing_progress = frac
            app.current_frame_display = frame_idx
            # Lưu frame hiện tại để hiển thị (mỗi 5 frames để giảm tải)
            if frame_rgb is not None and frame_idx % 5 == 0:
                app.current_frame = frame_rgb

        ok = analyzer._continue_processing_with_frame(progress_callback=on_progress)
        
        if ok:
            app.log("✅ Xử lý hoàn tất! Đang chuẩn bị kết quả...")

            # Build comprehensive summary
            tracks = analyzer.dead_tracks + list(analyzer.tracks.values())
            tracks = analyzer.filter_valid_tracks(tracks)
            total = len(tracks)
            
            # Collect all data
            all_speeds = []
            breakdown = defaultdict(int)
            recent = []
            detailed_stats = []
            summary_by_type = defaultdict(lambda: {
                'count': 0, 
                'speeds': [], 
                'avg_speed': 0.0, 
                'max_speed': 0.0, 
                'min_speed': float('inf')
            })
            
            for track in tracks:
                spd = track.get_average_speed()
                max_spd = track.get_max_speed()
                all_speeds.append(spd)
                
                # Breakdown by class
                breakdown[track.class_name] += 1
                
                # Recent detections
                recent.append({
                    "id": track.track_id, 
                    "class": track.class_name, 
                    "speed": spd
                })
                
                # Detailed stats per vehicle
                num_frames = len(track.positions)
                distance = 0.0
                if len(track.positions) > 1:
                    first_pos = track.positions[0]
                    last_pos = track.positions[-1]
                    distance = ((last_pos[0] - first_pos[0])**2 + 
                               (last_pos[1] - first_pos[1])**2) ** 0.5
                
                detailed_stats.append({
                    'vehicle_id': track.track_id,
                    'class_name': track.class_name,
                    'avg_speed': f"{spd:.2f}",
                    'max_speed': f"{max_spd:.2f}",
                    'num_frames': num_frames,
                    'distance_pixels': f"{distance:.2f}"
                })
                
                # Summary by type
                summary_by_type[track.class_name]['count'] += 1
                summary_by_type[track.class_name]['speeds'].append(spd)
                summary_by_type[track.class_name]['max_speed'] = max(
                    summary_by_type[track.class_name]['max_speed'], max_spd
                )
                summary_by_type[track.class_name]['min_speed'] = min(
                    summary_by_type[track.class_name]['min_speed'], spd
                )
            
            # Calculate averages for each type
            for class_name in summary_by_type:
                speeds = summary_by_type[class_name]['speeds']
                if speeds:
                    summary_by_type[class_name]['avg_speed'] = sum(speeds) / len(speeds)
                else:
                    summary_by_type[class_name]['avg_speed'] = 0.0
                
                # Reset min_speed if it's still infinity
                if summary_by_type[class_name]['min_speed'] == float('inf'):
                    summary_by_type[class_name]['min_speed'] = 0.0
            
            # Overall stats
            avg = sum(all_speeds) / len(all_speeds) if all_speeds else 0.0
            mx = max(all_speeds) if all_speeds else 0.0
            
            app.last_summary = {
                "total_vehicles": total,
                "avg_speed": avg,
                "max_speed": mx,
                "vehicle_count": analyzer.vehicle_count,
                "breakdown": dict(breakdown),
                "recent": sorted(recent, key=lambda x: x['speed'], reverse=True)[:10],
                "detailed_stats": detailed_stats,
                "summary_by_type": dict(summary_by_type),
            }
            
            app.log(f"✓ Tổng: {total} xe | Trung bình: {avg:.2f} km/h | Max: {mx:.2f} km/h")
            app.log(f"✓ Video: {app.output_video_path}")
            app.log(f"✓ CSV: {app.output_csv_path}")
            
        else:
            app.log("❌ Phân tích thất bại")
            
    except Exception as e:
        app.log(f"❌ Lỗi: {str(e)}")
    finally:
        app.is_running = False
        app.processing_progress = 1.0 if ok else 0.0
        # Restore stdout/stderr
        try:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
        except:
            pass


# Handle button actions
if start_btn:
    if not video_source or not os.path.exists(video_source):
        st.error("❌ Hãy tải video hoặc nhập đường dẫn chính xác.")
    elif app.is_running:
        st.warning("⏳ Đang chạy, vui lòng đợi...")
    else:
        threading.Thread(
            target=run_analysis_thread, 
            args=(video_source,), 
            daemon=True
        ).start()
        time.sleep(0.5)
        st.toast("✅ Bắt đầu nhận diện!", icon="🎯")
        st.rerun()

if stop_btn and app.is_running:
    app.is_running = False
    app.log("⚠ Yêu cầu dừng (sẽ áp dụng sau frame hiện tại).")
    st.info("Đã yêu cầu dừng.")


st.markdown("---")
st.caption("Powered by Ultralytics YOLOv8, ByteTrack, OpenCV | ITS Traffic Analytics")

# Auto-refresh UI while processing to enable live updates
if app.is_running:
    st.info("⏳ Đang xử lý video... Kết quả sẽ hiển thị ngay khi hoàn tất.")
    try:
        progress_frac = min(max(app.processing_progress, 0.0), 1.0)
        st.progress(progress_frac, key="processing_progress_bar")
    except Exception:
        pass
    time.sleep(0.8)
    st.rerun()


# ======================== RESULTS PAGE - PHAN LOAI XE ========================
st.markdown("""
<div id="phan-loai-xe"></div>
""", unsafe_allow_html=True)

if app.last_summary and app.last_summary.get("total_vehicles", 0) > 0:
    st.markdown("---")
    st.markdown("# 📊 PHÂN LOẠI XE & THỐNG KÊ CHI TIẾT")
    
    total_vehicles = app.last_summary.get("total_vehicles", 0)
    vehicles_passed = app.last_summary.get("vehicle_count", 0)
    breakdown = app.last_summary.get("breakdown", {})
    avg_speed = app.last_summary.get("avg_speed", 0.0)
    max_speed = app.last_summary.get("max_speed", 0.0)
    detailed_stats = app.last_summary.get("detailed_stats", [])
    summary_by_type = app.last_summary.get("summary_by_type", {})
    
    # Calculate additional metrics
    all_speeds = []
    speed_over_50 = 0
    if detailed_stats:
        for item in detailed_stats:
            try:
                spd = float(item['avg_speed'])
                all_speeds.append(spd)
                if spd > 50:
                    speed_over_50 += 1
            except:
                pass
    
    speed_over_50_pct = (speed_over_50 / len(all_speeds) * 100) if all_speeds else 0.0
    
    # ========== PHẦN 1: TỔNG QUAN ==========
    st.markdown("## 🎯 TỔNG QUAN")
    
    col_overview1, col_overview2, col_overview3, col_overview4 = st.columns(4)
    
    with col_overview1:
        st.metric(
            label="🚗 Tổng Xe",
            value=total_vehicles,
            help="Tổng số phương tiện phát hiện"
        )
    
    with col_overview2:
        st.metric(
            label="✅ Qua Line",
            value=vehicles_passed,
            help="Số xe vượt qua đường đếm"
        )
    
    with col_overview3:
        st.metric(
            label="📊 Tốc Độ TB",
            value=f"{avg_speed:.2f} km/h",
            help="Tốc độ trung bình"
        )
    
    with col_overview4:
        st.metric(
            label="⚡ Tốc Độ Max",
            value=f"{max_speed:.2f} km/h",
            help="Tốc độ cao nhất"
        )
    
    # ========== PHẦN 2: PHÂN LOẠI XE ==========
    st.markdown("## 🚙 PHÂN LOẠI XE")
    
    if breakdown:
        # Create breakdown with percentages
        breakdown_data = []
        for class_name, count in sorted(breakdown.items(), key=lambda x: x[1], reverse=True):
            pct = (count / total_vehicles * 100) if total_vehicles > 0 else 0
            breakdown_data.append({
                'Loại Xe': class_name.upper(),
                'Số Lượng': count,
                'Phần Trăm': f"{pct:.1f}%"
            })
        
        df_breakdown = pd.DataFrame(breakdown_data)
        
        # Display as columns with colors
        col_breakdown_left, col_breakdown_right = st.columns(2)
        
        with col_breakdown_left:
            st.markdown("### Bảng Thống Kê")
            st.dataframe(df_breakdown, use_container_width=True, hide_index=True)
        
        with col_breakdown_right:
            st.markdown("### Chi Tiết")
            detail_text = ""
            for item in breakdown_data:
                detail_text += f"**{item['Loại Xe']}:** {item['Số Lượng']} xe ({item['Phần Trăm']})\n\n"
            st.markdown(detail_text)
    
    # ========== PHẦN 3: THỐNG KÊ TỐC ĐỘ ==========
    st.markdown("## ⚡ THỐNG KÊ TỐC ĐỘ TỔNG QUÁT")
    
    col_speed1, col_speed2, col_speed4 = st.columns(3)
    
    with col_speed1:
        st.metric(label="Tốc Độ TB", value=f"{avg_speed:.2f} km/h")
    
    with col_speed2:
        st.metric(label="Tốc Độ Max", value=f"{max_speed:.2f} km/h")
    
    with col_speed4:
        st.metric(label="Vượt 50 km/h", value=f"{speed_over_50} ({speed_over_50_pct:.1f}%)")
    
    # ========== PHẦN 4: THỐNG KÊ THEO LOẠI XE ==========
    st.markdown("## 📈 THỐNG KÊ CHI TIẾT THEO LOẠI XE")
    
    if summary_by_type:
        # Create detailed stats table
        type_stats_data = []
        for class_name, stats in sorted(summary_by_type.items(), key=lambda x: x[1]['count'], reverse=True):
            type_stats_data.append({
                'Loại Xe': class_name.upper(),
                'Số Lượng': stats['count'],
                'Tốc Độ TB (km/h)': f"{stats['avg_speed']:.2f}",
                'Tốc Độ Max (km/h)': f"{stats['max_speed']:.2f}"
            })
        
        df_type_stats = pd.DataFrame(type_stats_data)
        st.dataframe(df_type_stats, use_container_width=True, hide_index=True)
        
        # Display detailed breakdown per type
        st.markdown("### Chi Tiết Từng Loại Xe")
        
        for class_name, stats in sorted(summary_by_type.items(), key=lambda x: x[1]['count'], reverse=True):
            with st.expander(f"🔍 {class_name.upper()} ({stats['count']} xe)"):
                col_type1, col_type2, col_type3 = st.columns(3)
                
                with col_type1:
                    st.metric("Số Lượng", stats['count'])
                
                with col_type2:
                    st.metric("Tốc Độ TB", f"{stats['avg_speed']:.2f} km/h")
                
                with col_type3:
                    st.metric("Tốc Độ Max", f"{stats['max_speed']:.2f} km/h")
                
                # List vehicles of this type
                vehicles_of_type = [v for v in detailed_stats if v['class_name'] == class_name]
                if vehicles_of_type:
                    st.markdown(f"#### Danh Sách {len(vehicles_of_type)} Phương Tiện {class_name.upper()}")
                    
                    type_vehicle_data = []
                    for v in sorted(vehicles_of_type, key=lambda x: float(x['avg_speed']), reverse=True):
                        type_vehicle_data.append({
                            'ID': v['vehicle_id'],
                            'Tốc Độ TB (km/h)': v['avg_speed'],
                            'Tốc Độ Max (km/h)': v['max_speed'],
                            'Frames': v['num_frames'],
                            'Khoảng Cách (px)': v['distance_pixels']
                        })
                    
                    df_type_vehicles = pd.DataFrame(type_vehicle_data)
                    st.dataframe(df_type_vehicles, use_container_width=True, hide_index=True)
    
    # ========== PHẦN 5: DANH SÁCH CHI TIẾT TẤT CẢ XE ==========
    st.markdown("## 📋 DANH SÁCH CHI TIẾT TẤT CẢ PHƯƠNG TIỆN")
    
    if detailed_stats:
        # Create detailed vehicle list
        vehicle_list_data = []
        for v in sorted(detailed_stats, key=lambda x: float(x['avg_speed']), reverse=True):
            vehicle_list_data.append({
                'ID': v['vehicle_id'],
                'Loại Xe': v['class_name'].upper(),
                'Tốc Độ TB (km/h)': f"{float(v['avg_speed']):.2f}",
                'Tốc Độ Max (km/h)': f"{float(v['max_speed']):.2f}",
                'Num Frames': v['num_frames'],
                'Khoảng Cách (px)': f"{float(v['distance_pixels']):.2f}"
            })
        
        df_vehicles = pd.DataFrame(vehicle_list_data)
        st.dataframe(df_vehicles, use_container_width=True, hide_index=True)
        
        # Summary statistics
        st.markdown("### 📊 Thống Kê Tóm Lược")
        st.write(f"""
        **Tổng Phương Tiện:** {len(vehicle_list_data)}
        **Tốc Độ Trung Bình:** {avg_speed:.2f} km/h
        **Tốc Độ Cao Nhất:** {max_speed:.2f} km/h
        **Xe Vượt 50 km/h:** {speed_over_50} ({speed_over_50_pct:.1f}%)
        """)
    
    # ========== PHẦN 6: TÓM TẮT CUỐI CÙNG ==========
    st.markdown("## ✅ TÓM TẮT KẾT QUẢ CUỐI CÙNG")
    
    summary_text = f"""
### 🚗 Phương Tiện Phát Hiện
- **Total Vehicles Detected:** {total_vehicles}
- **Vehicles Passed Counting Line:** {vehicles_passed}

### 📊 Tốc Độ Thống Kê
- **Average Speed:** {avg_speed:.2f} km/h
- **Max Speed:** {max_speed:.2f} km/h
- **Speed > 50 km/h:** {speed_over_50} ({speed_over_50_pct:.1f}%)

### 🚙 Vehicle Breakdown
"""

    for class_name, count in sorted(breakdown.items(), key=lambda x: x[1], reverse=True):
        pct = (count / total_vehicles * 100) if total_vehicles > 0 else 0
        summary_text += f"- **{class_name.upper()}:** {count} ({pct:.1f}%)\n"
    
    summary_text += "\n### ⚡ Speed Statistics by Vehicle Type\n"
    
    for class_name, stats in sorted(summary_by_type.items(), key=lambda x: x[1]['count'], reverse=True):
        summary_text += f"""**{class_name.upper()}:**
  - Count: {stats['count']}
  - Average Speed: {stats['avg_speed']:.2f} km/h
    - Max Speed: {stats['max_speed']:.2f} km/h

"""
    
    st.markdown(summary_text)
    
    # ========== PHẦN 7: PLAYBACK VIDEO ==========
    st.markdown("## ▶️ PLAYBACK VIDEO - Phát Lại Kết Quả")
    
    if app.output_video_path and os.path.exists(app.output_video_path):
        st.success(f"✅ Video đã render sẵn: `{app.output_video_path}`")
        file_size_mb = os.path.getsize(app.output_video_path) / (1024 * 1024)
        st.caption(f"Kích thước: {file_size_mb:.2f} MB")

        # Playback: chỉ phát file đã render, không inference / tính toán khi phát
        st.markdown("### Xem video kết quả:")
        st.video(app.output_video_path, format="video/mp4")
    else:
        st.info("⏳ Chạy xử lý video trước để tạo file kết quả")
    
    # ========== PHẦN 8: DỮ LIỆU ĐẦU RA ==========
    st.markdown("## 💾 DỮ LIỆU ĐẦU RA")
    
    col_file1, col_file2, col_file3 = st.columns(3)
    
    with col_file1:
        st.markdown("### 🎬 Video Kết Quả")
        if app.output_video_path and os.path.exists(app.output_video_path):
            file_size_mb = os.path.getsize(app.output_video_path) / (1024*1024)
            st.success(f"✅ {app.output_video_path}\n**Size:** {file_size_mb:.2f} MB")
        else:
            st.info("⏳ Chưa có video output")
    
    with col_file2:
        st.markdown("### 📊 CSV Thống Kê")
        if os.path.exists(app.output_csv_path):
            file_size_kb = os.path.getsize(app.output_csv_path) / 1024
            st.success(f"✅ {app.output_csv_path}\n**Size:** {file_size_kb:.1f} KB")
        else:
            st.warning(f"❌ File not found: {app.output_csv_path}")
    
    with col_file3:
        st.markdown("### 📋 JSON Frame Data")
        json_path = "traffic_statistics_frames.json"
        if os.path.exists(json_path):
            file_size_kb = os.path.getsize(json_path) / 1024
            st.success(f"✅ {json_path}\n**Size:** {file_size_kb:.1f} KB")
            
            # Hiển thị thông tin JSON
            try:
                import json
                with open(json_path, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                
                metadata = json_data.get('metadata', {})
                st.caption(f"Frames: {metadata.get('total_frames', 0)}")
                st.caption(f"FPS: {metadata.get('fps', 0):.1f}")
            except Exception:
                pass
        else:
            st.warning(f"❌ File not found: {json_path}")
    
    # Auto-scroll to this section when processing completes
    st.markdown("""
    <script>
        if (window.location.hash === '' || !window.location.hash.includes('phan-loai-xe')) {
            window.location.hash = '#phan-loai-xe';
        }
    </script>
    """, unsafe_allow_html=True)
