# Tạp chí khoa học trong nước (tiếng Việt) — hướng dẫn viết

Áp dụng cho các tạp chí như Tạp chí Khoa học Đại học Huế: Kinh tế và Phát triển, Tạp chí Kinh tế & Phát triển,
Tạp chí Khoa học Thương mại, Tạp chí Nghiên cứu Kinh tế… Điều chỉnh theo thể lệ cụ thể của từng tạp chí.

## Ngôn ngữ và độ dài
* Tiếng Việt học thuật, có dấu đầy đủ; thuật ngữ chuyên môn ghi kèm tiếng Anh trong ngoặc ở lần đầu.
* Độ dài thường 5.000–8.000 từ (10–15 trang A4), cỡ chữ 12, giãn dòng 1,2.
* Tóm tắt 150–250 từ: mục tiêu, dữ liệu & phương pháp, kết quả chính (có số liệu), hàm ý. Không trích dẫn.
* 3–5 từ khóa, phân cách bằng dấu chấm phẩy.

## Cấu trúc
1. Giới thiệu — bối cảnh, khoảng trống nghiên cứu, mục tiêu/câu hỏi nghiên cứu, đóng góp, bố cục bài.
2. Tổng quan tài liệu — tổng hợp theo chủ đề, chỉ ra khoảng trống; có thể nêu giả thuyết.
3. Dữ liệu và phương pháp nghiên cứu — nguồn dữ liệu, giai đoạn, biến, tiền xử lý, mô hình (phương trình đánh số),
   chỉ số đánh giá, kiểm định.
4. Kết quả và thảo luận — thống kê mô tả, kết quả chính, kiểm tra độ vững, thảo luận so với nghiên cứu trước,
   hàm ý chính sách/quản trị.
5. Kết luận — tóm tắt, đóng góp, hạn chế, hướng nghiên cứu tiếp theo.
6. Lời cảm ơn và tuyên bố — chỉ dùng thông tin tác giả cung cấp; không tự tạo nguồn tài trợ.

## Trích dẫn
* natbib tác giả–năm: `\citet{key}` ("Nguyễn và cộng sự (2020) cho thấy…"), `\citep{key}` trong ngoặc.
* Chỉ dùng khóa có trong references.bib.

## Bảng và hình
* Bảng booktabs, tiêu đề bảng ở TRÊN, tiêu đề hình ở DƯỚI; số liệu đúng như nhật ký thực nghiệm.
* Ghi "Nguồn: …" dưới bảng/hình khi phù hợp. Dùng `\cref{}` (đã cấu hình "Hình", "Bảng").
* Mọi hình nằm trong thư mục `figures/`; luôn ghi tiền tố `figures/`.

## Quy tắc quan trọng
* KHÔNG đổi `\usepackage[capitalize]{cleveref}` thành `cleverref`. Giữ nguyên phần khai báo (preamble).
* Tài liệu được biên dịch bằng XeLaTeX (hỗ trợ Unicode tiếng Việt trực tiếp).
