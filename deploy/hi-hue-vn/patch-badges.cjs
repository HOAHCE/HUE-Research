"use strict";
// Bỏ nhãn "sắp có" của các công cụ ĐÃ chạy (Viết nghiên cứu, Trắc lượng thư mục) trong bản build sẵn của site chính
// (./server/.next) và cập nhật mô tả công cụ Viết nghiên cứu. Dùng khi chưa có mã nguồn để build lại site chính.
//
//   node patch-badges.cjs --dry     chỉ báo cáo, không ghi
//   node patch-badges.cjs           sao lưu các tệp sẽ sửa vào ../hue-data/backup-badges-<thời điểm>.tgz rồi ghi
//
// Chạy lại nhiều lần không sao (lần sau không còn gì để sửa). Sau khi ghi: Khởi động lại ứng dụng.
const fs = require("node:fs");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

const ROOT = __dirname;
const NEXT_DIR = path.join(ROOT, "server", ".next");
const DRY = process.argv.includes("--dry");

const TOOLS = [
  { alias: "writium", name: "Viết nghiên cứu" },
  { alias: "bibliomap", name: "Trắc lượng thư mục" },
];
const OLD_DESC = "Soạn bài báo/báo cáo có AI hỗ trợ, xuất DOCX.";
const NEW_DESC = "Từ ý tưởng, dữ liệu và kết quả thực nghiệm đến bản thảo bài báo: đa tác tử AI lập dàn ý, tìm tài liệu đã kiểm chứng, viết, tự phản biện và xuất LaTeX/PDF theo mẫu tạp chí.";
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function patchText(t) {
  let n = 0;
  const rep = (re, by) => {
    t = t.replace(re, (...m) => {
      n++;
      return typeof by === "function" ? by(...m) : by;
    });
  };
  for (const { alias, name } of TOOLS) {
    const A = esc(alias);
    const N = esc(name);
    // 1) Dữ liệu registry trong JS: {alias:"x",...,status:"soon",...}
    rep(new RegExp(`(\\{alias:"${A}",[^{}]*?status:")soon(")`, "g"), (_m, a, b) => `${a}ready${b}`);
    // 2) Dữ liệu dạng JSON trong RSC, thường và đã thoát chuỗi (\")
    rep(new RegExp(`("alias":"${A}"[^{}]*?"status":")soon(")`, "g"), (_m, a, b) => `${a}ready${b}`);
    rep(new RegExp(`(\\\\"alias\\\\":\\\\"${A}\\\\"[^{}]*?\\\\"status\\\\":\\\\")soon(\\\\")`, "g"), (_m, a, b) => `${a}ready${b}`);
    // 3) HTML đã kết xuất: nhãn <span ...>sắp có</span> nằm trong thẻ <a href="/tools/x">...</a>
    rep(new RegExp(`(<a[^>]*href="/tools/${A}"[^>]*>(?:(?!</a>)[\\s\\S]){0,4000}?)<(span|div)[^>]*>sắp có</\\2>`, "g"), (_m, a) => a);
    // 4) Trang Hướng dẫn: <strong>Tên</strong> (sắp có) — HTML và RSC (thường/thoát chuỗi)
    rep(new RegExp(`(<strong>${N}</strong>)(?:<!-- -->)? \\(sắp có\\)`, "g"), (_m, a) => a);
    rep(new RegExp(`(\\{"children":"${N}"\\}\\]),\" \\(sắp có\\)\"`, "g"), (_m, a) => a);
    rep(new RegExp(`(\\{\\\\"children\\\\":\\\\"${N}\\\\"\\}\\]),\\\\" \\(sắp có\\)\\\\"`, "g"), (_m, a) => a);
  }
  if (t.includes(OLD_DESC)) rep(new RegExp(esc(OLD_DESC), "g"), NEW_DESC);
  return { t, n };
}

const files = [];
const walk = (d) => {
  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    const f = path.join(d, e.name);
    if (e.isDirectory()) {
      if (e.name !== "cache") walk(f);
    } else if (/\.(js|html|rsc|json|body|txt)$/.test(e.name)) files.push(f);
  }
};
walk(NEXT_DIR);

const changed = [];
let total = 0;
for (const f of files) {
  const src = fs.readFileSync(f, "utf8");
  if (!/writium|bibliomap|sắp có/.test(src)) continue;
  const { t, n } = patchText(src);
  if (n > 0 && t !== src) {
    changed.push({ f, t, n });
    total += n;
  }
}

console.log(`[patch-badges] ${DRY ? "(chạy thử) " : ""}${changed.length} tệp, ${total} chỗ sửa.`);
for (const c of changed.slice(0, 80)) console.log(`  ${path.relative(ROOT, c.f)}  (${c.n})`);

// Còn sót "sắp có" gần hai công cụ? In ngữ cảnh để kiểm tra bằng mắt.
let leftovers = 0;
for (const f of files) {
  const t = changed.find((c) => c.f === f)?.t ?? fs.readFileSync(f, "utf8");
  for (const { alias } of TOOLS) {
    let i = t.indexOf(`/tools/${alias}"`);
    while (i >= 0) {
      const seg = t.slice(i, i + 1500);
      const end = seg.indexOf("</a>");
      const inside = end >= 0 ? seg.slice(0, end) : "";
      if (inside.includes("sắp có")) {
        leftovers++;
        if (leftovers <= 5) console.log(`  CÒN SÓT ${path.relative(ROOT, f)}: …${inside.replace(/<svg[\s\S]*?<\/svg>/g, "<svg/>").slice(0, 400)}…`);
      }
      i = t.indexOf(`/tools/${alias}"`, i + 1);
    }
  }
}
console.log(`[patch-badges] còn sót: ${leftovers}`);

if (!DRY && changed.length) {
  const dataDir = path.resolve(ROOT, "..", "hue-data");
  const stamp = new Date().toISOString().replace(/[-:]/g, "").slice(0, 15);
  const tgz = path.join(fs.existsSync(dataDir) ? dataDir : ROOT, `backup-badges-${stamp}.tgz`);
  execFileSync("tar", ["czf", tgz, ...changed.map((c) => path.relative(ROOT, c.f))], { cwd: ROOT });
  for (const c of changed) fs.writeFileSync(c.f, c.t);
  console.log(`[patch-badges] đã ghi; bản sao lưu: ${tgz}`);
  console.log("[patch-badges] Hoàn tác: tar xzf <tệp sao lưu> (chạy trong httpdocs) rồi Khởi động lại.");
}
