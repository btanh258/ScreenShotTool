# Đóng góp cho ScreenShotTool

Cảm ơn bạn đã quan tâm. Dự án nhỏ, quy trình giữ đơn giản.

## Báo lỗi

Mở issue và cho biết:

- Phiên bản (xem menu khay → **Giới thiệu**, hoặc tên file Release)
- Windows phiên bản nào (10/11), độ phân giải và tỉ lệ DPI
- Các bước tái hiện, càng ngắn càng tốt
- File log: `%APPDATA%\ScreenShotTool\ScreenShotTool.log`

Nếu lỗi liên quan hình ảnh (chú thích lệch, cắt sai vùng), đính kèm ảnh chụp màn hình càng tốt.

## Gửi thay đổi

1. Fork, tạo nhánh từ `main`.
2. Chạy kiểm tra trước khi gửi:

   ```powershell
   python -m pip install -r requirements.txt ruff
   python -m ruff check .
   python -m unittest discover -s tests -v
   ```

3. Mở pull request vào `main`. Mô tả **vì sao** thay đổi cần thiết, không chỉ **cái gì** đã đổi.

CI chạy ruff và toàn bộ test trên `windows-latest`. PR chỉ được merge khi CI xanh.

## Quy ước mã nguồn

- **Logic vẽ, transform, render không được thay đổi** khi chỉ làm giao diện. Toàn bộ `tests/test_transform.py` là hợp đồng cho phần này và phải giữ nguyên, không sửa test để code chạy qua.
- Thay đổi giao diện thì thêm hoặc sửa test trong `tests/test_ui_smoke.py` / `test_ui_parity.py`.
- Comment viết bằng tiếng Anh, chuỗi hiển thị cho người dùng bằng tiếng Việt.
- Không dùng `except:` trần — bắt đúng exception cụ thể. `ruff check` sẽ báo nếu quên.
- Ghi file cấu hình phải nguyên tử (xem `save_config`): ghi file tạm rồi `os.replace`, không ghi đè trực tiếp.

## Cấu trúc

| File | Nội dung |
|---|---|
| `ScreenShotTool.pyw` | Điểm vào, tray, editor shell (`ImageEditor`), cấu hình, clipboard |
| `ui_capture.py` | Luồng chụp màn hình, chọn vùng, snapping cửa sổ |
| `ui_dialogs.py` | Dialog thông tin, phím tắt, cài đặt |
| `ui_theme.py` | Token thiết kế (màu, khoảng cách, font) |
| `ui_widgets.py` | Widget vẽ bằng Canvas (Tk gốc không bo góc được) |
| `ui_updates.py` | Kiểm tra bản mới qua GitHub Releases API |
| `hotkey_settings.py` | Dialog cấu hình phím tắt |

## Giấy phép

Khi đóng góp, bạn đồng ý phần mã của mình được phát hành theo [MIT License](LICENSE).
