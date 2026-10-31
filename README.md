# ScreenShotTool

[![tests](https://github.com/btanh258/ScreenShotTool/actions/workflows/tests.yml/badge.svg)](../../actions/workflows/tests.yml)
![Release](https://img.shields.io/github/v/release/btanh258/ScreenShotTool)
![License](https://img.shields.io/github/license/btanh258/ScreenShotTool)

ScreenShotTool là công cụ chụp màn hình cho Windows, viết bằng Python/Tkinter và Pillow. Ứng dụng chạy nền trong khay hệ thống, hỗ trợ phím tắt chụp nhanh, tự nhận diện cửa sổ/UI khi OpenCV khả dụng, sao chép ảnh vào clipboard và chỉnh sửa ảnh với annotation.

![Editor với một chú thích chữ nhật đang vẽ](docs/screenshots/editor-annotated.png)

*Editor: rail công cụ bên trái, inspector bên phải, canvas ở giữa với một hình chữ nhật đang được vẽ.*

| | |
|---|---|
| ![Cửa sổ hẹp — inspector nổi thành drawer](docs/screenshots/editor-narrow.png) | ![Dialog thông tin và phím tắt](docs/screenshots/info-dialog.png) |
| *Cửa sổ hẹp: inspector nổi thành drawer, có nút đóng* | *Dialog thông tin: phím tắt dạng nhóm* |

## Tải bản EXE

Bản chạy độc lập nằm ở tab **[Releases](../../releases/latest)** của repository, file `ScreenShotTool.exe` (one-file, ~72 MB, build từ đúng mã nguồn này).

Tải file EXE về máy Windows rồi chạy trực tiếp. Không cần cài Python hoặc các thư viện trong `requirements.txt`. Windows SmartScreen có thể hiển thị cảnh báo vì file chưa được ký số; đây là binary phát hành nội bộ từ repository này.

> Binary không được lưu trong git vì dung lượng lớn. Muốn tự build, xem mục **Đóng gói EXE** bên dưới.

## Cài đặt và chạy EXE

1. Vào tab **Releases**, tải `ScreenShotTool.exe` từ bản phát hành mới nhất.
2. Đặt file vào một thư mục mà tài khoản người dùng có quyền ghi, ví dụ `Documents\ScreenShotTool`.
3. Double-click file EXE để chạy. Ứng dụng sẽ thu nhỏ xuống system tray thay vì mở một cửa sổ chính.
4. Nhấn `Alt+X` để bắt đầu chụp. Có thể mở menu bằng cách click phải vào biểu tượng ScreenShotTool trong system tray.
5. Thoát ứng dụng từ menu tray khi không còn sử dụng.

Ứng dụng lưu `ScreenShotTool_config.json` cạnh file EXE. Nếu thư mục EXE không có quyền ghi, hãy đặt file trong thư mục người dùng hoặc cấp quyền phù hợp.

## Chạy từ mã nguồn

Yêu cầu Windows, Python 3.11+ và các dependency trong `requirements.txt`:

```powershell
py -m pip install -r requirements.txt
py ScreenShotTool.pyw
```

Biểu tượng `icon_ScreenShotTool.ico` phải nằm cạnh mã nguồn. Một số tính năng Windows như clipboard, system tray và global hotkey cần chạy trên Windows.

## Hướng dẫn sử dụng

### Chụp màn hình

- `Alt+X`: mở lớp phủ chụp toàn desktop.
- Kéo chuột để chọn một vùng; thả chuột để hoàn tất.
- Click vào một cửa sổ hoặc vùng UI được nhận diện để chụp nhanh vùng đó.
- Di chuyển chuột để xem kính lúp và đường căn chỉnh.
- `Esc`: hủy lần chụp hiện tại.
- Ảnh sau khi chụp được sao chép vào clipboard nếu clipboard khả dụng. Toast kết quả cho phép mở ảnh trong editor.

### Chỉnh sửa ảnh

Editor hỗ trợ các công cụ:

- **Chọn**: chọn, kéo di chuyển annotation; `Ctrl+click` chọn nhiều object; kéo marquee để chọn nhóm; `Ctrl+A` chọn tất cả.
- **Cắt**: kéo vùng cần giữ, nhấn `Enter` để xác nhận hoặc `Esc` để hủy.
- **Xóa**: xóa pixel nền trong vùng kéo chọn nhưng giữ annotation trong model.
- **Bút** và **Dạ quang**: vẽ tự do với độ dày và màu đang chọn.
- **Chữ nhật**, **Oval**, **Mũi tên**: thêm hình chú thích; giữ `Shift` khi vẽ oval để tạo hình tròn.
- **Văn bản**: click vào ảnh để nhập chữ; double-click văn bản trong chế độ Chọn để sửa.
- **Làm mờ**: kéo vùng cần làm mờ.

Các thao tác khác trên toolbar gồm đổi màu, đổi độ dày nét, bật nền chữ, zoom, lật ngang/dọc và xoay trái/phải 90 độ.

### Phím tắt editor

| Phím tắt | Tác vụ |
|---|---|
| `Ctrl+Z` | Hoàn tác |
| `Ctrl+Y` | Làm lại |
| `Ctrl+C` | Sao chép ảnh kết quả vào clipboard |
| `Ctrl+S` | Lưu ảnh PNG/JPEG |
| `Delete` | Xóa annotation đang chọn |
| Mũi tên | Di chuyển object hoặc nhóm 1 pixel |
| `Shift` + Mũi tên | Di chuyển object hoặc nhóm 10 pixel |
| `Enter` | Xác nhận crop |
| `Esc` | Bỏ chọn hoặc hủy overlay/chỉnh sửa |

Có thể thay đổi phím tắt trong **Info → Gán phím tắt**. Tổ hợp phím được kiểm tra trùng lặp trước khi lưu.

### Lưu và chia sẻ

- Nhấn **Copy** trong editor để đưa ảnh vào clipboard dưới dạng PNG và DIB.
- Nhấn **Lưu** để xuất PNG hoặc JPEG.
- Sau khi lật/xoay, annotation được cập nhật theo ảnh và vẫn có thể chọn/di chuyển. Text có thể được rasterize thành bitmap sau một số phép biến đổi.
- Menu tray có tùy chọn khởi động cùng Windows.

## Giao diện

Giao diện được cải tổ theo một hệ thống thiết kế riêng, không dùng widget mặc định của Tkinter:

- `ui_theme.py` - token thiết kế (màu, khoảng cách, bo góc, font, glyph) và engine style cho ttk.
- `ui_widgets.py` - bộ component tự vẽ trên Canvas: nút, segmented control, slider, switch, color swatch, status bar... để có bo tròn và trạng thái hover/pressed/disabled.
- `ui_capture.py` - lớp phủ chụp màn hình và toast kết quả.
- `ui_dialogs.py` - dialog thông tin, phím tắt và hướng dẫn.

Editor dùng bố cục ba vùng: header (thao tác chính), rail dọc bên trái (10 công cụ, có tooltip kèm phím tắt), inspector bên phải (Lịch sử / Nét vẽ / Màu sắc / Văn bản / Thu phóng / Biến đổi), canvas ở giữa và thanh trạng thái ở dưới.

**Responsive:** ở cửa sổ hẹp (dưới 1180px) bảng thuộc tính chuyển thành drawer nổi bên phải thay vì bị ẩn, nên mọi điều khiển vẫn truy cập được ở mọi kích thước cửa sổ (tối thiểu 760×520). Đóng drawer bằng nút ×, phím `Esc`, hoặc click vào canvas; mở lại bằng nút bánh răng trên header.

## Đóng gói EXE

Lệnh build one-file/windowed bằng PyInstaller:

```powershell
py -m pip install pyinstaller
py -m PyInstaller --noconfirm --clean --onefile --windowed `
  --name ScreenShotTool `
  --icon icon_ScreenShotTool.ico `
  --add-data "icon_ScreenShotTool.ico;." `
  --collect-submodules pystray --collect-submodules PIL `
  --hidden-import win32clipboard --hidden-import win32gui `
  --hidden-import win32con --hidden-import win32api `
  --hidden-import pystray._win32 --hidden-import keyboard `
  --hidden-import cv2 --hidden-import numpy `
  --exclude-module matplotlib --exclude-module pytest `
  ScreenShotTool.pyw
```

File tạo ra nằm trong `dist\ScreenShotTool.exe` (~72 MB). Binary này **không** được commit vào git; để phát hành, tạo một GitHub Release và đính kèm file đó làm asset:

```powershell
gh release create v1.0.0 dist\ScreenShotTool.exe --title "v1.0.0" --notes "..."
```

## Kiểm thử

```powershell
python -m unittest discover -s tests -v
```

Bộ test gồm 169 test:

- `tests/test_transform.py` (12) - test gốc, không chỉnh sửa, kiểm tra logic biến đổi.
- `tests/test_ui_parity.py` (86) - kiểm tra hệ thống thiết kế: token, helper màu, component, hành vi widget.
- `tests/test_ui_smoke.py` (71) - kiểm tra tích hợp trên ứng dụng thật: contract thuộc tính/phương thức, đường dẫn sự kiện, wiring dialog và chuỗi capture → toast → editor.

Ngoài ra `tests/visual_check.py` là script (không phải unittest) chụp ảnh giao diện ở nhiều kích thước cửa sổ để kiểm tra bằng mắt.

Báo cáo kiểm định độc lập: [`REDESIGN_VERIFICATION.md`](REDESIGN_VERIFICATION.md).

## Phụ thuộc và giới hạn

- OpenCV/NumPy cung cấp khả năng tự nhận diện các vùng UI; nếu thiếu, chụp kéo vùng vẫn hoạt động.
- Cần kiểm thử thủ công thêm trên nhiều màn hình, DPI khác nhau, clipboard bị khóa, UAC và ứng dụng DRM.
- EXE chưa được ký số, vì vậy Windows SmartScreen có thể cảnh báo.
- Khi biến đổi riêng lẻ, text annotation có thể trở thành bitmap và không còn sửa nội dung như text vector.
