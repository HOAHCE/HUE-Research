// Ứng dụng tách riêng cho mục Viết nghiên cứu: phục vụ dưới /tools/writium, proxy của hce-start.cjs chuyển tiếp vào đây.
/** @type {import('next').NextConfig} */
const nextConfig = {
  basePath: "/tools/writium",
  output: "standalone",
  env: { NEXT_PUBLIC_PAPER_API: "/tools/writium/api/paper" },
  poweredByHeader: false,
};
export default nextConfig;
