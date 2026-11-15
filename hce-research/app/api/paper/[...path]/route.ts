// /api/paper/* — cầu nối tới dịch vụ PO-Studio (mục "Viết bài báo", /tools/writium).
//   GET  /api/paper/config                       mẫu, mô hình, chính sách khoá & hạn mức
//   GET  /api/paper/jobs                         bản thảo của tài khoản đang đăng nhập
//   POST /api/paper/jobs                         tạo bản thảo (multipart: payload + tệp + api_key)
//   GET  /api/paper/jobs/:id                     tiến trình
//   GET  /api/paper/jobs/:id/download/:kind      pdf | zip | tex | bib | report | log | outline (?inline=1)
//   GET  /api/paper/jobs/:id/preview/:n          ảnh xem trước trang
//   POST /api/paper/jobs/:id/resume              chạy tiếp khi lỗi
import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import { audit, takeQuota } from "@/lib/db";
import { giveBackQuota, jobOwner, listJobs, paperCfg, paperEnabled, recordJob, upstream } from "@/lib/paper";

type Ctx = { params: Promise<{ path: string[] }> };

const JOB_ID = /^[a-f0-9]{12}$/;
const KINDS = new Set(["pdf", "zip", "tex", "bib", "report", "log", "outline"]);
const FILE_FIELDS = ["data_files", "result_files", "figure_files", "reference_files", "note_files"] as const;

const err = (error: string, status: number) => NextResponse.json({ error }, { status });

function clientIp(req: Request) {
  // Chỉ tin X-Forwarded-For khi chạy sau reverse proxy do bạn kiểm soát.
  return req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown";
}

/** Lỗi từ PO-Studio → thông báo tiếng Việt, không lộ chi tiết nội bộ. */
async function upstreamError(res: Response) {
  let detail = "";
  try {
    detail = String(((await res.json()) as { detail?: unknown }).detail ?? "");
  } catch {}
  const vi: Record<string, string> = {
    "Method and experimental results are required.": "Cần nhập phương pháp và kết quả thực nghiệm (hoặc tải tệp kết quả).",
    "unknown template": "Mẫu định dạng không hợp lệ.",
    "unknown model": "Mô hình AI không hợp lệ.",
    "job not found": "Không tìm thấy bản thảo.",
    "job is running": "Bản thảo đang được xử lý.",
    "file not available": "Tệp chưa sẵn sàng.",
  };
  if (res.status === 413) return err("Tổng dung lượng tệp vượt giới hạn của máy chủ viết bài.", 413);
  if (res.status === 403) return err("Máy chủ viết bài từ chối yêu cầu (thiếu khoá API hoặc cấu hình cầu nối sai).", 403);
  return err(vi[detail] ?? (detail.startsWith("With a personal API key") ? "Khi dùng khoá API cá nhân, mô hình viết và mô hình phản biện phải cùng nhà cung cấp." : "Máy chủ viết bài báo lỗi, vui lòng thử lại sau."), res.status >= 500 ? 502 : res.status);
}

/** Bản thảo gắn với tài khoản chỉ chủ tài khoản xem được; bản thảo của khách xem được bằng mã công việc. */
async function canSee(req: Request, id: string) {
  const owner = jobOwner(id);
  if (!owner) return true;
  const s = await getSession(req.headers);
  return s?.user.id === owner;
}

export async function GET(req: Request, { params }: Ctx) {
  const { path } = await params;
  const session = await getSession(req.headers);

  if (path.length === 1 && path[0] === "config") {
    const base = {
      enabled: paperEnabled(),
      loggedIn: Boolean(session),
      serverKey: paperCfg.serverKeyForUsers && Boolean(paperCfg.accessCode),
      limits: { guest: paperCfg.guestDaily, user: paperCfg.userDaily, serverKey: paperCfg.serverKeyDaily },
      maxUploadMb: paperCfg.maxUploadMb,
    };
    if (!base.enabled) return NextResponse.json(base);
    try {
      const res = await upstream("/api/config", { signal: AbortSignal.timeout(8000) });
      if (!res.ok) throw new Error(String(res.status));
      const cfg = (await res.json()) as { templates: unknown; models: unknown; server_keys: Record<string, boolean>; max_upload_mb: number };
      return NextResponse.json({
        ...base,
        online: true,
        templates: cfg.templates,
        models: cfg.models,
        serverKeys: cfg.server_keys,
        maxUploadMb: Math.min(paperCfg.maxUploadMb, cfg.max_upload_mb || paperCfg.maxUploadMb),
      });
    } catch {
      return NextResponse.json({ ...base, online: false });
    }
  }

  if (path.length === 1 && path[0] === "jobs") {
    if (!session) return NextResponse.json({ jobs: [] });
    return NextResponse.json({ jobs: listJobs(session.user.id) });
  }

  if (path[0] !== "jobs" || !JOB_ID.test(path[1] ?? "")) return err("Không tìm thấy", 404);
  if (!paperEnabled()) return err("Máy chủ viết bài báo chưa được kết nối.", 503);
  const id = path[1];
  if (!(await canSee(req, id))) return err("Bản thảo này thuộc tài khoản khác.", 403);

  try {
    if (path.length === 2) {
      const res = await upstream(`/api/jobs/${id}`);
      if (!res.ok) return upstreamError(res);
      const st = (await res.json()) as Record<string, unknown>;
      delete st.config; // không cần cho giao diện
      return NextResponse.json(st);
    }
    let up: Response;
    if (path.length === 4 && path[2] === "download" && KINDS.has(path[3])) {
      const inline = new URL(req.url).searchParams.get("inline") === "1";
      up = await upstream(`/api/jobs/${id}/download/${path[3]}${inline ? "?inline=true" : ""}`, { signal: AbortSignal.timeout(120_000) });
    } else if (path.length === 4 && path[2] === "preview" && /^\d{1,2}$/.test(path[3])) {
      up = await upstream(`/api/jobs/${id}/preview/${path[3]}`);
    } else {
      return err("Không tìm thấy", 404);
    }
    if (!up.ok) return upstreamError(up);
    const headers = new Headers({ "cache-control": "private, no-store", "x-content-type-options": "nosniff" });
    for (const h of ["content-type", "content-length", "content-disposition"]) {
      const v = up.headers.get(h);
      if (v) headers.set(h, v);
    }
    return new Response(up.body, { status: 200, headers });
  } catch {
    return err("Không kết nối được máy chủ viết bài báo.", 502);
  }
}

export async function POST(req: Request, { params }: Ctx) {
  const { path } = await params;
  if (!paperEnabled()) return err("Máy chủ viết bài báo chưa được kết nối.", 503);
  const session = await getSession(req.headers);

  const len = Number(req.headers.get("content-length") ?? 0);
  if (len > paperCfg.maxUploadMb * 1024 * 1024 + 2_000_000) return err(`Tổng dung lượng tệp vượt ${paperCfg.maxUploadMb} MB.`, 413);

  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    return err("Dữ liệu gửi lên không hợp lệ.", 400);
  }
  const apiKey = String(form.get("api_key") ?? "").trim();
  const payloadText = String(form.get("payload") ?? "");
  let payload: { form?: { title?: string; method?: string; results?: string }; options?: { template?: string; writer_model?: string } } = {};
  if (path.length === 1) {
    try {
      payload = JSON.parse(payloadText);
    } catch {
      return err("Dữ liệu biểu mẫu không hợp lệ.", 400);
    }
  }
  const mock = (payload.options?.writer_model ?? "").startsWith("mock");

  // Chính sách khoá AI: khoá cá nhân (mọi người) | khoá chung của Trường (chỉ người đã đăng nhập, khi được bật).
  let useServerKey = false;
  if (!apiKey && !mock) {
    if (!session) return err("Hãy nhập khoá API của bạn, hoặc đăng nhập để dùng khoá AI của Trường (nếu được cấp).", 401);
    if (!(paperCfg.serverKeyForUsers && paperCfg.accessCode)) return err("Hệ thống chưa cấp khoá AI chung cho mục này. Hãy nhập khoá API cá nhân.", 403);
    useServerKey = true;
  }

  // ---- Tạo bản thảo mới ----
  if (path.length === 1 && path[0] === "jobs") {
    const hasResultFile = form.getAll("result_files").some((f) => f instanceof File && f.size > 0);
    if (!payload.form?.method?.trim() || !(payload.form.results?.trim() || hasResultFile))
      return err("Cần nhập phương pháp và kết quả thực nghiệm (hoặc tải tệp kết quả).", 400);
    const subject = session ? `paper:u:${session.user.id}` : `paper:ip:${clientIp(req)}`;
    const q = takeQuota(subject, session ? paperCfg.userDaily : paperCfg.guestDaily);
    if (!q.ok) return err(session ? "Bạn đã dùng hết lượt tạo bản thảo hôm nay." : "Khách đã dùng hết lượt tạo bản thảo hôm nay. Hãy đăng nhập để dùng nhiều hơn.", 429);
    const keySubject = useServerKey ? `paper:key:${session!.user.id}` : "";
    if (keySubject && !takeQuota(keySubject, paperCfg.serverKeyDaily).ok) {
      giveBackQuota(subject);
      return err("Bạn đã dùng hết lượt dùng khoá AI chung hôm nay. Hãy nhập khoá API cá nhân để tiếp tục.", 429);
    }
    const refund = () => {
      giveBackQuota(subject);
      if (keySubject) giveBackQuota(keySubject);
    };
    const out = new FormData();
    out.set("payload", payloadText);
    if (apiKey) out.set("api_key", apiKey);
    for (const f of FILE_FIELDS) for (const file of form.getAll(f)) if (file instanceof File && file.size > 0) out.append(f, file, file.name);
    try {
      const res = await upstream("/api/jobs", { method: "POST", body: out, accessCode: useServerKey, signal: AbortSignal.timeout(120_000) });
      if (!res.ok) {
        refund();
        return upstreamError(res);
      }
      const { job_id } = (await res.json()) as { job_id: string };
      if (!JOB_ID.test(job_id)) return err("Máy chủ viết bài trả về mã không hợp lệ.", 502);
      recordJob(job_id, session?.user.id ?? null, payload.form?.title ?? "", payload.options?.template ?? "");
      audit(session?.user.id ?? null, "paper.create", `${job_id}${useServerKey ? " server-key" : ""}`);
      return NextResponse.json({ job_id, owned: Boolean(session) });
    } catch {
      refund();
      return err("Không kết nối được máy chủ viết bài báo.", 502);
    }
  }

  // ---- Chạy tiếp bản thảo bị lỗi ----
  if (path.length === 3 && path[0] === "jobs" && JOB_ID.test(path[1]) && path[2] === "resume") {
    const id = path[1];
    if (!(await canSee(req, id))) return err("Bản thảo này thuộc tài khoản khác.", 403);
    const out = new FormData();
    if (apiKey) out.set("api_key", apiKey);
    try {
      const res = await upstream(`/api/jobs/${id}/resume`, { method: "POST", body: out, accessCode: useServerKey });
      if (!res.ok) return upstreamError(res);
      audit(session?.user.id ?? null, "paper.resume", id);
      return NextResponse.json({ ok: true });
    } catch {
      return err("Không kết nối được máy chủ viết bài báo.", 502);
    }
  }
  return err("Không tìm thấy", 404);
}
