# Báo cáo rà soát ScreenShotTool

## Phạm vi

Đã đọc toàn bộ `ScreenShotTool.pyw` (1.261 dòng). Thư mục dự án có thêm `icon_ScreenShotTool.ico`; không thấy test, tài liệu, cấu hình build hay dependency manifest để đối chiếu.

## Tính năng hiện có

- Chụp vùng màn hình qua `Alt+X`, menu khay hệ thống; overlay tối, kính lúp và đường căn chỉnh.
- Tự nhận vùng cửa sổ/UI khi rê chuột (Win32/DWM và OpenCV); click vùng được nhận diện để chụp nhanh, hoặc kéo chọn thủ công.
- Chép ảnh PNG và DIB vào clipboard; hiển thị toast, từ đó mở trình chỉnh sửa.
- Editor có zoom, cuộn, undo/redo tối đa 11 trạng thái, chọn/di chuyển/xóa annotation.
- Annotation: bút, hình chữ nhật, mũi tên, chữ có nền, highlight, blur; cắt và xóa vùng ảnh.
- Lưu PNG/JPEG, chọn màu/độ dày, màu ngẫu nhiên; lưu màu và độ dày trong JSON.
- Tùy chọn khởi động cùng Windows, thoát từ tray.

## Lỗi/rủi ro logic đáng chú ý

1. **Toast có thể lỗi ngay sau khi dựng**: `show_toast()` bind các widget hợp lệ, sau đó dùng `inner` ở dòng 1187 nhưng biến này chưa được khai báo trong hàm. Kết quả là `NameError` sau khi chụp, dù toast đã được tạo; đoạn bind và hẹn giờ thứ hai cũng trùng với logic phía trên (dòng 1158–1178). Đây là lỗi ưu tiên cao nhất.
2. **Smart selection lệch tọa độ ở màn hình phụ**: vùng cửa sổ lấy bằng tọa độ desktop (`GetWindowRect`/DWM), còn ảnh chụp `sct.monitors[0]` và event canvas dùng hệ tọa độ monitor ảo cục bộ. Chưa trừ `monitor.left/top` khi tạo window rect, nên nhận diện cửa sổ có thể lệch trên thiết lập nhiều màn hình hoặc gốc desktop âm (dòng 821–848, 879–885).
3. **OpenCV là phụ thuộc bắt buộc trên đường chụp**: `import cv2` và `numpy` nằm trong `_prepare_smart_rects()` và không được bắt lỗi; thiếu một trong hai sẽ làm `start_snipping()` dừng trước khi overlay mở (dòng 854–856). Nếu smart snap không thiết yếu, nên fallback sang chụp thủ công.
4. **Vùng blur/highlight có thể tạo ảnh kích thước 0**: highlight chỉ kiểm tra `len(coords) < 4`; di chuyển rất ít hoặc kéo dọc/ngang có thể khiến `bw` hoặc `bh` thành 0 sau ép `int`, làm `Image.new` lỗi (dòng 569–576). Blur có ngưỡng kích thước trước xử lý nên ít rủi ro hơn.
5. **Dữ liệu config phụ thuộc working directory**: `CONFIG_FILE` là đường dẫn tương đối; chạy shortcut/startup từ thư mục khác sẽ đọc/ghi config ở thư mục hiện hành không dự kiến (dòng 35, 61–71).
6. **Không có thao tác ảnh gốc trong Select**: lựa chọn chỉ tìm tag `shape_*`; ảnh nền không có tag chọn được. Cần phân biệt “ảnh nền” và annotation khi bổ sung transform.
7. **Một số lỗi bị che**: nhiều `except: pass` (clipboard/config/đăng ký startup/Win32) khiến hỏng chức năng không có thông báo chẩn đoán.

## Đề xuất flip/rotate

### Phạm vi và ngữ nghĩa

Nên có hai nhóm lệnh rõ ràng:

- **Ảnh**: áp dụng lên toàn bộ nội dung đã render (ảnh gốc + mọi annotation), tạo một canvas mới. Flip ngang/dọc và quay 90° trái/phải là các phép biến đổi không mất chất lượng ngoài quá trình raster hiện tại. Sau quay 90°, hoán đổi `orig_w` và `orig_h`.
- **Object được chọn**: chỉ biến đổi annotation được chọn quanh tâm bounding box của nó; không biến đổi ảnh nền. Bắt đầu với flip ngang/dọc và quay 90°; tránh hỗ trợ góc tùy ý ở phiên bản đầu vì text, blur/highlight và hitbox cần xử lý góc tổng quát.

### Kiến trúc ít xung đột

- Tách helper thuần cho ảnh: `transform_document(operation)` gọi `render_final_image()`, dùng Pillow `Image.Transpose.FLIP_LEFT_RIGHT`, `FLIP_TOP_BOTTOM`, `ROTATE_90`, `ROTATE_270`, gán lại `pil_image`, cập nhật kích thước, xóa shapes vì chúng đã được hợp nhất vào ảnh, rồi `redraw_all()` và `save_state()` đúng một lần.
- Tách helper cho object: `transform_selected(operation)` tìm shape qua `selected_tag`, biến đổi các tọa độ quanh tâm bounds; với các loại blur/highlight cần biến đổi `orig_pil_img` và cập nhật `min_x/min_y` đồng bộ. Sau đó redraw, vẽ lại selection và ghi history một lần.
- Pen/rect/arrow là annotation dựa trên tọa độ; arrow tự đổi hướng theo điểm đầu/cuối. Text được rasterize thành bitmap ngay khi biến đổi riêng lẻ để phản chiếu/quay đúng trực quan; sau đó text không còn chỉnh sửa như vector.
- Với blur/highlight, transform bitmap vùng chọn và đặt lại góc trên-trái sau biến đổi. Nên chuẩn hóa bounds, kiểm tra kích thước dương, và đảm bảo vùng ảnh nằm trong canvas.
- Các thao tác chỉ sửa state model, không dùng `canvas.scale()` làm nguồn dữ liệu; canvas được dựng lại từ model. Đây là cách giữ render cuối, chọn, undo/redo và lưu file nhất quán.
- Bổ sung nút/toolbar riêng cho ảnh và object. Nút object disabled nếu không có annotation đang chọn. Tên lệnh nên tường minh, ví dụ “Ảnh: Lật ngang” và “Đối tượng: Xoay 90°”.

### Các quyết định cần xác nhận trước triển khai

- Khi transform ảnh, có chấp nhận hợp nhất annotation vào ảnh và không còn chọn riêng được từng object không? Nếu không, phải biến đổi ảnh nền và toàn bộ annotation cùng nhau trong model.
- Text object có cần flip/rotate thật sự hay chỉ di chuyển/biến đổi các loại hình học?
- Có cần góc xoay tùy ý hay chỉ 90°?

## Kiểm thử đề xuất

- Transform ảnh trên ảnh không vuông: kích thước sau 90° đổi chính xác; nội dung và alpha giữ nguyên; undo/redo khôi phục đúng.
- Transform object ở các góc phần tư: tọa độ, selection bounds, vị trí blur/highlight và render cuối khớp nhau.
- Transform object không được làm đổi ảnh nền; transform toàn ảnh tạo một trạng thái undo duy nhất.
- Toast sau chụp hoạt động khi click và tự đóng; thiếu OpenCV vẫn mở được chế độ chụp tay.
- Chụp/nhận diện ở monitor có tọa độ âm hoặc `left/top` khác 0.

## Kết luận

Chưa sửa code chính theo yêu cầu tránh xung đột. Ưu tiên sửa lỗi `inner` trong toast và xử lý tọa độ đa màn hình/thiếu OpenCV trước khi triển khai thao tác transform. Thiết kế transform nên dựa trên model PIL + history, không dựa vào biến đổi trực tiếp canvas.

> Lưu ý: tài liệu này là đề xuất, chưa phải bản vá mã nguồn.
