import type { Metadata } from "next";
import "./globals.css";
import { Shell } from "@/components/Shell";

export const metadata: Metadata = {
  title: "Viết nghiên cứu — HUE - Research",
  description: "Từ ý tưởng, dữ liệu và kết quả thực nghiệm đến bản thảo bài báo theo mẫu tạp chí (đa tác tử AI dựa trên PaperOrchestra).",
};

// Đặt giao diện tối trước khi vẽ trang, dùng chung khoá "hce.theme" với site chính.
const themeScript = `try{var t=localStorage.getItem('hce.theme')||'';if(t.indexOf('dark')>-1)document.documentElement.classList.add('dark')}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
