// Cấu hình cầu nối tới PO-Studio + lưu trữ nhẹ (tệp JSON) + đọc phiên đăng nhập từ site chính.
// Ứng dụng này chạy như tiến trình con của hce-start.cjs (giống BiblioMap) nên không mở CSDL SQLite của site chính.
import fs from "node:fs";
import path from "node:path";

const env = process.env;

export const paperCfg = {
  url: (env.POSTUDIO_URL ?? "").replace(/\/+$/, ""),
  bridgeToken: env.POSTUDIO_BRIDGE_TOKEN ?? "",
  accessCode: env.POSTUDIO_ACCESS_CODE ?? "",
  serverKeyForUsers: env.PAPER_SERVER_KEY === "1",
  guestDaily: Number(env.PAPER_GUEST_DAILY_LIMIT ?? 2),
  userDaily: Number(env.PAPER_USER_DAILY_LIMIT ?? 5),
  serverKeyDaily: Number(env.PAPER_SERVER_KEY_DAILY_LIMIT ?? 1),
  maxUploadMb: Number(env.PAPER_MAX_UPLOAD_MB ?? 40),
  /** Địa chỉ nội bộ của site chính (hce-start.cjs đặt), dùng để hỏi phiên đăng nhập. */
  mainUrl: (env.HCE_MAIN_URL ?? "").replace(/\/+$/, ""),
};

export const paperEnabled = () => Boolean(paperCfg.url);

// ------------------------------------------------------------------ phiên đăng nhập (hỏi site chính)
export type SessionUser = { id: string; name?: string; email?: string };

export async function getSession(req: Request): Promise<{ user: SessionUser } | null> {
  const cookie = req.headers.get("cookie");
  if (!cookie || !paperCfg.mainUrl) return null;
  try {
    const r = await fetch(`${paperCfg.mainUrl}/api/auth/get-session`, {
      headers: { cookie, accept: "application/json", "x-forwarded-host": req.headers.get("x-forwarded-host") ?? req.headers.get("host") ?? "", "x-forwarded-proto": "https" },
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (!r.ok) return null;
    const j = (await r.json()) as { user?: SessionUser } | null;
    return j?.user?.id ? { user: { id: j.user.id, name: j.user.name, email: j.user.email } } : null;
  } catch {
    return null;
  }
}

// ------------------------------------------------------------------ lưu trữ JSON
type JobRow = { id: string; userId: string | null; title: string; template: string; createdAt: number };
type Store = { jobs: JobRow[]; usage: Record<string, number> };

const DATA_DIR = path.resolve(/*turbopackIgnore: true*/ env.WRITIUM_DATA_DIR || path.join(/*turbopackIgnore: true*/ process.cwd(), "data"));
const FILE = path.join(DATA_DIR, "writium-store.json");
let cache: Store | null = null;

function load(): Store {
  if (cache) return cache;
  try {
    cache = JSON.parse(fs.readFileSync(FILE, "utf8")) as Store;
  } catch {
    cache = { jobs: [], usage: {} };
  }
  cache.jobs ??= [];
  cache.usage ??= {};
  return cache;
}

function save() {
  const s = load();
  // bỏ bộ đếm cũ hơn 3 ngày, giữ tối đa 5000 bản thảo
  const keep = new Date(Date.now() - 3 * 86400_000).toISOString().slice(0, 10);
  for (const k of Object.keys(s.usage)) if (k.slice(0, 10) < keep) delete s.usage[k];
  if (s.jobs.length > 5000) s.jobs = s.jobs.slice(-5000);
  fs.mkdirSync(DATA_DIR, { recursive: true });
  const tmp = `${FILE}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(s));
  fs.renameSync(tmp, FILE);
}

const today = () => new Date().toISOString().slice(0, 10);

/** Tăng bộ đếm trong ngày; không tăng nếu đã chạm giới hạn. */
export function takeQuota(subject: string, limit: number): { ok: boolean; used: number } {
  const s = load();
  const k = `${today()}|${subject}`;
  const used = s.usage[k] ?? 0;
  if (used >= limit) return { ok: false, used };
  s.usage[k] = used + 1;
  save();
  return { ok: true, used: used + 1 };
}

export function giveBackQuota(subject: string) {
  const s = load();
  const k = `${today()}|${subject}`;
  if ((s.usage[k] ?? 0) > 0) {
    s.usage[k] -= 1;
    save();
  }
}

export function recordJob(id: string, userId: string | null, title: string, template: string) {
  const s = load();
  if (s.jobs.some((j) => j.id === id)) return;
  s.jobs.push({ id, userId, title: title.slice(0, 300), template, createdAt: Date.now() });
  save();
}

export function jobOwner(id: string): string | null | undefined {
  const j = load().jobs.find((x) => x.id === id);
  return j ? j.userId : undefined;
}

export function listJobs(userId: string) {
  return load()
    .jobs.filter((j) => j.userId === userId)
    .sort((a, b) => b.createdAt - a.createdAt)
    .slice(0, 50)
    .map(({ id, title, template, createdAt }) => ({ id, title, template, createdAt }));
}

export function audit(userId: string | null, action: string, detail?: string) {
  console.log(`[writium] ${new Date().toISOString()} ${action} ${userId ?? "khách"} ${detail ?? ""}`);
}

// ------------------------------------------------------------------ gọi PO-Studio
export function upstream(p: string, init: RequestInit & { accessCode?: boolean } = {}) {
  const headers = new Headers(init.headers);
  if (paperCfg.bridgeToken) headers.set("x-bridge-token", paperCfg.bridgeToken);
  if (init.accessCode && paperCfg.accessCode) headers.set("x-access-code", paperCfg.accessCode);
  return fetch(paperCfg.url + p, { ...init, headers, cache: "no-store", signal: init.signal ?? AbortSignal.timeout(60_000) });
}
