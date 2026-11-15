"use strict";
// Tệp khởi động thật của HUE - Research (Next.js standalone trong ./server) — bản có BiblioMap + Viết nghiên cứu.
// app.js là wrapper của Tenten 1-Click Launch và sẽ require tệp này (entryFile = 'hce-start.cjs').
//
// Cách chạy (từ 15/11/2026):
//   1. Chuẩn bị biến môi trường như trước (hce-env.cjs), nạp dữ liệu lần đầu nếu cần.
//   2. Chạy các tiến trình con trên cổng nội bộ 127.0.0.1:
//        - site chính:       ./server/server.js
//        - BiblioMap:        ./bibliomap/server.js  (Trắc lượng thư mục, basePath /tools/bibliomap)
//        - Viết nghiên cứu:  ./writium/server.js    (basePath /tools/writium; máy viết bài PO-Studio chạy nơi khác, POSTUDIO_URL)
//   3. Mở một proxy HTTP nhẹ trên cổng công khai (PORT): /tools/bibliomap... -> BiblioMap, /tools/writium... -> Viết nghiên cứu,
//      mọi đường dẫn khác -> site chính. Ứng dụng phụ lỗi/không khởi động được -> tự trả về site chính.
//
// HOÀN TÁC NHANH:
//   - Bỏ riêng Viết nghiên cứu: đặt WRITIUM_DISABLE=1 (trong hue-data/.env) rồi Khởi động lại, hoặc xoá thư mục ./writium.
//   - Về bản trước (chỉ BiblioMap): đổi tên hce-start.bibliomap.cjs thành hce-start.cjs rồi Khởi động lại.
//   - Về bản cũ nhất (không proxy): hce-start.legacy.cjs, hoặc BIBLIOMAP_DISABLE=1 và WRITIUM_DISABLE=1.
const path = require("node:path");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const { spawn } = require("node:child_process");

const ROOT = __dirname;
process.chdir(ROOT);

const { SERVER_DIR, prepareEnv } = require("./hce-env.cjs");
const info = prepareEnv();
console.log(`[hue-research] Node ${process.version} — thư mục dữ liệu: ${info.dataDir}` +
  (info.loaded.length ? ` — .env: ${info.loaded.join(", ")}` : ""));

// Lần chạy đầu (chưa có dữ liệu): nạp dữ liệu nền, không chặn máy chủ web.
if (!fs.existsSync(path.join(info.dataDir, ".seeded"))) {
  try {
    const child = spawn(process.execPath, [path.join(ROOT, "sync.mjs"), "seed"], {
      cwd: ROOT,
      env: process.env,
      detached: true,
      stdio: "ignore",
    });
    child.unref();
    console.log("[hue-research] Đang nạp dữ liệu lần đầu ở nền (xem sync.log trong thư mục dữ liệu).");
  } catch (err) {
    console.error("[hue-research] Không khởi chạy được nạp dữ liệu:", err);
  }
}

// Ứng dụng phụ: mỗi ứng dụng chỉ nhận các biến môi trường cần thiết (không truyền khoá SMTP/AI/OAuth của site chính).
const BASE_ENV_KEYS = ["PATH", "HOME", "TZ", "LANG", "LC_ALL", "NODE_OPTIONS", "NODE_EXTRA_CA_CERTS", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"];
const SUBAPPS = [
  {
    key: "bm",
    name: "BiblioMap",
    dir: path.join(ROOT, "bibliomap"),
    prefix: "/tools/bibliomap",
    disabled: process.env.BIBLIOMAP_DISABLE === "1",
    envPattern: /^(BIBLIOMAP_|OPENALEX_API_KEY$|S2_API_KEY$|NCBI_API_KEY$)/,
    extraEnv: () => {
      const e = {};
      if (!process.env.BIBLIOMAP_CONTACT_EMAIL && process.env.ADMIN_EMAILS) {
        e.BIBLIOMAP_CONTACT_EMAIL = String(process.env.ADMIN_EMAILS).split(/[,;\s]+/).filter(Boolean)[0];
      }
      return e;
    },
  },
  {
    key: "writium",
    name: "Viết nghiên cứu",
    dir: path.join(ROOT, "writium"),
    prefix: "/tools/writium",
    disabled: process.env.WRITIUM_DISABLE === "1",
    envPattern: /^(POSTUDIO_URL$|POSTUDIO_BRIDGE_TOKEN$|POSTUDIO_ACCESS_CODE$|PAPER_)/,
    extraEnv: (ports) => ({
      HCE_MAIN_URL: `http://127.0.0.1:${ports.main}`, // để hỏi phiên đăng nhập của site chính
      WRITIUM_DATA_DIR: path.join(info.dataDir, "writium"),
    }),
  },
].filter((a) => !a.disabled && fs.existsSync(path.join(a.dir, "server.js")));

if (SUBAPPS.length === 0) {
  // Chế độ cũ: chạy site chính ngay trong tiến trình này.
  console.log("[hue-research] Chạy site chính (không có ứng dụng phụ).");
  require(path.join(SERVER_DIR, "server.js"));
} else {
  startWithSubApps();
}

function freePort() {
  return new Promise((resolve, reject) => {
    const s = net.createServer();
    s.unref();
    s.on("error", reject);
    s.listen(0, "127.0.0.1", () => {
      const { port } = s.address();
      s.close(() => resolve(port));
    });
  });
}

function waitForPort(port, timeoutMs) {
  const until = Date.now() + timeoutMs;
  return new Promise((resolve) => {
    const tryOnce = () => {
      const sock = net.connect(port, "127.0.0.1");
      sock.once("connect", () => {
        sock.destroy();
        resolve(true);
      });
      sock.once("error", () => {
        sock.destroy();
        if (Date.now() > until) resolve(false);
        else setTimeout(tryOnce, 300);
      });
    };
    tryOnce();
  });
}

// Tiến trình con có tự khởi động lại khi thoát bất thường (giãn cách tăng dần, tối đa 30 giây).
function supervise(name, script, cwd, port, env) {
  const state = { name, port, ready: false, failures: 0, child: null, stopping: false, readyWaiters: [] };
  const run = () => {
    state.ready = false;
    const guard = path.join(ROOT, "hce-child-guard.cjs");
    const args = fs.existsSync(guard) ? ["--require", guard, script] : [script];
    const child = spawn(process.execPath, args, {
      cwd,
      env: { ...env, PORT: String(port), HOSTNAME: "127.0.0.1", NODE_ENV: "production" },
      stdio: ["ignore", "inherit", "inherit"],
    });
    state.child = child;
    const started = Date.now();
    waitForPort(port, 60000).then((ok) => {
      if (ok && state.child === child) {
        state.ready = true;
        state.readyWaiters.splice(0).forEach((fn) => fn(true));
        console.log(`[hue-research] ${name} sẵn sàng trên 127.0.0.1:${port} (${Date.now() - started} ms).`);
      }
    });
    child.on("exit", (code, signal) => {
      state.ready = false;
      if (state.stopping) return;
      state.failures = Date.now() - started > 60000 ? 1 : state.failures + 1;
      const delay = Math.min(30000, 1000 * 2 ** Math.min(5, state.failures - 1));
      console.error(`[hue-research] ${name} dừng (mã ${code}, tín hiệu ${signal}); chạy lại sau ${delay} ms.`);
      setTimeout(run, delay);
    });
  };
  state.whenReady = (ms) =>
    state.ready
      ? Promise.resolve(true)
      : new Promise((resolve) => {
          const t = setTimeout(() => resolve(false), ms);
          state.readyWaiters.push((v) => {
            clearTimeout(t);
            resolve(v);
          });
        });
  run();
  return state;
}

async function startWithSubApps() {
  const PUBLIC_PORT = parseInt(process.env.PORT, 10) || 3000;
  const PUBLIC_HOST = process.env.HOSTNAME || "0.0.0.0"; // giống server.js gốc
  const ports = { main: await freePort() };
  for (const a of SUBAPPS) ports[a.key] = await freePort();

  const main = supervise("Site chính", path.join(SERVER_DIR, "server.js"), SERVER_DIR, ports.main, process.env);
  const subs = SUBAPPS.map((a) => {
    const env = {};
    for (const k of BASE_ENV_KEYS) if (process.env[k]) env[k] = process.env[k];
    for (const [k, v] of Object.entries(process.env)) if (a.envPattern.test(k)) env[k] = v;
    Object.assign(env, a.extraEnv(ports));
    return { app: a, state: supervise(a.name, path.join(a.dir, "server.js"), a.dir, ports[a.key], env) };
  });
  const all = [main, ...subs.map((s) => s.state)];

  const agent = new http.Agent({ keepAlive: true, maxSockets: 512, keepAliveMsecs: 10000 });
  const matches = (url, prefix) => url === prefix || url.startsWith(prefix + "/") || url.startsWith(prefix + "?");
  // Header điều hướng RSC của site chính: bỏ đi để ứng dụng phụ trả HTML -> trình duyệt tải hẳn trang.
  const STRIP_SUB = ["rsc", "next-router-state-tree", "next-router-prefetch", "next-router-segment-prefetch", "next-url", "next-hmr-refresh"];
  const HOP = ["connection", "keep-alive", "proxy-connection", "transfer-encoding", "upgrade", "te", "trailer"];

  const pickTarget = async (url) => {
    for (const s of subs) {
      if (matches(url, s.app.prefix)) {
        if (s.state.ready || (await s.state.whenReady(15000))) return s.state;
        break; // ứng dụng phụ chưa chạy được -> để site chính phục vụ trang cũ
      }
    }
    if (!main.ready) await main.whenReady(30000);
    return main;
  };

  const server = http.createServer(async (req, res) => {
    let target;
    try {
      target = await pickTarget(req.url || "/");
    } catch {
      target = main;
    }
    const headers = { ...req.headers };
    for (const h of HOP) if (h !== "transfer-encoding") delete headers[h];
    if (target !== main) for (const h of STRIP_SUB) delete headers[h];
    const up = http.request(
      { host: "127.0.0.1", port: target.port, method: req.method, path: req.url, headers, agent },
      (pr) => {
        const out = { ...pr.headers };
        for (const h of HOP) delete out[h];
        res.writeHead(pr.statusCode || 502, pr.statusMessage, out);
        pr.pipe(res);
        pr.on("error", () => res.destroy());
      }
    );
    up.on("error", (err) => {
      if (!res.headersSent) {
        res.writeHead(502, { "content-type": "text/plain; charset=utf-8", "retry-after": "5" });
        res.end("Máy chủ đang khởi động hoặc tạm thời không phản hồi, vui lòng tải lại sau ít giây.");
      } else res.destroy();
      console.error(`[hue-research] proxy -> ${target.name}: ${err.code || err.message} ${req.method} ${req.url}`);
    });
    req.pipe(up);
    req.on("aborted", () => up.destroy());
  });

  // WebSocket / upgrade (nếu có) chuyển thẳng tới đích.
  server.on("upgrade", async (req, socket, head) => {
    const target = await pickTarget(req.url || "/");
    const conn = net.connect(target.port, "127.0.0.1", () => {
      const lines = [`${req.method} ${req.url} HTTP/${req.httpVersion}`];
      for (let i = 0; i < req.rawHeaders.length; i += 2) lines.push(`${req.rawHeaders[i]}: ${req.rawHeaders[i + 1]}`);
      conn.write(lines.join("\r\n") + "\r\n\r\n");
      if (head && head.length) conn.write(head);
      socket.pipe(conn).pipe(socket);
    });
    conn.on("error", () => socket.destroy());
    socket.on("error", () => conn.destroy());
  });

  server.keepAliveTimeout = 65000;
  server.headersTimeout = 66000;
  server.requestTimeout = 0;
  server.listen(PUBLIC_PORT, PUBLIC_HOST, () => {
    const list = subs.map((s) => `${s.app.name} :${s.state.port} (${s.app.prefix})`).join(", ");
    console.log(`[hue-research] Proxy công khai ${PUBLIC_HOST}:${PUBLIC_PORT} -> site chính :${ports.main}, ${list}.`);
  });

  const stopAll = () => {
    for (const s of all) {
      s.stopping = true;
      try {
        s.child && s.child.kill("SIGTERM");
      } catch {
        /* bỏ qua */
      }
    }
  };
  const shutdown = (sig) => {
    console.log(`[hue-research] Nhận ${sig}, dừng các tiến trình con.`);
    stopAll();
    server.close();
    setTimeout(() => process.exit(0), 3000).unref();
  };
  process.on("SIGTERM", () => shutdown("SIGTERM"));
  process.on("SIGINT", () => shutdown("SIGINT"));
  process.on("exit", stopAll);
  process.on("uncaughtException", (err) => console.error("[hue-research] Lỗi không bắt được trong proxy:", err));
}
