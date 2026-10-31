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
- `Enter`: chụp toàn bộ màn hình đang trỏ tới, không cần kéo chuột.
- `Space`: chụp cửa sổ đang nằm dưới con trỏ.
- Ảnh sau khi chụp được sao chép vào clipboard nếu clipboard khả dụng. Toast kết quả cho phép mở ảnh trong editor hoặc **ghim** ảnh lên màn hình.

#### Chụp có hẹn giờ

Menu khay → **Chụp sau** → chọn *3 giây* / *5 giây* / *10 giây*.

Hữu ích khi cần mở menu, chờ tooltip hiện, hoặc chờ animation chạy xong trước khi ảnh được "đóng băng". Phím tắt `Alt+X` luôn chụp ngay lập tức — hẹn giờ là đường chủ động.

#### Ghim ảnh lên màn hình

Bấm **Ghim** trên toast kết quả (hoặc mở ảnh rồi dùng cùng nút) để giữ ảnh trong một cửa sổ không viền, luôn nổi trên các cửa sổ khác. Dùng để đối chiếu ảnh tham chiếu với nội dung đang làm.

- Kéo chuột để di chuyển.
- Lăn chuột để đổi độ mờ (25%–100%).
- Nháy đúp, `Esc`, hoặc chuột phải để đóng.

#### Ảnh gần đây

Mỗi lần chụp đều được lưu một bản PNG vào `%APPDATA%\ScreenShotTool\history\`. Menu khay → **Ảnh gần đây** liệt kê 8 ảnh mới nhất; chọn một ảnh để mở lại trong editor. Chỉ giữ **20 ảnh gần nhất** — ảnh cũ hơn tự động bị xóa, nên thư mục không phình ra.

Tính năng này cứu bạn khi lỡ tay chụp đè hoặc đóng editor trước khi lưu. Chọn **Xoá lịch sử ảnh** trong cùng menu để dọn sạch.

### Menu khay hệ thống

| Mục | Tác dụng |
|---|---|
| Chụp màn hình (`Alt+X`) | Chụp ngay |
| Chụp sau | Chụp hẹn giờ 3/5/10 giây |
| Khởi động cùng Windows | Bật/tắt tự chạy khi đăng nhập |
| Giao diện | Chọn *Theo Windows* / *Tối* / *Sáng* |
| Mở ảnh… (`Ctrl+O`) | Mở file ảnh có sẵn trong editor |
| Ảnh gần đây | Mở lại ảnh vừa chụp, hoặc xóa lịch sử |
| Kiểm tra cập nhật | Hỏi GitHub xem có bản mới |
| Giới thiệu (v…) | Bảng phím tắt và phiên bản |
| Thoát | Thoát hoàn toàn |

**Nếu phím tắt bị ứng dụng khác chiếm:** ScreenShotTool sẽ **thông báo một lần** qua khay hệ thống và ghi vào log, thay vì im lặng để phím không hoạt động. Bạn vẫn chụp được bằng menu khay, hoặc đổi phím trong **Giới thiệu → Giảm phím tắt**.

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
| `Ctrl+S` | Lưu ảnh PNG / WebP / JPEG / BMP |
| `Ctrl+O` | Mở một file ảnh khác |
| `Ctrl+0` | Thu phóng vừa khung |
| `Delete` | Xóa annotation đang chọn |
| Mũi tên | Di chuyển object hoặc nhóm 1 pixel |
| `Shift` + Mũi tên | Di chuyển object hoặc nhóm 10 pixel |
| `Enter` | Xác nhận crop |
| `Esc` | Bỏ chọn hoặc hủy overlay/chỉnh sửa |

Có thể thay đổi phím tắt trong **Info → Gán phím tắt**. Tổ hợp phím được kiểm tra trùng lặp trước khi lưu.

### Lưu và chia sẻ

- Nhấn **Copy** trong editor để đưa ảnh vào clipboard dưới dạng PNG và DIB.
- Nhấn **Lưu** để xuất **PNG**, **WebP**, **JPEG** hoặc **BMP** — đuôi file bạn chọn quyết định định dạng.
  - **WebP** lưu không mất dữ liệu và giữ trong suốt; ảnh chụp màn hình thường nhỏ hơn PNG khoảng 90%, rất tiện khi gửi qua chat hoặc email.
  - **JPEG** và **BMP** không có kênh trong suốt, nên vùng trong suốt được trộn lên nền trắng thay vì thành màu đen.
- Mở lại ảnh có sẵn bằng **Ctrl+O** hoặc menu khay → **Mở ảnh…**.
- Sau khi lật/xoay, annotation được cập nhật theo ảnh và vẫn có thể chọn/di chuyển. Text có thể được rasterize thành bitmap sau một số phép biến đổi.

Khi mở ảnh, editor tự thu phóng **vừa khung** (không bao giờ phóng to ảnh nhỏ hơn khung). Nút `⤢` hoặc `Ctrl+0` để vừa lại khung bất cứ lúc nào.

## Giao diện

Giao diện được cải tổ theo một hệ thống thiết kế riêng, không dùng widget mặc định của Tkinter:

- `ui_theme.py` - token thiết kế (màu, khoảng cách, bo góc, font, glyph), engine style cho ttk, và hai bảng màu tối/sáng.
- `ui_widgets.py` - bộ component tự vẽ trên Canvas: nút, segmented control, slider, switch, color swatch, status bar... để có bo tròn và trạng thái hover/pressed/disabled.
- `ui_capture.py` - lớp phủ chụp màn hình và toast kết quả.
- `ui_dialogs.py` - dialog thông tin, phím tắt và hướng dẫn.
- `ui_extras.py` - lịch sử ảnh gần đây và cửa sổ ghim ảnh nổi.

Editor dùng bố cục ba vùng: header (thao tác chính), rail dọc bên trái (10 công cụ, có tooltip kèm phím tắt), inspector bên phải (Lịch sử / Nét vẽ / Màu sắc / Văn bản / Thu phóng / Biến đổi), canvas ở giữa và thanh trạng thái ở dưới.

**Responsive:** ở cửa sổ hẹp (dưới 1180px) bảng thuộc tính chuyển thành drawer nổi bên phải thay vì bị ẩn, nên mọi điều khiển vẫn truy cập được ở mọi kích thước cửa sổ (tối thiểu 760×520). Đóng drawer bằng nút ×, phím `Esc`, hoặc click vào canvas; mở lại bằng nút bánh răng trên header.

**Sáng / tối:** mặc định bám theo thiết lập *Chế độ ứng dụng* của Windows. Đổi thủ công ở menu khay → **Giao diện**. Lựa chọn được lưu vào file cấu hình và áp dụng từ lần mở cửa sổ tiếp theo — Tkinter gắn màu vào widget lúc tạo, nên đổi màu cửa sổ đang mở sẽ cần dựng lại toàn bộ. Bảng màu sáng đã được kiểm tra độ tương phản WCAG AA (chữ chính ≥ 4.5:1, chữ phụ ≥ 3:1) bằng test tự động.

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
  --hidden-import ui_editor_io --hidden-import ui_updates --hidden-import ui_extras `
  --exclude-module matplotlib --exclude-module pytest `
  ScreenShotTool.pyw
```

File tạo ra nằm trong `dist\ScreenShotTool.exe` (~72 MB). Binary này **không** được commit vào git.

### Phát hành

Có hai cách, cả hai đều **chạy toàn bộ test trước** rồi mới build (`needs: unit-tests` trong `.github/workflows/release.yml`):

1. **Tự động:** đẩy một tag, CI build và đính kèm exe vào Release.

   ```powershell
   git tag -a v1.1.0 -m "ScreenShotTool v1.1.0"
   git push origin v1.1.0
   ```

2. **Thủ công từ máy:** build rồi tự tạo Release (test không được tự chạy ở đây — phải tự đảm bảo đã chạy `unittest` và `ruff` trước).

   ```powershell
   gh release create v1.1.0 dist\ScreenShotTool.exe --title "v1.1.0" --notes-file notes.md
   ```

## Kiểm thử

```powershell
python -m ruff check .
python -m unittest discover -s tests -v
```

Bộ test gồm **269 test**:

| File | Số test | Nội dung |
|---|---|---|
| `tests/test_transform.py` | 12 | Test gốc, **không chỉnh sửa**, kiểm tra logic biến đổi |
| `tests/test_ui_parity.py` | 86 | Hệ thống thiết kế: token, helper màu, component, hành vi widget |
| `tests/test_ui_smoke.py` | 71 | Tích hợp trên ứng dụng thật: contract, đường dẫn sự kiện, wiring dialog |
| `tests/test_runtime_paths.py` | 39 | Đường lỗi: config hỏng/thiếu, clipboard khoá, registry, thiếu icon, hotkey bị chiếm |
| `tests/test_ui_features.py` | 33 | Undo copy-on-write + ngân sách bộ nhớ, fit-to-window, debounce resize, 4 định dạng xuất, lịch sử ảnh, ghim ảnh, đổi theme + tương phản WCAG |
| `tests/test_updates.py` | 17 | So sánh phiên bản, xử lý lỗi mạng, callback nền |
| `tests/test_multi_monitor.py` | 11 | Toạ độ đa màn hình (gốc âm), snapping cửa sổ, DPI awareness |

Đo độ phủ:

```powershell
python -m coverage run --source=. -m unittest discover -s tests
python -m coverage report --skip-covered --omit="tests/*,_*.py"
```

Ngoài ra `tests/visual_check.py` là script (không phải unittest) chụp ảnh giao diện ở nhiều kích thước cửa sổ để kiểm tra bằng mắt.

Báo cáo kiểm định độc lập: [`docs/REDESIGN_VERIFICATION.md`](docs/REDESIGN_VERIFICATION.md).

## Phụ thuộc và giới hạn

- OpenCV/NumPy cung cấp khả năng tự nhận diện các vùng UI; nếu thiếu, chụp kéo vùng vẫn hoạt động.
- Cần kiểm thử thủ công thêm trên nhiều màn hình, DPI khác nhau, clipboard bị khóa, UAC và ứng dụng DRM.

  Phần **số học** của snapping đa màn hình (trục toạ độ âm khi màn hình phụ nằm bên trái/trên) đã được test trong `tests/test_multi_monitor.py`. Phần **chưa ai kiểm chứng trên phần cứng thật**: hai màn hình ở tỉ lệ DPI khác nhau (ví dụ laptop 150% + màn ngoài 100%). Nếu bạn gặp lỗi lệch vùng chọn ở cấu hình đó, hãy báo kèm thông tin DPI.
- EXE chưa được ký số, vì vậy Windows SmartScreen có thể cảnh báo. Xem mục **Chữ ký số** bên dưới để biết cách xử lý và cách bật ký tự động.
- Khi biến đổi riêng lẻ, text annotation có thể trở thành bitmap và không còn sửa nội dung như text vector.

## Cấu hình và log

| Đường dẫn | Nội dung |
|---|---|
| `%APPDATA%\ScreenShotTool\ScreenShotTool_config.json` | Cấu hình (màu, độ dày, phím tắt, giao diện sáng/tối) |
| `%APPDATA%\ScreenShotTool\ScreenShotTool.log` | Log, tự cắt vòng ở ~1 MB |
| `%APPDATA%\ScreenShotTool\history\` | 20 ảnh chụp gần nhất (tự tạo khi chụp lần đầu) |

File cấu hình đọc được cả khi có BOM UTF-8 (Notepad và PowerShell đều ghi BOM), nên sửa tay bằng Notepad không làm mất cài đặt.

Menu khay → **Ảnh gần đây** → **Xoá lịch sử ảnh** để dọn thư mục `history\` bất cứ lúc nào.

Nếu có file `ScreenShotTool_config.json` **nằm cạnh file exe**, bản portable đó được ưu tiên — tiện mang theo USB. Cấu hình cũ (cạnh exe hoặc trong thư mục làm việc) vẫn được đọc khi nâng cấp, nên không mất cài đặt.

Ghi cấu hình là **nguyên tử**: ghi file tạm rồi đổi tên, nên mất điện giữa lúc ghi không làm hỏng file.

## Giấy phép

[MIT](LICENSE).

## Chữ ký số và SmartScreen

### Nếu bạn tải và chạy

Bản phát hành hiện **chưa được ký số**, nên lần chạy đầu Windows SmartScreen có thể hiện: *"Windows protected your PC"*.

Cách chạy:

1. Bấm **More info**
2. Bấm **Run anyway**

Sau lần chạy đầu, Windows ghi nhớ file đó và không hỏi lại (trừ khi file thay đổi).

Muốn chắc chắn file tải về không bị chỉnh sửa trên đường truyền, mỗi Release có kèm file `SHA256SUMS.txt`:

```powershell
Get-FileHash .\ScreenShotTool.exe -Algorithm SHA256
# so với nội dung SHA256SUMS.txt trong cùng Release
```

### Bật ký số tự động

Workflow phát hành đã có bước ký sẵn. Nó **tự bỏ qua** khi chưa có chứng chỉ, và **tự bật** khi bạn thêm hai secret vào repository:

| Secret | Nội dung |
|---|---|
| `SIGNING_CERT_BASE64` | Nội dung file `.pfx` mã hoá base64 |
| `SIGNING_CERT_PASSWORD` | Mật khẩu của file `.pfx` |

Tạo chuỗi base64:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("chungchi.pfx")) | Set-Clipboard
```

Thêm secret bằng giao diện GitHub (Settings → Secrets and variables → Actions) hoặc:

```powershell
gh secret set SIGNING_CERT_BASE64 --repo btanh258/ScreenShotTool < cert.b64
gh secret set SIGNING_CERT_PASSWORD --repo btanh258/ScreenShotTool
```

Sau đó mọi Release đều được ký và kiểm tra chữ ký hợp lệ trước khi phát hành.

### Về việc mua chứng chỉ

Không có cách nào để bản phát hành miễn phí hết cảnh báo SmartScreen. Danh tiếng SmartScreen được tích luỹ theo **chứng chỉ**, không theo file: một chứng chỉ mới vẫn bị cảnh báo cho tới khi có đủ lượt tải. Chứng chỉ EV được nhiều nơi quảng cáo là bỏ qua giai đoạn đó, nhưng cần xác minh với nhà cung cấp tại thời điểm mua.

Chứng chỉ EV cần **xác minh doanh nghiệp** (giấy phép kinh doanh), nên cá nhân thường không mua được. Chứng chỉ OV dành cho cá nhân có thể mua nhưng đắt hơn giá trị một công cụ nội bộ nhỏ. Đây là lý do dự án chọn cách **công bố rõ là chưa ký** thay vì ký bằng chứng chỉ tự tạo — chứng chỉ tự tạo còn tệ hơn không ký, vì nó làm cảnh báo trông đáng ngại hơn.

Điều thực sự giúp người dùng tin tưởng ở đây là mã nguồn mở và CI công khai: họ đọc được code, thấy test chạy.


