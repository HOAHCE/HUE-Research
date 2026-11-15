"use client";

// Khung trang giống site chính hi.hue.vn (thanh tiêu đề + thanh bên theo 6 giai đoạn), dùng chung kiểu với BiblioMap.
// Các liên kết là <a> thường vì trỏ sang site chính (ngoài basePath /tools/writium).
import { useEffect, useState } from "react";
import {
  Award, BarChart3, BookOpen, ClipboardList, FileText, FolderKanban, FolderSearch, Globe, LayoutGrid, ListChecks,
  ListTodo, Menu, MessageSquarePlus, MessagesSquare, Moon, Network, PenLine, ShieldCheck, Sun, UserRound, Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

type Item = { href: string; label: string; icon: LucideIcon; soon?: boolean };
const STAGES: { n: number; name: string; items: Item[] }[] = [
  { n: 1, name: "TÌM HIỂU", items: [
    { href: "/tools/experts", label: "Tìm kiếm chuyên gia", icon: Users },
    { href: "/tools/topics", label: "Đề tài khoa học", icon: FolderSearch },
  ] },
  { n: 2, name: "TỔNG QUAN TÀI LIỆU", items: [
    { href: "/tools/papers", label: "Tra cứu bài báo", icon: FileText },
    { href: "/tools/bibliomap", label: "Trắc lượng thư mục", icon: Network },
  ] },
  { n: 3, name: "THIẾT KẾ & THU THẬP DỮ LIỆU", items: [
    { href: "/tools/surveylab", label: "Thiết kế khảo sát", icon: ClipboardList },
  ] },
  { n: 4, name: "PHÂN TÍCH", items: [
    { href: "/tools/quantis", label: "Phân tích định lượng", icon: BarChart3 },
    { href: "/tools/annota", label: "Phân tích định tính", icon: MessagesSquare },
  ] },
  { n: 5, name: "VIẾT & PHẢN BIỆN", items: [
    { href: "/tools/writium", label: "Viết nghiên cứu", icon: PenLine },
    { href: "/tools/plagiarism", label: "Kiểm tra đạo văn", icon: ShieldCheck, soon: true },
    { href: "/tools/review", label: "Phản biện bài báo", icon: ListTodo, soon: true },
  ] },
  { n: 6, name: "CÔNG BỐ & TÀI TRỢ", items: [
    { href: "/tools/journals", label: "Hội thảo – tạp chí", icon: Globe },
    { href: "/tools/funds", label: "Tra cứu quỹ", icon: Award },
    { href: "/tools/regulations", label: "Quy trình, biểu mẫu", icon: ListChecks },
  ] },
];

const ACTIVE = "/tools/writium";

export function Shell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [dark, setDark] = useState(false);
  const [user, setUser] = useState<string | null>(null);

  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
    fetch("/tools/writium/api/paper/config")
      .then((r) => r.json())
      .then((c: { loggedIn?: boolean; userName?: string }) => setUser(c.loggedIn ? c.userName || "Tài khoản" : null))
      .catch(() => {});
  }, []);

  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("hce.theme", next ? "dark" : "light");
    } catch {}
  };

  return (
    <div className="hs-app">
      <header className="hs-header">
        <button type="button" className="hs-icon-btn hs-menu-btn" aria-label="Mở menu" onClick={() => setOpen((o) => !o)}>
          <Menu size={18} />
        </button>
        <a className="hs-brand" href="/">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.png" alt="Logo Trường Đại học Kinh tế, Đại học Huế" width={34} height={34} />
          <span>
            <span className="hs-brand-title">HUE - Research</span>
            <span className="hs-brand-sub">Trường Đại học Kinh tế, Đại học Huế</span>
          </span>
        </a>
        <div className="hs-actions">
          <button type="button" className="hs-icon-btn" aria-label={dark ? "Giao diện sáng" : "Giao diện tối"} title={dark ? "Giao diện sáng" : "Giao diện tối"} onClick={toggleTheme}>
            {dark ? <Sun size={17} /> : <Moon size={17} />}
          </button>
          {user ? (
            <a className="hs-user" href="/profile" title={user}><UserRound size={15} /><span>{user}</span></a>
          ) : (
            <a className="hs-login" href={`/login?next=${encodeURIComponent(ACTIVE)}`}>Đăng nhập</a>
          )}
        </div>
      </header>
      <div className="hs-body">
        <aside className={`hs-side ${open ? "hs-open" : ""}`}>
          <a className="hs-newchat" href="/chat"><MessageSquarePlus size={16} /> Trò chuyện mới</a>
          <nav className="hs-nav">
            <a href="/tools"><LayoutGrid size={16} /> Kho công cụ</a>
            <a href="/projects"><FolderKanban size={16} /> Dự án của tôi</a>
          </nav>
          {STAGES.map((s) => (
            <div key={s.n}>
              <div className="hs-stage"><span className="hs-stage-num">{s.n}</span>{s.name}</div>
              <nav className="hs-nav hs-sub">
                {s.items.map((it) => (
                  <a key={it.href} href={it.href} className={it.href === ACTIVE ? "hs-active" : ""} aria-current={it.href === ACTIVE ? "page" : undefined}>
                    <it.icon size={16} />
                    <span className="min-w-0 truncate">{it.label}</span>
                    {it.soon && <span className="hs-soon">sắp có</span>}
                  </a>
                ))}
              </nav>
            </div>
          ))}
          <div className="hs-sep" />
          <nav className="hs-nav">
            <a href="/huong-dan"><BookOpen size={16} /> Hướng dẫn sử dụng</a>
            <a href="/ai-responsibility"><ShieldCheck size={16} /> Dùng AI có trách nhiệm</a>
          </nav>
        </aside>
        <div className={`hs-overlay ${open ? "hs-open" : ""}`} onClick={() => setOpen(false)} />
        <main className="hs-main">{children}</main>
      </div>
    </div>
  );
}
