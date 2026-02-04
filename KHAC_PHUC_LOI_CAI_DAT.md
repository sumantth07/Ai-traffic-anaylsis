# 🔧 KHẮC PHỤC LỖI CÀI ĐẶT

## ❌ Lỗi: "AttributeError: module 'pkgutil' has no attribute 'ImpImporter'"

### Nguyên nhân:
- Bạn đang dùng **Python 3.13** (quá mới)
- File `requirements.txt` cũ có **numpy 1.24.3** (không tương thích với Python 3.13)

### ✅ Giải pháp:

#### Cách 1: Cài đặt lại (Đã fix)

File `requirements.txt` đã được cập nhật để tương thích với Python 3.9-3.13:

```bash
pip install -r requirements.txt
```

#### Cách 2: Nếu vẫn lỗi

Cài từng package riêng:

```bash
pip install opencv-python
pip install numpy
pip install ultralytics
pip install streamlit
pip install pandas
pip install matplotlib
pip install pyyaml
pip install tqdm
pip install Pillow
```

#### Cách 3: Dùng Python 3.11 (Khuyến nghị cho ổn định)

1. Gỡ virtual environment cũ:
```bash
rmdir /s /q .venv
```

2. Cài Python 3.11 từ: https://www.python.org/downloads/

3. Tạo virtual environment mới với Python 3.11:
```bash
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## ✅ Kiểm Tra Cài Đặt Thành Công

```bash
python -c "import cv2, numpy, ultralytics, streamlit; print('✅ All packages installed!')"
```

Nếu không có lỗi → Cài đặt thành công!

## 🚀 Bắt Đầu Sử Dụng

```bash
streamlit run traffic_web_app.py --server.port 5173
```

Hoặc:
```bash
START_WEB_APP.bat
```

## 📝 Lưu Ý

### Python Version Compatibility:
- ✅ **Python 3.9 - 3.12**: Hoàn toàn tương thích
- ⚠️ **Python 3.13**: Tương thích nhưng cần numpy >= 1.26.0
- ❌ **Python 3.8 trở xuống**: Không được hỗ trợ

### Khuyến nghị:
- Dùng **Python 3.11** cho ổn định nhất
- Dùng **Python 3.12** cho hiệu năng tốt
- Tránh dùng Python 3.13 (quá mới, có thể có lỗi)

## 🔍 Các Lỗi Khác

### Lỗi: "torch not found"
PyTorch không bắt buộc (ultralytics sẽ tự cài). Nếu muốn cài thủ công:

**CPU only:**
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

**GPU (CUDA 11.8):**
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

### Lỗi: "ffmpeg not found"
Video vẫn được tạo (format mp4v). Để có H.264:

**Windows:**
1. Download ffmpeg: https://ffmpeg.org/download.html
2. Giải nén và thêm vào PATH

**Linux:**
```bash
sudo apt install ffmpeg
```

### Lỗi: "streamlit command not found"
```bash
pip install --upgrade streamlit
```

Hoặc chạy trực tiếp:
```bash
python -m streamlit run traffic_web_app.py --server.port 5173
```

## ✅ Checklist Cài Đặt

- [ ] Python 3.9-3.12 đã cài
- [ ] Virtual environment đã tạo
- [ ] `pip install -r requirements.txt` thành công
- [ ] Test import packages thành công
- [ ] Streamlit chạy được

## 🎉 Hoàn Thành!

Nếu tất cả OK, bắt đầu sử dụng:

```bash
streamlit run traffic_web_app.py --server.port 5173
```

Đọc thêm: [BAT_DAU_O_DAY.md](BAT_DAU_O_DAY.md)
