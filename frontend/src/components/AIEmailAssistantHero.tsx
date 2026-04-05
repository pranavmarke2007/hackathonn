import React from "react";
import { motion } from "framer-motion";
import { Mail, Sparkles, CalendarDays, BrainCircuit } from "lucide-react";

const BACKEND = "http://127.0.0.1:5000";

const labels = [
  { text: "Takes Data", delay: 0, radiusX: 272, radiusY: 150 },
  { text: "Analyzes", delay: 1.2, radiusX: 242, radiusY: 136 },
  { text: "Schedules", delay: 2.4, radiusX: 214, radiusY: 122 },
  { text: "Replies", delay: 3.6, radiusX: 186, radiusY: 108 },
];

const orbitPath = (radiusX: number, radiusY: number) => {
  const pts = [
    { x: 0, y: -radiusY },
    { x: radiusX * 0.72, y: -radiusY * 0.52 },
    { x: radiusX, y: 0 },
    { x: radiusX * 0.72, y: radiusY * 0.52 },
    { x: 0, y: radiusY },
    { x: -radiusX * 0.72, y: radiusY * 0.52 },
    { x: -radiusX, y: 0 },
    { x: -radiusX * 0.72, y: -radiusY * 0.52 },
    { x: 0, y: -radiusY },
  ];
  return { x: pts.map((p) => p.x), y: pts.map((p) => p.y) };
};

const OrbitArrow = ({
  text,
  delay = 0,
  radiusX,
  radiusY,
}: {
  text: string;
  delay?: number;
  radiusX: number;
  radiusY: number;
}) => {
  const path = orbitPath(radiusX, radiusY);
  return (
    <motion.div
      className="absolute left-1/2 top-1/2 z-30"
      animate={{ x: path.x, y: path.y }}
      transition={{ duration: 10, repeat: Infinity, ease: "linear", delay }}
      style={{ marginLeft: -96, marginTop: -18 }}
    >
      <motion.div
        animate={{
          scale: [0.9, 0.98, 1, 0.98, 0.9, 0.8, 0.72, 0.8, 0.9],
          opacity: [0.2, 0.5, 1, 0.95, 0.8, 0.28, 0.12, 0.18, 0.2],
          filter: [
            "blur(1px)", "blur(0.5px)", "blur(0px)", "blur(0px)",
            "blur(0.3px)", "blur(1.2px)", "blur(2.4px)", "blur(1.6px)", "blur(1px)",
          ],
        }}
        transition={{ duration: 10, repeat: Infinity, ease: "linear", delay }}
        className="relative"
      >
        <div className="absolute inset-0 rounded-full bg-sky-300/20 blur-2xl" />
        <div className="relative flex items-center gap-2 rounded-full border border-white/60 bg-white/70 px-4 py-2 backdrop-blur-2xl shadow-[0_10px_40px_rgba(15,23,42,0.10)]">
          <div className="h-2 w-2 rounded-full bg-sky-500" />
          <span className="whitespace-nowrap text-[10px] font-semibold uppercase tracking-[0.28em] text-slate-700">
            {text}
          </span>
          <div className="relative ml-1 h-px w-16 overflow-visible bg-gradient-to-r from-sky-400 via-cyan-400 to-indigo-500">
            <div className="absolute -right-1.5 -top-[4px] h-0 w-0 border-b-[5px] border-l-[9px] border-t-[5px] border-b-transparent border-l-indigo-500 border-t-transparent" />
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
};

const FloatingChip = ({
  icon,
  text,
  className,
}: {
  icon: React.ReactNode;
  text: string;
  className: string;
}) => (
  <motion.div
    className={`absolute rounded-[26px] border border-white/60 bg-white/45 px-4 py-3 backdrop-blur-2xl shadow-[0_20px_80px_rgba(15,23,42,0.08)] ${className}`}
    animate={{ y: [0, -10, 0], opacity: [0.84, 1, 0.84] }}
    transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
  >
    <div className="flex items-center gap-3">
      <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-950 text-white shadow-[0_8px_30px_rgba(2,6,23,0.25)]">
        {icon}
      </div>
      <div>
        <p className="text-[10px] font-medium uppercase tracking-[0.24em] text-slate-400">AI Action</p>
        <p className="text-sm font-semibold text-slate-800">{text}</p>
      </div>
    </div>
  </motion.div>
);

const GlassStat = ({ value, label }: { value: string; label: string }) => (
  <div className="rounded-[28px] border border-white/60 bg-white/40 p-5 backdrop-blur-2xl shadow-[0_14px_50px_rgba(15,23,42,0.06)]">
    <div className="text-2xl font-semibold tracking-[-0.04em] text-slate-950">{value}</div>
    <div className="mt-1 text-sm text-slate-500">{label}</div>
  </div>
);

export default function AIEmailAssistantHero() {
  const handleLogin = () => {
    window.location.href = `${BACKEND}/login`;
  };

  return (
    <div className="min-h-screen overflow-hidden bg-[#f5f5f7] text-slate-900">
      {/* Background layers — identical to screenshot */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(255,255,255,0.95),_transparent_28%),radial-gradient(circle_at_80%_20%,_rgba(186,230,253,0.5),_transparent_26%),radial-gradient(circle_at_78%_72%,_rgba(196,181,253,0.28),_transparent_24%),linear-gradient(180deg,_#fbfbfd_0%,_#f5f5f7_52%,_#eff3f8_100%)]" />
      <div className="absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-white/80 to-transparent" />
      <div className="absolute left-[8%] top-[12%] h-[22rem] w-[22rem] rounded-full bg-sky-200/25 blur-3xl" />
      <div className="absolute right-[6%] top-[20%] h-[24rem] w-[24rem] rounded-full bg-indigo-200/20 blur-3xl" />

      {/* ── HEADER: exactly matches screenshot ── */}
      <header className="relative z-20 mx-auto flex w-full max-w-7xl items-center justify-between px-6 pt-6 lg:px-12">
        {/* Logo */}
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[linear-gradient(135deg,#2563eb,#4f46e5)] text-white shadow-[0_16px_40px_rgba(37,99,235,0.28)]">
            <Mail className="h-5 w-5" />
          </div>
          <div>
            <div
              className="text-2xl font-semibold tracking-[-0.04em] text-slate-900"
              style={{ fontFamily: "Playfair Display, Georgia, serif" }}
            >
              MailFlow
            </div>
            <div className="text-xs uppercase tracking-[0.28em] text-slate-400">AI Email Assistant</div>
          </div>
        </div>

        {/* Nav buttons — plain text exactly like screenshot */}
        <nav className="flex items-center gap-7">
          <button
            onClick={handleLogin}
            className="text-[15px] font-normal text-slate-700 hover:text-slate-900 transition-colors"
          >
            Log in
          </button>
          <button
            onClick={handleLogin}
            className="text-[15px] font-normal text-slate-700 hover:text-slate-900 transition-colors"
          >
            Sign up
          </button>
        </nav>
      </header>

      {/* ── HERO SECTION ── */}
      <section className="relative mx-auto grid min-h-screen max-w-7xl items-center gap-10 px-6 py-12 lg:grid-cols-[1.05fr_0.95fr] lg:px-12">
        {/* Left: copy */}
        <div className="relative z-10 max-w-2xl pt-6 lg:pt-0">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7 }}
            className="mb-7 inline-flex items-center gap-2 rounded-full border border-white/70 bg-white/55 px-4 py-2 backdrop-blur-2xl shadow-[0_8px_40px_rgba(15,23,42,0.05)]"
          >
            <Sparkles className="h-4 w-4 text-slate-700" />
            <span className="text-sm font-medium text-slate-700">AI Email Assistant</span>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.9, delay: 0.05 }}
            className="text-5xl leading-[0.95] tracking-[-0.04em] text-slate-900 sm:text-6xl lg:text-[5rem]"
            style={{ fontFamily: "Playfair Display, Georgia, serif" }}
          >
            <span className="block">Your inbox,</span>
            <span className="block bg-gradient-to-r from-blue-600 to-indigo-500 bg-clip-text italic text-transparent">
              intelligently
            </span>
            <span className="block">managed.</span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.15 }}
            className="mt-7 max-w-xl text-[1.08rem] leading-8 text-slate-600"
          >
            A calm, premium AI workspace that reads your inbox, understands intent, extracts signals,
            and schedules meetings with near-instant clarity.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.9, delay: 0.35 }}
            className="mt-12 grid max-w-xl grid-cols-1 gap-3 sm:grid-cols-2"
          >
            <GlassStat value="99%" label="Intent clarity" />
            <GlassStat value="24/7" label="Inbox awareness" />
          </motion.div>
        </div>

        {/* Right: orbit visual */}
        <div className="relative z-10 flex min-h-[640px] items-center justify-center">
          <div className="relative h-[620px] w-full max-w-[720px]">
            {/* Glow blobs */}
            <div className="absolute left-1/2 top-1/2 h-[470px] w-[470px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-white/35 blur-3xl" />
            <div className="absolute left-1/2 top-1/2 h-[430px] w-[430px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/40 bg-white/18 backdrop-blur-[2px]" />
            <div className="absolute left-1/2 top-1/2 h-[350px] w-[350px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/45 bg-gradient-to-b from-white/35 to-white/10 backdrop-blur-xl shadow-[0_30px_120px_rgba(148,163,184,0.12)]" />
            <div className="absolute left-1/2 top-1/2 h-[290px] w-[460px] -translate-x-1/2 -translate-y-1/2 rounded-[100%] border border-white/35 opacity-70" />
            <div className="absolute left-1/2 top-1/2 h-[220px] w-[380px] -translate-x-1/2 -translate-y-1/2 rounded-[100%] border border-white/25 opacity-55" />

            {/* Floating chips */}
            <FloatingChip
              icon={<BrainCircuit className="h-5 w-5" />}
              text="Intent Analysis Active"
              className="left-3 top-16"
            />
            <FloatingChip
              icon={<CalendarDays className="h-5 w-5" />}
              text="Meeting Slot Ready"
              className="bottom-20 right-2"
            />

            {/* Orbiting labels */}
            {labels.map((item) => (
              <OrbitArrow
                key={item.text}
                text={item.text}
                delay={item.delay}
                radiusX={item.radiusX}
                radiusY={item.radiusY}
              />
            ))}

            {/* Central mail icon card */}
            <div className="absolute left-1/2 top-1/2 z-10 flex h-[250px] w-[250px] -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-[3rem] border border-white/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.85),rgba(255,255,255,0.58))] backdrop-blur-3xl shadow-[0_35px_140px_rgba(15,23,42,0.09)]">
              <div className="absolute inset-[14px] rounded-[2.4rem] border border-white/75 bg-[radial-gradient(circle_at_30%_20%,rgba(255,255,255,0.98),rgba(255,255,255,0.58)_42%,rgba(241,245,249,0.7)_100%)]" />
              <div className="absolute inset-[30px] rounded-[2rem] border border-slate-200/60 bg-[linear-gradient(180deg,rgba(255,255,255,0.92),rgba(241,245,249,0.8))] shadow-inner" />
              <motion.div
                className="absolute inset-0 rounded-[3rem]"
                animate={{ rotate: 360 }}
                transition={{ duration: 30, repeat: Infinity, ease: "linear" }}
              >
                <div className="absolute left-1/2 top-4 h-3 w-3 -translate-x-1/2 rounded-full bg-sky-300/80 blur-[1px]" />
                <div className="absolute bottom-5 left-8 h-3 w-3 rounded-full bg-indigo-200/80 blur-[1px]" />
                <div className="absolute right-7 top-1/2 h-4 w-4 -translate-y-1/2 rounded-full bg-cyan-200/80 blur-[1px]" />
              </motion.div>
              <motion.div
                animate={{ y: [0, -7, 0], rotateX: [0, 4, 0] }}
                transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}
                className="relative z-10 flex h-32 w-32 items-center justify-center rounded-[2rem] bg-[linear-gradient(180deg,#0f172a,#111827)] text-white shadow-[0_20px_80px_rgba(2,6,23,0.32)]"
              >
                <div className="absolute inset-0 rounded-[2rem] bg-[radial-gradient(circle_at_30%_20%,rgba(255,255,255,0.16),transparent_42%)]" />
                <Mail className="relative z-10 h-14 w-14" />
              </motion.div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
