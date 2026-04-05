import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Mail, Calendar, LogOut, RefreshCw,
  ChevronLeft, ChevronRight, Inbox,
  CheckCircle, AlertCircle, Users, Zap, X
} from "lucide-react";

const BACKEND = "http://127.0.0.1:5000";

// ─── Types ───────────────────────────────────────────────────────────────────
interface Email {
  id: string;
  from: string;
  subject: string;
  body: string;
  status: string;
  tag: string;
}

interface DaySlot {
  hour: number;
  busy: boolean;
  event?: string;
}

type Tab = "emails" | "calendar";

// ─── Helpers ─────────────────────────────────────────────────────────────────
function statusMeta(status: string) {
  if (!status) return { dot: "bg-slate-300", pill: "bg-slate-100 text-slate-500" };
  if (status.includes("✅") || status.includes("Scheduled"))
    return { dot: "bg-emerald-400", pill: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200" };
  if (status.includes("🤖") || status.includes("Booked"))
    return { dot: "bg-blue-400",    pill: "bg-blue-50 text-blue-700 ring-1 ring-blue-200" };
  if (status.includes("🔁") || status.includes("Rescheduled"))
    return { dot: "bg-violet-400",  pill: "bg-violet-50 text-violet-700 ring-1 ring-violet-200" };
  if (status.includes("🟡") || status.includes("Busy"))
    return { dot: "bg-amber-400",   pill: "bg-amber-50 text-amber-700 ring-1 ring-amber-200" };
  if (status.includes("❌") || status.includes("No "))
    return { dot: "bg-red-400",     pill: "bg-red-50 text-red-700 ring-1 ring-red-200" };
  if (status.includes("❓") || status.includes("Ambiguous"))
    return { dot: "bg-orange-400",  pill: "bg-orange-50 text-orange-700 ring-1 ring-orange-200" };
  return { dot: "bg-slate-300",   pill: "bg-slate-100 text-slate-500" };
}

function initials(from: string) {
  const name = from.split("@")[0].replace(/[._-]/g, " ");
  const parts = name.split(" ").filter(Boolean);
  return parts.length >= 2
    ? (parts[0][0] + parts[1][0]).toUpperCase()
    : name.slice(0, 2).toUpperCase();
}

const AVATAR_COLORS = [
  "from-blue-500 to-blue-600",
  "from-violet-500 to-violet-600",
  "from-emerald-500 to-emerald-600",
  "from-amber-500 to-amber-600",
  "from-rose-500 to-rose-600",
  "from-cyan-500 to-cyan-600",
  "from-indigo-500 to-indigo-600",
];
function avatarColor(from: string) {
  let h = 0;
  for (let i = 0; i < from.length; i++) h = from.charCodeAt(i) + ((h << 5) - h);
  return AVATAR_COLORS[Math.abs(h) % AVATAR_COLORS.length];
}

// ─── Email row ────────────────────────────────────────────────────────────────
function EmailRow({ mail, index }: { mail: Email; index: number }) {
  const [open, setOpen] = useState(false);
  const { dot, pill } = statusMeta(mail.status);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.035, duration: 0.28 }}
      className="group"
    >
      <div
        onClick={() => setOpen(!open)}
        className="flex cursor-pointer items-start gap-4 rounded-2xl border border-slate-200/50 bg-white px-5 py-4 transition-all hover:border-slate-300/60 hover:shadow-[0_4px_24px_rgba(15,23,42,0.07)]"
      >
        {/* Avatar */}
        <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br ${avatarColor(mail.from)} text-white text-[11px] font-bold shadow-sm`}>
          {initials(mail.from)}
        </div>

        {/* Content */}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
            <span className="text-sm font-semibold text-slate-800 truncate max-w-[260px]">
              {mail.from}
            </span>
            <div className="flex items-center gap-2 shrink-0">
              {mail.tag?.includes("Meeting") && (
                <span className="rounded-full bg-indigo-100 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-indigo-700">
                  Meeting
                </span>
              )}
            </div>
          </div>

          <p className="mt-0.5 text-sm text-slate-600 truncate">
            {mail.subject || <span className="italic text-slate-400">(no subject)</span>}
          </p>

          {open && mail.body && (
            <motion.p
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="mt-2 text-xs leading-relaxed text-slate-500 border-t border-slate-100 pt-2"
            >
              {mail.body}
            </motion.p>
          )}
        </div>

        {/* Status + dot */}
        <div className="flex shrink-0 flex-col items-end gap-2">
          <div className={`flex items-center gap-1.5`}>
            <span className={`h-2 w-2 rounded-full ${dot}`} />
          </div>
          {mail.status && (
            <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${pill}`}>
              {mail.status}
            </span>
          )}
        </div>
      </div>
    </motion.div>
  );
}

// ─── Calendar ────────────────────────────────────────────────────────────────
function CalendarView() {
  const today = new Date();
  const [cur, setCur] = useState(today);
  const [slots, setSlots] = useState<DaySlot[]>([]);
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [busyDays, setBusyDays] = useState<number[]>([]);

  const yr = cur.getFullYear();
  const mo = cur.getMonth();
  const dateStr = cur.toISOString().split("T")[0];
  const daysInMonth = new Date(yr, mo + 1, 0).getDate();
  const firstDow = new Date(yr, mo, 1).getDay();
  const monthLabel = cur.toLocaleString("default", { month: "long", year: "numeric" });

  useEffect(() => {
    fetch(`${BACKEND}/month_overview/${yr}/${mo + 1}`)
      .then(r => r.json()).then(d => setBusyDays(Array.isArray(d) ? d : [])).catch(() => setBusyDays([]));
  }, [yr, mo]);

  useEffect(() => {
    setSlotsLoading(true);
    fetch(`${BACKEND}/day_slots/${dateStr}`)
      .then(r => r.json()).then(d => { setSlots(Array.isArray(d) ? d : []); setSlotsLoading(false); })
      .catch(() => { setSlots([]); setSlotsLoading(false); });
  }, [dateStr]);

  const isToday = (d: number) => d === today.getDate() && mo === today.getMonth() && yr === today.getFullYear();
  const isSel   = (d: number) => d === cur.getDate();

  return (
    <div className="grid gap-5 lg:grid-cols-[340px_1fr]">
      {/* Mini calendar */}
      <div className="rounded-2xl border border-slate-200/50 bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between mb-5">
          <span className="text-sm font-semibold text-slate-800">{monthLabel}</span>
          <div className="flex gap-0.5">
            <button onClick={() => setCur(new Date(yr, mo - 1, cur.getDate()))}
              className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition-colors">
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button onClick={() => setCur(new Date(yr, mo + 1, cur.getDate()))}
              className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition-colors">
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Day-of-week headers */}
        <div className="grid grid-cols-7 mb-2">
          {["Su","Mo","Tu","We","Th","Fr","Sa"].map(d => (
            <div key={d} className="text-center text-[11px] font-medium text-slate-400 py-1">{d}</div>
          ))}
        </div>

        {/* Days grid */}
        <div className="grid grid-cols-7 gap-y-1">
          {Array.from({ length: firstDow }).map((_, i) => <div key={`e${i}`} />)}
          {Array.from({ length: daysInMonth }).map((_, i) => {
            const day = i + 1;
            const busy = busyDays.includes(day);
            const sel  = isSel(day);
            const tod  = isToday(day);
            return (
              <button key={day} onClick={() => setCur(new Date(yr, mo, day))}
                className={`relative mx-auto flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium transition-all
                  ${sel  ? "bg-slate-900 text-white shadow"
                  : tod  ? "bg-blue-100 text-blue-700"
                  :        "text-slate-600 hover:bg-slate-100"}`}>
                {day}
                {busy && !sel && (
                  <span className="absolute bottom-0.5 left-1/2 -translate-x-1/2 h-1 w-1 rounded-full bg-blue-500" />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Day slots */}
      <div className="rounded-2xl border border-slate-200/50 bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-sm font-semibold text-slate-800">
              {cur.toLocaleDateString("default", { weekday: "long", month: "long", day: "numeric" })}
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">Daily schedule</p>
          </div>
          {/* Legend */}
          <div className="flex items-center gap-4 text-xs text-slate-500">
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-emerald-400"/>Free</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-rose-400"/>Busy</span>
          </div>
        </div>

        {slotsLoading ? (
          <div className="flex items-center justify-center py-16">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-slate-200 border-t-blue-500" />
          </div>
        ) : slots.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100">
              <Calendar className="h-6 w-6 text-slate-300" />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-600">No schedule data</p>
              <p className="text-xs text-slate-400 mt-0.5">Calendar access requires Google login</p>
            </div>
          </div>
        ) : (
          <div className="space-y-1.5 max-h-72 overflow-y-auto pr-1 scrollbar-thin">
            {slots.map(slot => (
              <div key={slot.hour} className={`flex items-center gap-3 rounded-xl px-4 py-2.5 ${slot.busy ? "bg-rose-50 border border-rose-100" : "bg-emerald-50 border border-emerald-100"}`}>
                <span className="w-12 shrink-0 font-mono text-xs text-slate-500">
                  {String(slot.hour).padStart(2,"0")}:00
                </span>
                <span className={`h-2 w-2 rounded-full shrink-0 ${slot.busy ? "bg-rose-400" : "bg-emerald-400"}`} />
                <span className="truncate text-xs font-medium text-slate-700">
                  {slot.busy ? (slot.event || "Busy") : "Available"}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Main App Page ────────────────────────────────────────────────────────────
export default function AppPage() {
  const [tab, setTab]         = useState<Tab>("emails");
  const [emails, setEmails]   = useState<Email[]>([]);
  const [loading, setLoading] = useState(true);
  const [spinning, setSpinning] = useState(false);
  const [today, setToday]     = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selected, setSelected] = useState<Email | null>(null);

  const load = (refresh = false) => {
    if (refresh) setSpinning(true); else setLoading(true);
    fetch(`${BACKEND}/emails`)
      .then(r => r.json())
      .then(d => {
        setEmails(Array.isArray(d.emails) ? d.emails : []);
        setToday(d.today || "");
        setLoading(false); setSpinning(false);
      })
      .catch(() => { setLoading(false); setSpinning(false); });
  };

  useEffect(() => { load(); }, []);

  const stats = [
    { label: "Total",      value: emails.length,                                                              icon: <Inbox className="h-4 w-4" />,       color: "text-slate-600 bg-slate-100" },
    { label: "Meetings",   value: emails.filter(e => e.tag?.includes("Meeting")).length,                      icon: <Users className="h-4 w-4" />,        color: "text-indigo-600 bg-indigo-100" },
    { label: "Scheduled",  value: emails.filter(e => e.status?.includes("✅") || e.status?.includes("🤖")).length, icon: <CheckCircle className="h-4 w-4" />, color: "text-emerald-600 bg-emerald-100" },
    { label: "Attention",  value: emails.filter(e => e.status?.includes("🟡") || e.status?.includes("❌")).length, icon: <AlertCircle className="h-4 w-4" />, color: "text-amber-600 bg-amber-100" },
  ];

  return (
    <div className="flex h-screen overflow-hidden bg-[#f5f5f7]">
      {/* ── Sidebar ── */}
      <aside className="flex w-[68px] shrink-0 flex-col items-center gap-3 border-r border-slate-200/70 bg-white/80 py-5 backdrop-blur-xl">
        {/* Logo */}
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[linear-gradient(135deg,#2563eb,#4f46e5)] text-white shadow-lg">
          <Mail className="h-[18px] w-[18px]" />
        </div>

        <div className="mt-4 flex flex-1 flex-col items-center gap-1.5">
          <button
            onClick={() => setTab("emails")}
            title="Inbox"
            className={`flex h-10 w-10 items-center justify-center rounded-xl transition-all
              ${tab === "emails" ? "bg-slate-900 text-white shadow" : "text-slate-400 hover:bg-slate-100 hover:text-slate-700"}`}
          >
            <Inbox className="h-5 w-5" />
          </button>
          <button
            onClick={() => setTab("calendar")}
            title="Calendar"
            className={`flex h-10 w-10 items-center justify-center rounded-xl transition-all
              ${tab === "calendar" ? "bg-slate-900 text-white shadow" : "text-slate-400 hover:bg-slate-100 hover:text-slate-700"}`}
          >
            <Calendar className="h-5 w-5" />
          </button>
        </div>

        <button
          onClick={() => { window.location.href = `${BACKEND}/logout`; }}
          title="Logout"
          className="flex h-10 w-10 items-center justify-center rounded-xl text-slate-400 hover:bg-red-50 hover:text-red-500 transition-all"
        >
          <LogOut className="h-4 w-4" />
        </button>
      </aside>

      {/* ── Main ── */}
      <main className="flex flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex items-center justify-between border-b border-slate-200/60 bg-white/70 px-8 py-4 backdrop-blur-xl">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-slate-900"
                style={{ fontFamily: "Playfair Display, Georgia, serif" }}>
              {tab === "emails" ? "Inbox" : "Calendar"}
            </h1>
            {today && <p className="text-xs text-slate-400 mt-0.5">{today}</p>}
          </div>
          {tab === "emails" && (
            <button
              onClick={() => load(true)}
              disabled={spinning}
              className="flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 shadow-sm transition-all hover:shadow-md disabled:opacity-40"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${spinning ? "animate-spin" : ""}`} />
              Refresh
            </button>
          )}
        </header>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto px-8 py-6">
          <AnimatePresence mode="wait">
            {tab === "emails" ? (
              <motion.div key="emails" initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}>
                {/* Stats */}
                {!loading && emails.length > 0 && (
                  <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {stats.map(s => (
                      <div key={s.label} className="flex items-center gap-3 rounded-2xl border border-slate-200/50 bg-white px-4 py-3 shadow-sm">
                        <div className={`flex h-8 w-8 items-center justify-center rounded-xl ${s.color}`}>{s.icon}</div>
                        <div>
                          <div className="text-lg font-semibold text-slate-900 leading-none">{s.value}</div>
                          <div className="text-[11px] text-slate-400 mt-0.5">{s.label}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Email list */}
                {loading ? (
                  <div className="flex flex-col items-center justify-center py-32 gap-4">
                    <div className="relative h-12 w-12">
                      <div className="absolute inset-0 rounded-full border-2 border-slate-100" />
                      <div className="absolute inset-0 rounded-full border-2 border-t-blue-500 animate-spin" />
                    </div>
                    <div className="text-center">
                      <p className="text-sm font-medium text-slate-700">Processing your inbox…</p>
                      <p className="text-xs text-slate-400 mt-1">AI is reading and scheduling meetings</p>
                    </div>
                  </div>
                ) : emails.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-32 text-center gap-4">
                    <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-slate-100">
                      <Inbox className="h-8 w-8 text-slate-300" />
                    </div>
                    <div>
                      <p className="font-medium text-slate-700">No emails found</p>
                      <p className="text-sm text-slate-400 mt-1">Make sure you're signed in with Google</p>
                    </div>
                    <button
                      onClick={() => { window.location.href = `${BACKEND}/login`; }}
                      className="mt-1 rounded-full bg-slate-900 px-5 py-2 text-sm font-medium text-white hover:bg-slate-800 transition-colors"
                    >
                      Sign in with Google
                    </button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {emails.map((mail, i) => (
                      <EmailRow key={mail.id || i} mail={mail} index={i} />
                    ))}
                  </div>
                )}
              </motion.div>
            ) : (
              <motion.div key="calendar" initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}>
                <CalendarView />
                <div className="mt-5 flex items-start gap-3 rounded-2xl border border-blue-100 bg-blue-50/70 p-4">
                  <Zap className="h-4 w-4 text-blue-500 mt-0.5 shrink-0" />
                  <p className="text-sm text-blue-700">
                    <strong>AI Scheduler active</strong> — MailFlow automatically detects meeting requests in your inbox and books calendar events. Blue dots mark days with existing events.
                  </p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>
    </div>
  );
}
