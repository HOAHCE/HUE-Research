// Dùng chung một mã giao diện với site chính: chép components/PaperWriter.tsx từ hce-research.
import { copyFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
const here = path.dirname(fileURLToPath(import.meta.url));
const src = path.resolve(here, "../../hce-research/components/PaperWriter.tsx");
const dst = path.resolve(here, "../components/PaperWriter.tsx");
if (existsSync(src)) {
  copyFileSync(src, dst);
  console.log("[writium] đã chép PaperWriter.tsx từ hce-research");
} else if (!existsSync(dst)) {
  throw new Error("Không tìm thấy hce-research/components/PaperWriter.tsx");
}
