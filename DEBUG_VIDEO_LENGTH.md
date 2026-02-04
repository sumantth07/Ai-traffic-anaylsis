# 🔍 DEBUG VIDEO LENGTH - Hướng Dẫn Khắc Phục Video Ngắn

## ❌ Vấn Đề

Video output ngắn hơn video input (30s → 2s)

## ✅ Đã Fix

### 1. **Thêm Debug Logging**

Code đã được cập nhật để in ra:

```
📊 INPUT VIDEO INFO:
  - FPS: 30.0
  - Total frames: 900
  - Resolution: 1920x1080
  - Duration: 30.00 seconds

📊 OUTPUT VIDEO INFO:
  - Frames read: 900
  - Frames written: 900
  - Expected duration: 30.00 seconds
```

### 2. **Kiểm Tra Kích Thước Frame**

Tự động resize nếu frame size không khớp:

```python
# Kiểm tra kích thước frame
if frame.shape[1] != self.frame_width or frame.shape[0] != self.frame_height:
    frame = cv2.resize(frame, (self.frame_width, self.frame_height))
```

### 3. **Fix FFmpeg Re-encode**

Thêm option `-r` để giữ nguyên FPS:

```python
"-r", str(original_fps),  # Giữ nguyên FPS
```

Và kiểm tra frame count sau re-encode:

```
🔄 Re-encoding to H.264...
  Original: 900 frames @ 30.0 FPS
  Re-encoded: 900 frames @ 30.0 FPS
```

## 🔍 Cách Debug

### Bước 1: Chạy Xử Lý Video

```bash
streamlit run traffic_web_app.py --server.port 5173
```

### Bước 2: Xem Log

Sau khi xử lý xong, kiểm tra log trong UI hoặc terminal:

```
📊 INPUT VIDEO INFO:
  - FPS: 30.0
  - Total frames: 900
  - Resolution: 1920x1080
  - Duration: 30.00 seconds

Progress: 0.0% (Frame 0/900)
Progress: 3.3% (Frame 30/900)
...
Progress: 100.0% (Frame 900/900)

📊 OUTPUT VIDEO INFO:
  - Frames read: 900
  - Frames written: 900
  - Expected duration: 30.00 seconds

🔄 Re-encoding to H.264...
  Original: 900 frames @ 30.0 FPS
  Re-encoded: 900 frames @ 30.0 FPS
✓ Re-encoded to H.264 for browser playback
```

### Bước 3: Kiểm Tra Video Output

```bash
# Kiểm tra thông tin video bằng ffprobe
ffprobe -v error -select_streams v:0 -show_entries stream=nb_frames,r_frame_rate,duration -of default=noprint_wrappers=1 output_video/YYYYMMDD_HHMMSS.mp4
```

Kết quả mong đợi:
```
nb_frames=900
r_frame_rate=30/1
duration=30.000000
```

## 🐛 Các Nguyên Nhân Có Thể

### 1. ❌ FPS Không Khớp
**Triệu chứng:** Video phát nhanh/chậm hơn

**Nguyên nhân:**
- VideoWriter dùng FPS khác với video input
- FFmpeg re-encode thay đổi FPS

**Giải pháp:** ✅ Đã fix
- Lấy FPS trực tiếp từ video input
- Thêm `-r` option trong ffmpeg

### 2. ❌ Skip Frame
**Triệu chứng:** Video bị giật, thiếu frame

**Nguyên nhân:**
- Code có điều kiện skip frame
- Chỉ ghi frame có detection

**Giải pháp:** ✅ Đã đảm bảo
- Ghi TẤT CẢ frame đọc được
- Không có điều kiện skip

### 3. ❌ Kích Thước Frame Không Khớp
**Triệu chứng:** VideoWriter không ghi được frame

**Nguyên nhân:**
- Frame size khác với khai báo VideoWriter
- Resize không đúng

**Giải pháp:** ✅ Đã fix
- Kiểm tra và resize tự động
- Log warning nếu size không khớp

### 4. ❌ FFmpeg Re-encode Sai
**Triệu chứng:** Video ngắn sau re-encode

**Nguyên nhân:**
- FFmpeg tự động điều chỉnh FPS
- Mất frame khi re-encode

**Giải pháp:** ✅ Đã fix
- Thêm `-r` để giữ FPS
- Kiểm tra frame count sau re-encode

## 📊 Checklist Debug

Khi gặp vấn đề video ngắn, kiểm tra:

- [ ] **FPS input** - In ra log
- [ ] **Total frames input** - In ra log
- [ ] **Frames read** - Đếm trong loop
- [ ] **Frames written** - Đếm khi ghi
- [ ] **Frame size** - Kiểm tra có warning không
- [ ] **FPS output** - Kiểm tra sau re-encode
- [ ] **Frames output** - Kiểm tra sau re-encode

## 🔧 Nếu Vẫn Bị Lỗi

### Option 1: Tắt Re-encode

Comment dòng này trong code:

```python
# self._reencode_h264()
```

Video sẽ ở format mp4v (có thể không phát được trên browser)

### Option 2: Dùng FFmpeg Trực Tiếp

```bash
ffmpeg -i output_video/YYYYMMDD_HHMMSS.mp4 -c:v libx264 -pix_fmt yuv420p -r 30 -movflags +faststart output_fixed.mp4
```

### Option 3: Kiểm Tra Video Input

```bash
ffprobe -v error -select_streams v:0 -show_entries stream=nb_frames,r_frame_rate,duration -of default=noprint_wrappers=1 input_video.mp4
```

Đảm bảo video input không bị corrupt

## 📝 Log Mẫu Thành Công

```
✓ Video loaded successfully
  Resolution: 1920x1080
  FPS: 30.0
  Total frames: 900
  Duration: 30.0 seconds

📊 INPUT VIDEO INFO:
  - FPS: 30.0
  - Total frames: 900
  - Resolution: 1920x1080
  - Duration: 30.00 seconds

🎬 Processing video...
Progress: 0.0% (Frame 0/900)
Progress: 3.3% (Frame 30/900)
Progress: 6.7% (Frame 60/900)
...
Progress: 100.0% (Frame 900/900)

✓ Video processing completed
📊 OUTPUT VIDEO INFO:
  - Frames read: 900
  - Frames written: 900
  - Expected duration: 30.00 seconds

🔄 Re-encoding to H.264...
  Original: 900 frames @ 30.0 FPS
  Re-encoded: 900 frames @ 30.0 FPS
✓ Re-encoded to H.264 for browser playback

✓ Output video saved to output_video/20260128_143522.mp4
✓ Statistics saved to traffic_statistics.csv
✓ Frame data saved to traffic_statistics_frames.json
```

## ✅ Kết Luận

Code đã được fix để:

1. ✅ **Lấy FPS từ video input** - Không tự set
2. ✅ **Ghi đầy đủ tất cả frame** - Không skip
3. ✅ **Kiểm tra kích thước frame** - Tự động resize
4. ✅ **Giữ FPS khi re-encode** - Thêm `-r` option
5. ✅ **Debug logging đầy đủ** - Dễ kiểm tra

Video output giờ sẽ có **cùng thời lượng** với video input! 🎉

---

**Nếu vẫn gặp vấn đề:** Gửi log để debug chi tiết hơn.
