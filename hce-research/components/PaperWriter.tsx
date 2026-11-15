"use client";

// Mục "Viết bài báo" (/tools/writium): biểu mẫu 4 bước → PO-Studio (đa tác tử, dựa trên google-research/paper-orchestra)
// → theo dõi tiến trình → tải PDF/LaTeX/gói nộp bài. Giao diện dùng lớp chung của hệ thống (btn, card, input, chip).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, BookOpenCheck, Check, CheckCircle2, ChevronLeft, ChevronRight, Download, ExternalLink, FileText,
  FlaskConical, Info, KeyRound, ListTree, Loader2, PenLine, Plus, RotateCw, ScanSearch, ShieldCheck, Sparkles,
  Trash2, Upload, X,
} from "lucide-react";

// ---------------------------------------------------------------- kiểu dữ liệu
type TemplateMeta = { name: string; available?: boolean; missing?: string[]; anonymous?: boolean; language?: string; citation_style?: string; venue_type?: string };
type Config = {
  enabled: boolean;
  online?: boolean;
  loggedIn: boolean;
  serverKey: boolean;
  limits: { guest: number; user: number; serverKey: number };
  maxUploadMb: number;
  templates?: Record<string, TemplateMeta>;
  models?: Record<string, string[]>;
  serverKeys?: Record<string, boolean>;
};
type Author = { name: string; affiliation: string; email: string; corresponding: boolean };
type Draft = {
  template: string; venue_name: string; language: string; anonymous: boolean;
  field: string; title: string; keywords: string;
  authors: Author[];
  funding: string; conflicts: string; data_availability: string; acknowledgements: string;
  problem: string; research_questions: string; contributions: string; method: string; related_notes: string;
  data_description: string; experimental_setup: string; results: string; ablations: string; discussion_notes: string; limitations: string;
  writer_model: string; reviewer_model: string; cutoff: string; mailto: string;
  refine_rounds: number; max_papers: number; use_plotting: boolean; format_check: boolean;
};
type JobRef = { id: string; title: string; createdAt: number };
type JobStatus = {
  state: "queued" | "running" | "done" | "failed";
  stage: string | null;
  stages: Record<string, "pending" | "running" | "done" | "skipped" | "failed">;
  messages?: string[];
  error?: string;
  review?: Record<string, unknown> & { Weaknesses?: string[] };
  report?: { ok: boolean; errors: string[]; warnings: string[]; stats?: Record<string, unknown> };
  usage?: { calls: number; input_tokens: number; output_tokens: number };
  elapsed_sec?: number;
};
type Files = { data_files: File[]; result_files: File[]; figure_files: File[]; reference_files: File[]; note_files: File[] };

// ---------------------------------------------------------------- hằng số
const DRAFT_KEY = "writium:draft:v1";
const JOBS_KEY = "writium:jobs:v1";

const FALLBACK_TEMPLATES: Record<string, TemplateMeta> = {
  journal_generic: { name: "International journal (generic, author-year, single column)", language: "en" },
  journal_vi: { name: "Tạp chí trong nước (tiếng Việt, XeLaTeX, APA/author-year)", language: "vi" },
  elsevier: { name: "Elsevier journal (elsarticle, author-year)", language: "en" },
  ieee_journal: { name: "IEEE journal (IEEEtran, numeric)", language: "en" },
  cvpr2025: { name: "CVPR 2025 (conference, double-blind)", language: "en", anonymous: true },
  iclr2025: { name: "ICLR 2025 (conference, double-blind)", language: "en", anonymous: true },
};
const FALLBACK_MODELS: Record<string, string[]> = {
  anthropic: ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"],
  gemini: ["gemini-3.1-pro-preview", "gemini-3-flash-preview"],
  openai: ["gpt-5", "gpt-5-mini"],
};
const PROVIDER_NAME: Record<string, string> = { anthropic: "Anthropic (Claude)", gemini: "Google (Gemini)", openai: "OpenAI (GPT)", mock: "Mô phỏng (chạy thử)" };
const KEY_HINT: Record<string, string> = { anthropic: "sk-ant-…", gemini: "AIza…", openai: "sk-…" };

const STAGE_LABEL: Record<string, string> = {
  prepare: "Chuẩn bị mẫu", outline: "Lập dàn ý", plotting: "Vẽ hình", literature: "Tìm tài liệu", sections: "Viết các mục",
  compile: "Biên dịch LaTeX", refine: "Phản biện ⇄ sửa", format: "Kiểm tra trình bày", checks: "Kiểm tra liêm chính", package: "Đóng gói",
};
const STAGES = Object.keys(STAGE_LABEL);
const STAT_LABEL: Record<string, string> = {
  pages: "Số trang", approx_words: "Số từ (ước tính)", abstract_words: "Số từ tóm tắt", citations_used: "Tài liệu được trích",
  bib_entries: "Mục BibTeX", figures_included: "Hình", tables: "Bảng",
};

const STEPS = [
  { n: 1, label: "Tạp chí & tác giả" },
  { n: 2, label: "Ý tưởng & phương pháp" },
  { n: 3, label: "Dữ liệu & kết quả" },
  { n: 4, label: "Cấu hình AI & gửi" },
] as const;

const AGENTS = [
  { icon: ListTree, name: "Lập dàn ý", en: "Outline agent", desc: "Đọc ý tưởng, nhật ký thực nghiệm và hướng dẫn của tạp chí → dàn ý, kế hoạch hình và kế hoạch tìm tài liệu." },
  { icon: FlaskConical, name: "Vẽ hình", en: "Plotting agent", desc: "Vẽ biểu đồ chỉ từ số liệu có trong kết quả của bạn, tự xem lại và sửa." },
  { icon: BookOpenCheck, name: "Tìm tài liệu", en: "Literature agent", desc: "Tìm trên OpenAlex/Semantic Scholar; AI chỉ được chọn trong bản ghi thật có DOI, rồi tạo BibTeX." },
  { icon: PenLine, name: "Viết các mục", en: "Section writing agent", desc: "Giới thiệu, tổng quan, phương pháp, kết quả & thảo luận, kết luận, tóm tắt theo mẫu tạp chí." },
  { icon: RotateCw, name: "Phản biện ⇄ chỉnh sửa", en: "Content refinement", desc: "Phản biện mô phỏng chấm điểm; bản sửa chỉ được giữ khi điểm tăng, nếu không thì hoàn tác." },
  { icon: ScanSearch, name: "Trình bày & liêm chính", en: "Format + integrity", desc: "Soát bố cục PDF, đối chiếu từng số trong bảng với kết quả, khoá trích dẫn, hình, nhãn; đóng gói nộp bài." },
];

const EMPTY: Draft = {
  template: "journal_generic", venue_name: "", language: "", anonymous: false,
  field: "", title: "", keywords: "",
  authors: [{ name: "", affiliation: "Trường Đại học Kinh tế, Đại học Huế", email: "", corresponding: true }],
  funding: "", conflicts: "", data_availability: "", acknowledgements: "",
  problem: "", research_questions: "", contributions: "", method: "", related_notes: "",
  data_description: "", experimental_setup: "", results: "", ablations: "", discussion_notes: "", limitations: "",
  writer_model: "claude-opus-5-5", reviewer_model: "claude-sonnet-5-5", cutoff: new Date().toISOString().slice(0, 7), mailto: "",
  refine_rounds: 2, max_papers: 60, use_plotting: true, format_check: true,
};

const DEMO: Partial<Draft> = {
  venue_name: "Expert Systems with Applications",
  field: "financial time-series forecasting",
  keywords: "cryptocurrency; Bitcoin; deep learning; LSTM; variational mode decomposition",
  problem: "[DỮ LIỆU MINH HOẠ — thay bằng nghiên cứu của bạn] Bitcoin prices are highly volatile and non-stationary, which degrades single-model forecasters.",
  research_questions: "RQ1: Does VMD decomposition before LSTM forecasting reduce error versus ARIMA and a plain LSTM? RQ2: Is the improvement significant (Diebold–Mariano)?",
  contributions: "1) A VMD-LSTM hybrid for daily Bitcoin prices. 2) Comparison with ARIMA and LSTM at 1- and 7-day horizons. 3) Significance testing.",
  method: "Daily closes are decomposed by VMD into K=5 modes; each mode is forecast by an LSTM (2 layers, 64 units, look-back 30, Adam lr=0.001, early stopping); forecasts are summed. Baselines: ARIMA (AIC) and a single LSTM.",
  data_description: "Daily BTC-USD close, 2018-01-01 to 2024-12-31 (2557 obs.), chronological 80/20 split, min-max scaling fitted on training data.",
  experimental_setup: "RMSE, MAE, MAPE on the test set; horizons 1 and 7 days (direct); mean of 5 seeds; Diebold–Mariano test (squared loss).",
  results:
    "SYNTHETIC DEMO NUMBERS — NOT REAL RESULTS\n| Model | Horizon | RMSE | MAE | MAPE |\n|---|---|---|---|---|\n| ARIMA | 1 | 1523.4 | 1011.7 | 2.91 |\n| LSTM | 1 | 1398.2 | 952.3 | 2.71 |\n| VMD-LSTM | 1 | 1104.6 | 768.9 | 2.18 |\n| ARIMA | 7 | 3876.5 | 2754.1 | 7.62 |\n| LSTM | 7 | 3512.8 | 2490.6 | 6.95 |\n| VMD-LSTM | 7 | 2987.3 | 2101.4 | 5.88 |\nDM (VMD-LSTM vs LSTM): -3.42 (p=0.0007) at h=1; -2.87 (p=0.0042) at h=7.",
  ablations: "K=3 RMSE 1236.8; K=5 RMSE 1104.6; K=7 RMSE 1129.5 (h=1).",
  discussion_notes: "Decomposition separates trend from high-frequency noise; errors grow with horizon.",
  limitations: "Single asset; no exogenous variables; no transaction costs.",
  authors: [{ name: "Tác giả minh hoạ", affiliation: "Trường Đại học Kinh tế, Đại học Huế", email: "", corresponding: true }],
};

// ---------------------------------------------------------------- tiện ích
const providerOf = (m: string) =>
  m.startsWith("mock") ? "mock" : m.startsWith("claude") ? "anthropic" : m.startsWith("gemini") ? "gemini" : "openai";

function readLocal<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    return v ? (JSON.parse(v) as T) : fallback;
  } catch {
    return fallback;
  }
}
function writeLocal(key: string, v: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(v));
  } catch {}
}

/** Bảng dán từ Excel/Sheets (cột cách nhau bằng Tab) → bảng Markdown, giữ nguyên giá trị. */
function tsvToMarkdown(text: string): string | null {
  const rows = text.replace(/\r/g, "").split("\n").filter((r) => r.trim() !== "");
  if (rows.length < 2 || !rows.every((r) => r.includes("\t"))) return null;
  const cells = rows.map((r) => r.split("\t").map((c) => c.trim().replace(/\|/g, "\\|")));
  const w = Math.max(...cells.map((c) => c.length));
  const line = (c: string[]) => `| ${Array.from({ length: w }, (_, i) => c[i] ?? "").join(" | ")} |`;
  return [line(cells[0]), `|${" --- |".repeat(w)}`, ...cells.slice(1).map(line)].join("\n");
}

const fmtTime = (t: number) => new Date(t).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
const fmtSize = (b: number) => (b > 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);

// ---------------------------------------------------------------- thành phần nhỏ
function Field({ label, hint, req, children, className = "" }: { label: string; hint?: string; req?: boolean; children: React.ReactNode; className?: string }) {
  return (
    <label className={`block space-y-1 ${className}`}>
      <span className="text-sm font-medium">
        {label}
        {req && <span className="text-[var(--danger)]"> *</span>}
        {hint && <span className="font-normal text-muted-foreground"> — {hint}</span>}
      </span>
      {children}
    </label>
  );
}

function FilePick({ label, hint, accept, files, onChange, multiple = true }: { label: string; hint?: string; accept: string; files: File[]; onChange: (f: File[]) => void; multiple?: boolean }) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div className="space-y-1.5">
      <span className="text-sm font-medium">{label}</span>
      <button
        type="button"
        onClick={() => ref.current?.click()}
        className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-border px-3 py-3 text-xs text-muted-foreground hover:border-primary hover:text-primary"
      >
        <Upload size={14} /> {hint ?? "Chọn tệp"}
      </button>
      <input
        ref={ref}
        type="file"
        className="hidden"
        accept={accept}
        multiple={multiple}
        onChange={(e) => {
          const add = Array.from(e.target.files ?? []);
          const names = new Set(files.map((f) => f.name));
          onChange([...files, ...add.filter((f) => !names.has(f.name))]);
          e.target.value = "";
        }}
      />
      {files.length > 0 && (
        <ul className="space-y-1">
          {files.map((f) => (
            <li key={f.name} className="flex items-center gap-2 rounded-md bg-muted px-2 py-1 text-xs">
              <FileText size={13} className="shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1 truncate">{f.name}</span>
              <span className="text-muted-foreground">{fmtSize(f.size)}</span>
              <button type="button" aria-label={`Bỏ ${f.name}`} onClick={() => onChange(files.filter((x) => x !== f))} className="text-muted-foreground hover:text-foreground">
                <X size={13} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Note({ tone = "info", children }: { tone?: "info" | "warn" | "ok"; children: React.ReactNode }) {
  const cls =
    tone === "warn"
      ? "border-accent/50 bg-accent/10"
      : tone === "ok"
        ? "border-emerald-600/30 bg-emerald-600/5"
        : "border-primary/20 bg-primary/5";
  const Ico = tone === "warn" ? AlertTriangle : tone === "ok" ? CheckCircle2 : Info;
  return (
    <div className={`flex gap-2 rounded-lg border px-3 py-2 text-sm ${cls}`}>
      <Ico size={16} className={`mt-0.5 shrink-0 ${tone === "ok" ? "text-emerald-700 dark:text-emerald-400" : tone === "warn" ? "text-accent" : "text-primary"}`} />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

// ---------------------------------------------------------------- thành phần chính
export function PaperWriter() {
  const [cfg, setCfg] = useState<Config | null>(null);
  const [d, setD] = useState<Draft>(EMPTY);
  const [loaded, setLoaded] = useState(false);
  const [tab, setTab] = useState<number | "jobs">(1);
  const [files, setFiles] = useState<Files>({ data_files: [], result_files: [], figure_files: [], reference_files: [], note_files: [] });
  const [captions, setCaptions] = useState<Record<string, string>>({});
  const [apiKey, setApiKey] = useState("");
  const [keyMode, setKeyMode] = useState<"own" | "server">("own");
  const [submitting, setSubmitting] = useState(false);
  const [submitErr, setSubmitErr] = useState("");
  const [jobs, setJobs] = useState<JobRef[]>([]);
  const [activeJob, setActiveJob] = useState<string | null>(null);

  // nạp cấu hình, bản nháp, danh sách bản thảo
  useEffect(() => {
    setD({ ...EMPTY, ...readLocal<Partial<Draft>>(DRAFT_KEY, {}) });
    const local = readLocal<JobRef[]>(JOBS_KEY, []);
    setJobs(local);
    setLoaded(true);
    fetch("/api/paper/config")
      .then((r) => r.json())
      .then((c: Config) => {
        setCfg(c);
        if (c.serverKey && c.loggedIn) setKeyMode("server");
      })
      .catch(() => setCfg({ enabled: false, loggedIn: false, serverKey: false, limits: { guest: 0, user: 0, serverKey: 0 }, maxUploadMb: 40 }));
    fetch("/api/paper/jobs")
      .then((r) => r.json())
      .then((j: { jobs?: JobRef[] }) => {
        if (!j.jobs?.length) return;
        setJobs((cur) => {
          const ids = new Set(cur.map((x) => x.id));
          return [...cur, ...j.jobs!.filter((x) => !ids.has(x.id))].sort((a, b) => b.createdAt - a.createdAt);
        });
      })
      .catch(() => {});
    const m = location.hash.match(/job=([a-f0-9]{12})/);
    if (m) {
      setActiveJob(m[1]);
      setTab("jobs");
    }
  }, []);

  // lưu nháp (bỏ qua lần nạp đầu)
  useEffect(() => {
    if (loaded) writeLocal(DRAFT_KEY, d);
  }, [d, loaded]);

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((p) => ({ ...p, [k]: v }));
  const bind = (k: keyof Draft) => ({
    value: String(d[k] ?? ""),
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => set(k, e.target.value as never),
  });

  const templates = cfg?.templates ?? FALLBACK_TEMPLATES;
  const models = cfg?.models ?? FALLBACK_MODELS;
  const tmpl = templates[d.template] ?? FALLBACK_TEMPLATES.journal_generic;
  const provider = providerOf(d.writer_model);
  const ready = Boolean(cfg?.enabled && cfg.online);
  const usingServerKey = keyMode === "server" && Boolean(cfg?.serverKey && cfg.loggedIn) && provider !== "mock";

  const checks = useMemo(() => {
    const filled = (s: string) => s.trim().length > 0;
    return [
      { ok: filled(d.method), req: true, label: "Phương pháp", step: 2 },
      { ok: filled(d.results) || files.result_files.length > 0, req: true, label: "Kết quả thực nghiệm", step: 3 },
      { ok: filled(d.problem), label: "Vấn đề & động lực", step: 2 },
      { ok: filled(d.contributions), label: "Đóng góp dự kiến", step: 2 },
      { ok: filled(d.data_description) || files.data_files.length > 0, label: "Mô tả dữ liệu", step: 3 },
      { ok: filled(d.experimental_setup), label: "Thiết lập thực nghiệm", step: 3 },
      { ok: d.anonymous || d.authors.some((a) => a.name.trim()), label: "Tác giả", step: 1 },
      { ok: filled(d.field), label: "Lĩnh vực nghiên cứu", step: 1 },
    ];
  }, [d, files.result_files.length, files.data_files.length]);
  const requiredOk = checks.filter((c) => c.req).every((c) => c.ok);
  const score = checks.filter((c) => c.ok).length;

  const totalBytes = Object.values(files).flat().reduce((s, f) => s + f.size, 0);

  const go = (n: number | "jobs") => {
    setTab(n);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const openJob = useCallback((id: string) => {
    setActiveJob(id);
    setTab("jobs");
    history.replaceState(null, "", `#job=${id}`);
  }, []);

  const removeJob = (id: string) => {
    const next = jobs.filter((j) => j.id !== id);
    setJobs(next);
    writeLocal(JOBS_KEY, next);
    if (activeJob === id) {
      setActiveJob(null);
      history.replaceState(null, "", location.pathname);
    }
  };

  async function submit() {
    setSubmitErr("");
    if (!requiredOk) {
      setSubmitErr("Vui lòng nhập phương pháp (bước 2) và kết quả thực nghiệm (bước 3, hoặc tải tệp kết quả).");
      return;
    }
    if (!usingServerKey && provider !== "mock" && !apiKey.trim()) {
      setSubmitErr(cfg?.serverKey && !cfg.loggedIn ? "Hãy nhập khoá API, hoặc đăng nhập để dùng khoá AI của Trường." : "Hãy nhập khoá API của nhà cung cấp đã chọn.");
      return;
    }
    if (cfg && totalBytes > cfg.maxUploadMb * 1048576) {
      setSubmitErr(`Tổng dung lượng tệp (${fmtSize(totalBytes)}) vượt giới hạn ${cfg.maxUploadMb} MB.`);
      return;
    }
    const form = Object.fromEntries(
      (["field", "title", "keywords", "problem", "research_questions", "contributions", "method", "related_notes", "data_description",
        "experimental_setup", "results", "ablations", "discussion_notes", "limitations"] as const).map((k) => [k, d[k]]),
    );
    const figure_captions: Record<string, string> = {};
    for (const f of files.figure_files) figure_captions[f.name.replace(/[^A-Za-z0-9._-]/g, "_").slice(0, 120)] = captions[f.name] ?? "";
    const payload = {
      form,
      authors: d.authors.filter((a) => a.name.trim()),
      figure_captions,
      declarations: { funding: d.funding, conflicts: d.conflicts, data_availability: d.data_availability, acknowledgements: d.acknowledgements },
      options: {
        template: d.template, venue_name: d.venue_name, language: d.language, anonymous: d.anonymous,
        writer_model: d.writer_model, reviewer_model: d.reviewer_model, cutoff: d.cutoff, mailto: d.mailto,
        refine_rounds: d.refine_rounds, max_papers: d.max_papers, use_plotting: d.use_plotting, format_check: d.format_check,
      },
    };
    const fd = new FormData();
    fd.set("payload", JSON.stringify(payload));
    if (!usingServerKey && apiKey.trim()) fd.set("api_key", apiKey.trim());
    for (const [k, list] of Object.entries(files)) for (const f of list as File[]) fd.append(k, f, f.name);

    setSubmitting(true);
    try {
      const r = await fetch("/api/paper/jobs", { method: "POST", body: fd });
      const j = (await r.json()) as { job_id?: string; error?: string };
      if (!r.ok || !j.job_id) throw new Error(j.error || `Lỗi ${r.status}`);
      const ref: JobRef = { id: j.job_id, title: d.title.trim() || d.keywords.split(";")[0]?.trim() || "Bản thảo chưa đặt tên", createdAt: Date.now() };
      const next = [ref, ...jobs.filter((x) => x.id !== ref.id)];
      setJobs(next);
      writeLocal(JOBS_KEY, next);
      setApiKey("");
      openJob(j.job_id);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      setSubmitErr(e instanceof Error ? e.message : "Không gửi được.");
    } finally {
      setSubmitting(false);
    }
  }

  const tabCls = (on: boolean) =>
    `-mb-px flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${on ? "border-accent text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`;
  const stepIndex = typeof tab === "number" ? tab : 0;

  // ------------------------------------------------------------ render
  return (
    <div className="space-y-4">
      {/* thanh trạng thái */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground">
          Dựa trên <a className="underline hover:text-primary" href="https://github.com/google-research/paper-orchestra" target="_blank" rel="noreferrer">PaperOrchestra</a> (Google Research) · bản nháp lưu trên trình duyệt
        </span>
        <span className={`chip ${ready ? "text-emerald-700 dark:text-emerald-400" : "text-muted-foreground"}`}>
          <span className={`size-1.5 rounded-full ${ready ? "bg-emerald-600" : cfg === null ? "bg-muted-foreground" : "bg-accent"}`} />
          {cfg === null ? "Đang kiểm tra máy chủ…" : ready ? "Máy chủ viết bài sẵn sàng" : cfg.enabled ? "Máy chủ viết bài tạm ngưng" : "Máy chủ viết bài chưa kết nối"}
        </span>
        <div className="ml-auto flex flex-wrap gap-2">
          <button type="button" className="btn btn-outline py-1.5" onClick={() => setD((p) => ({ ...p, ...DEMO }))} title="Điền dữ liệu minh hoạ (số liệu giả) để xem thử luồng">
            <Sparkles size={15} /> Nạp ví dụ
          </button>
          <button
            type="button"
            className="btn btn-outline py-1.5"
            onClick={() => {
              if (confirm("Xoá toàn bộ nội dung đang nhập?")) {
                setD(EMPTY);
                setFiles({ data_files: [], result_files: [], figure_files: [], reference_files: [], note_files: [] });
              }
            }}
          >
            <Trash2 size={15} /> Xoá nháp
          </button>
        </div>
      </div>

      {/* tab */}
      <div className="flex gap-1 overflow-x-auto border-b border-border">
        {STEPS.map((s) => (
          <button key={s.n} type="button" className={tabCls(tab === s.n)} onClick={() => go(s.n)}>
            <span className={`grid size-5 place-items-center rounded-full text-[11px] ${tab === s.n ? "bg-primary text-primary-foreground" : "bg-muted"}`}>{s.n}</span>
            {s.label}
          </button>
        ))}
        <button type="button" className={tabCls(tab === "jobs")} onClick={() => go("jobs")}>
          <FileText size={15} /> Bản thảo của tôi
          {jobs.length > 0 && <span className="chip py-0">{jobs.length}</span>}
        </button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
        {/* cột chính */}
        <div className="min-w-0 space-y-4">
          {tab === 1 && (
            <section className="card space-y-4 border-t-4 border-t-primary p-4 sm:p-5">
              <header>
                <h2 className="font-semibold">Tạp chí & tác giả</h2>
                <p className="text-sm text-muted-foreground">Chọn mẫu định dạng, ngôn ngữ bài viết và thông tin tác giả.</p>
              </header>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Mẫu định dạng">
                  <select
                    className="input"
                    value={d.template}
                    onChange={(e) => {
                      const k = e.target.value;
                      setD((p) => ({ ...p, template: k, anonymous: Boolean(templates[k]?.anonymous) }));
                    }}
                  >
                    {Object.entries(templates).map(([k, m]) => (
                      <option key={k} value={k} disabled={m.available === false}>
                        {m.name}
                        {m.available === false ? ` (máy chủ thiếu ${m.missing?.join(", ")})` : ""}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Tạp chí / hội nghị mục tiêu">
                  <input className="input" placeholder="VD: Expert Systems with Applications" {...bind("venue_name")} />
                </Field>
                <Field label="Ngôn ngữ bài viết">
                  <select className="input" {...bind("language")}>
                    <option value="">Theo mẫu ({tmpl.language === "vi" ? "tiếng Việt" : "tiếng Anh"})</option>
                    <option value="en">Tiếng Anh</option>
                    <option value="vi">Tiếng Việt</option>
                  </select>
                </Field>
                <Field label="Lĩnh vực nghiên cứu">
                  <input className="input" placeholder="VD: dự báo chuỗi thời gian tài chính" {...bind("field")} />
                </Field>
                <Field label="Tiêu đề" hint="để trống để AI đề xuất">
                  <input className="input" {...bind("title")} />
                </Field>
                <Field label="Từ khoá" hint="cách nhau bằng dấu ;">
                  <input className="input" placeholder="deep learning; Bitcoin; forecasting" {...bind("keywords")} />
                </Field>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={d.anonymous} onChange={(e) => set("anonymous", e.target.checked)} /> Ẩn danh (phản biện kín hai chiều — không in tên tác giả)
              </label>

              <div className="space-y-2">
                <div className="text-sm font-medium">Tác giả</div>
                {d.authors.map((a, i) => (
                  <div key={i} className="grid gap-2 rounded-lg border border-border p-2 sm:grid-cols-[1fr_1.4fr_1fr_auto_auto] sm:items-center sm:border-0 sm:p-0">
                    {(["name", "affiliation", "email"] as const).map((k) => (
                      <input
                        key={k}
                        className="input"
                        type={k === "email" ? "email" : "text"}
                        placeholder={k === "name" ? "Họ tên" : k === "affiliation" ? "Đơn vị" : "Email"}
                        value={a[k]}
                        onChange={(e) => set("authors", d.authors.map((x, j) => (j === i ? { ...x, [k]: e.target.value } : x)))}
                      />
                    ))}
                    <label className="flex items-center gap-1 whitespace-nowrap text-xs">
                      <input type="radio" name="corr" checked={a.corresponding} onChange={() => set("authors", d.authors.map((x, j) => ({ ...x, corresponding: j === i })))} /> Liên hệ
                    </label>
                    <button type="button" className="btn btn-outline px-2 py-1.5" aria-label="Xoá tác giả" onClick={() => set("authors", d.authors.filter((_, j) => j !== i))}>
                      <X size={14} />
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  className="flex w-full items-center justify-center gap-1 rounded-lg border border-dashed border-border py-1.5 text-xs text-muted-foreground hover:border-primary hover:text-primary"
                  onClick={() => set("authors", [...d.authors, { name: "", affiliation: "", email: "", corresponding: d.authors.length === 0 }])}
                >
                  <Plus size={14} /> Thêm tác giả
                </button>
              </div>

              <details className="rounded-lg border border-border p-3">
                <summary className="cursor-pointer text-sm font-medium">Tuyên bố (tài trợ, xung đột lợi ích, dữ liệu, lời cảm ơn)</summary>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <Field label="Tài trợ"><input className="input" {...bind("funding")} /></Field>
                  <Field label="Xung đột lợi ích"><input className="input" placeholder="The authors declare no conflict of interest." {...bind("conflicts")} /></Field>
                  <Field label="Tính sẵn có của dữ liệu"><input className="input" {...bind("data_availability")} /></Field>
                  <Field label="Lời cảm ơn"><input className="input" {...bind("acknowledgements")} /></Field>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">Mục &ldquo;Sử dụng AI tạo sinh&rdquo; được thêm tự động. Để trống mục nào thì bản thảo ghi chỗ trống để bạn tự điền — hệ thống không tự bịa.</p>
              </details>
              <StepNav next={() => go(2)} />
            </section>
          )}

          {tab === 2 && (
            <section className="card space-y-4 border-t-4 border-t-primary p-4 sm:p-5">
              <header>
                <h2 className="font-semibold">Ý tưởng & phương pháp</h2>
                <p className="text-sm text-muted-foreground">Càng cụ thể càng tốt: AI chỉ viết từ những gì bạn cung cấp, không tự thêm số liệu hay kết quả.</p>
              </header>
              <Field label="Vấn đề nghiên cứu & động lực"><textarea className="input min-h-24" {...bind("problem")} /></Field>
              <Field label="Câu hỏi / giả thuyết nghiên cứu"><textarea className="input min-h-20" {...bind("research_questions")} /></Field>
              <Field label="Đóng góp dự kiến"><textarea className="input min-h-20" placeholder={"1) …\n2) …"} {...bind("contributions")} /></Field>
              <Field label="Phương pháp đề xuất" req hint="mô hình, công thức, quy trình, tham số">
                <textarea className="input min-h-40" {...bind("method")} />
              </Field>
              <Field label="Ghi chú về nghiên cứu liên quan / mô hình so sánh đã biết" hint="tuỳ chọn">
                <textarea className="input min-h-20" {...bind("related_notes")} />
              </Field>
              <StepNav back={() => go(1)} next={() => go(3)} />
            </section>
          )}

          {tab === 3 && (
            <section className="card space-y-4 border-t-4 border-t-primary p-4 sm:p-5">
              <header>
                <h2 className="font-semibold">Dữ liệu & kết quả</h2>
                <p className="text-sm text-muted-foreground">Mọi con số trong bản thảo được đối chiếu với phần này.</p>
              </header>
              <Note tone="warn">Hệ thống <b>không chạy thực nghiệm</b> thay bạn và không được tạo số liệu. Hãy cung cấp kết quả thật (bảng số, kiểm định); số liệu sẽ được chép nguyên văn.</Note>
              <Field label="Mô tả dữ liệu" hint="nguồn, giai đoạn, số quan sát, tiền xử lý"><textarea className="input min-h-20" {...bind("data_description")} /></Field>
              <FilePick
                label="Tệp dữ liệu (CSV/XLSX)"
                hint="Chọn tệp — hệ thống tự tính thống kê mô tả"
                accept=".csv,.tsv,.xlsx,.xls,.parquet"
                files={files.data_files}
                onChange={(f) => setFiles((p) => ({ ...p, data_files: f }))}
              />
              <Field label="Thiết lập thực nghiệm" hint="chia dữ liệu, siêu tham số, chỉ số đánh giá"><textarea className="input min-h-20" {...bind("experimental_setup")} /></Field>
              <Field label="Kết quả" req hint="bảng Markdown, chỉ số, kiểm định — dán từ Excel sẽ tự chuyển thành bảng">
                <textarea
                  className="input min-h-44 font-mono text-[13px]"
                  placeholder={"| Mô hình | RMSE | MAE |\n|---|---|---|\n| ARIMA | … | … |"}
                  {...bind("results")}
                  onPaste={(e) => {
                    const md = tsvToMarkdown(e.clipboardData.getData("text/plain"));
                    if (!md) return;
                    e.preventDefault();
                    const el = e.currentTarget;
                    const v = el.value.slice(0, el.selectionStart) + md + el.value.slice(el.selectionEnd);
                    set("results", v);
                  }}
                />
              </Field>
              <FilePick
                label="Hoặc tải bảng kết quả (CSV/XLSX/MD)"
                hint="Chọn tệp — giữ nguyên từng giá trị"
                accept=".csv,.tsv,.xlsx,.xls,.md,.txt"
                files={files.result_files}
                onChange={(f) => setFiles((p) => ({ ...p, result_files: f }))}
              />
              <Field label="Phân tích bổ sung / độ vững / ablation"><textarea className="input min-h-20" {...bind("ablations")} /></Field>
              <Field label="Diễn giải & thảo luận của tác giả"><textarea className="input min-h-20" {...bind("discussion_notes")} /></Field>
              <Field label="Hạn chế đã biết"><textarea className="input min-h-16" {...bind("limitations")} /></Field>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <FilePick
                    label="Hình có sẵn (PNG/JPG/PDF)"
                    accept=".png,.jpg,.jpeg,.pdf"
                    files={files.figure_files}
                    onChange={(f) => setFiles((p) => ({ ...p, figure_files: f }))}
                  />
                  {files.figure_files.map((f) => (
                    <input
                      key={f.name}
                      className="input text-xs"
                      placeholder={`Chú thích cho ${f.name}`}
                      value={captions[f.name] ?? ""}
                      onChange={(e) => setCaptions((c) => ({ ...c, [f.name]: e.target.value }))}
                    />
                  ))}
                </div>
                <div className="space-y-3">
                  <FilePick
                    label="Tài liệu tham khảo của bạn (.bib)"
                    hint="Chọn tệp — được ưu tiên trích dẫn"
                    accept=".bib"
                    files={files.reference_files}
                    onChange={(f) => setFiles((p) => ({ ...p, reference_files: f }))}
                  />
                  <FilePick
                    label="Ghi chú / bản nháp khác (PDF/DOCX/MD)"
                    accept=".pdf,.docx,.md,.txt"
                    files={files.note_files}
                    onChange={(f) => setFiles((p) => ({ ...p, note_files: f }))}
                  />
                </div>
              </div>
              {Object.values(files).some((l) => l.length) && (
                <p className="text-xs text-muted-foreground">Tệp chỉ giữ trong trang này (không lưu vào bản nháp). Tổng: {fmtSize(totalBytes)} / {cfg?.maxUploadMb ?? 40} MB.</p>
              )}
              <StepNav back={() => go(2)} next={() => go(4)} />
            </section>
          )}

          {tab === 4 && (
            <section className="card space-y-4 border-t-4 border-t-primary p-4 sm:p-5">
              <header>
                <h2 className="font-semibold">Cấu hình AI & gửi</h2>
                <p className="text-sm text-muted-foreground">Chọn mô hình viết, mô hình phản biện và nguồn khoá AI.</p>
              </header>

              {cfg && !ready && (
                <Note tone="warn">
                  {cfg.enabled
                    ? "Máy chủ viết bài báo đang tạm ngưng hoặc không phản hồi. Bản nháp của bạn vẫn được lưu; hãy thử gửi lại sau."
                    : "Máy chủ viết bài báo (PO-Studio) chưa được kết nối với hệ thống. Bạn vẫn có thể soạn và lưu bản nháp; nút gửi sẽ mở khi quản trị bật dịch vụ."}
                </Note>
              )}

              <div className="grid gap-3 sm:grid-cols-2">
                {(["writer_model", "reviewer_model"] as const).map((k) => (
                  <Field key={k} label={k === "writer_model" ? "Mô hình viết" : "Mô hình phản biện"} hint={k === "reviewer_model" ? "có thể chọn mô hình rẻ hơn" : undefined}>
                    <select className="input" {...bind(k)}>
                      {Object.entries(models).map(([p, ms]) => (
                        <optgroup key={p} label={`${PROVIDER_NAME[p] ?? p}${cfg?.serverKeys?.[p] && p !== "mock" ? " · có khoá Trường" : ""}`}>
                          {ms.map((m) => (
                            <option key={m} value={m}>{m}</option>
                          ))}
                        </optgroup>
                      ))}
                    </select>
                  </Field>
                ))}
              </div>
              {provider !== "mock" && providerOf(d.reviewer_model) !== provider && !usingServerKey && (
                <Note tone="warn">Khi dùng khoá API cá nhân, mô hình phản biện phải cùng nhà cung cấp với mô hình viết ({PROVIDER_NAME[provider]}).</Note>
              )}

              {provider === "mock" ? (
                <Note>Mô hình mô phỏng chỉ để chạy thử luồng (văn bản và tài liệu tham khảo đều là giả), không cần khoá API.</Note>
              ) : (
                <div className="space-y-2 rounded-lg border border-border p-3">
                  <div className="flex items-center gap-2 text-sm font-medium"><KeyRound size={15} className="text-primary" /> Khoá AI</div>
                  {cfg?.serverKey && (
                    <label className={`flex items-start gap-2 text-sm ${cfg.loggedIn ? "" : "opacity-60"}`}>
                      <input type="radio" className="mt-1" disabled={!cfg.loggedIn} checked={keyMode === "server"} onChange={() => setKeyMode("server")} />
                      <span>
                        Dùng khoá AI chung của Trường
                        <span className="block text-xs text-muted-foreground">
                          {cfg.loggedIn ? `Tối đa ${cfg.limits.serverKey} bản thảo/ngày cho mỗi tài khoản.` : "Cần đăng nhập để dùng."}
                        </span>
                      </span>
                    </label>
                  )}
                  <label className="flex items-start gap-2 text-sm">
                    {cfg?.serverKey && <input type="radio" className="mt-1" checked={keyMode === "own"} onChange={() => setKeyMode("own")} />}
                    <span className="min-w-0 flex-1 space-y-1">
                      <span>Dùng khoá API cá nhân ({PROVIDER_NAME[provider]})</span>
                      <input
                        type="password"
                        autoComplete="off"
                        className="input"
                        placeholder={KEY_HINT[provider] ?? ""}
                        value={apiKey}
                        disabled={usingServerKey}
                        onChange={(e) => {
                          setApiKey(e.target.value);
                          setKeyMode("own");
                        }}
                      />
                      <span className="block text-xs text-muted-foreground">Khoá chỉ gửi kèm bản thảo này, giữ trong bộ nhớ của tác vụ và không lưu vào cơ sở dữ liệu hay trình duyệt.</span>
                    </span>
                  </label>
                </div>
              )}

              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Mốc thời gian tài liệu" hint="không trích bài sau tháng này">
                  <input type="month" className="input" {...bind("cutoff")} />
                </Field>
                <Field label="Email liên hệ cho OpenAlex" hint="tuỳ chọn">
                  <input type="email" className="input" {...bind("mailto")} />
                </Field>
                <Field label="Số vòng phản biện – chỉnh sửa">
                  <input type="number" min={0} max={5} className="input" value={d.refine_rounds} onChange={(e) => set("refine_rounds", Math.max(0, Math.min(5, Number(e.target.value) || 0)))} />
                </Field>
                <Field label="Số tài liệu tham khảo tối đa">
                  <input type="number" min={10} max={120} className="input" value={d.max_papers} onChange={(e) => set("max_papers", Math.max(10, Math.min(120, Number(e.target.value) || 60)))} />
                </Field>
              </div>
              <div className="space-y-1.5 text-sm">
                <label className="flex items-center gap-2"><input type="checkbox" checked={d.use_plotting} onChange={(e) => set("use_plotting", e.target.checked)} /> Tự vẽ biểu đồ từ bảng kết quả</label>
                <label className="flex items-center gap-2"><input type="checkbox" checked={d.format_check} onChange={(e) => set("format_check", e.target.checked)} /> Kiểm tra trình bày PDF bằng thị giác máy</label>
              </div>

              <Note>
                Một bài khoảng 10 trang thường cần 60–120 lượt gọi mô hình và 15–40 phút. Bản thảo do AI hỗ trợ phải được tác giả đọc, kiểm chứng từng trích dẫn và con số, rồi khai báo việc dùng AI theo chính sách của tạp chí.
              </Note>

              {!requiredOk && (
                <Note tone="warn">
                  Còn thiếu:{" "}
                  {checks.filter((c) => c.req && !c.ok).map((c, i) => (
                    <button key={c.label} type="button" className="underline hover:text-primary" onClick={() => go(c.step)}>
                      {i > 0 && ", "}
                      {c.label} (bước {c.step})
                    </button>
                  ))}
                </Note>
              )}
              {submitErr && <p className="text-sm text-[var(--danger)]">{submitErr}</p>}
              <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                <button type="button" className="btn btn-outline" onClick={() => go(3)}>
                  <ChevronLeft size={15} /> Quay lại
                </button>
                <button type="button" className="btn btn-primary" disabled={!ready || submitting} onClick={submit}>
                  {submitting ? <Loader2 size={15} className="animate-spin" /> : <PenLine size={15} />} {submitting ? "Đang gửi…" : "Tạo bản thảo"}
                </button>
              </div>
            </section>
          )}

          {tab === "jobs" && (
            <JobsPanel
              jobs={jobs}
              active={activeJob}
              onOpen={openJob}
              onRemove={removeJob}
              onNew={() => {
                setActiveJob(null);
                history.replaceState(null, "", location.pathname);
                go(1);
              }}
              loggedIn={Boolean(cfg?.loggedIn)}
              serverKey={Boolean(cfg?.serverKey && cfg.loggedIn)}
            />
          )}
        </div>

        {/* cột phụ */}
        <aside className="space-y-4">
          {typeof tab === "number" && (
            <section className="card space-y-2 p-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold">Mức đầy đủ của tư liệu</h3>
                <span className="text-xs text-muted-foreground">{score}/{checks.length}</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${(score / checks.length) * 100}%` }} />
              </div>
              <ul className="space-y-1 text-sm">
                {checks.map((c) => (
                  <li key={c.label}>
                    <button type="button" onClick={() => go(c.step)} className="flex w-full items-center gap-2 text-left hover:text-primary">
                      {c.ok ? <Check size={14} className="text-emerald-600" /> : <span className={`size-3.5 rounded-full border ${c.req ? "border-[var(--danger)]" : "border-border"}`} />}
                      <span className={c.ok ? "" : "text-muted-foreground"}>{c.label}</span>
                      {c.req && !c.ok && <span className="ml-auto text-[11px] text-[var(--danger)]">bắt buộc</span>}
                      {stepIndex === c.step && <span className="ml-auto size-1.5 rounded-full bg-primary" />}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="card space-y-3 p-4">
            <h3 className="text-sm font-semibold">Quy trình đa tác tử</h3>
            <ol className="space-y-2.5">
              {AGENTS.map((a, i) => (
                <li key={a.en} className="flex gap-2.5">
                  <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"><a.icon size={15} /></span>
                  <div className="min-w-0">
                    <div className="text-sm font-medium leading-tight">
                      {i + 1}. {a.name} <span className="text-xs font-normal text-muted-foreground">· {a.en}</span>
                    </div>
                    <p className="text-xs text-muted-foreground">{a.desc}</p>
                  </div>
                </li>
              ))}
            </ol>
            <p className="text-[11px] text-muted-foreground">
              Kế thừa kiến trúc{" "}
              <a className="underline" href="https://github.com/google-research/paper-orchestra" target="_blank" rel="noreferrer">google-research/paper-orchestra</a> (Song và cs., 2026,{" "}
              <a className="underline" href="https://arxiv.org/abs/2604.05018" target="_blank" rel="noreferrer">arXiv:2604.05018</a>, Apache-2.0).
            </p>
          </section>

          <section className="card space-y-2 p-4">
            <h3 className="flex items-center gap-1.5 text-sm font-semibold"><ShieldCheck size={15} className="text-primary" /> Nguyên tắc liêm chính</h3>
            <ul className="list-disc space-y-1 pl-4 text-xs text-muted-foreground">
              <li>Không tạo số liệu: mọi số trong bảng phải có trong kết quả bạn nhập.</li>
              <li>Chỉ trích dẫn bài có thật, đã tra trên OpenAlex/Semantic Scholar hoặc từ tệp .bib của bạn.</li>
              <li>Không tự nhận vượt trội nếu so sánh đó không có trong kết quả.</li>
              <li>Tự thêm mục khai báo sử dụng AI tạo sinh.</li>
            </ul>
            <a href="/ai-responsibility" className="inline-flex items-center gap-1 text-xs text-primary hover:underline">Dùng AI có trách nhiệm <ExternalLink size={11} /></a>
          </section>
        </aside>
      </div>
    </div>
  );
}

function StepNav({ back, next }: { back?: () => void; next?: () => void }) {
  return (
    <div className="flex items-center justify-between gap-2 pt-1">
      {back ? (
        <button type="button" className="btn btn-outline" onClick={back}><ChevronLeft size={15} /> Quay lại</button>
      ) : <span />}
      {next && <button type="button" className="btn btn-primary" onClick={next}>Tiếp tục <ChevronRight size={15} /></button>}
    </div>
  );
}

// ---------------------------------------------------------------- danh sách & chi tiết bản thảo
function JobsPanel({ jobs, active, onOpen, onRemove, onNew, loggedIn, serverKey }: {
  jobs: JobRef[]; active: string | null; onOpen: (id: string) => void; onRemove: (id: string) => void; onNew: () => void; loggedIn: boolean; serverKey: boolean;
}) {
  if (active) return <JobView id={active} onBack={() => onOpen("")} onNew={onNew} serverKey={serverKey} title={jobs.find((j) => j.id === active)?.title} />;
  return (
    <section className="card space-y-3 border-t-4 border-t-primary p-4 sm:p-5">
      <div className="flex flex-wrap items-center gap-2">
        <div>
          <h2 className="font-semibold">Bản thảo của tôi</h2>
          <p className="text-sm text-muted-foreground">{loggedIn ? "Gồm bản thảo của tài khoản và của trình duyệt này." : "Lưu trên trình duyệt này. Đăng nhập để giữ danh sách theo tài khoản."}</p>
        </div>
        <button type="button" className="btn btn-primary ml-auto" onClick={onNew}><Plus size={15} /> Bài mới</button>
      </div>
      {jobs.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground">Chưa có bản thảo nào. Điền 4 bước rồi bấm &ldquo;Tạo bản thảo&rdquo;.</div>
      ) : (
        <ul className="divide-y divide-border">
          {jobs.map((j) => (
            <li key={j.id} className="flex items-center gap-3 py-2.5">
              <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"><FileText size={15} /></span>
              <button type="button" className="min-w-0 flex-1 text-left" onClick={() => onOpen(j.id)}>
                <div className="truncate text-sm font-medium hover:text-primary">{j.title || "Bản thảo chưa đặt tên"}</div>
                <div className="text-xs text-muted-foreground">{fmtTime(j.createdAt)} · mã {j.id}</div>
              </button>
              <button type="button" className="btn btn-outline px-2 py-1.5" aria-label="Bỏ khỏi danh sách" title="Bỏ khỏi danh sách" onClick={() => onRemove(j.id)}>
                <X size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function JobView({ id, title, onBack, onNew, serverKey }: { id: string; title?: string; onBack: () => void; onNew: () => void; serverKey: boolean }) {
  const [st, setSt] = useState<JobStatus | null>(null);
  const [loadErr, setLoadErr] = useState("");
  const [tick, setTick] = useState(0);
  const [resumeKey, setResumeKey] = useState("");
  const [resumeErr, setResumeErr] = useState("");
  const logRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const r = await fetch(`/api/paper/jobs/${id}`, { cache: "no-store" });
        const j = (await r.json()) as JobStatus & { error?: string };
        if (!r.ok) throw new Error(j.error || `Lỗi ${r.status}`);
        if (stop) return;
        setSt(j);
        setLoadErr("");
        if (j.state === "queued" || j.state === "running") timer = setTimeout(poll, 3000);
      } catch (e) {
        if (stop) return;
        setLoadErr(e instanceof Error ? e.message : "Không tải được tiến trình.");
        timer = setTimeout(poll, 10000);
      }
    };
    poll();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [id, tick]);

  useEffect(() => {
    const el = logRef.current;
    if (el && el.scrollTop + el.clientHeight >= el.scrollHeight - 40) el.scrollTop = el.scrollHeight;
  }, [st?.messages?.length]);

  const resume = async () => {
    setResumeErr("");
    const fd = new FormData();
    if (resumeKey.trim()) fd.set("api_key", resumeKey.trim());
    const r = await fetch(`/api/paper/jobs/${id}/resume`, { method: "POST", body: fd });
    const j = (await r.json().catch(() => ({}))) as { error?: string };
    if (!r.ok) return setResumeErr(j.error || `Lỗi ${r.status}`);
    setResumeKey("");
    setTick((t) => t + 1);
  };

  const base = `/api/paper/jobs/${id}/download/`;
  const review = st?.review ?? {};
  const report = st?.report;
  const stateLabel = { queued: "Đang chờ", running: "Đang viết", done: "Hoàn tất", failed: "Lỗi" } as const;
  const doneCount = st ? STAGES.filter((s) => st.stages[s] === "done" || st.stages[s] === "skipped").length : 0;

  return (
    <div className="space-y-4">
      <section className="card space-y-3 border-t-4 border-t-primary p-4 sm:p-5">
        <div className="flex flex-wrap items-start gap-2">
          <button type="button" className="btn btn-outline px-2 py-1.5" onClick={onBack} aria-label="Danh sách bản thảo"><ChevronLeft size={15} /></button>
          <div className="min-w-0 flex-1">
            <h2 className="truncate font-semibold">{title || "Bản thảo"}</h2>
            <p className="text-xs text-muted-foreground">
              Mã công việc <code>{id}</code>
              {st && <> · {stateLabel[st.state]}{st.elapsed_sec ? ` sau ${st.elapsed_sec < 60 ? `${Math.round(st.elapsed_sec)} giây` : `${Math.round(st.elapsed_sec / 60)} phút`}` : ""}</>}
              {st?.usage?.calls ? ` · ${st.usage.calls} lượt gọi AI` : ""}
            </p>
          </div>
          <button type="button" className="btn btn-outline py-1.5" onClick={onNew}><Plus size={15} /> Bài mới</button>
        </div>

        {loadErr && <Note tone="warn">{loadErr}</Note>}
        {!st && !loadErr && <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 size={15} className="animate-spin" /> Đang tải tiến trình…</p>}

        {st && (
          <>
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
              <div className={`h-full rounded-full transition-all ${st.state === "failed" ? "bg-[var(--danger)]" : "bg-primary"}`} style={{ width: `${(doneCount / STAGES.length) * 100}%` }} />
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
              {STAGES.map((s, i) => {
                const v = st.stages[s] ?? "pending";
                const cls =
                  v === "done" ? "border-emerald-600/30 bg-emerald-600/5 text-emerald-700 dark:text-emerald-400"
                    : v === "running" ? "border-primary bg-primary/5 text-primary"
                      : v === "failed" ? "border-[var(--danger)] text-[var(--danger)]"
                        : "border-border text-muted-foreground";
                return (
                  <div key={s} className={`rounded-lg border px-2.5 py-2 text-xs ${cls}`}>
                    <div className="flex items-center gap-1 font-medium">
                      {v === "running" ? <Loader2 size={12} className="animate-spin" /> : v === "done" ? <Check size={12} /> : <span className="text-[10px]">{i + 1}</span>}
                      {STAGE_LABEL[s]}
                    </div>
                    <div className="opacity-80">{{ pending: "chờ", running: "đang chạy", done: "xong", skipped: "bỏ qua", failed: "lỗi" }[v]}</div>
                  </div>
                );
              })}
            </div>
            <details open={st.state !== "done"}>
              <summary className="cursor-pointer text-sm font-medium">Nhật ký xử lý</summary>
              <pre ref={logRef} className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-[#121a2e] p-3 font-mono text-[12px] leading-relaxed text-slate-200">
                {(st.messages ?? []).join("\n") || "…"}
              </pre>
            </details>
          </>
        )}

        {st?.state === "failed" && (
          <div className="space-y-2 rounded-lg border border-[var(--danger)]/40 p-3">
            <p className="text-sm font-medium text-[var(--danger)]">Bản thảo dừng giữa chừng. Các bước đã xong được giữ lại; bạn có thể chạy tiếp.</p>
            <div className="flex flex-wrap gap-2">
              <input type="password" autoComplete="off" className="input min-w-0 flex-1" placeholder={serverKey ? "Khoá API (để trống để dùng khoá Trường)" : "Nhập lại khoá API"} value={resumeKey} onChange={(e) => setResumeKey(e.target.value)} />
              <button type="button" className="btn btn-primary" onClick={resume}><RotateCw size={15} /> Chạy tiếp</button>
            </div>
            {resumeErr && <p className="text-sm text-[var(--danger)]">{resumeErr}</p>}
          </div>
        )}
      </section>

      {st?.state === "done" && (
        <section className="card space-y-4 p-4 sm:p-5">
          <h2 className="font-semibold">Kết quả</h2>
          <div className="flex flex-wrap gap-2">
            {(["Overall", "Soundness", "Presentation", "Contribution", "Originality", "Clarity"] as const).filter((k) => review[k] != null).map((k) => (
              <span key={k} className="chip px-2.5 py-1 text-xs">
                {{ Overall: "Điểm chung", Soundness: "Độ vững", Presentation: "Trình bày", Contribution: "Đóng góp", Originality: "Tính mới", Clarity: "Rõ ràng" }[k]}{" "}
                <b className="text-sm">{String(review[k])}</b>/{k === "Overall" ? 10 : 4}
              </span>
            ))}
            {report?.stats && Object.entries(report.stats).map(([k, v]) => (
              <span key={k} className="chip px-2.5 py-1 text-xs text-muted-foreground">{STAT_LABEL[k] ?? k} <b className="text-foreground">{String(v)}</b></span>
            ))}
          </div>

          {report?.ok && <Note tone="ok">Đã qua mọi kiểm tra liêm chính (trích dẫn, số liệu trong bảng, hình, nhãn).</Note>}
          {!!report?.errors?.length && (
            <Note tone="warn">
              <b>Cần xử lý</b>
              <ul className="mt-1 list-disc pl-4">{report.errors.map((e) => <li key={e}>{e}</li>)}</ul>
            </Note>
          )}
          {!!report?.warnings?.length && (
            <details className="text-sm">
              <summary className="cursor-pointer font-medium">Cảnh báo ({report.warnings.length})</summary>
              <ul className="mt-1 list-disc pl-5 text-muted-foreground">{report.warnings.map((e) => <li key={e}>{e}</li>)}</ul>
            </details>
          )}
          {!!review.Weaknesses?.length && (
            <details className="text-sm">
              <summary className="cursor-pointer font-medium">Điểm yếu phản biện nêu ({review.Weaknesses.length})</summary>
              <ul className="mt-1 list-disc pl-5 text-muted-foreground">{review.Weaknesses.map((e) => <li key={e}>{e}</li>)}</ul>
            </details>
          )}

          <div className="flex flex-wrap gap-2">
            <a className="btn btn-primary" href={`${base}pdf`}><Download size={15} /> PDF</a>
            <a className="btn btn-accent" href={`${base}zip`}><Download size={15} /> Gói nộp bài (.zip)</a>
            <a className="btn btn-outline" href={`${base}tex`}>LaTeX</a>
            <a className="btn btn-outline" href={`${base}bib`}>BibTeX</a>
            <a className="btn btn-outline" href={`${base}report`}>Báo cáo kiểm tra</a>
            <a className="btn btn-outline" href={`${base}log`}>Nhật ký</a>
          </div>
          <iframe title="Xem trước PDF" src={`${base}pdf?inline=1`} className="h-[75vh] w-full rounded-lg border border-border bg-white" />
          <p className="text-xs text-muted-foreground">Đây là bản nháp có AI hỗ trợ. Hãy đọc kỹ, kiểm chứng từng trích dẫn và con số trước khi nộp, và khai báo việc dùng AI theo chính sách của tạp chí.</p>
        </section>
      )}
    </div>
  );
}
