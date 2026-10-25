# Phân tích hi.hue.vn và kế hoạch bổ sung tính năng AI qua Oxion AI

Ngày lập: 25/10/2026 · Phạm vi: hi.hue.vn (HUE - Research), mã nguồn trong repo này, và API của Oxion AI (oxionai.com).

Quy ước nhãn độ tin cậy: **[Quan sát]** thấy trực tiếp trên trang công khai hoặc trong mã; **[Tài liệu]** lấy từ tài liệu công khai của Oxion; **[Suy luận]** là nhận định của người phân tích; **[Chưa kiểm chứng]** cần thử với khoá thật trước khi dựa vào.

---

## 0. Tóm tắt

1. **Mã trong GitHub không phải là bản đang chạy ở hi.hue.vn.** Trang đang chạy có khảo sát 17 loại câu hỏi có thu phản hồi bằng liên kết, Phân tích định lượng (hơn 40 phương pháp), Phân tích định tính, chia sẻ dự án, tệp nền, chuông nhắc hạn, đánh giá công cụ. Nhánh `main` (commit `5b5b757`) vẫn ghi các công cụ này là "sắp có". Mọi việc code bên dưới phải bắt đầu bằng việc xác định đúng kho mã đang triển khai (mục 2.1).
2. **Oxion AI dùng được cho hầu hết tính năng AI của hệ thống** vì nó là API tương thích OpenAI (`/v1/chat/completions`, `/v1/models`, `/v1/embeddings`) với 33 mô hình, có streaming, gọi công cụ, ảnh đầu vào, JSON mode. Hệ thống hiện chỉ gọi cứng Anthropic, không stream, không gọi công cụ.
3. **Đề xuất kiến trúc:** thêm lớp "nhà cung cấp AI" có thể thay thế, trong đó Oxion là một adapter. Khoá API nhập qua trang Cài đặt, **lưu mã hoá phía máy chủ, không bao giờ gửi lại trình duyệt**. Hai chế độ cấp khoá: khoá của Trường do quản trị nhập (mặc định) và khoá cá nhân do người dùng nhập (tuỳ chọn).
4. **Thứ tự làm:** nền tảng (provider, kho khoá, định tuyến mô hình, streaming, hạn mức theo token, bộ đánh giá) → Trợ lý chính dùng gọi công cụ thay cho đoán từ khoá → hỏi AI theo từng bản ghi, gợi ý tạp chí từ bản thảo → các công cụ khảo sát/định lượng/định tính → viết, phản biện, điền biểu mẫu.
5. **Ba việc không nên giao cho mô hình ngôn ngữ:** kiểm tra đạo văn, sinh trích dẫn, tính thống kê. Mô hình chỉ giải thích kết quả của bộ máy tất định (mục 6).
6. **Rủi ro lớn nhất không nằm ở kỹ thuật** mà ở dữ liệu: Oxion là bên trung gian, chưa rõ chính sách lưu giữ và nhà cung cấp phía sau. Bản thảo chưa công bố và dữ liệu phỏng vấn không được gửi đi nếu chưa có quyết định của Trường (mục 7).

Việc tôi **chưa làm**: chưa gọi thử API Oxion (không có khoá), chưa đăng nhập hay gửi tin nhắn trên hi.hue.vn, chưa đọc điều khoản và chính sách riêng tư của Oxion. Chưa có dòng mã nào của hệ thống bị sửa.

---

## 1. Phương pháp

- Đọc thụ động các trang công khai của hi.hue.vn (`/`, `/tools`, `/huong-dan`) và oxionai.com (trang chủ, `/pricing`, `/models`, `/docs/*`: getting-started, authentication, chat-completions, models, reasoning). Trang `/docs/embeddings` hai lần hết thời gian chờ nên **chưa đọc được**.
- Đọc toàn bộ phần lõi của repo: `lib/assistant.ts`, `app/api/chat/route.ts`, `lib/registry.ts`, `lib/db.ts`, `lib/store.ts`, `lib/stats.ts`, `lib/auth.ts`, `lib/source.ts`, `lib/jobs.ts`, `components/SurveyLab.tsx`, `components/Md.tsx`, trang dự án/chat/công cụ, CI, và hai tài liệu phân tích sẵn có (`PHAN-TICH-NEU-RESEARCH.md`, `BO-SUNG-TU-TAI-LIEU.md`).
- Đối chiếu hai nguồn trên để biết chỗ nào đã có, chỗ nào còn trống, chỗ nào lệch.

---

## 2. Hiện trạng hi.hue.vn

### 2.1 Bản đang chạy và bản trong GitHub không khớp [Quan sát]

| Hạng mục | hi.hue.vn (25/10/2026) | `main` @ `5b5b757` |
|---|---|---|
| Tên hiển thị | "HUE - Research" | "HCE Research" |
| Thiết kế khảo sát | 17 loại câu, AI gợi ý/rà soát, thu phản hồi qua liên kết, tổng hợp, CSV, sổ mã biến | 3 loại câu, xuất khung CSV, tính Cronbach alpha |
| Phân tích định lượng | "Hơn 40 phương pháp", chạy trên trình duyệt, báo cáo Word, AI giải thích | Trang "sắp có" |
| Phân tích định tính | Gắn mã, bóc băng ghi âm, ma trận mã, AI gợi ý mã và chủ đề | Trang "sắp có" |
| Dự án | Mời cộng sự (chỉ xem), tệp nền ≤ 10 MB làm ngữ cảnh cho trợ lý, thẻ "Bước tiếp theo", chuông nhắc hạn | 6 giai đoạn, việc cần làm, đồng bộ theo tài khoản; chưa chia sẻ, chưa tệp đính kèm |
| Đăng nhập | Email trường + mật khẩu, liên kết qua email, GitHub, ORCID | Liên kết qua email, GitHub, ORCID |
| Hạn mức chat | Khách 10 tin/ngày/trợ lý/thiết bị; tài khoản 100/ngày, quản trị chỉnh riêng | 10 và 100 dùng chung, khách tính theo IP |
| Đánh giá công cụ | Có (nút "Đánh giá" từng công cụ) | Không |
| Hội thảo | Danh mục hội thảo tổ chức tại Việt Nam | Dữ liệu mẫu |

**Hệ quả [Suy luận]:** hoặc có một kho/nhánh khác (riêng tư) chứa bản mới, hoặc bản mới được dựng từ máy khác chưa đẩy lên. Chưa rõ trang đang chạy gọi Anthropic hay mô hình nội bộ khi trả lời. Trước khi viết mã cần: (a) xác nhận kho mã đang triển khai, (b) rebase nhánh làm việc lên đó. Phần còn lại của tài liệu viết theo kiến trúc quan sát được trong repo, vốn vẫn là khung của bản đang chạy (Next.js, Better Auth, SQLite, registry công cụ).

### 2.2 Kiến trúc AI hiện tại (theo mã trong repo) [Quan sát]

```
Trình duyệt ── POST /api/chat ──► route.ts
                                   ├─ giới hạn: khách 10/ngày theo IP, tài khoản 100/ngày   (takeQuota, dòng 30)
                                   ├─ pickTool(): so khớp từ khoá trong registry               (assistant.ts:11)
                                   ├─ retrieve(): LIKE theo từ khoá, ≤3 bản ghi/nguồn          (assistant.ts:40)
                                   ├─ systemPrompt(): nhét kết quả tra cứu vào system prompt   (assistant.ts:143)
                                   └─ fetch https://api.anthropic.com/v1/messages              (route.ts:58)
                                        không có khoá, hoặc lỗi ⇒ localAnswer() (từ khoá + FAQ)
```

Điểm mạnh nên giữ: có chế độ cục bộ khi không có khoá (hệ thống không chết khi nhà cung cấp AI lỗi); nhiều nguồn dữ liệu thật đã đồng bộ (bài báo, chuyên gia, đề tài, biểu mẫu, quỹ EU, tạp chí SJR/QĐ 2244/DOAJ); lời nhắc hệ thống đã có nguyên tắc "không bịa, nêu nguồn"; trang "Dùng AI có trách nhiệm"; nhật ký kiểm toán; quản lý khoá bằng biến môi trường.

### 2.3 Điểm yếu cần xử lý trước hoặc cùng lúc với việc thêm AI [Quan sát]

| # | Vấn đề | Vị trí | Hệ quả |
|---|---|---|---|
| 1 | Chỉ gọi cứng Anthropic, mô hình qua `HCE_MODEL` | `route.ts:58-63` | Không đổi được nhà cung cấp; đổi sang Oxion phải sửa trực tiếp |
| 2 | Không stream; `max_tokens` cố định 1024 | `route.ts:63` | Chờ lâu mới thấy chữ đầu tiên; mô hình suy luận (reasoning) dễ hết ngân sách token mà không ra đáp án |
| 3 | Chọn công cụ bằng so khớp từ khoá, truy xuất bằng `LIKE` | `assistant.ts:11-23, 40` | Câu hỏi diễn đạt khác từ khoá là trượt; không hiểu ngữ nghĩa, không lọc kết hợp (ví dụ "Q1 + có trong QĐ 2244") |
| 4 | Quỹ EU tra bằng từ điển 24 cặp Việt→Anh viết tay | `assistant.ts:25-32` | Dữ liệu EU toàn tiếng Anh; câu tiếng Việt ngoài 24 từ gần như không ra kết quả |
| 5 | Trừ hạn mức **trước** khi gọi nhà cung cấp, rồi âm thầm rơi về chế độ cục bộ khi lỗi | `route.ts:30, 74` | Người dùng mất lượt mà không biết câu trả lời không phải của AI (chỉ có trường `mode` mà giao diện không hiển thị) |
| 6 | Địa chỉ khách lấy từ `X-Forwarded-For` | `route.ts:11` | Nếu không đứng sau proxy tin cậy, khách giả header để lách hạn mức. Mã đã có ghi chú về điều này |
| 7 | Hạn mức tính theo **số tin nhắn**, không theo token | `registry.ts:51-52` | Với API tính tiền theo token, một tin nhắn có thể tốn gấp trăm lần tin khác |
| 8 | Kết quả tra cứu (nội dung cào từ web: biểu mẫu, lời kêu gọi EU) được nhét vào system prompt | `assistant.ts:143` | Là đường cho prompt injection gián tiếp (mục 7.3) |
| 9 | Hội thoại chỉ lưu `localStorage`; `Md` không hiển thị bảng, liên kết, mã | `chat/page.tsx:15`, `Md.tsx` | Mất khi đổi thiết bị; câu trả lời của mô hình thường có bảng/liên kết sẽ hiện thô |
| 10 | Không có bộ kiểm thử; CI chỉ chạy `tsc` và `build` | `.github/workflows/ci.yml` | Thêm mã mã hoá khoá và định tuyến mà không có test là rủi ro |

Còn một khoảng trống nội dung: **hội thảo và quỹ trong nước vẫn là dữ liệu mẫu** (theo README), và danh mục HĐGSNN chưa có vì là PDF quét cần OCR. Hai việc này mô hình có thể hỗ trợ (mục 5, F13 và F17).

---

## 3. Oxion AI

### 3.1 Những gì tài liệu công khai cho biết [Tài liệu]

| Hạng mục | Nội dung |
|---|---|
| Địa chỉ | `https://oxionai.com/v1`, tương thích OpenAI SDK |
| Xác thực | `Authorization: Bearer cc_…` (khoá bắt đầu `cc_`, thêm 48 ký tự); khoá lưu dạng băm SHA-256, chỉ hiện một lần khi tạo |
| Phạm vi khoá | `inference` (chat), `models:read` (liệt kê mô hình), `embeddings` |
| Endpoint | `GET /models`, `GET /models/{id}`, `POST /chat/completions`, `POST /embeddings` |
| Tham số chat | `stream`, `max_tokens` (mặc định 8192), `temperature`, `top_p`, `tools`, `tool_choice`, `response_format: json_object`, `stop`, `seed`, … |
| Khả năng từng mô hình | `reasoning`, `vision`, `tools`, `streaming`, `json_mode`, `web_search`, lấy bằng `GET /models` (trường `capabilities`) |
| Suy luận | Nội dung suy luận ở trường riêng `reasoning_content` (khi stream là `delta.reasoning_content`); token suy luận tính vào `completion_tokens` |
| Lỗi | Dạng như OpenAI: 401, 402 (hết tiền/hết hạn mức), 403 (thiếu scope), 404, 422, 429 (kèm `Retry-After`), 502 |
| Hạn mức tốc độ | Theo RPM và TPM mỗi phút, trả về qua header `X-RateLimit-*` |
| Gói | Free 0,5 triệu token/tháng, không cần thẻ; Starter 50M = 3,5 USD; Pro 200M = 9,5 USD; Scale 500M = 15,5 USD; Unlimited = 50 USD/tháng. Hết hạn mức thì trừ số dư theo giá từng mô hình; số dư bằng 0 thì trả 402 |
| Thanh toán | Paddle (thẻ), Binance Pay, tiền mã hoá |

Giá theo triệu token (cùng giá cho vào và ra, trừ Gemma 2 2B): `deepseek-v4-flash-0731` 0,12 USD; `gpt-5.6-luna` 0,36; `deepseek-v4-pro-0813` 0,55; `qwen3.8-27b` 0,57; `gemini-3.7-flash` 1,24; `claude-sonnet-5` 3,32; `claude-opus-5.5` 8,30; `gpt-5.6-sol` 8,95; `claude-fable-5.1` 16,61.

### 3.2 Nên kiểm tra trước khi tin [Chưa kiểm chứng]

- Trang `/models` gắn nhãn **"Maintenance"** cho cả 33 mô hình. Có thể chỉ là lỗi giao diện, cũng có thể là trạng thái thật. Chỉ `GET /v1/models` với khoá thật mới cho biết mô hình nào đang dùng được ("chỉ liệt kê mô hình đang hoạt động").
- **Hạn mức tốc độ mâu thuẫn** giữa thẻ gói và bảng so sánh trên `/pricing` (Basic 300 hay 120 yêu cầu/phút; Scale 1.200 hay 120). Số đúng nằm ở Dashboard → Usage → Rate Limits.
- **Embeddings:** có endpoint, nhưng danh mục 33 mô hình đều là mô hình chat, và tôi chưa đọc được trang `/docs/embeddings`. Chưa biết có mô hình embedding nào, số chiều, và chất lượng tiếng Việt. Tìm kiếm ngữ nghĩa (F5) phụ thuộc điểm này.
- **Chất lượng tiếng Việt** của từng mô hình, độ ổn định gọi công cụ, và độ trễ thực tế: chưa có số đo. Phải đo bằng bộ đánh giá (mục 8).
- **"Unlimited"** có điều khoản sử dụng hợp lý (fair use) hay không.
- **Nguồn gốc mô hình:** danh mục gồm nhiều tên của Anthropic, OpenAI, Google, xAI bán qua một đầu mối với giá phẳng. Tôi không biết hợp đồng và đường đi của dữ liệu phía sau. Đây là điều một Trường nên hỏi bằng văn bản trước khi gửi dữ liệu nghiên cứu (mục 7).
- Điều khoản dịch vụ, chính sách riêng tư, chính sách lưu nhật ký của Oxion: **chưa đọc**.

### 3.3 Cách chọn mô hình theo nhóm (ứng viên để đo, chưa phải kết luận)

| Nhóm | Ứng viên | Có | Dùng cho |
|---|---|---|---|
| Nhanh, rẻ | `deepseek-v4-flash-0731`, `gpt-5.6-luna`, `qwen3.8-27b` | tools, JSON, suy luận; `luna` có thêm vision | Chat thường, định tuyến, dịch truy vấn, trích xuất JSON, gợi ý câu hỏi khảo sát |
| Cân bằng | `gemini-3.7-flash`, `kimi-k2.6`, `glm-5.3`, `claude-sonnet-5` | tools, vision, nhiều mô hình có web_search | Hỏi đáp trên bài báo, gợi ý mã định tính, giải thích kết quả thống kê, phản biện sơ bộ |
| Cao cấp | `claude-opus-5.5`, `gpt-5.6-sol`, `claude-fable-5.1` | suy luận mạnh | Viết nghiên cứu dài, phản biện sâu. Đắt hơn nhóm nhanh 70 đến 140 lần; chỉ bật theo yêu cầu của người dùng |
| Không dùng cho tính năng | `gemma-2-2b` | Không có tools/vision, ngữ cảnh 8K | Chỉ để kiểm tra kết nối (ví dụ mặc định trong tài liệu Oxion) |

---

## 4. Thiết kế tích hợp và nhập khoá API Oxion

### 4.1 Ai nhập khoá: ba chế độ, đề xuất bật hai

| Chế độ | Người nhập | Nơi lưu | Ưu | Nhược | Đề xuất |
|---|---|---|---|---|---|
| **A. Khoá của Trường** | Quản trị viên (`ADMIN_EMAILS`) | CSDL, mã hoá; hoặc biến môi trường `OXION_API_KEY` | Người dùng không cần làm gì; quản trị kiểm soát chi phí và mô hình | Một khoá chung, cần hạn mức theo người để tránh một người dùng hết | **Mặc định** |
| **B. Khoá cá nhân (BYOK)** | Từng người dùng | CSDL, mã hoá, gắn tài khoản | Chi phí do người dùng chịu; gói Free của Oxion cho mỗi người 0,5M token/tháng, đủ khoảng 100 đến 150 lượt hỏi đáp | Người dùng phải tự đăng ký Oxion; trách nhiệm về dữ liệu chuyển sang họ | **Tuỳ chọn** |
| C. Khoá chỉ trong phiên | Người dùng | Bộ nhớ tab, gửi mỗi yêu cầu | Không lưu gì | Mất khi tải lại; khoá đi qua trình duyệt mỗi lần, dễ lộ qua tiện ích mở rộng | Không làm |

Thứ tự chọn khoá cho một yêu cầu: khoá cá nhân của người dùng (nếu có và đang bật) → khoá của Trường → chế độ cục bộ. Nếu khoá cá nhân trả 401/402 thì báo rõ cho người dùng, **không** tự động chuyển sang khoá của Trường (để không tiêu tiền Trường ngoài ý muốn).

### 4.2 Bảo mật khoá (bắt buộc)

1. **Mã hoá khi lưu:** AES-256-GCM, khoá chủ `AI_KEY_SECRET` (32 byte, base64) đặt trong biến môi trường, không nằm trong CSDL. Lưu `iv | tag | ciphertext`, thêm `last4` để hiển thị `cc_…a1b2`. Production từ chối khởi động tính năng khoá nếu thiếu `AI_KEY_SECRET` (cùng tinh thần với kiểm tra SMTP hiện có).
2. **Một chiều với trình duyệt:** API chỉ có `PUT` (ghi), `DELETE`, và `GET` trả `{set: true, last4, scopesOk, checkedAt}`. Không có đường nào trả khoá về.
3. **Không ghi nhật ký:** khoá và nội dung prompt không vào `audit_log`; chỉ ghi hành động (`ai.key.set`, `ai.key.delete`, `ai.key.test`).
4. **Không dùng `localStorage`** cho khoá (khác với `useLocal` hiện dùng cho hội thoại): một lỗi XSS sẽ lấy được khoá.
5. **Chống SSRF:** địa chỉ gốc cố định `https://oxionai.com/v1` trong mã; chỉ quản trị mới đổi được qua biến môi trường `OXION_BASE_URL`. Người dùng không được nhập URL.
6. **Kiểm tra khi lưu:** đúng dạng `^cc_\S{48}$`, rồi gọi `GET /models`. Nếu 403 `insufficient_scope` thì báo "khoá thiếu quyền `models:read`" (khoá vẫn dùng được cho chat nếu có `inference`). Lưu ý bước kiểm tra tốn một yêu cầu.
7. **Giới hạn tốc độ** riêng cho `PUT/test` để chống dò khoá.
8. **Xoay khoá:** nút "Thay khoá" và "Xoá khoá"; khi người dùng bị khoá tài khoản thì khoá cá nhân bị xoá.
9. **Sao lưu:** mất `AI_KEY_SECRET` thì mọi khoá đã lưu vô dụng (người dùng nhập lại). Ghi rõ trong hướng dẫn triển khai.

### 4.3 Lớp nhà cung cấp AI (phác thảo, chưa chạy thử)

```ts
// lib/ai/types.ts
export type Cap = "reasoning" | "vision" | "tools" | "streaming" | "json_mode" | "web_search";
export type ModelInfo = { id: string; name: string; contextWindow: number; caps: Cap[]; inPer1M: number; outPer1M: number };

export type ChatRequest = {
  model: string;
  messages: ChatMessage[];          // role: system | user | assistant | tool
  tools?: ToolDef[];
  json?: boolean;
  maxTokens?: number;
  signal?: AbortSignal;
};

export type ChatEvent =             // luồng sự kiện chuẩn hoá cho giao diện
  | { type: "reasoning"; text: string }
  | { type: "text"; text: string }
  | { type: "tool_call"; id: string; name: string; args: unknown }
  | { type: "usage"; promptTokens: number; completionTokens: number }
  | { type: "done"; finish: "stop" | "length" | "tool_calls" };

export interface AiProvider {
  id: "oxion" | "anthropic";
  listModels(): Promise<ModelInfo[]>;
  chat(req: ChatRequest): AsyncIterable<ChatEvent>;
  embed?(model: string, input: string[]): Promise<number[][]>;
}
```

- `lib/ai/oxion.ts`: gọi `fetch` thẳng vào `/chat/completions` với `stream: true`, đọc SSE, chuyển `delta.content` thành `text`, `delta.reasoning_content` thành `reasoning`, ghép các mảnh `tool_calls` theo `index`. Không cần thêm thư viện `openai` (repo hiện chỉ có 9 thư viện phụ thuộc khi chạy; giữ nguyên là một lợi thế).
- `lib/ai/anthropic.ts`: chuyển phần gọi hiện tại của `route.ts` vào đây, để khách hiện dùng khoá Anthropic không bị ảnh hưởng.
- `lib/ai/router.ts`: `pick(task, {user, org}) → {provider, model, key}`; đọc cấu hình tác vụ (4.4), kiểm tra `caps` của mô hình trước khi gửi ảnh hoặc công cụ (đúng khuyến nghị "inspect `capabilities`" của Oxion), và có chuỗi dự phòng: mô hình chính → mô hình phụ cùng nhóm → chế độ cục bộ. Mọi lần rơi về dự phòng phải được **báo cho người dùng** (khắc phục điểm yếu số 5).
- Xử lý lỗi theo bảng của Oxion: 401 → báo khoá sai/hết hạn; 402 → hết số dư, không thử lại; 429 → chờ `Retry-After` rồi thử lại tối đa 1 lần; 502 → thử mô hình phụ.
- `max_tokens`: nếu mô hình có `reasoning` thì mặc định ≥ 4096 cho chat ngắn, 16000 cho viết/phản biện (tài liệu Oxion nêu đây là lỗi hay gặp nhất: ngân sách bị suy luận ăn hết, `content` rỗng). Khi `finish = length` và `content` rỗng thì tự thử lại với ngân sách gấp đôi.

### 4.4 Cấu hình theo tác vụ

Quản trị chọn mô hình cho từng tác vụ; hệ thống chỉ cho chọn mô hình có đủ `caps` mà tác vụ đòi hỏi.

| Tác vụ | Cần | Nhóm đề xuất | Ghi chú |
|---|---|---|---|
| `chat.central` | tools, streaming | Nhanh | Mặc định cho mọi người |
| `chat.deep` | reasoning | Cân bằng/Cao cấp | Người dùng bấm "Suy nghĩ kỹ"; tính hạn mức gấp nhiều lần |
| `extract.json` | json_mode | Nhanh | Dịch truy vấn, trích từ khoá, gợi ý tạp chí |
| `record.qa` | streaming | Cân bằng | Hỏi AI trên một bài báo/quỹ/biểu mẫu |
| `survey.assist` | json_mode | Nhanh | Gợi ý/rà soát câu hỏi |
| `stats.explain` | streaming | Cân bằng | Chỉ nhận số liệu tổng hợp |
| `qual.code` | json_mode | Cân bằng | Gợi ý mã kèm trích dẫn nguyên văn |
| `vision.ocr` | vision | Nhanh có vision | PDF quét, ảnh bảng |
| `write.draft` / `review.manuscript` | reasoning | Cao cấp | Dài, bật theo yêu cầu |
| `embed` | embeddings | (chưa rõ) | Chỉ khi xác nhận có mô hình embedding |

### 4.5 Bảng dữ liệu mới (SQLite, cùng tệp `hce.db`)

```sql
CREATE TABLE IF NOT EXISTS ai_credential (
  owner      TEXT NOT NULL,            -- 'org' hoặc 'u:<userId>'
  provider   TEXT NOT NULL,            -- 'oxion'
  secret     BLOB NOT NULL,            -- iv|tag|ciphertext (AES-256-GCM)
  last4      TEXT NOT NULL,
  scopes_ok  TEXT,                     -- JSON: {models:true,inference:true,embeddings:false}
  checked_at INTEGER,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (owner, provider)
);
CREATE TABLE IF NOT EXISTS ai_task_config (
  task TEXT PRIMARY KEY, model TEXT NOT NULL, fallback TEXT, max_tokens INTEGER, enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS ai_usage (          -- thay cho đếm theo tin nhắn
  day TEXT NOT NULL, subject TEXT NOT NULL, task TEXT NOT NULL, model TEXT NOT NULL,
  prompt_tokens INTEGER NOT NULL DEFAULT 0, completion_tokens INTEGER NOT NULL DEFAULT 0,
  cost_usd REAL NOT NULL DEFAULT 0, requests INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, subject, task, model)
);
CREATE TABLE IF NOT EXISTS ai_cache (          -- cache dịch truy vấn, tóm tắt bản ghi
  key TEXT PRIMARY KEY, value TEXT NOT NULL, created_at INTEGER NOT NULL
);
```

### 4.6 Giao diện

- **Trang `/settings/ai` (mọi người dùng đã đăng nhập):** nhập/thay/xoá khoá cá nhân; nút "Kiểm tra kết nối"; hiển thị `last4`, thời điểm kiểm tra, phạm vi quyền; chọn "Dùng khoá của tôi / khoá của Trường"; lượng token đã dùng hôm nay và tháng này.
- **Trang `/admin/ai` (quản trị):** khoá của Trường; bảng tác vụ → mô hình (lọc theo khả năng, hiển thị giá); hạn mức token mỗi ngày cho khách/tài khoản/từng người; biểu đồ chi phí theo ngày/tác vụ/mô hình; công tắc tắt từng tính năng AI; xem nhật ký lỗi nhà cung cấp. Hiện README ghi hệ thống **chưa có trang quản trị**, nên đây là hạng mục mới.
- **Chat:** hiện tên mô hình đã trả lời, nhãn "chế độ cục bộ" khi rơi về dự phòng, ô thu gọn "Quá trình suy luận" cho `reasoning_content`, nút "Dừng", đếm token thay cho đếm tin.

### 4.7 Hạn mức và chi phí

Chuyển hạn mức từ "số tin nhắn" sang **token quy đổi**, giữ cách hiển thị thân thiện ("còn khoảng 35 câu hỏi"). Khách vẫn có mức rất thấp và chỉ dùng nhóm Nhanh.

Ước tính minh hoạ [Suy luận, giả định nêu rõ]: 500 người dùng hoạt động × 20 lượt/ngày × 4.000 token/lượt = 40 triệu token/ngày = **1,2 tỷ token/tháng**.

| Cách dùng | Chi phí/tháng |
|---|---|
| Toàn bộ trên nhóm Nhanh (`deepseek-v4-flash-0731`, 0,115 USD/triệu) | ≈ 138 USD |
| 80% nhóm Nhanh + 20% `claude-sonnet-5` (3,32 USD/triệu) | ≈ 907 USD |
| Toàn bộ trên `claude-sonnet-5` | ≈ 3.984 USD |
| Gói Unlimited (nếu điều khoản cho phép dùng ở quy mô này) | 50 USD |

Kết luận: định tuyến theo nhóm quyết định chi phí hơn mọi yếu tố khác; và nên hỏi Oxion về điều khoản Unlimited cho mục đích tổ chức trước khi chọn mô hình trả theo token. Với 0,5M token Free mỗi tháng, khoảng 125 lượt 4.000 token, chỉ đủ để thử nghiệm.

---

## 5. Danh mục tính năng bổ sung

Ký hiệu độ khó (ước lượng cho một lập trình viên đã quen mã nguồn): **S** ≤ 2 ngày, **M** 3 đến 7 ngày, **L** 1 đến 3 tuần. Ưu tiên: P0 nền tảng, P1 giá trị cao làm ngay, P2, P3, P4 để sau.

### 5.1 Nền tảng (P0)

| ID | Hạng mục | Độ khó | Nội dung |
|---|---|---|---|
| N1 | Lớp `AiProvider` + adapter Oxion + adapter Anthropic + chế độ cục bộ | M | Mục 4.3 |
| N2 | Kho khoá mã hoá, trang `/settings/ai`, kiểm tra kết nối | M | Mục 4.2, 4.6 |
| N3 | Danh mục mô hình theo khả năng + cấu hình theo tác vụ | S–M | Gọi `GET /models`, cache 1 giờ, ánh xạ `capabilities` |
| N4 | Chat stream (SSE) + `reasoning_content` + Markdown đầy đủ | M | Thay `Md.tsx` bằng bộ hiển thị an toàn (bảng, liên kết, mã) **không cho HTML thô**; chỉ cho liên kết tới miền trong danh sách cho phép (mục 7.3) |
| N5 | Hạn mức theo token, bảng chi phí, trang quản trị | M | Thay `takeQuota`; trừ **sau** khi nhà cung cấp trả lời thành công |
| N6 | Bộ đánh giá (mục 8) + thêm kiểm thử đơn vị (vitest) vào CI | M | Cho mã hoá khoá, SSE parser, định tuyến, hạn mức |

### 5.2 Tính năng cho người dùng

| ID | Tính năng | Ưu tiên | Độ khó | Công cụ liên quan | Khả năng Oxion cần | Cách làm và rủi ro chính |
|---|---|---|---|---|---|---|
| F1 | Trợ lý chính **gọi công cụ** thay cho đoán từ khoá | P1 | M | Chat | tools, streaming | Khai báo hàm `search_papers`, `search_experts`, `search_topics`, `search_journals`, `search_eu_calls`, `search_forms`, `get_record`. Mô hình tự chọn và kết hợp, ví dụ "tạp chí Q1 ngành kinh tế có trong QĐ 2244". Giới hạn 4 vòng gọi, cắt kết quả. Mô hình không có `tools` thì rơi về `retrieve()` hiện tại. Xem 5.3 |
| F2 | Dịch và mở rộng truy vấn Việt→Anh cho quỹ EU | P1 | S | Tra cứu quỹ, Chat | json_mode | Thay từ điển 24 cặp bằng một lệnh gọi `extract.json` ra 3 đến 5 từ khoá tiếng Anh, cache theo câu hỏi. Rẻ nhất, hiệu quả thấy ngay |
| F3 | **Hỏi AI trên từng bản ghi** (bài báo, tạp chí, quỹ, biểu mẫu) | P1 | M | Bài báo, Tạp chí, Quỹ, Biểu mẫu | streaming | Tài liệu bổ sung của repo ghi mục này còn thiếu. Gửi chính bản ghi (tiêu đề, tóm tắt, nguồn) làm ngữ cảnh. Chỉ hỏi trên **dữ liệu đã có trong CSDL**; không tự tải toàn văn từ nguồn ngoài |
| F4 | **Gợi ý tạp chí từ bản thảo** | P1 | M | Hội thảo–tạp chí | json_mode | Người dùng dán tóm tắt hoặc tải PDF/DOCX. Mô hình **chỉ trích xuất** (lĩnh vực, từ khoá, loại nghiên cứu, ngôn ngữ), rồi **SQL xếp hạng** trên bảng tạp chí đã có (SJR quartile, QĐ 2244, DOAJ, ISSN). Mô hình không được nêu tên tạp chí không có trong CSDL |
| F5 | Tìm kiếm ngữ nghĩa bài báo/chuyên gia/đề tài | P2 | M–L | Tra cứu | embeddings | **Phụ thuộc** mô hình embedding của Oxion (chưa xác nhận). Với khoảng 2.300 bài, 236 chuyên gia, brute-force cosine trong bộ nhớ là đủ, chưa cần CSDL vector. Nếu không có embedding, dùng SQLite FTS5 (BM25) thay cho `LIKE`, vẫn cải thiện lớn |
| F6 | Khảo sát: soạn và rà soát câu hỏi, gợi ý thang đo | P2 | M | Thiết kế khảo sát | json_mode | Sinh bảng hỏi từ mục tiêu nghiên cứu; rà lỗi câu hỏi dẫn dắt, hai ý trong một câu, thang đo lệch. Đầu ra là JSON khớp kiểu `Question` rồi nhập vào trình soạn, người dùng duyệt |
| F7 | Định lượng: giải thích kết quả, gợi ý phương pháp, viết đoạn kết quả theo APA | P2 | M | Phân tích định lượng | streaming | **Chỉ gửi thống kê tổng hợp** (hệ số, p, cỡ mẫu), không gửi dữ liệu thô. Con số lấy từ bộ máy thống kê, mô hình chỉ diễn giải |
| F8 | Định tính: gợi ý mã và chủ đề kèm trích dẫn | P2 | M–L | Phân tích định tính | json_mode | Mỗi mã đi kèm trích dẫn nguyên văn; **máy chủ kiểm tra chuỗi đó có thật trong văn bản gốc**, không có thì loại. Bắt buộc bước ẩn danh trước khi gửi (mục 7) |
| F9 | Dự án: tóm tắt tệp nền, "Bước tiếp theo", nhắc việc có ngữ cảnh | P2 | M | Dự án | streaming | Dựa trên giai đoạn, ngày dự kiến, ghi chú. Đã có trên bản chạy; bổ sung bản dùng nhà cung cấp mới |
| F10 | AI điền biểu mẫu Word/Excel | P3 | L | Quy trình, biểu mẫu | json_mode | Trích trường từ mẫu, điền từ hồ sơ/dự án, **đánh dấu rõ mục do AI điền** (như hệ thống tham chiếu). Cần thư viện sửa DOCX/XLSX giữ nguyên định dạng |
| F11 | Viết nghiên cứu: dàn ý IMRaD, diễn đạt lại, dịch, xuất DOCX | P3 | L | Viết nghiên cứu | reasoning, streaming | Trích dẫn chỉ lấy từ danh sách đã xác thực (mục 6). Mức 2 của khung "Dùng AI có trách nhiệm" |
| F12 | Phản biện sơ bộ bản thảo | P3 | L | Phản biện bài báo | reasoning, json_mode | Trích văn bản PDF (đã có `pdfjs-dist`), chấm theo thang tiêu chí, trả JSON rồi hiển thị. Công việc dài: chạy nền, báo bằng email khi xong |
| F13 | OCR và đọc bảng từ PDF/ảnh quét | P3 | M | Nhập dữ liệu, Tạp chí | vision | Mở khoá danh mục HĐGSNN mà README ghi là "cần OCR". Kết quả vào hàng chờ duyệt (F17), không ghi thẳng |
| F14 | Tự động soạn lời **khai báo dùng AI** theo dự án | P2 | S | Dùng AI có trách nhiệm, Dự án | không | Ghi lại tác vụ AI đã dùng trong từng dự án (từ `ai_usage`) rồi điền sẵn vào công cụ soạn lời khai báo đã có |
| F15 | Trắc lượng thư mục: AI đặt tên cụm, diễn giải bản đồ | P4 | L | Trắc lượng thư mục | streaming | Phần lớn là xử lý tất định (đọc RIS/CSV, đồng xuất hiện, phân cụm); AI chỉ gắn nhãn |
| F16 | Kiểm tra đạo văn | P4 | L | Kiểm tra đạo văn | (một phần) | Xem mục 6: cần bộ máy so khớp văn bản, AI chỉ giải thích |
| F17 | **Quy trình thu thập dữ liệu có người duyệt** cho hội thảo, quỹ trong nước | P2 | M–L | Hội thảo, Quỹ | json_mode, web_search (tuỳ chọn) | Giải quyết khoảng trống "dữ liệu mẫu": tải trang chính thức của NAFOSTED, VinIF… → mô hình trích JSON (tên, hạn nộp, lĩnh vực, liên kết gốc) → **hàng chờ để quản trị duyệt** → mới xuất bản. Không bao giờ ghi thẳng kết quả của mô hình vào dữ liệu công khai; luôn lưu URL gốc và ngày thu thập |

### 5.3 Chi tiết F1: đổi cách Trợ lý chính hoạt động

Luồng đề xuất:

1. Gửi lịch sử (≤ 12 tin như hiện nay) + `systemPrompt` rút gọn (không còn khối "DỮ LIỆU HỆ THỐNG") + danh sách hàm.
2. Mô hình trả `tool_calls` → máy chủ chạy các hàm trên SQLite (mọi hàm chỉ đọc), trả kết quả dạng `role: "tool"`, mỗi bản ghi có mã ổn định (`papers:123`).
3. Lặp tối đa 4 vòng, rồi mô hình viết câu trả lời. Quy tắc: mọi khẳng định về bài báo/chuyên gia/quỹ/biểu mẫu của Trường phải kèm mã bản ghi.
4. **Máy chủ kiểm tra hậu kỳ:** mã bản ghi trong câu trả lời phải nằm trong số đã được hàm trả về; nếu không, gắn cảnh báo "chưa xác minh" (chống bịa).
5. Giao diện hiện các nút "Mở công cụ" từ các lần gọi hàm (thay cho trường `tool` hiện tại).

Phương án dự phòng giữ nguyên hành vi hiện tại: mô hình không có `tools` hoặc lỗi → `pickTool` + `retrieve`. Nhờ vậy việc nâng cấp không làm hệ thống tệ đi trong trường hợp xấu nhất.

---

## 6. Những việc không nên giao cho mô hình ngôn ngữ

| Việc | Vì sao | Cách làm đúng |
|---|---|---|
| **Kiểm tra đạo văn** | Mô hình không đo được tỷ lệ trùng lặp; nó có thể "nói" một con số bịa. Mô hình có `web_search` cũng không thay được so khớp văn bản | Bộ máy so khớp tất định (băm n-gram/shingling, MinHash) chạy trên kho nội bộ (bài báo của Trường, đề tài, luận văn nếu được cấp) cộng người dùng tự tải thêm nguồn. Báo cáo ghi rõ **phạm vi đối chiếu** và "chỉ mang tính tham khảo, không thay Turnitin/iThenticate". AI chỉ giải thích đoạn trùng và gợi ý diễn đạt lại |
| **Trích dẫn tài liệu tham khảo** | Mô hình hay bịa bài báo, tác giả, DOI | Mọi trích dẫn phải xác thực qua DOI (Crossref/OpenAlex) hoặc khớp CSDL nội bộ. Không xác thực được thì không đưa vào bản thảo. Khớp với nguyên tắc "không bịa trích dẫn" đã có trong lời nhắc hệ thống |
| **Tính toán thống kê** | Sai số học ở mô hình là phổ biến | Giữ bộ máy trên trình duyệt (như `lib/stats.ts`, mà tài liệu bổ sung ghi là đã đối chiếu bằng ví dụ tính tay); mô hình chỉ nhận kết quả để giải thích |
| **Điền hạn nộp, điều kiện quỹ** từ trí nhớ | Dữ liệu thay đổi, mô hình không biết | Chỉ lấy từ nguồn đã thu thập có URL và ngày; luôn nhắc kiểm tra thông báo chính thức |

---

## 7. An toàn, riêng tư, tuân thủ

### 7.1 Phân loại dữ liệu gửi cho Oxion

| Lớp | Ví dụ | Quy tắc |
|---|---|---|
| C0 Công khai | Bài báo đã công bố, danh mục tạp chí, lời kêu gọi quỹ, biểu mẫu | Gửi được |
| C1 Thông tin tài khoản | Hồ sơ (trình độ, đơn vị, lĩnh vực), tên dự án | Gửi ở mức tối thiểu cần để xưng hô/gợi ý, không gửi email, tên đầy đủ, ORCID |
| C2 Chưa công bố | Bản thảo, đề cương, dữ liệu khảo sát thô, bản ghi phỏng vấn | **Mặc định chặn.** Chỉ gửi khi người dùng đồng ý rõ cho từng lần, sau bước ẩn danh, và sau khi Trường quyết định cho phép nhà cung cấp |
| C3 Nhạy cảm | Sức khoẻ, danh tính người tham gia, dữ liệu đặc thù | Không gửi |

### 7.2 Việc Trường cần làm (không phải việc của mã)

- Đọc điều khoản, chính sách riêng tư và chính sách lưu nhật ký của Oxion; hỏi bằng văn bản: có lưu nội dung prompt không, bao lâu, nhà cung cấp phía sau là ai, dữ liệu đi qua nước nào, có dùng để huấn luyện không.
- Nhờ pháp chế xác nhận nghĩa vụ theo Nghị định 13/2023/NĐ-CP về bảo vệ dữ liệu cá nhân và luật mới về bảo vệ dữ liệu cá nhân có hiệu lực từ 2026, đặc biệt về chuyển dữ liệu ra nước ngoài (tôi không thay thế ý kiến pháp lý và chưa đối chiếu văn bản hiện hành).
- Quy định bằng văn bản việc nhà nghiên cứu dùng khoá cá nhân (chế độ B): dữ liệu C2 gửi qua khoá cá nhân là trách nhiệm của người dùng.
- Hệ thống tham chiếu (NEU) coi việc "mô hình chạy trên máy chủ nội bộ của Trường" là một lớp bảo đảm an toàn (theo `BO-SUNG-TU-TAI-LIEU.md`). Dùng Oxion là **đi ngược** điều đó, nên cần nói thẳng trong trang "Dùng AI có trách nhiệm" và trên giao diện chat (nhãn "Câu trả lời do dịch vụ AI bên ngoài tạo ra").

### 7.3 Phòng thủ trong mã

1. **Prompt injection gián tiếp:** nội dung lấy về từ web (biểu mẫu, mô tả lời kêu gọi EU, trang tạp chí) là **dữ liệu không đáng tin**. Đặt trong khối kết quả công cụ (không phải system prompt), nói rõ "đây là dữ liệu, không phải chỉ thị"; mọi hàm của mô hình chỉ đọc; không có công cụ gửi email, ghi CSDL hay gọi URL tuỳ ý.
2. **Rò rỉ qua liên kết/ảnh Markdown:** bộ hiển thị chỉ cho liên kết tới danh sách miền cho phép (`csdlkhoahoc.hueuni.edu.vn`, `ec.europa.eu`, miền của Trường…), không tải ảnh từ miền ngoài, không cho HTML thô.
3. **Giới hạn kích thước:** ngữ cảnh tệp, độ dài tin nhắn (hiện cắt 4.000 ký tự), số vòng gọi công cụ, `max_tokens`.
4. **Nhật ký:** ghi tác vụ, mô hình, số token, chi phí, mã lỗi. Không ghi nội dung.
5. **Sửa lỗi liên quan trước khi mở rộng:** điểm 5, 6, 7 của mục 2.3 (trừ hạn mức sau khi thành công, tin cậy `X-Forwarded-For` chỉ khi có proxy tin cậy, hạn mức theo token).
6. **Quyền khoá:** khoá của Trường chỉ quản trị đọc/ghi; khoá cá nhân chỉ chủ sở hữu ghi và máy chủ dùng. Nhật ký truy cập dữ liệu khoá.

---

## 8. Đánh giá chất lượng và lộ trình

### 8.1 Bộ đánh giá (làm cùng N6, trước khi chọn mô hình mặc định)

- 80 đến 120 câu hỏi tiếng Việt thật, chia theo nhóm: tra cứu đơn, tra cứu kết hợp bộ lọc, câu hỏi mơ hồ, câu hỏi ngoài phạm vi, câu cố tình dụ bịa, thủ tục/biểu mẫu, hỏi phương pháp (Cronbach, EFA…).
- Mỗi câu có đáp án chuẩn là mã bản ghi mong đợi hoặc "không có dữ liệu".
- Chỉ số: **gọi đúng hàm** (%), **mã bản ghi bịa** (%, mục tiêu 0), **JSON hợp lệ** (%), độ trễ đến chữ đầu tiên, chi phí/câu, tỷ lệ `content` rỗng do hết ngân sách suy luận.
- Chạy cho 5 đến 6 mô hình ở ba nhóm giá. Ước tính 100 câu × 6 mô hình × khoảng 4.000 token ≈ 2,4 triệu token, vài USD với các mô hình nhóm Nhanh và Cân bằng. Kết quả quyết định mô hình mặc định và bảng dự phòng, không dùng cảm tính.

### 8.2 Lộ trình

| Giai đoạn | Nội dung | Điều kiện hoàn thành |
|---|---|---|
| **0. Chuẩn bị** | Xác định kho mã đang triển khai; rebase; hỏi Oxion các điểm ở 3.2 và 7.2; xin khoá thử | Có khoá thử; `GET /v1/models` chạy được; biết có embedding hay không |
| **1. Nền tảng** | N1–N6; sửa điểm yếu 5, 6, 7 | Chat chạy được trên Oxion, có stream, có dự phòng, khoá lưu mã hoá, test của CI xanh, trang cài đặt hoạt động |
| **2. Trợ lý thông minh** | F1, F2, F3, F4, F14 | Bộ đánh giá: mã bản ghi bịa = 0; gọi đúng hàm ≥ 90% ở mô hình mặc định |
| **3. Công cụ phân tích** | F5 (nếu có embedding, nếu không FTS5), F6, F7, F8, F9, F17 | Mỗi tính năng có chế độ ẩn danh/tối thiểu hoá dữ liệu và kiểm tra trích dẫn nguyên văn (F8) |
| **4. Viết và phản biện** | F10, F11, F12, F13 | Trích dẫn chỉ từ nguồn xác thực; đánh dấu rõ mục do AI tạo |
| **5. Bộ máy nặng** | F15, F16 | Báo cáo đạo văn nêu rõ phạm vi đối chiếu |

---

## 9. Quyết định cần xác nhận

1. **Kho mã nào là bản đang chạy hi.hue.vn?** Không xác định được thì không nên bắt đầu code.
2. **Chế độ khoá:** chỉ khoá của Trường, hay thêm khoá cá nhân (đề xuất: cả hai)?
3. **Trường chấp nhận nhà cung cấp bên ngoài** cho mức dữ liệu nào (C0/C1 có; C2 có hay không)? Đây là quyết định chính sách, không phải kỹ thuật.
4. **Ngân sách tháng** để đặt hạn mức token, và có chọn gói Unlimited hay trả theo token?
5. **Có giữ Anthropic làm nhà cung cấp song song** (đề xuất giữ làm dự phòng) hay chuyển hẳn sang Oxion?

---

## Phụ lục: nguồn tham khảo

- hi.hue.vn: `/`, `/tools`, `/huong-dan` (đọc 25/10/2026).
- Oxion AI: `oxionai.com`, `/pricing`, `/models`, `/docs`, `/docs/getting-started`, `/docs/authentication`, `/docs/chat-completions`, `/docs/models`, `/docs/reasoning` (đọc 25/10/2026). `/docs/embeddings`: không đọc được (hết thời gian chờ).
- Mã nguồn: `hce-research/lib/assistant.ts`, `app/api/chat/route.ts`, `lib/registry.ts`, `lib/db.ts`, `lib/store.ts`, `lib/stats.ts`, `lib/auth.ts`, `lib/source.ts`, `lib/jobs.ts`, `components/Md.tsx`, `components/SurveyLab.tsx`, `app/chat/page.tsx`, `.github/workflows/ci.yml`; tài liệu `docs/PHAN-TICH-NEU-RESEARCH.md`, `docs/BO-SUNG-TU-TAI-LIEU.md`, `README.md`.
- Giá, danh sách mô hình và hạn mức của Oxion có thể đổi bất cứ lúc nào; đối chiếu lại với `GET /v1/models` và Dashboard trước khi cấu hình.
