"""
STREAMING FRONTEND - Streamlit Web UI
Tích hợp với FastAPI backend để hiển thị real-time stream
"""

import os
import time
import requests
import streamlit as st
import streamlit.components.v1 as components
from typing import Dict, Any

# ==================== CONFIG ====================
BACKEND_URL = "http://localhost:8002"

st.set_page_config(
    page_title="Hệ Thống Giám Sát Giao Thông - Real-time Streaming",
    page_icon="🚦",
    layout="wide"
)

# ==================== SESSION STATE ====================
if "is_streaming" not in st.session_state:
    st.session_state.is_streaming = False
if "stats" not in st.session_state:
    st.session_state.stats = {
        "total_vehicles": 0,
        "vehicle_count": 0,
        "avg_speed": 0.0,
        "max_speed": 0.0,
        "breakdown": {},
        "fps": 0.0
    }

# ==================== SIDEBAR ====================
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

# ==================== HEADER ====================
st.markdown("# 🚦 Hệ Thống Giám Sát Giao Thông")
st.markdown("### 🎥 Real-time Video Streaming (YOLO + ByteTrack)")
st.markdown("---")

# ==================== MAIN LAYOUT ====================
col_video, col_stats = st.columns([2, 1], gap="large")

with col_video:
    st.markdown("### 📹 Nguồn Video")
    
    # Video source
    uploaded_video = st.file_uploader(
        "Tải Video",
        type=["mp4", "avi", "mov", "mkv"],
        disabled=st.session_state.is_streaming
    )
    
    video_path_text = st.text_input(
        "Hoặc đường dẫn video",
        value="video_giao_thong.mp4",
        disabled=st.session_state.is_streaming
    )

    # Determine video source
    if uploaded_video is not None:
        tmp_path = "uploaded_video_temp.mp4"
        if not st.session_state.is_streaming:
            with open(tmp_path, "wb") as f:
                f.write(uploaded_video.read())
        video_source = tmp_path
    else:
        video_source = video_path_text

    # Start/Stop buttons
    col_btn1, col_btn2 = st.columns(2)
    
    with col_btn1:
        start_btn = st.button(
            "🚀 Bắt Đầu Nhận Diện",
            type="primary",
            use_container_width=True,
            disabled=st.session_state.is_streaming
        )
    
    with col_btn2:
        stop_btn = st.button(
            "⏹ Dừng",
            use_container_width=True,
            disabled=not st.session_state.is_streaming
        )

    # ===== VIDEO STREAM DISPLAY =====
    st.markdown("### 🎬 Video Stream")
    
    video_html = f"""
    <div style="width: 100%; background: #000; border-radius: 8px; overflow: hidden;">
        <img 
            id="video-stream" 
            src="{BACKEND_URL}/video_feed" 
            style="width: 100%; height: auto; display: {'block' if st.session_state.is_streaming else 'none'};"
        />
        <div 
            id="no-stream-msg" 
            style="padding: 100px; text-align: center; color: #888; display: {'none' if st.session_state.is_streaming else 'block'};"
        >
            <h3>⏸️ Chưa có stream</h3>
            <p>Nhấn "Bắt Đầu Nhận Diện" để bắt đầu</p>
        </div>
    </div>
    
    <script>
        // Auto-refresh image khi streaming
        const videoImg = document.getElementById('video-stream');
        const noStreamMsg = document.getElementById('no-stream-msg');
        
        function updateStreamVisibility(isStreaming) {{
            if (isStreaming) {{
                videoImg.style.display = 'block';
                noStreamMsg.style.display = 'none';
                // Refresh stream URL to prevent caching
                videoImg.src = "{BACKEND_URL}/video_feed?t=" + new Date().getTime();
            }} else {{
                videoImg.style.display = 'none';
                noStreamMsg.style.display = 'block';
                videoImg.src = '';
            }}
        }}
        
        // Initial state
        updateStreamVisibility({str(st.session_state.is_streaming).lower()});
    </script>
    """
    
    components.html(video_html, height=500)

with col_stats:
    st.markdown("### 📊 Thống Kê Real-time")
    
    # Metrics
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
    
    # FPS
    st.metric("FPS", f"{st.session_state.stats.get('fps', 0.0):.1f}")
    
    st.markdown("---")
    st.markdown("### 🚗 Phân Loại")
    
    breakdown = st.session_state.stats.get("breakdown", {})
    if breakdown:
        for class_name, count in sorted(breakdown.items(), key=lambda x: x[1], reverse=True):
            st.write(f"• **{class_name.upper()}**: {count}")
    else:
        st.write("_(chưa có dữ liệu)_")
    
    st.markdown("---")
    
    # Backend status
    try:
        response = requests.get(f"{BACKEND_URL}/status", timeout=1)
        if response.status_code == 200:
            status_data = response.json()
            if status_data["is_streaming"]:
                st.success("🟢 Backend đang streaming")
            else:
                st.info("⚪ Backend sẵn sàng")
        else:
            st.warning("⚠️ Backend không phản hồi")
    except:
        st.error("🔴 Backend offline")

# ==================== BUTTON ACTIONS ====================

if start_btn:
    if not video_source or not os.path.exists(video_source):
        st.error("❌ Video không tồn tại!")
    else:
        # Call backend API to start streaming
        try:
            with st.spinner("⏳ Đang khởi động streaming..."):
                response = requests.post(
                    f"{BACKEND_URL}/start",
                    params={
                        "video_path": video_source,
                        "model_path": model_choice,
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
                    },
                    timeout=10
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result["status"] == "success":
                        st.session_state.is_streaming = True
                        st.success("✅ Streaming đã bắt đầu!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(f"❌ {result['message']}")
                else:
                    st.error("❌ Không thể kết nối backend!")
        except Exception as e:
            st.error(f"❌ Lỗi: {str(e)}")

if stop_btn:
    try:
        with st.spinner("⏳ Đang dừng streaming..."):
            response = requests.post(f"{BACKEND_URL}/stop", timeout=5)
            
            if response.status_code == 200:
                result = response.json()
                if result["status"] == "success":
                    st.session_state.is_streaming = False
                    st.info("⏹️ Streaming đã dừng")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error(f"❌ {result['message']}")
            else:
                st.error("❌ Không thể dừng streaming!")
    except Exception as e:
        st.error(f"❌ Lỗi: {str(e)}")

# ==================== AUTO-UPDATE STATS ====================

if st.session_state.is_streaming:
    # Fetch stats from backend
    try:
        response = requests.get(f"{BACKEND_URL}/stats", timeout=1)
        if response.status_code == 200:
            st.session_state.stats = response.json()
    except:
        pass
    
    # Auto-refresh UI
    time.sleep(1)
    st.rerun()

# ==================== FOOTER ====================
st.markdown("---")
st.caption("🚀 Powered by YOLOv8 + ByteTrack + FastAPI + Streamlit | Real-time Streaming")
st.caption(f"📡 Backend: {BACKEND_URL}")
