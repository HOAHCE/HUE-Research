"use strict";
// Cài/cập nhật mục Viết nghiên cứu trên hosting hi.hue.vn (Tenten/Plesk), chạy trong httpdocs:
//   node deploy-writium.cjs            tải gói từ GitHub, thay thư mục ./writium, cập nhật hce-start.cjs, bỏ nhãn "sắp có"
//   node deploy-writium.cjs --dry      chỉ kiểm tra tải được và báo cáo (không ghi)
// Sau đó bấm "Restart App" (Node.js) hoặc "Khởi động lại" ở Tenten 1-Click Launch.
//
// Sao lưu: hce-start.bibliomap.cjs (bản khởi động trước đó), writium.old/ (gói trước), ../hue-data/backup-badges-*.tgz.
const fs = require("node:fs");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

const REPO = process.env.WRITIUM_REPO || "HOAHCE/hue-research";
const SRC_REF = process.env.WRITIUM_SRC_REF || "claude/viet-bai-bao"; // nhánh chứa deploy/hi-hue-vn/*
const PKG_REF = process.env.WRITIUM_PKG_REF || "deploy/writium"; // nhánh chứa gói build sẵn (server.js ở gốc)
const DRY = process.argv.includes("--dry");
const ROOT = __dirname;
const log = (...a) => console.log("[deploy-writium]", ...a);
const sh = (cmd, args, opts = {}) => execFileSync(cmd, args, { cwd: ROOT, stdio: ["ignore", "pipe", "pipe"], encoding: "utf8", ...opts });

function download(url, dest) {
  sh("curl", ["-fsSL", "--retry", "3", "-o", dest, url]);
  const size = fs.statSync(dest).size;
  log("tải", url, `(${Math.round(size / 1024)} KB)`);
  return size;
}

const tmp = path.join(ROOT, ".tmp", `writium-${Date.now()}`);
fs.mkdirSync(tmp, { recursive: true });

// 1) Gói ứng dụng
const tgz = path.join(tmp, "pkg.tgz");
download(`https://codeload.github.com/${REPO}/tar.gz/refs/heads/${PKG_REF}`, tgz);
const unpack = path.join(tmp, "pkg");
fs.mkdirSync(unpack);
sh("tar", ["xzf", tgz, "-C", unpack, "--strip-components=1"]);
if (!fs.existsSync(path.join(unpack, "server.js")) || !fs.existsSync(path.join(unpack, ".next"))) throw new Error("Gói tải về thiếu server.js/.next");
const build = JSON.parse(fs.readFileSync(path.join(unpack, "BUILD.json"), "utf8"));
log("gói:", JSON.stringify(build));

// 2) Tệp khởi động + công cụ vá nhãn
const raw = (p) => `https://raw.githubusercontent.com/${REPO}/${SRC_REF}/${p}`;
const startNew = path.join(tmp, "hce-start.cjs");
const patchNew = path.join(tmp, "patch-badges.cjs");
download(raw("deploy/hi-hue-vn/hce-start.cjs"), startNew);
download(raw("deploy/hi-hue-vn/patch-badges.cjs"), patchNew);
sh(process.execPath, ["--check", startNew]);
sh(process.execPath, ["--check", patchNew]);

if (DRY) {
  log("chạy thử xong — chưa ghi gì. Thư mục tạm:", tmp);
  process.exit(0);
}

// 3) Thay thư mục writium (giữ bản trước ở writium.old)
const dest = path.join(ROOT, "writium");
const old = path.join(ROOT, "writium.old");
fs.rmSync(old, { recursive: true, force: true });
if (fs.existsSync(dest)) fs.renameSync(dest, old);
fs.renameSync(unpack, dest);
log("đã cài ./writium");

// 4) Tệp khởi động: giữ bản đang chạy (bản có BiblioMap) làm hce-start.bibliomap.cjs nếu chưa có
const start = path.join(ROOT, "hce-start.cjs");
const backup = path.join(ROOT, "hce-start.bibliomap.cjs");
if (fs.existsSync(start) && !fs.existsSync(backup) && !fs.readFileSync(start, "utf8").includes("WRITIUM_DISABLE")) {
  fs.copyFileSync(start, backup);
  log("đã sao lưu hce-start.cjs -> hce-start.bibliomap.cjs");
}
fs.copyFileSync(startNew, start);
fs.copyFileSync(patchNew, path.join(ROOT, "patch-badges.cjs"));
log("đã cập nhật hce-start.cjs, patch-badges.cjs");

// 5) Bỏ nhãn "sắp có" của các công cụ đã chạy trong site chính (có sao lưu)
if (!process.argv.includes("--no-badges")) {
  process.stdout.write(sh(process.execPath, [path.join(ROOT, "patch-badges.cjs")]));
}
fs.rmSync(tmp, { recursive: true, force: true });
log("XONG. Hãy Restart App để áp dụng.");
