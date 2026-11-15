# PO-Studio — Viết bài báo khoa học tự động (dựa trên PaperOrchestra)

PO-Studio biến **ý tưởng + dữ liệu + phương pháp + kết quả thực nghiệm** thành **bản thảo LaTeX/PDF hoàn chỉnh theo mẫu tạp chí**, bằng một đội tác tử AI kế thừa kiến trúc của
[google-research/paper-orchestra](https://github.com/google-research/paper-orchestra) (Song et al., 2026, arXiv:2604.05018).

```
raw materials ─► Outline ─► Plotting ─► Literature (OpenAlex/S2, đã kiểm chứng) ─► Intro + Related Work
             ─► Section writing ─► Compile/auto-fix ─► Peer-review ⇄ Revision (accept/revert)
             ─► Visual format check ─► Integrity report ─► submission_package.zip
```

## Khác biệt so với paper-orchestra gốc

| | paper-orchestra | PO-Studio |
|---|---|---|
| LLM | Gemini / OpenAI | **Claude** (mặc định), Gemini, OpenAI, `mock` để test |
| Tìm tài liệu | Gemini + Google Search grounding (có thể ra tên bài không tồn tại, rồi lọc qua S2) | LLM chỉ **chọn trong bản ghi thật** của OpenAlex (+ Semantic Scholar nếu có key) và file `.bib` của tác giả → không thể bịa tài liệu |
| Mục tiêu | Hội nghị ML ẩn danh (CVPR, ICLR) | + Tạp chí quốc tế (author-year), Elsevier, IEEE, **tạp chí tiếng Việt (XeLaTeX)**; có/không ẩn danh; khai báo tác giả, tuyên bố, khai báo dùng AI |
| Ràng buộc nội dung | "No-leakage" phục vụ benchmark | Quy tắc liêm chính nghiên cứu: không bịa số liệu, chỉ trích dẫn từ thư viện đã xác minh, không tự nhận vượt trội nếu không có trong log |
| Đầu vào | `idea.md` + `experimental_log.md` | + form web, CSV/XLSX dữ liệu (tự thống kê mô tả), bảng kết quả (giữ nguyên giá trị), hình + chú thích, `.bib`, ghi chú PDF/DOCX |
| Đầu ra | PDF | PDF + LaTeX + bib + hình + **báo cáo kiểm tra toàn vẹn** (khoá trích dẫn, số trong bảng ↔ log, hình, nhãn, placeholder) + điểm phản biện |
| Vận hành | CLI + Streamlit demo | CLI + **web FastAPI** (hàng đợi job, tiến trình trực tiếp, chạy tiếp khi lỗi), Docker |

## Cài đặt

```bash
git clone <repo> po-studio && cd po-studio
pip install -e .                    # hoặc: pip install -r requirements.txt
# LaTeX: TeX Live (pdflatex, xelatex, bibtex); cho Elsevier/IEEE cần thêm texlive-publishers
cp .env.example .env                # điền ANTHROPIC_API_KEY (hoặc GEMINI/OPENAI), OPENALEX_MAILTO
postudio templates                  # liệt kê mẫu & kiểm tra lớp LaTeX còn thiếu
```

## Dùng bằng dòng lệnh

```bash
# 1) Tạo raw_materials từ form JSON (cùng cấu trúc với form web) + tệp
postudio materials --form examples/demo_forecasting/form.json --out runs/p1/raw_materials \
                   --data btc.csv --results results.xlsx --figures fig1.png::"Forecast vs actual" --references my.bib

# 2) Chạy toàn bộ pipeline
export ANTHROPIC_API_KEY=...
postudio run --materials runs/p1/raw_materials --out runs/p1 --template journal_generic \
             --writer-model claude-opus-5-5 --reviewer-model claude-sonnet-5-5 \
             --venue "Expert Systems with Applications" --authors authors.json --cutoff 2026-10

# Bị gián đoạn? chạy lại đúng lệnh trên — pipeline tiếp tục từ bước dở (status.json). Dùng --fresh để làm lại.

# Công cụ rời
postudio lit-search "variational mode decomposition LSTM bitcoin" --cutoff 2026-10 -n 10 [--bib]
postudio verify-bib my.bib          # đối chiếu từng mục với OpenAlex
postudio check runs/p1/final/paper.tex --bib runs/p1/final/references.bib --materials runs/p1/raw_materials
```

Kết quả trong `runs/p1/`: `final/` (paper.tex, paper.pdf, references.bib, figures/), `report.md`, `peer_reviews/`, `literature/citation_map.json`, `submission_package.zip`.

## Website

```bash
uvicorn web.app:app --port 8000            # mở http://localhost:8000
# hoặc
docker compose up -d --build               # TeX Live đầy đủ + Elsevier/IEEE + tiếng Việt
```

Form 4 bước (song ngữ Việt/Anh): (1) tạp chí & tác giả, (2) ý tưởng & phương pháp, (3) dữ liệu & kết quả, (4) mô hình AI & gửi. Người dùng có thể dán khoá API riêng (chỉ giữ trong bộ nhớ của job) hoặc dùng khoá của máy chủ khi nhập đúng `POSTUDIO_ACCESS_CODE`.

API: `GET /api/config`, `POST /api/jobs` (multipart: `payload` JSON + `data_files`, `result_files`, `figure_files`, `reference_files`, `note_files`), `GET /api/jobs/{id}`, `GET /api/jobs/{id}/download/{pdf|zip|tex|bib|report|log|outline}`, `POST /api/jobs/{id}/resume`.

**Lưu ý triển khai:** tác tử vẽ hình chạy mã Python do LLM sinh ra → luôn chạy trong Docker (người dùng không đặc quyền, giới hạn RAM). Không đặt website tĩnh (GitHub Pages) làm backend; cần VPS/hosting chạy được Docker (ví dụ máy chủ của hi.hue.vn), có thể nhúng giao diện vào trang tĩnh và trỏ `fetch` sang API.

## Mẫu định dạng

`journal_generic` (quốc tế, author-year), `journal_vi` (tiếng Việt, XeLaTeX), `elsevier` (elsarticle), `ieee_journal` (IEEEtran), `cvpr2025`, `iclr2025` (từ paper-orchestra). Thêm mẫu mới: tạo thư mục `templates/<tên>/` gồm `template.tex` (giữ các marker `%%%%%%%%% INTRODUCTION %%%%%%%%%` …, placeholder `%%TITLE%%`, `%%AUTHORS%%`, `%%KEYWORDS%%`, `%%DECLARATIONS%%`), `guidelines.md`, `meta.json`.

## Chi phí ước tính

Một bài ~10 trang, 50–60 tài liệu, 2 vòng phản biện: khoảng 60–120 lời gọi LLM, ~0,6–1,2 triệu token vào / 80–150 nghìn token ra (phần lớn ở bước chọn tài liệu và các vòng viết lại toàn văn). Dùng mô hình rẻ hơn cho `--reviewer-model`/`--selector-model` để giảm chi phí.

## Liêm chính học thuật

Hệ thống không chạy thí nghiệm và không được phép tạo số liệu. Bản thảo là **bản nháp có AI hỗ trợ**: tác giả phải đọc, kiểm chứng từng trích dẫn và con số, chỉnh sửa văn phong, và khai báo việc dùng AI theo chính sách của tạp chí (mục *Use of generative AI* được chèn sẵn).

## Kiểm thử

```bash
pytest -q        # chạy toàn pipeline offline với LLM giả lập + tài liệu giả (fixture) trên 3 mẫu
```

## Giấy phép

Apache-2.0. Prompt và logic tác tử được chuyển thể từ google-research/paper-orchestra (Copyright 2026 Google LLC, Apache-2.0; xem `LICENSE-paper-orchestra`). Mẫu CVPR/ICLR giữ nguyên từ repo gốc.
