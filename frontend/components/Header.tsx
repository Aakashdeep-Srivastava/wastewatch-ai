import Image from "next/image";
import Link from "next/link";

export default function Header({ active }: { active: "inspect" | "dashboard" }) {
  const link = "rounded-lg px-3 py-1.5 text-sm font-semibold";
  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6">
      <div className="flex items-center gap-3">
        <Image src="/logo.png" width={38} height={38} alt="WasteWatch AI" className="rounded-lg" priority />
        <div>
          <h1 className="text-base font-bold leading-tight">WasteWatch AI</h1>
          <p className="text-xs text-slate-500">Satellite Environmental Intelligence</p>
        </div>
      </div>
      <nav className="flex items-center gap-2">
        <Link href="/" className={`${link} ${active === "inspect" ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"}`}>
          New Inspection
        </Link>
        <Link href="/dashboard" className={`${link} ${active === "dashboard" ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"}`}>
          Dashboard
        </Link>
      </nav>
    </header>
  );
}
