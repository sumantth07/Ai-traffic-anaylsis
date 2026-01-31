# 🚦 HƯỚNG DẪN SỬ DỤNG HỆ THỐNG PHÂN TÍCH GIAO THÔNG ITS

## 📋 Tổng Quan

Hệ thống phân tích video giao thông thông minh sử dụng YOLOv8 + ByteTrack để:
- ✅ Phát hiện và theo dõi phương tiện (xe hơi, xe máy, xe buýt, xe tải)
- ✅ Đếm xe qua đường đếm (counting line)
- ✅ Tính toán tốc độ từng phương tiện
- ✅ Xuất kết quả: Video đã render + CSV thống kê + JSON frame data

## 🎯 Đặc Điểm Chính

### 1. **Xử Lý Offline - Không Real-time**
- Video được xử lý **hoàn toàn offline** trước
- YOLO inference + tracking chạy 1 lần duy nhất
- Kết quả được lưu vào:
  - `output_rendered.mp4` - Video đã vẽ bounding box, ID, tốc độ
  - `traffic_statistics.csv` - Thống kê tổng hợp từng xe
  - `traffic_statistics_frames.json` - Tracking data chi tiết từng frame

### 2. **Tracking Chính Xác - Không Duplicate ID**
- Mỗi xe có **1 ID duy nhất** trong toàn bộ video
- ByteTrack với Re-identification:
  - `track_iou_threshold`: Ngưỡng IoU để match detection với track
  - `reid_iou_threshold`: Ngưỡng IoU để re-identify lost tracks
  - `max_age`: Số frame tối đa track có thể mất detection
  - `reid_max_age`: Số frame tối đa để re-identify track đã mất
  - `min_track_frames`: Số frame tối thiểu để track được coi là hợp lệ

### 3. **Giả Lập Real-time Trên UI**
- Khi xem kết quả: phát video đã render sẵn
- **KHÔNG** chạy inference lúc playback
- Tạo cảm giác real-time nhưng thực chất là playback

## 🚀 Cách Sử Dụng

### Bước 1: Khởi động Web App

```bash
streamlit run traffic_web_app.py --server.port 5173
```

Hoặc sử dụng file batch:
```bash
START_WEB_APP.bat
```

### Bước 2: Cấu Hình Trên Sidebar

#### **Model YOLO**
- `yolov8n.pt` - Nano (nhanh nhất, độ chính xác thấp)
- `yolov8s.pt` - Small (cân bằng)
- `yolov8m.pt` - Medium (chính xác hơn)
- `yolov8l.pt` - Large (chính xác nhất, chậm nhất)

**Khuyến nghị:** Dùng `yolov8n.pt` hoặc `yolov8s.pt` cho đồ án

#### **Detection Thresholds**
- **Confidence Threshold** (0.5): Ngưỡng tin cậy detection
- **IoU Threshold** (0.5): Ngưỡng IoU cho NMS

#### **Tracking Parameters** (QUAN TRỌNG!)
- **Track IoU Threshold** (0.3): Ngưỡng IoU để match detection với track hiện tại
  - Giảm → dễ match hơn, ít mất track
  - Tăng → khó match hơn, nhiều ID mới
  
- **ReID IoU Threshold** (0.25): Ngưỡng IoU để re-identify lost tracks
  - Giảm → dễ re-ID, giảm duplicate ID
  - Tăng → khó re-ID, nhiều ID mới
  
- **Max Age** (60 frames): Số frame tối đa track có thể mất detection
  - Tăng → giữ track lâu hơn khi bị che khuất
  - Giảm → xóa track nhanh hơn
  
- **ReID Max Age** (150 frames): Số frame tối đa để re-identify
  - Tăng → có thể re-ID sau khi mất lâu
  - Giảm → chỉ re-ID trong thời gian ngắn
  
- **Min Track Frames** (10): Số frame tối thiểu để track hợp lệ
  - Tăng → lọc bỏ track ngắn (giảm noise)
  - Giảm → giữ nhiều track hơn

#### **Calibration (Tính Tốc Độ)**
- **Chiều dài xe (pixels)**: Đo chiều dài xe trong video (ví dụ: 150 px)
- **Chiều dài thực (m)**: Chiều dài thực tế của xe (ví dụ: 4.5 m)

**Cách đo:**
1. Pause video tại frame có xe rõ ràng
2. Dùng công cụ đo (Paint, Photoshop) để đo chiều dài xe trong video
3. Nhập giá trị vào UI

#### **Counting Line**
- **Y-coordinate**: Tọa độ Y của đường đếm (0 = tự động ở 2/3 chiều cao)
- Xe cắt qua line từ trên xuống sẽ được đếm

### Bước 3: Upload Video

**Cách 1:** Upload file từ máy
- Click "Tải Video"
- Chọn file MP4/AVI/MOV/MKV

**Cách 2:** Nhập đường dẫn
- Nhập path vào ô "Hoặc nhập đường dẫn video"
- Ví dụ: `test_traffic.mp4`

### Bước 4: Bắt Đầu Xử Lý

1. Click **"🚀 Bắt Đầu Nhận Diện"**
2. Đợi xử lý (có progress bar)
3. Kết quả sẽ hiển thị tự động khi hoàn tất

**Lưu ý:**
- Xử lý có thể mất vài phút tùy video
- Không tắt trình duyệt khi đang xử lý
- Có thể click "⏹ Dừng" để dừng giữa chừng

### Bước 5: Xem Kết Quả

#### **Thống Kê Nhanh**
- Tổng số xe phát hiện
- Tốc độ trung bình / tối đa
- Số xe qua counting line

#### **Phân Loại Xe**
- Số lượng từng loại: Car, Motorbike, Bus, Truck, ...
- Phần trăm từng loại

#### **Bảng Chi Tiết**
- Danh sách tất cả xe với:
  - ID xe
  - Loại xe
  - Tốc độ TB / Max
  - Số frame xuất hiện
  - Khoảng cách di chuyển

#### **Playback Video**
- Xem video đã render với:
  - Bounding box màu sắc theo ID
  - Label: ID + Loại xe + Tốc độ
  - Trajectory (đường đi)
  - Counting line
  - Info bar (frame, FPS, số xe)

## 📊 Kết Quả Đầu Ra

### 1. **Video Rendered** (`output_rendered.mp4`)
- Video gốc + overlay tracking
- Có thể phát trực tiếp trên browser
- Format: H.264 (tương thích tốt)

### 2. **CSV Thống Kê** (`traffic_statistics.csv`)
```csv
vehicle_id,class_name,frame_started,num_frames,avg_speed,max_speed,distance_pixels
1,car,10,150,45.23,52.10,850.50
2,motorbike,25,120,38.50,45.00,720.30
...
```

### 3. **JSON Frame Data** (`traffic_statistics_frames.json`)
```json
{
  "metadata": {
    "video_path": "test_traffic.mp4",
    "total_frames": 1500,
    "fps": 30.0,
    "resolution": {"width": 1920, "height": 1080},
    "counting_line_y": 720,
    "total_vehicles": 25,
    "vehicles_passed": 18
  },
  "frames": {
    "0": [
      {
        "track_id": 1,
        "class_name": "car",
        "bbox": {"x1": 100, "y1": 200, "x2": 250, "y2": 350},
        "center": {"x": 175, "y": 275},
        "speed": 45.5,
        "crossed_line": false
      }
    ],
    "1": [...],
    ...
  }
}
```

**Ứng dụng JSON:**
- Phân tích chi tiết từng frame
- Tái tạo visualization tùy chỉnh
- Export sang format khác
- Tích hợp với hệ thống khác

## 🔧 Tối Ưu Tracking

### Vấn đề: Nhiều ID cho 1 xe

**Nguyên nhân:**
- Track bị mất khi xe bị che khuất
- Không re-identify được khi xe xuất hiện lại

**Giải pháp:**
1. Tăng `Max Age` (60 → 90)
2. Tăng `ReID Max Age` (150 → 200)
3. Giảm `ReID IoU Threshold` (0.25 → 0.20)

### Vấn đề: Nhiều xe chung 1 ID

**Nguyên nhân:**
- IoU threshold quá thấp
- Match nhầm giữa các xe

**Giải pháp:**
1. Tăng `Track IoU Threshold` (0.3 → 0.4)
2. Tăng `ReID IoU Threshold` (0.25 → 0.30)

### Vấn đề: Đếm trùng xe

**Nguyên nhân:**
- Track bị tạo mới nhiều lần
- Không filter track ngắn

**Giải pháp:**
1. Tăng `Min Track Frames` (10 → 20)
2. Tăng `Max Age` để giữ track lâu hơn

## 📝 Tips & Best Practices

### 1. **Chọn Video Tốt**
- Góc nhìn từ trên cao (bird's eye view)
- Ánh sáng tốt, không bị mờ
- Xe di chuyển rõ ràng, không bị che khuất nhiều
- FPS ổn định (30 FPS trở lên)

### 2. **Calibration Chính Xác**
- Đo nhiều xe khác nhau, lấy trung bình
- Chọn xe ở giữa frame (ít bị méo)
- Dùng xe có kích thước chuẩn (4.5m cho sedan)

### 3. **Counting Line Hợp Lý**
- Đặt ở vị trí xe đi qua rõ ràng
- Tránh đặt ở chỗ xe dừng/tắc đường
- Thường đặt ở 2/3 chiều cao video

### 4. **Xử Lý Batch**
- Nếu có nhiều video, xử lý từng video riêng
- Lưu kết quả với tên khác nhau
- So sánh kết quả giữa các video

## 🎓 Ứng Dụng Cho Đồ Án ITS

### 1. **Phân Tích Lưu Lượng Giao Thông**
- Đếm số xe qua điểm quan sát
- Phân loại loại xe (car, bike, bus, truck)
- Tính tốc độ trung bình theo từng loại

### 2. **Phát Hiện Vi Phạm**
- Xe chạy quá tốc độ (> 50 km/h)
- Thống kê tỷ lệ vi phạm
- Xuất danh sách xe vi phạm

### 3. **Tối Ưu Hạ Tầng**
- Phân tích giờ cao điểm
- Đề xuất cải thiện đường
- Tính toán mật độ giao thông

### 4. **Báo Cáo Đồ Án**
- Screenshot kết quả từ UI
- Xuất CSV/JSON để vẽ biểu đồ
- Video demo với tracking

## ❓ Troubleshooting

### Lỗi: "Cannot open video"
- Kiểm tra đường dẫn video đúng
- Kiểm tra format video (MP4/AVI/MOV)
- Thử upload trực tiếp thay vì dùng path

### Lỗi: "YOLO not installed"
```bash
pip install ultralytics
```

### Lỗi: "ffmpeg not found"
- Video vẫn được tạo nhưng format mp4v
- Cài ffmpeg để có H.264:
  - Windows: Download từ ffmpeg.org
  - Linux: `sudo apt install ffmpeg`

### Video không phát được trên browser
- Cài ffmpeg để re-encode sang H.264
- Hoặc download video về xem bằng VLC

### Tracking không chính xác
- Điều chỉnh tracking parameters (xem phần Tối Ưu Tracking)
- Thử model YOLO lớn hơn (s → m → l)
- Kiểm tra chất lượng video đầu vào

## 📚 Tài Liệu Tham Khảo

- **YOLOv8**: https://docs.ultralytics.com/
- **ByteTrack**: https://github.com/ifzhang/ByteTrack
- **OpenCV**: https://docs.opencv.org/
- **Streamlit**: https://docs.streamlit.io/

## 🎉 Kết Luận

Hệ thống này đáp ứng đầy đủ yêu cầu đồ án ITS:
- ✅ Xử lý offline, không real-time
- ✅ Tracking chính xác, không duplicate ID
- ✅ Lưu kết quả chi tiết (video + CSV + JSON)
- ✅ UI trực quan, dễ sử dụng
- ✅ Giả lập real-time khi playback

Chúc bạn thành công với đồ án! 🚀
