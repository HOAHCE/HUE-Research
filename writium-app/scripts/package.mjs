// Đóng gói bản build standalone thành thư mục dist/writium để chép vào httpdocs/writium trên hosting.
//   npm run build && npm run package
import { cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execSync } from "node:child_process";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const out = path.join(root, "dist", "writium");
rmSync(path.join(root, "dist"), { recursive: true, force: true });
mkdirSync(out, { recursive: true });
cpSync(path.join(root, ".next", "standalone"), out, { recursive: true });
cpSync(path.join(root, ".next", "static"), path.join(out, ".next", "static"), { recursive: true });
if (existsSync(path.join(root, "public"))) cpSync(path.join(root, "public"), path.join(out, "public"), { recursive: true });
// Không dùng tối ưu ảnh của Next -> bỏ sharp/@img (≈ 28 MB).
for (const d of ["node_modules/@img", "node_modules/sharp"]) rmSync(path.join(out, d), { recursive: true, force: true });
let commit = "";
try { commit = execSync("git rev-parse --short HEAD", { cwd: root }).toString().trim(); } catch {}
writeFileSync(path.join(out, "BUILD.json"), JSON.stringify({ app: "writium", commit, builtAt: new Date().toISOString(), node: process.version }, null, 2));
console.log("[writium] gói nằm ở", out);
