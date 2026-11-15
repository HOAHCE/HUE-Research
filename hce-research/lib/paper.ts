// Cầu nối tới dịch vụ PO-Studio (viết bài báo tự động, dựa trên google-research/paper-orchestra).
// Trình duyệt chỉ gọi /api/paper/*; máy chủ web chuyển tiếp sang POSTUDIO_URL kèm X-Bridge-Token.
import { db } from "./db";

const env = process.env;

export const paperCfg = {
  /** Địa chỉ nội bộ của dịch vụ PO-Studio, ví dụ http://postudio:8000. Trống = chưa kết nối. */
  url: (env.POSTUDIO_URL ?? "").replace(/\/+$/, ""),
  /** Phải trùng POSTUDIO_BRIDGE_TOKEN của dịch vụ PO-Studio. */
  bridgeToken: env.POSTUDIO_BRIDGE_TOKEN ?? "",
  /** Mã truy cập để dùng khoá AI của máy chủ PO-Studio (POSTUDIO_ACCESS_CODE bên dịch vụ). */
  accessCode: env.POSTUDIO_ACCESS_CODE ?? "",
  /** "1" = cho người đã đăng nhập dùng khoá AI chung của Trường (nếu dịch vụ có khoá). */
  serverKeyForUsers: env.PAPER_SERVER_KEY === "1",
  guestDaily: Number(env.PAPER_GUEST_DAILY_LIMIT ?? 2),
  userDaily: Number(env.PAPER_USER_DAILY_LIMIT ?? 5),
  serverKeyDaily: Number(env.PAPER_SERVER_KEY_DAILY_LIMIT ?? 1),
  maxUploadMb: Number(env.PAPER_MAX_UPLOAD_MB ?? 40),
};

export const paperEnabled = () => Boolean(paperCfg.url);

db.exec(`
  CREATE TABLE IF NOT EXISTS paper_jobs (
    job_id TEXT PRIMARY KEY,
    user_id TEXT,
    title TEXT,
    template TEXT,
    created_at INTEGER NOT NULL
  );
  CREATE INDEX IF NOT EXISTS paper_jobs_user ON paper_jobs(user_id, created_at);
`);

export function recordJob(jobId: string, userId: string | null, title: string, template: string) {
  db.prepare("INSERT OR IGNORE INTO paper_jobs (job_id, user_id, title, template, created_at) VALUES (?,?,?,?,?)").run(
    jobId, userId, title.slice(0, 300), template, Date.now(),
  );
}

export function jobOwner(jobId: string): string | null | undefined {
  const row = db.prepare("SELECT user_id FROM paper_jobs WHERE job_id=?").get(jobId) as { user_id: string | null } | undefined;
  return row ? row.user_id : undefined;
}

export function listJobs(userId: string) {
  return db
    .prepare("SELECT job_id AS id, title, template, created_at AS createdAt FROM paper_jobs WHERE user_id=? ORDER BY created_at DESC LIMIT 50")
    .all(userId) as { id: string; title: string; template: string; createdAt: number }[];
}

/** Trả lại một lượt đã trừ (khi dịch vụ từ chối hoặc lỗi, người dùng không mất lượt). */
export function giveBackQuota(subject: string) {
  const day = new Date().toISOString().slice(0, 10);
  db.prepare("UPDATE usage SET n = n - 1 WHERE day=? AND subject=? AND n > 0").run(day, subject);
}

/** Gọi dịch vụ PO-Studio. `path` bắt đầu bằng /api/... */
export function upstream(path: string, init: RequestInit & { accessCode?: boolean } = {}) {
  const headers = new Headers(init.headers);
  if (paperCfg.bridgeToken) headers.set("x-bridge-token", paperCfg.bridgeToken);
  if (init.accessCode && paperCfg.accessCode) headers.set("x-access-code", paperCfg.accessCode);
  return fetch(paperCfg.url + path, { ...init, headers, cache: "no-store", signal: init.signal ?? AbortSignal.timeout(60_000) });
}
