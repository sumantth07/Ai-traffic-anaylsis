# 🚀 HỆ THỐNG STREAMING REAL-TIME - HƯỚNG DẪN

## 🎯 KIẾN TRÚC MỚI

```
┌─────────────────────┐         ┌──────────────────────┐
│   BACKEND           │         │   FRONTEND           │
│   FastAPI           │ ◄─────► │   Streamlit          │
│   Port 8000         │  HTTP   │   Port 5173          │
│                     │         │                      │
│ - YOLO Detection    │         │ - <img> tag stream   │
│ - ByteTrack         │         │ - Real-time stats    │
│ - MJPEG Stream      │         │ - No reload          │
│ - /video_feed       │         │                      │
│ - /stats            │         │                      │
└─────────────────────┘         └──────────────────────┘
```

## ✨ TÍNH NĂNG

### ✅ HOÀN THÀNH
- **Real-time streaming** - Video xử lý hiển thị trực tiếp
- **MJPEG stream** - Không ghi file video ra disk
- **Async processing** - FastAPI backend async
- **Live stats** - FPS, số xe, tốc độ real-time
- **No reload** - Không reload page khi stream
- **Clean shutdown** - Dọn dẹp VideoCapture đúng cách

### 📊 DISPLAY
- Bounding boxes + Track ID
- Tốc độ từng xe (km/h)
- Trajectory (đường đi)
- Counting line
- FPS real-time
- Thống kê trên video

---

## 🚀 CÁCH CHẠY (2 TERMINAL)

### **Terminal 1: Backend (FastAPI)**
```bash
# Chạy backend
python streaming_backend.py
```

**Output mong đợi:**
```
🚀 Starting FastAPI Streaming Backend...
📡 Video stream: http://localhost:8000/video_feed
📊 Stats API: http://localhost:8000/stats
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### **Terminal 2: Frontend (Streamlit)**
```bash
# Chạy frontend
python -m streamlit run traffic_web_app_streaming.py --server.port 5173
```

**Output mong đợi:**
```
You can now view your Streamlit app in your browser.
Local URL: http://localhost:5173
```

---

## 📖 CÁCH SỬ DỤNG

### **Bước 1: Mở trình duyệt**
- Frontend: **http://localhost:5173**
- Backend API: **http://localhost:8000/docs** (FastAPI Swagger UI)

### **Bước 2: Upload video**
- Click "Tải Video" hoặc nhập đường dẫn
- VD: `video_giao_thong.mp4`

### **Bước 3: Cấu hình (Sidebar)**
- Model YOLO: `yolov8n.pt` (nhanh) hoặc `yolov8s.pt`
- Tracking parameters: Giữ mặc định
- Calibration: 150 px = 4.5 m

### **Bước 4: Bắt đầu streaming**
- Click **"🚀 Bắt Đầu Nhận Diện"**
- Video sẽ **hiển thị ngay** ở "Nguồn Video"
- Thống kê cập nhật real-time (bên phải)

### **Bước 5: Dừng streaming**
- Click **"⏹ Dừng"** bất cứ lúc nào
- Stream sẽ dừng ngay lập tức

---

## 🔧 API ENDPOINTS (Backend)

### **POST /start**
Bắt đầu streaming
```python
params = {
    "video_path": "video.mp4",
    "model_path": "yolov8n.pt",
    "conf_threshold": 0.5,
    "track_iou_threshold": 0.3,
    # ... other params
}
```

### **POST /stop**
Dừng streaming
```python
# No params needed
```

### **GET /video_feed**
MJPEG video stream
```
Content-Type: multipart/x-mixed-replace; boundary=frame
```

### **GET /stats**
Lấy thống kê real-time
```json
{
    "total_vehicles": 14,
    "vehicle_count": 10,
    "avg_speed": 45.2,
    "max_speed": 92.7,
    "breakdown": {
        "car": 8,
        "truck": 5,
        "bus": 1
    },
    "fps": 28.5
}
```

### **GET /status**
Kiểm tra trạng thái
```json
{
    "is_streaming": true,
    "video_path": "video_giao_thong.mp4"
}
```

---

## 📂 FILES

### **Mới tạo:**
1. **`streaming_backend.py`** - FastAPI backend
2. **`traffic_web_app_streaming.py`** - Streamlit frontend
3. **`STREAMING_GUIDE.md`** - File này

### **Giữ nguyên:**
- `traffic_analysis.py` - YOLO + ByteTrack logic
- `yolov8n.pt`, `yolov8s.pt` - Models

### **Không dùng:**
- `traffic_web_app.py` - Version offline cũ
- `traffic_web_app_realtime.py` - Version cũ không dùng backend

---

## ⚡ ƯU ĐIỂM

| Tính năng | Offline Version | **Streaming Version** ✨ |
|-----------|----------------|------------------------|
| Hiển thị | Sau khi xử lý | **Real-time** |
| File output | Ghi video .mp4 | **Không ghi file** |
| Memory | Tốn RAM cao | **Tiết kiệm RAM** |
| Tốc độ | Chậm (ghi file) | **Nhanh (no I/O)** |
| Tương tác | Chờ đợi | **Dừng bất kỳ lúc nào** |
| FPS display | Không | **Có** |
| Stats | Sau khi xong | **Real-time** |

---

## 🐛 TROUBLESHOOTING

### **Lỗi: Backend không kết nối**
```bash
# Kiểm tra backend đang chạy
curl http://localhost:8000

# Hoặc mở browser: http://localhost:8000
```

### **Lỗi: Video không hiển thị**
1. Kiểm tra backend logs (Terminal 1)
2. Kiểm tra đường dẫn video đúng
3. F12 browser → Console → Xem lỗi

### **Lỗi: Cannot find video file**
```bash
# Kiểm tra file tồn tại
ls video_giao_thong.mp4

# Hoặc dùng đường dẫn đầy đủ
D:\Videos\traffic.mp4
```

### **Lỗi: Port already in use**
```bash
# Dừng process trên port 8000
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Hoặc thay đổi port trong streaming_backend.py
uvicorn.run(app, host="0.0.0.0", port=8001)
```

---

## 🔥 SO SÁNH 3 VERSIONS

### **1. traffic_web_app.py (Offline)**
- ✅ Xử lý offline hoàn chỉnh
- ✅ Ghi video output
- ❌ Phải chờ lâu

### **2. traffic_web_app_realtime.py (Single Thread)**
- ✅ Hiển thị real-time
- ❌ Reload page liên tục
- ❌ Chậm

### **3. traffic_web_app_streaming.py (Streaming)** ⭐
- ✅ Real-time streaming
- ✅ Không reload page
- ✅ FastAPI async
- ✅ Không ghi file
- ✅ FPS cao

---

## 📚 TECH STACK

- **Backend:** FastAPI + Uvicorn
- **Frontend:** Streamlit + Custom HTML/JS
- **Video:** OpenCV
- **Detection:** YOLOv8 (Ultralytics)
- **Tracking:** ByteTrack
- **Streaming:** MJPEG (multipart/x-mixed-replace)

---

## 💡 TIPS

1. **Tối ưu FPS:** Dùng `yolov8n.pt` cho tốc độ cao
2. **GPU:** YOLO tự động dùng GPU nếu có CUDA
3. **Network:** Có thể truy cập từ máy khác: `http://<YOUR_IP>:5173`
4. **Production:** Nên dùng NGINX reverse proxy
5. **Debug:** Xem logs ở cả 2 terminal

---

**Hoàn tất! Hệ thống streaming real-time sẵn sàng!** 🚀
