# CLB Hỗ trợ Học tập Bách khoa — Ôn tập Giải tích

Ứng dụng tiếng Việt, dùng **Python 3.10+**, SQLite và HTML/CSS/JavaScript. Không cần cài thư viện ngoài. Thư mục C++ hiện có được giữ nguyên.

## Chạy trên Windows

Mở PowerShell tại thư mục dự án:

```powershell
cd quiz-web
python server.py
```

- Trang làm bài: http://127.0.0.1:8000
- Trang quản trị: http://127.0.0.1:8000/admin
- Mật khẩu quản trị được tạo ngẫu nhiên và in trong terminal mỗi lần chạy.
- Dừng máy chủ bằng `Ctrl+C`.

Muốn đặt mật khẩu cố định, khai báo trước khi chạy:

```powershell
$env:QUIZ_ADMIN_PASSWORD = 'Thay-bang-mat-khau-rieng-cua-ban'
python server.py
```

Đây là web chạy bằng Python; không chạy bằng nút Build/Run của dự án C++ trong Code::Blocks.

## Cách sử dụng

1. Đăng nhập `/admin`, thêm hoặc sửa nội dung, nhập đủ 4 lựa chọn và đánh dấu một đáp án đúng. Có sẵn 12 câu giải tích cơ bản: giới hạn, đạo hàm, cực trị, nguyên hàm, tích phân xác định/suy rộng và chuỗi hình học.
2. Người làm bài mở trang chính, nhập họ tên, đọc quy định và bắt đầu.
3. Chỉ chọn một trong A/B/C/D. Đáp án được lưu vào backend ngay khi chọn, có thể đổi trước khi nộp hoặc khóa.
4. Rời tab, chuyển cửa sổ, thu nhỏ trình duyệt hoặc tải lại trang đang làm bài được tính là rời phòng thi. Các tín hiệu `blur`, `visibilitychange`, `pagehide` trong cùng một lần rời trang chỉ tạo một cảnh cáo.
5. Lần 1 và 2 hiện hộp cảnh cáo khi quay lại. Lần 3 khóa trả lời; backend cũng từ chối yêu cầu thay đổi đáp án và nộp bài.
6. Bài đã nộp hoặc bị khóa **ẩn điểm mặc định**, hiển thị thông báo chờ quản trị viên. Tải lại trang không gỡ khóa hoặc tự cho phép xem điểm.
7. Quản trị viên có thể xem tối đa 100 lượt gần nhất và chọn **Cấp lượt mới** để xóa bài cũ, cho phép người đó bắt đầu lại. Thao tác này có hộp xác nhận.
8. Để công bố điểm, vào `/admin` → **Lượt làm bài gần đây** → **Làm mới** → **Cho phép xem điểm** ở đúng người cần cấp. Quản trị viên xem được số câu đúng của bài đã kết thúc; chỉ những bài đã nộp hoặc bị khóa mới có nút công bố. Người làm bài thấy điểm trong khoảng 5 giây khi trang đang mở và có kết nối, hoặc ngay khi tải lại trang.

Quyền xem điểm được lưu trong SQLite và giữ nguyên sau khi khởi động lại server. Khi nâng cấp từ bản cũ, điểm của các lượt đã lưu cũng được đặt về trạng thái chưa công bố; điểm đã được người dùng xem trước khi nâng cấp không thể thu hồi. **Cấp lượt mới** tạo một bài mới với điểm tiếp tục được ẩn mặc định.

## Giao diện câu lạc bộ và bộ đề Giải tích

- Giao diện dùng màu cam, đỏ đô, xanh bảng và nền kem theo poster bạn cung cấp. Logo được dùng ở đầu trang, bảng giới thiệu và biểu tượng tab trình duyệt.
- File logo: `static/club-logo.png`. Đây là bản tách bằng công cụ ImageGen tích hợp từ biểu tượng trên poster, có thể khác nhẹ bản gốc. Nếu có file logo chính thức, thay file PNG này để dùng đúng bản gốc.
- Yêu cầu xử lý ảnh: “Tách riêng biểu tượng cam và đỏ đô ở giữa bảng; giữ hình dáng, vòng mắt trắng, viền trắng và màu sắc; bỏ nền, chữ, nhân vật cú và các logo khác; xuất PNG nền trong suốt.”
- Kiểu giao diện riêng: `static/club.css`. Câu hỏi mẫu: `CALCULUS_SAMPLES` trong `server.py`.
- Khi chạy bản cập nhật lần đầu, ứng dụng thay các câu mẫu tin học còn nguyên bằng 12 câu giải tích. Câu hỏi do bạn tự thêm hoặc đã sửa được giữ lại; các lần khởi động sau không tự thêm lại bộ mẫu.
- Các bài đã bắt đầu vẫn giữ bộ câu hỏi cũ. Để làm bộ đề Giải tích, vào `/admin` → **Lượt làm bài gần đây** → **Cấp lượt mới**, rồi tải lại trang làm bài. Thao tác này xóa bài cũ của người được chọn.
- Công thức dùng ký tự Unicode, có thể nhập trực tiếp trong trang quản trị; chưa hỗ trợ cú pháp LaTeX.

## Lưu trữ và bảo vệ trạng thái

- Dữ liệu nằm ở `data/quiz.sqlite3`, tự tạo khi khởi động. Sao lưu thư mục `data` khi đã dừng máy chủ.
- Mỗi lượt lưu một bản chụp bộ câu hỏi. Sửa/xóa câu hỏi chỉ ảnh hưởng lượt bắt đầu sau đó.
- API dành cho người làm bài không gửi đáp án đúng và không gửi trường `score` trước khi quản trị viên cấp quyền xem điểm. Backend chấm điểm và kiểm tra quyền ở mọi phản hồi bài làm.
- Cookie HttpOnly xác định lượt làm bài và phiên quản trị; trang quản trị yêu cầu đăng nhập. Phiên quản trị hết hạn sau 8 giờ.
- Backend xử lý cập nhật theo giao dịch SQLite, kiểm tra trạng thái trước khi ghi đáp án. Mã cảnh cáo duy nhất tránh đếm trùng khi gửi lại.
- Cảnh cáo được gửi bằng `sendBeacon` và yêu cầu xác nhận; hàng đợi được lưu ở trình duyệt để thử lại sau khi tải lại/mất mạng. Trong lúc chưa đồng bộ cảnh cáo, trả lời bị tạm khóa.
- Chỉ nên mở một tab làm bài cho mỗi trình duyệt. Trang tự cập nhật trạng thái với máy chủ mỗi 5 giây khi đang hiển thị.

## Giới hạn cần hiểu

Đây là cơ chế nhắc nhở và khóa bài dựa trên tín hiệu do trình duyệt cung cấp, không phải hệ thống giám sát thi tuyệt đối. Website không biết người dùng mở website nào. Chuyển sang ứng dụng khác hoặc mất tiêu điểm cửa sổ cũng có thể bị cảnh cáo. Việc đóng cưỡng bức trình duyệt không đảm bảo gửi được sự kiện rời trang.

Họ tên không phải tài khoản đã xác thực. Xóa cookie, dùng trình duyệt khác/chế độ riêng tư có thể tạo lượt mới. Người dùng có kỹ thuật có thể vô hiệu hóa mã phát hiện ở phía trình duyệt. Muốn dùng cho kỳ thi thật cần bổ sung tài khoản thí sinh và lượt thi do máy chủ cấp; việc phát hiện rời trang vẫn phụ thuộc trình duyệt.

## Cấu hình tùy chọn

| Biến môi trường | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `QUIZ_ADMIN_PASSWORD` | Ngẫu nhiên mỗi lần chạy | Mật khẩu quản trị |
| `PORT` | `8000` | Cổng HTTP |
| `HOST` | `127.0.0.1` | Địa chỉ lắng nghe |
| `QUIZ_DB` | `data/quiz.sqlite3` | Vị trí cơ sở dữ liệu |
| `COOKIE_SECURE` | Tắt | Đặt `1` khi chạy qua HTTPS |

Để truy cập từ máy khác cùng mạng LAN, đặt `$env:HOST = '0.0.0.0'` trước khi chạy và truy cập bằng IP LAN của máy chủ. Mở cổng tường lửa nếu cần. Bản hiện tại dùng máy chủ HTTP phát triển của Python; khi triển khai Internet cần HTTPS và máy chủ ứng dụng phù hợp.

## Kiểm tra

```powershell
python -m unittest discover -s tests -v
node --test tests/test_frontend.cjs
```

Các bài kiểm tra dùng cơ sở dữ liệu tạm riêng, không thay đổi câu hỏi hoặc bài làm thật.
Node.js chỉ cần cho kiểm thử logic frontend; chạy web bình thường chỉ cần Python. Kiểm thử frontend mô phỏng sự kiện và DOM, không thay thế kiểm tra giao diện trên trình duyệt thật.
