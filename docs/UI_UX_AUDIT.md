# ScreenShotTool — UI/UX Audit & Redesign Direction

> **Trạng thái (2026-11-01):** tài liệu lịch sử — bản đánh giá **trước** khi cải tổ.
> Toàn bộ vấn đề ở mục 2 đã được xử lý; hệ thống thiết kế ở mục 3 đã được hiện thực
> (`ui_theme.py`, `ui_widgets.py`). Các câu hỏi ở mục 4 đã có câu trả lời trong sản
> phẩm: UI một ngôn ngữ tiếng Việt, màu nhấn azure `#3B82F6`, tối thiểu 760×520, và
> **đã có chế độ Sáng/Tối chuyển ngay trong editor**. Đừng đọc mục 2 như mô tả hiện
> trạng — xem README.

**Ngày:** 2026-10-31 · **Baseline:** commit `c3c340c` · **Nền tảng:** Python 3.11+/Tkinter + Pillow (Windows desktop)

---

## 1. Kiến trúc hiện tại (đã đọc mã nguồn)

| Thành phần | Vị trí | Vai trò |
|---|---|---|
| `ScreenShotTool.pyw` (1.834 dòng) | `class ImageEditor` (L188–1366) | Cửa sổ chính: toolbar + canvas + toàn bộ logic annotation |
| | `class SnippingTool` (L1367–1760) | Overlay chụp toàn màn hình + magnifier + toast |
| | `main()` (L1780+) | Tray icon, global hotkey `Alt+X`, vòng lặp Tk |
| `hotkey_settings.py` (89 dòng) | `open_hotkey_settings()` | Hộp thoại gán phím tắt |
| `tests/test_transform.py` | 12 test | Test logic biến đổi ảnh (không test UI) |

**Framework UI:** Tkinter/ttk thuần, theme `clam`. Không dùng thư viện component ngoài.

**Các màn hình:** (1) Editor, (2) Overlay chụp, (3) Toast kết quả, (4) Dialog Info, (5) Dialog Phím tắt, (6) Dialog Gán phím tắt, (7) Tray menu.

**Luồng chính:** `Alt+X` → overlay → kéo chọn / click cửa sổ → chụp → clipboard + toast → mở Editor → annotation → Copy/Lưu.

---

## 2. Đánh giá vấn đề hiện có

### 2.1 Bố cục & phân cấp thị giác — nghiêm trọng
- **Toàn bộ chức năng dồn vào một thanh ngang duy nhất** cao 30px: 10 công cụ + undo/redo + độ dày + màu + nền chữ + 3 nút zoom + 4 nút biến đổi + Info/Lưu/Copy. Không có nhóm, không có phân cấp.
- **Không phân biệt được hành động chính và phụ.** `Copy` (xanh lá), `Lưu` (xanh dương), `Info` (xám) nằm cùng hàng, cùng trọng lượng thị giác → người dùng không biết đâu là hành động chính.
- **Không có vùng trạng thái.** Không hiển thị kích thước ảnh, mức zoom, toạ độ con trỏ, kích thước vùng chọn → người dùng phải đoán.
- **Canvas không được "đóng khung".** Ảnh nằm trôi trên nền `#cccccc`, không có bóng đổ/viền → không rõ đâu là ảnh, đâu là không gian làm việc.
- **Toolbar tràn/clip ở màn hình hẹp.** Tổng bề rộng các control vượt 1.400px; ở 1280px hoặc khi scale 125% các nút bên phải bị đẩy ra ngoài.

### 2.2 Màu sắc — không có hệ thống
- Hard-code rải rác: `#f3f3f3`, `#005a9e`, `#28a745`, `#cccccc`, `#f7f7f7`, `#1f1f1f`, `#555555`, `#b42318`.
- Không có token màu, không có trạng thái hover/pressed/disabled/focus nhất quán.
- Nền sáng `#f3f3f3` + canvas `#cccccc` tranh chấp với ảnh chụp — ảnh không phải tâm điểm.
- Màu nhấn không thống nhất: `Copy` xanh lá, `Lưu` xanh dương, selection `#005a9e`, marquee `#0078d4`, auto-select `yellow`, magnifier `#00ff00` → 6 sắc nhấn khác nhau.

### 2.3 Typography
- Chỉ một cỡ chữ (Segoe UI 9) cho mọi thứ; tiêu đề dialog dùng 14 bold nhưng body vẫn 9 → tương phản yếu.
- Không có thang chữ (display/title/heading/body/caption).
- Nhãn công cụ là chữ thuần ("Chọn", "Cắt"...) — không có icon, không có tooltip, không gợi ý phím tắt.

### 2.4 Khoảng cách & hình dạng
- Padding tuỳ tiện (`padx=2`, `pady=1`, `padx=5`), không theo thang.
- Bo góc 0 (ttk mặc định) — không có `radius` nhất quán.
- Mật độ quá dày ở toolbar, quá loãng ở canvas.

### 2.5 Trạng thái tương tác
- `Undo`/`Redo` chỉ đổi màu chữ xám khi disabled — gần như không nhận ra.
- Không có hover state rõ ràng trên công cụ; công cụ đang chọn chỉ khác bằng nền xám nhạt.
- Không có focus ring → không dùng được bằng bàn phím.
- Không có phím tắt để chuyển công cụ (chỉ dùng chuột).

### 2.6 Responsive
- `state('zoomed')` luôn toàn màn hình, không có layout thay thế cho màn hình nhỏ.
- Không có cơ chế thu gọn toolbar/sidebar.

### 2.7 Trải nghiệm người dùng
- Hộp thoại Info/Phím tắt là form mặc định Tk, không có validation trực tiếp — chỉ báo lỗi sau khi bấm Lưu.
- Không có hướng dẫn trực quan khi overlay mở (chỉ có con trỏ cross).
- Toast kết quả đơn giản, thiếu thumbnail, thiếu hành động rõ ràng.

---

## 3. Định hướng thiết kế mới

### 3.1 Nguyên tắc
1. **Ảnh là nhân vật chính** — shell tối (deep slate), ảnh sáng nổi bật.
2. **Một màu nhấn duy nhất** — azure `#3B82F6` mang toàn bộ tính tương tác; semantic chỉ dùng cho đúng nghĩa (success/danger/warning).
3. **Ba tầng chữ** — `text_primary` / `text_secondary` / `text_muted` tạo phân cấp không cần kẻ đường.
4. **Thang 4/8/12/16/24** cho spacing, `6/10/14/20` cho bo góc.
5. **Công cụ ở rail dọc, thuộc tính ở inspector phải, hành động ở header** — mỗi vùng một nhiệm vụ.

### 3.2 Hệ thống thiết kế (`ui_theme.py`)
- Token: `COLORS`, `SPACE`, `RADIUS`, `METRICS`, `FONTS`, `GLYPH`.
- Style engine ttk idempotent + helper `round_rect`, `mix`, `lighten`, `darken`, `readable_on`, `apply_dark_titlebar`, `center_window`.
- Widget tự vẽ (`ui_widgets.py`): `RailButton`, `IconButton`, `PillButton`, `SegmentedControl`, `ColorSwatch`, `NumberStepper`, `Slider`, `ToggleSwitch`, `InspectorSection`, `StatusBar`, `Tooltip`, `Divider` — tất cả giữ được "classic Tk dialect" (`.config(state=...)`, `.cget("text")`, `.invoke()`) để mã ứng dụng cũ không vỡ.

### 3.3 Bố cục Editor mới
```
┌──────────────────────────────────────────────────────────────┐
│ HEADER  [icon] ScreenShotTool · Ảnh đã chụp   [Info][Lưu][Copy]│
├──────┬────────────────────────────────────────┬──────────────┤
│ RAIL │                                        │  INSPECTOR   │
│ Chọn │              CANVAS                    │  Lịch sử     │
│ Cắt  │        (ảnh trên nền tối,              │  Nét vẽ      │
│ Xóa  │         có viền + bóng đổ)             │  Màu sắc     │
│ Bút  │                                        │  Văn bản     │
│ ...  │                                        │  Thu phóng   │
│      │                                        │  Biến đổi    │
├──────┴────────────────────────────────────────┴──────────────┤
│ STATUS  Gợi ý công cụ            1920×1080 · 100% · ⌖ x, y   │
└──────────────────────────────────────────────────────────────┘
```
- Responsive: < 1180px → inspector thu thành drawer; < 900px → rail chỉ còn icon.

### 3.4 Overlay chụp mới
- Scrim tối, vùng chọn sáng rõ với viền accent + 8 tay nắm góc.
- Badge kích thước `W×H` sống động cạnh vùng chọn.
- Hint pill giữa-dưới khi chưa thao tác.
- Magnifier dạng card bo góc, hiển thị toạ độ + màu pixel.

### 3.5 Dialog mới
- Card tối, header có icon + tiêu đề + phụ đề.
- Nhóm theo section, phím tắt dạng "kbd chip".
- Validation trực tiếp: ✔ xanh / ✖ đỏ ngay dưới trường; nút Lưu disabled đến khi hợp lệ.

---

## 4. Thông tin cần bổ sung

Các điểm sau **không thể suy ra từ mã nguồn**, cần xác nhận của chủ dự án:

- `(待补充：Ngôn ngữ chính thức của sản phẩm)` — hiện UI là tiếng Việt, nhưng tên app và README có yếu tố tiếng Anh. Có cần đa ngôn ngữ (VI/EN) không?
- `(待补充：Bảng màu thương hiệu)` — dự án chưa có brand guideline. Bản cải tổ dùng azure `#3B82F6` làm màu nhấn; nếu có màu thương hiệu riêng, chỉ cần đổi token `COLORS.accent` trong `ui_theme.py`.
- `(待补充：Mức hỗ trợ màn hình tối thiểu)` — hiện giả định 1280×720 là tối thiểu. Có cần hỗ trợ 1024×768 hoặc tablet/DPI thấp không?
- `(待补充：Chế độ Sáng/Tối)` — bản này chọn shell tối cố định. Có cần cho người dùng chuyển sang theme sáng không? (Hạ tầng token đã sẵn sàng, chỉ cần thêm bộ token thứ hai.)
- `(待补充：Ký số & phát hành)` — README nêu EXE chưa ký số. Việc ký số nằm ngoài phạm vi bản cải tổ UI.

---

## 5. Phạm vi & ràng buộc

**Trong phạm vi:** toàn bộ lớp trình bày (bố cục, màu, chữ, spacing, trạng thái, icon, tooltip, dialog, overlay, toast, responsive).

**Ngoài phạm vi (giữ nguyên tuyệt đối):** logic annotation, thuật toán biến đổi, DWM window detection, OpenCV contour detection, clipboard PNG/DIB, hotkey listener, tray, config I/O.

**Ràng buộc:** không thêm dependency mới; giữ tương thích Python 3.11+; giữ toàn bộ API công khai mà `tests/` và `hotkey_settings.py` phụ thuộc.
