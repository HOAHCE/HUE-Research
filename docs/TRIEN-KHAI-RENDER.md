# Triển khai HUE Research lên Render, cấu hình đăng nhập GitHub và email

Thông tin Render dưới đây đã đối chiếu với tài liệu của Render ngày 22/10/2026 (giao diện và giá có thể đổi). Giá hiện tại: https://render.com/pricing.

## 0. Chọn gói trước khi bắt đầu

| | Free | Trả phí (Starter trở lên) + Disk |
|---|---|---|
| Địa chỉ `*.onrender.com` | Có | Có |
| Ngủ khi không có truy cập | **Có, sau 15 phút** (lần truy cập sau chờ khởi động lại) | Không |
| Dữ liệu (tài khoản đăng nhập, dự án, dữ liệu đã nạp) | **Mất mỗi lần khởi động lại/ngủ dậy**, dữ liệu thật nạp lại từ đầu (vài phút) | Giữ nguyên trên Disk `/data` |
| Gửi email qua SMTP cổng 25/465/587 | **Bị chặn** | Cổng 25 vẫn bị chặn; 465/587 dùng được |
| RAM | 512 MB (bước nạp DOAJ có thể thiếu bộ nhớ) | Tuỳ gói |

Kết luận: gói **Free chỉ để xem thử**; đăng nhập chỉ có ý nghĩa khi dùng gói trả phí kèm Disk, vì CSDL (kể cả tài khoản) nằm trong một tệp SQLite.

## 1. Tạo dịch vụ từ GitHub

1. Vào https://render.com và đăng ký/đăng nhập (tài khoản của bạn, có thể bằng GitHub).
2. Mở https://render.com/deploy?repo=https://github.com/HOAHCE/HUE-Research (hoặc Dashboard → **New → Blueprint** → chọn repo `HOAHCE/HUE-Research`). Nếu Render xin quyền đọc repo GitHub, cấp quyền cho repo này.
3. Render đọc `render.yaml` và hiện dịch vụ `hue-research` (Docker, gói free). Bấm **Deploy Blueprint**.
4. Đợi build (vài phút đến mười mấy phút vì phải biên dịch `better-sqlite3`). Khi trạng thái là **Live**, mở địa chỉ dạng `https://hue-research.onrender.com` (xem chính xác trong trang dịch vụ; nếu tên đã bị dùng, Render thêm hậu tố ngẫu nhiên).
5. Kiểm tra: mở `https://<địa-chỉ>/api/providers`, phải thấy `{"email":true,"github":false,"orcid":false}`. Trang chủ mở được; công cụ Tra cứu bài báo/chuyên gia sẽ trống cho tới khi nạp dữ liệu xong (theo dõi tại **Logs**, dòng bắt đầu bằng `=== node scripts/...`; ghi cả vào `/data/seed.log`).

Địa chỉ web tự được dùng làm địa chỉ gốc cho đăng nhập (qua biến `RENDER_EXTERNAL_URL` của Render). Khoá bí mật đăng nhập (`BETTER_AUTH_SECRET`) do Render tự sinh. Không phải điền gì lúc tạo Blueprint.

## 2. Giữ dữ liệu (nên làm nếu dùng thật)

1. Dashboard → dịch vụ `hue-research` → **Settings → Instance Type** → chọn gói trả phí (Starter trở lên).
2. **Settings → Disks → Add Disk**: Name `hue-data`, **Mount Path `/data`**, dung lượng 1 GB. Lưu; Render khởi động lại dịch vụ.
3. Từ đó CSDL `hce.db`, khoá bí mật dự phòng và đánh dấu "đã nạp dữ liệu" nằm trên Disk; dữ liệu chỉ nạp một lần.
4. Ghi chú của Render: gắn Disk thì mỗi lần triển khai có vài giây gián đoạn và không chạy nhiều bản sao.

Container khởi động bằng root để sửa quyền thư mục `/data` rồi chạy ứng dụng bằng người dùng không đặc quyền, nên Disk (thường thuộc root) vẫn ghi được.

## 3. Đăng nhập bằng GitHub

Tạo ứng dụng OAuth trên GitHub (làm trong tài khoản/tổ chức của bạn):

1. GitHub → ảnh đại diện → **Settings → Developer settings → OAuth Apps → New OAuth App**.
2. Điền:
   - **Application name**: `HUE Research`
   - **Homepage URL**: `https://<địa-chỉ>.onrender.com`
   - **Authorization callback URL**: `https://<địa-chỉ>.onrender.com/api/auth/callback/github` (đúng từng ký tự, có `https`, không dấu `/` thừa ở cuối)
3. **Register application** → trong trang ứng dụng bấm **Generate a new client secret**. Sao chép **Client ID** và **Client secret** (secret chỉ hiện một lần).

Điền vào Render (**không dán các giá trị này vào cuộc trò chuyện hay mã nguồn**):

1. Dashboard → dịch vụ → **Environment → Add Environment Variable**:
   - `GITHUB_CLIENT_ID` = Client ID
   - `GITHUB_CLIENT_SECRET` = Client secret
2. **Save, rebuild, and deploy** (hoặc Save rồi để Render tự triển khai lại).
3. Kiểm tra `https://<địa-chỉ>/api/providers` phải có `"github":true`; mở `/login`, nút "Đăng nhập bằng GitHub" sáng lên. Bấm thử: GitHub hỏi quyền, rồi quay về web và hiện tên bạn ở góc trên.

Lỗi thường gặp: `redirect_uri_mismatch` nghĩa là callback URL trên GitHub không khớp địa chỉ thật; sửa trong **OAuth Apps → ứng dụng → Authorization callback URL**. Nếu sau này dùng tên miền riêng, tạo lại/sửa callback theo tên miền đó và đặt thêm biến `BETTER_AUTH_URL=https://tên-miền-của-bạn`.

## 4. Đăng nhập bằng email (liên kết một lần)

Ứng dụng gửi email bằng SMTP (nodemailer), **bắt buộc có SMTP ở bản production** (thiếu SMTP thì từ chối gửi, để không lộ liên kết đăng nhập trong nhật ký).

**Trên gói Free, Render chặn cổng 25/465/587**, nên cách thông thường (Gmail 587/465…) không chạy. Có hai lựa chọn:

- **A. Nâng lên gói trả phí** (cũng cần để giữ dữ liệu) rồi dùng SMTP cổng 587 hoặc 465.
- **B. Dùng nhà cung cấp SMTP có cổng khác** (thường là 2525 hoặc 2465/2587). Hãy xác nhận cổng trên trang tài liệu SMTP của nhà cung cấp bạn chọn (Brevo, Mailgun, SendGrid, Resend…; tôi chưa kiểm tra từng nhà cung cấp).

Cấu hình (Environment của dịch vụ Render):

| Biến | Giá trị |
|---|---|
| `SMTP_HOST` | máy chủ SMTP của nhà cung cấp |
| `SMTP_PORT` | ví dụ `2525` (cổng không bị chặn) hoặc `587` (gói trả phí) |
| `SMTP_SECURE` | `false` cho STARTTLS (587, 2525); `true` cho SSL trực tiếp (465, 2465) |
| `SMTP_USER`, `SMTP_PASS` | tên đăng nhập và mật khẩu/khoá SMTP của nhà cung cấp |
| `SMTP_FROM` | ví dụ `HUE Research <no-reply@tên-miền-đã-xác-thực>` (nhà cung cấp thường yêu cầu xác thực tên miền gửi) |
| `ALLOWED_EMAIL_DOMAINS` | (tuỳ chọn) giới hạn email, ví dụ `hce.edu.vn,hueuni.edu.vn`; để trống = mọi email |
| `ADMIN_EMAILS` | (tuỳ chọn) email quản trị, cách nhau bằng dấu phẩy |

Sau khi triển khai lại: `/api/providers` vẫn có `"email":true` (email luôn bật), nên hãy **thử thật**: vào `/login`, nhập email của bạn, kiểm tra hộp thư (kể cả thư rác), bấm liên kết (hiệu lực 10 phút, dùng một lần). Nếu báo "Không gửi được liên kết", xem **Logs** của Render: lỗi `SMTP chưa được cấu hình` nghĩa là thiếu `SMTP_HOST`; lỗi kết nối/timeout thường do cổng bị chặn hoặc sai thông tin.

## 5. (Tuỳ chọn) Trợ lý AI thật và ORCID

- `ANTHROPIC_API_KEY` (khoá API của bạn; không có thì Trợ lý chạy chế độ cục bộ dựa trên từ khoá).
- ORCID: đăng ký ứng dụng tại orcid.org/developer-tools với Redirect URI `https://<địa-chỉ>/api/auth/callback/orcid`, rồi đặt `ORCID_CLIENT_ID`, `ORCID_CLIENT_SECRET`.

## 6. Cập nhật và vận hành

- Mỗi lần đẩy mã lên nhánh `main`, Render tự build và triển khai lại (`autoDeploy`).
- Cập nhật dữ liệu thật định kỳ: Dashboard → **Shell** (gói trả phí) rồi chạy `node scripts/sync-eu-funding.mjs` (quỹ EU, nên chạy hằng ngày), `node scripts/sync-hueuni.mjs`, `node scripts/sync-hce-forms.mjs`, `node scripts/journals.mjs doaj`. Chạy tự động theo lịch cần thêm một Cron Job của Render (chưa cấu hình sẵn).
- SJR cần tệp CSV tải bằng trình duyệt; đưa lên máy chủ rồi chạy `node scripts/journals.mjs sjr --file …` (chưa có quy trình tải lên sẵn).
- Sao lưu: tải tệp `/data/hce.db` định kỳ (SQLite) nếu dùng Disk.
