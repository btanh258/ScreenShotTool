# Changelog

Mọi thay đổi đáng chú ý của ScreenShotTool. Định dạng theo [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/),
phiên bản theo [Semantic Versioning](https://semver.org/lang/vi/).

## [Chưa phát hành]

_(chưa có thay đổi)_

## [1.4.0] — 2026-11-01

### Sửa lỗi

- **Toast kết quả cắt mất nút "Ghim".** Thẻ có bề rộng cố định 400 px trong khi các nút
  được xếp theo tổng cộng dồn không đối chiếu với bề rộng đó, nên nút thứ ba lòi ra
  ngoài mép phải. Giờ các nút được dựng và đo trước, thẻ nới rộng theo nhu cầu
  (400 → 430 px khi có Ghim).
- **Bút và dạ quang không vẽ được chấm khi bấm một lần.** Dạ quang bỏ mọi nét dưới hai
  điểm; bút vẽ `create_line` một điểm mà Tk không vẽ gì. Giờ bấm-thả không kéo sẽ để
  lại một chấm tròn, hiện trên canvas, có trong model và trong ảnh xuất ra.
- **Hoàn tác hết cỡ không về được ảnh gốc khi phiên chỉnh sửa dài.** Khi lịch sử đầy,
  tool xoá phần tử đầu tiên — chính là ảnh chụp lúc mở — nên sàn hoàn tác thành một
  trạng thái bất kỳ giữa phiên và các object vẽ trước đó coi như mất. Giờ bản gốc được
  ghim lại, chỉ bỏ bước cũ thứ nhì.
- **Timer không được huỷ khi đóng cửa sổ editor.** Callback hẹn giờ chạy vào cửa sổ đã
  chết, sinh ra lỗi `bgerror` và làm hỏng trạng thái của test chạy sau.

### Thay đổi

- Giới hạn hoàn tác nâng từ **50 lên 200 bước**. Nhờ copy-on-write, bước chỉ đổi
  annotation dùng chung ảnh gốc nên gần như không tốn bộ nhớ (đo trên ảnh 4K: 31 bước
  tốn 31.6 MB thay vì 261 MB).

### Thêm mới

- **Tự cập nhật:** "Kiểm tra cập nhật" giờ tải thẳng file EXE của bản mới rồi thay thế
  bản đang chạy và khởi động lại. File tải về ghi qua `.part` rồi mới đổi tên; một
  script phụ chờ tiến trình thoát (Windows khoá file đang chạy), đổi tên, khởi động
  lại rồi tự xoá. Tải hoặc thay thế thất bại thì bản đang chạy vẫn nguyên.

### Kiểm thử

- Thêm 33 test (tổng **329**): bố cục toast đo từ hình học widget, chấm tròn ở canvas/
  model/ảnh xuất, giữ bản gốc hoàn tác dưới cả giới hạn bước và ngân sách bộ nhớ, chọn
  asset và tính nguyên tử của bước tải, cùng đường dẫn cài đặt ở menu khay.

## [1.3.0] — 2026-11-01

### Thêm mới

- **Chuyển giao diện sáng/tối ngay trong editor** bằng nút ◑ trên header. Cửa sổ đang
  mở được dựng lại với bảng màu mới; ảnh, annotation, lịch sử hoàn tác và mức thu
  phóng giữ nguyên. Mọi cửa sổ editor khác cũng đổi theo, lựa chọn được lưu lại.
- Hộp thoại giới thiệu chỉ hiện khi bấm **Giới thiệu**, không tự bật sau khi chụp.

### Sửa lỗi

- Hộp thoại **Giới thiệu** không hiện khi mở từ menu khay (root ẩn nên cửa sổ
  `transient` bị Tk triệt tiêu, tạo ra ở kích thước 1×1).

### Thay đổi

- Mục **Giao diện** trong menu khay được bỏ — chức năng đã chuyển vào editor.

## [1.2.1] — 2026-11-01

### Sửa lỗi

- Menu khay bị lỗi khi mở (callback sai chữ ký).
- Mục "Giới thiệu" không mở được.
- Báo sai "mất mạng" khi kiểm tra cập nhật gặp lỗi 404 của kho riêng tư.

## [1.2.0] — 2026-11-01

### Thêm mới

- Toast kết quả sau khi chụp, có thumbnail và nút mở editor.
- **Ghim ảnh** nổi trên màn hình: kéo để di chuyển, lăn chuột đổi độ mờ, nháy đúp để đóng.
- **Ảnh gần đây:** 20 ảnh chụp gần nhất, mở lại từ menu khay.
- Phím tắt chụp tuỳ chỉnh, kiểm tra trùng lặp trước khi lưu.

## [1.1.1] — 2026-11-01

### Thay đổi

- Workflow phát hành ký số **tuỳ chọn**: tự bỏ qua khi thiếu chứng chỉ, tự bật khi có
  hai secret `SIGNING_CERT_BASE64` / `SIGNING_CERT_PASSWORD`.
- Tài liệu hoá luồng phát hành theo tag và các `--hidden-import` cần thêm khi build.

## [1.1.0] — 2026-11-01

### Thêm mới

- Bộ widget tự vẽ trên Canvas (bo góc, hover/pressed/disabled) thay cho widget mặc định.
- Bảng màu tối/sáng, dialog thông tin và phím tắt thiết kế lại.
- Inspector dạng drawer khi cửa sổ hẹp dưới 1180 px.
- **Chụp sau** 3/5/10 giây từ menu khay.
- **Kiểm tra cập nhật** qua GitHub Releases API.
- Cảnh báo khi phím tắt toàn cục bị ứng dụng khác chiếm, thay vì im lặng.
- Chuyển cấu hình sang `%APPDATA%` (vẫn đọc cấu hình cũ), ghi nguyên tử.
- Thêm ruff và đo độ phủ vào CI; giấy phép MIT; ảnh chụp giao diện trong `docs/screenshots/`.

## [1.0.0] — 2026-11-01

### Thêm mới

- Bản phát hành đầu tiên: chụp màn hình bằng `Alt+X`, nhận diện cửa sổ/vùng UI, sao
  chép clipboard, editor có annotation, tray icon, khởi động cùng Windows.

[Chưa phát hành]: https://github.com/btanh258/ScreenShotTool/compare/v1.4.0...HEAD
[1.4.0]: https://github.com/btanh258/ScreenShotTool/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/btanh258/ScreenShotTool/compare/v1.2.1...v1.3.0
[1.2.1]: https://github.com/btanh258/ScreenShotTool/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/btanh258/ScreenShotTool/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/btanh258/ScreenShotTool/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/btanh258/ScreenShotTool/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/btanh258/ScreenShotTool/releases/tag/v1.0.0
