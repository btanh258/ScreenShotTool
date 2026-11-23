# Changelog

Mọi thay đổi đáng chú ý của ScreenShotTool. Định dạng theo [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/),
phiên bản theo [Semantic Versioning](https://semver.org/lang/vi/).

## [Chưa phát hành]

_(chưa có thay đổi)_

## [1.4.3] — 2026-11-24

### Thay đổi

- Hộp thoại Giới thiệu thêm dòng **"GitHub: github.com/btanh258/ScreenShotTool"** bấm được ngay dưới dòng mô tả — bấm mở trang repo bằng trình duyệt.

### Kiểm thử

- Thêm test: hộp thoại Giới thiệu có link GitHub (con trỏ tay), bấm vào mở đúng URL của repo.

## [1.4.2] — 2026-11-24

### Sửa lỗi

- **Lỗi DLL ngay sau khi cập nhật (báo lại sau 1.4.1, giống YouTube Downloader).** Nguyên nhân gốc: bản 1 file exe tự giải nén `python311.dll` ra `%TEMP%\_MEI*` mỗi lần mở app; script cập nhật mở exe mới lên ngay sau khi thay file, đúng lúc Defender đang quét DLL vừa giải nén nên bootloader không tải được DLL. Đợi vài giây không sửa được vì Defender quét DLL lúc giải nén, tức là SAU khi mở app. Sửa triệt để: đổi sang dạng thư mục app (onedir) — `python311.dll` + các DLL nằm cạnh exe trong thư mục app, không còn bước giải nén ra `%TEMP%` nên lỗi này không thể xảy ra; người dùng tải file zip về, giải nén, chạy exe trong thư mục `ScreenShotTool`.
- **Tự cập nhật đổi theo dạng thư mục app.** Bản onedir tải file zip về, giải nén trong lúc bản cũ vẫn chạy (Defender có thời gian quét DLL trước khi exe mới được mở), rồi script phụ đổi cả thư mục app (thư mục cũ đổi tên `.old`, bản mới mở lên được sẽ tự xóa). File cấu hình không bị ảnh hưởng vì đã nằm ở `%APPDATA%`.
- **Cầu nối cho bản 1 file cũ.** Bản 1.4.1 chỉ biết tải file exe, mà release 1.4.2 chỉ có file zip thì nó không cập nhật được — nên release 1.4.2 kèm cả file zip onedir và file exe 1 file (cùng code 1.4.2): bản 1.4.1 bấm cập nhật tải exe cầu nối về trước, rồi bấm cập nhật thêm 1 lần nữa thì bản cầu nối hỏi chuyển sang dạng thư mục app. Từ đó về sau cập nhật bình thường bằng file zip.

### Kiểm thử

- Thêm test cho: nhận diện dạng build 1 file/onedir, chọn đúng asset (exe hay zip) theo dạng build, giải nén zip + đổi thư mục app (cả trường hợp cài mới vào `%LOCALAPPDATA%` và thay tại chỗ), từ chối zip hỏng, dọn thư mục `.old` sau khi đổi, và `_install_update(force_zip=True)` tải đúng file zip.

## [1.4.1] — 2026-11-24

### Thay đổi

- **Tone nâu theo màu icon thay cho tone xanh.** Accent tối `#E09A5F` (nền icon) / sáng `#8A5A2B` (nâu đậm trong icon), chữ trên nút accent tối đổi sang nâu đậm `#241708` để vẫn đạt tương phản 7.5:1; khung chọn/crop/marquee trên canvas và icon khay dự phòng cũng đổi theo. Bảng màu vẽ của bút không đổi.

### Sửa lỗi

- **Bấm Ctrl+Z hoàn tác 2 bước (Ctrl+Y làm lại 2 bước).** Undo/redo vừa bind trên toplevel qua `_refresh_editor_hotkeys()` vừa bind_all, mà bindtag chạy toplevel trước rồi mới tới all nên mỗi lần bấm chạy 2 lần. Đã bỏ 2 dòng bind_all thừa.
- **Gán undo/redo/delete bằng phím F hoặc Ctrl+Delete làm editor không mở được nữa.** `_tk_sequence` lower-case toàn bộ keysym nên `<Control-f5>`, `<Control-delete>`, ... raise `TclError` trong constructor mà không được guard. Giờ map đúng keysym (`F1`–`F12`, `Delete`, `Escape`, `Return`, `Tab`, ...) và `_refresh_editor_hotkeys()` bỏ qua phím không bind được kèm cảnh báo trong log thay vì crash.
- **Lỗi sau bước grab treo chế độ chụp tới khi restart app.** Phần sau `mss.grab` (tạo PhotoImage, dò khối UI bằng OpenCV) không được guard nên exception để lại `is_active=True` với root đã withdraw. Giờ toàn bộ đoạn đó nằm trong try/except, lỗi thì dọn trạng thái và báo rõ. `cv2.findContours` cũng đọc được cả OpenCV 3 (trả 3 giá trị) lẫn OpenCV 4 (trả 2).
- **Chụp hẹn giờ (3/5/10 giây) không hủy được.** Timer không được hủy trong `cancel_snip`, hook Esc chỉ cài sau khi grab xong. Giờ Esc được cài ngay khi bắt đầu chờ và `cancel_snip` hủy timer đang chờ.
- **Một giá trị config lỗi làm mất toàn bộ setting.** `int(width)` lỗi thì cả màu/phím/theme rơi về default; màu `"#zzzzzz"` cũng lọt qua kiểm tra `startswith("#")` rồi gây lỗi ở chỗ khác. Giờ mỗi field validate riêng với fallback riêng, màu phải đúng dạng `#RGB` / `#RRGGBB`.
- **Tự cập nhật không kiểm tra file tải về có đủ không.** `download_asset` chỉ kiểm tra size > 0 nên file tải cụt vẫn được swap vào thay exe. Giờ đối chiếu với `Content-Length`, thiếu byte thì hủy và giữ nguyên bản đang chạy.
- **Xóa trắng ô nhập khi sửa chữ cũ không xóa được chữ.** `commit_text` chỉ xóa shape khi tạo mới; giờ xóa trắng thì xóa luôn shape đang sửa (có lưu lịch sử để hoàn tác).
- **Đổi theme giữa lúc đang gõ text làm mất chữ đã gõ.** `_rebuild_for_theme` phá cây widget mà không commit text đang sửa; giờ commit trước khi rebuild.
- **Dialog chấp nhận phím mà bộ đăng ký không hiểu.** `_validate` và `validate_hotkey` chấp nhận `F13`–`F99`, `FABC` và lặng lẽ bỏ token modifier lạ (`CTRL+META+X` thành `CTRL+X`) rồi rơi về Alt+X. Giờ chỉ nhận F1–F12 và từ chối token lạ. Thông báo "phím bị chiếm" cũng hiện đúng tên phím Delete/Esc/Space/Enter thay vì chỉ hiện modifier.

### Kiểm thử

- Thêm test cho: map keysym của `_tk_sequence`, `_validate` từ chối F13/F99 và modifier lạ, `load_config` giữ lại các setting đúng khi một field lỗi, `download_asset` từ chối file tải cụt.

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

[Chưa phát hành]: https://github.com/btanh258/ScreenShotTool/compare/v1.4.3...HEAD
[1.4.3]: https://github.com/btanh258/ScreenShotTool/compare/v1.4.2...v1.4.3
[1.4.2]: https://github.com/btanh258/ScreenShotTool/compare/v1.4.1...v1.4.2
[1.4.1]: https://github.com/btanh258/ScreenShotTool/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/btanh258/ScreenShotTool/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/btanh258/ScreenShotTool/compare/v1.2.1...v1.3.0
[1.2.1]: https://github.com/btanh258/ScreenShotTool/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/btanh258/ScreenShotTool/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/btanh258/ScreenShotTool/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/btanh258/ScreenShotTool/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/btanh258/ScreenShotTool/releases/tag/v1.0.0
