import { PaperWriter } from "@/components/PaperWriter";

export default function WritiumPage() {
  return (
    <div className="hs-content">
      <div className="hs-titlebar">
        <div className="min-w-0 flex-1">
          <h1 className="hs-title">Viết nghiên cứu</h1>
          <p className="hs-desc">
            Giai đoạn 5. Viết &amp; phản biện — Từ ý tưởng, dữ liệu và kết quả thực nghiệm đến bản thảo bài báo: đa tác tử AI lập dàn ý, tìm tài liệu đã kiểm chứng, viết, tự phản biện và xuất LaTeX/PDF theo mẫu tạp chí.
          </p>
        </div>
        <a className="hs-back" href="/tools">← Kho công cụ</a>
      </div>
      <PaperWriter />
    </div>
  );
}
