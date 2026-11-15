# Triển khai mục Viết nghiên cứu lên hi.hue.vn (Tenten / Plesk)

hi.hue.vn chạy bản build sẵn trong `httpdocs` (không build trên hosting). `hce-start.cjs` mở một proxy:
`/tools/bibliomap…` → BiblioMap, `/tools/writium…` → ứng dụng Viết nghiên cứu (`writium-app/`, Next.js standalone,
basePath `/tools/writium`), còn lại → site chính `./server`.

| Tệp | Vai trò |
|---|---|
| `hce-start.cjs` | tệp khởi động mới (giữ nguyên hành vi BiblioMap, thêm Viết nghiên cứu) |
| `deploy-writium.cjs` | chạy trên hosting: tải gói từ nhánh `deploy/writium`, cài vào `httpdocs/writium`, cập nhật `hce-start.cjs`, bỏ nhãn "sắp có" |
| `patch-badges.cjs` | bỏ nhãn "sắp có" của Viết nghiên cứu và Trắc lượng thư mục trong bản build của site chính (có sao lưu .tgz) |

## Cập nhật gói

```bash
cd writium-app && npm ci && npm run build && npm run package   # -> dist/writium
# đẩy nội dung dist/writium lên nhánh deploy/writium (server.js ở gốc nhánh)
```

Trên hosting (Plesk → Node.js → Run Node.js commands, thư mục /httpdocs):
`exec -- node deploy-writium.cjs` rồi **Restart App**.

## Biến môi trường (đặt trong `hue-data/.env` hoặc Plesk → Node.js → Environment)

| Biến | Ý nghĩa |
|---|---|
| `POSTUDIO_URL`, `POSTUDIO_BRIDGE_TOKEN` | địa chỉ & mã bí mật của máy viết bài PO-Studio (chạy ở máy có Docker, xem `po-studio/`). Chưa đặt: trang chỉ soạn/lưu nháp, nút gửi bị khoá |
| `POSTUDIO_ACCESS_CODE`, `PAPER_SERVER_KEY=1` | cho người đã đăng nhập dùng khoá AI chung của Trường |
| `PAPER_GUEST_DAILY_LIMIT`, `PAPER_USER_DAILY_LIMIT`, `PAPER_SERVER_KEY_DAILY_LIMIT`, `PAPER_MAX_UPLOAD_MB` | hạn mức |
| `WRITIUM_DISABLE=1` | tắt riêng ứng dụng này (proxy trả /tools/writium về trang cũ của site chính) |

Ứng dụng chỉ nhận các biến `POSTUDIO_*`/`PAPER_*` (không nhận khoá SMTP/OAuth của site chính); phiên đăng nhập được hỏi
từ site chính qua `HCE_MAIN_URL/api/auth/get-session`; lượt dùng và chủ bản thảo lưu ở `hue-data/writium/`.

## Hoàn tác

- Tắt Viết nghiên cứu: `WRITIUM_DISABLE=1` rồi Restart App, hoặc đổi tên `hce-start.bibliomap.cjs` → `hce-start.cjs`.
- Nhãn "sắp có": `tar xzf ../hue-data/backup-badges-<thời điểm>.tgz` trong `httpdocs`, rồi Restart App.
