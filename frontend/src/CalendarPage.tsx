import { useEffect, useState, useCallback } from "react";
import { ChevronLeft, ChevronRight, RefreshCw, Calendar, Mail, LogOut } from "lucide-react";
import { useNavigate } from "react-router-dom";

// ─── types ────────────────────────────────────────────────────────────────────
interface Slot {
  display: string;
  time: string;
  hour: number;
  status: "free" | "busy";
}

interface CalEvent {
  id: string;
  summary: string;
  start: string;
  end: string;
  attendees?: string[];
}

// ─── helpers ──────────────────────────────────────────────────────────────────
const pad = (n: number) => String(n).padStart(2, "0");

const MONTHS = [
  "January","February","March","April","May","June",
  "July","August","September","October","November","December",
];

const WEEKDAYS_SHORT = ["Su","Mo","Tu","We","Th","Fr","Sa"];

function toDateStr(y: number, m: number, d: number) {
  return `${y}-${pad(m + 1)}-${pad(d)}`;
}

function formatDateHeader(dateStr: string) {
  const [y, m, d] = dateStr.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  const weekday = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"][dt.getDay()];
  return `${weekday} ${d} ${MONTHS[m - 1]}`;
}

function formatEventTime(iso: string) {
  const d = new Date(iso);
  const h = d.getHours(), mn = d.getMinutes();
  const suffix = h >= 12 ? "pm" : "am";
  const hh = h % 12 || 12;
  return `${hh}:${pad(mn)} ${suffix}`;
}

// ─── component ────────────────────────────────────────────────────────────────
export default function CalendarPage() {
  const navigate = useNavigate();
  const today = new Date();
  const todayStr = toDateStr(today.getFullYear(), today.getMonth(), today.getDate());

  const [year, setYear]         = useState(today.getFullYear());
  const [month, setMonth]       = useState(today.getMonth());          // 0-based
  const [selectedDate, setSelectedDate] = useState(todayStr);
  const [slots, setSlots]       = useState<Slot[]>([]);
  const [busyDays, setBusyDays] = useState<number[]>([]);
  const [events, setEvents]     = useState<CalEvent[]>([]);
  const [evLoading, setEvLoading]   = useState(false);
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [evError, setEvError]   = useState("");

  // ── fetch slots for selected date ──────────────────────────────────────────
  const fetchSlots = useCallback(async (dateStr: string) => {
    setSlotsLoading(true);
    try {
      const res = await fetch(`/api/day_slots/${dateStr}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: Slot[] = await res.json();
      setSlots(data);
    } catch (e) {
      console.error("day_slots error:", e);
      setSlots([]);
    } finally {
      setSlotsLoading(false);
    }
  }, []);

  // ── fetch busy days for current month ──────────────────────────────────────
  const fetchBusyDays = useCallback(async (y: number, m: number) => {
    try {
      const res = await fetch(`/api/month_overview/${y}/${m + 1}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: number[] = await res.json();
      setBusyDays(data);
    } catch (e) {
      console.error("month_overview error:", e);
      setBusyDays([]);
    }
  }, []);

  // ── fetch upcoming AI-created events ───────────────────────────────────────
  const fetchEvents = useCallback(async () => {
    setEvLoading(true);
    setEvError("");
    try {
      const res = await fetch("/api/upcoming_events");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setEvents(data.events ?? []);
    } catch (e: any) {
      console.error("upcoming_events error:", e);
      setEvError("Could not reach backend.");
      setEvents([]);
    } finally {
      setEvLoading(false);
    }
  }, []);

  // ── initial load ───────────────────────────────────────────────────────────
  useEffect(() => {
    fetchSlots(selectedDate);
    fetchBusyDays(year, month);
    fetchEvents();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── re-fetch slots when date changes ───────────────────────────────────────
  useEffect(() => { fetchSlots(selectedDate); }, [selectedDate, fetchSlots]);

  // ── re-fetch busy days when month/year changes ─────────────────────────────
  useEffect(() => { fetchBusyDays(year, month); }, [year, month, fetchBusyDays]);

  // ── calendar nav ───────────────────────────────────────────────────────────
  function prevMonth() {
    if (month === 0) { setYear(y => y - 1); setMonth(11); }
    else setMonth(m => m - 1);
  }
  function nextMonth() {
    if (month === 11) { setYear(y => y + 1); setMonth(0); }
    else setMonth(m => m + 1);
  }

  // ── calendar grid ──────────────────────────────────────────────────────────
  const firstDow = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: (number | null)[] = [
    ...Array(firstDow).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];

  // ── render ─────────────────────────────────────────────────────────────────
  return (
    <div className="flex h-screen bg-gray-50 font-sans">

      {/* ── Sidebar ─────────────────────────────────────────────────── */}
      <aside className="w-14 flex flex-col items-center py-5 gap-5 bg-white border-r border-gray-100 shadow-sm">
        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-500 flex items-center justify-center text-white shadow">
          <Mail size={16} />
        </div>
        <button
          onClick={() => navigate("/app")}
          className="w-9 h-9 rounded-xl flex items-center justify-center text-gray-400 hover:bg-gray-100 transition"
          title="Inbox"
        >
          <Mail size={18} />
        </button>
        <button
          className="w-9 h-9 rounded-xl flex items-center justify-center bg-slate-900 text-white shadow"
          title="Calendar"
        >
          <Calendar size={18} />
        </button>
        <div className="flex-1" />
        <button
          onClick={() => (window.location.href = "/api/logout")}
          className="w-9 h-9 rounded-xl flex items-center justify-center text-gray-400 hover:bg-red-50 hover:text-red-500 transition"
          title="Logout"
        >
          <LogOut size={16} />
        </button>
      </aside>

      {/* ── Main ────────────────────────────────────────────────────── */}
      <main className="flex-1 overflow-y-auto p-6 space-y-6">

        {/* Header */}
        <div>
          <h1 className="text-xl font-semibold text-gray-800">Calendar</h1>
          <p className="text-xs text-gray-400 mt-0.5">{todayStr}</p>
        </div>

        {/* Top row: mini-calendar + day slots */}
        <div className="flex gap-5 items-start flex-wrap">

          {/* Mini calendar */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 w-72 shrink-0">
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm font-semibold text-gray-700">
                {MONTHS[month]} {year}
              </span>
              <div className="flex gap-1">
                <button onClick={prevMonth} className="p-1 rounded hover:bg-gray-100 text-gray-500 transition">
                  <ChevronLeft size={15} />
                </button>
                <button onClick={nextMonth} className="p-1 rounded hover:bg-gray-100 text-gray-500 transition">
                  <ChevronRight size={15} />
                </button>
              </div>
            </div>

            {/* Weekday headers */}
            <div className="grid grid-cols-7 mb-1">
              {WEEKDAYS_SHORT.map(d => (
                <div key={d} className="text-center text-[10px] text-gray-400 font-medium py-1">{d}</div>
              ))}
            </div>

            {/* Day cells */}
            <div className="grid grid-cols-7 gap-y-1">
              {cells.map((day, i) => {
                if (!day) return <div key={`e-${i}`} />;
                const ds = toDateStr(year, month, day);
                const isToday = ds === todayStr;
                const isSel   = ds === selectedDate;
                const isBusy  = busyDays.includes(day);
                return (
                  <button
                    key={ds}
                    onClick={() => setSelectedDate(ds)}
                    className={[
                      "relative flex items-center justify-center h-8 w-8 mx-auto rounded-full text-sm transition",
                      isSel
                        ? "bg-slate-900 text-white font-semibold"
                        : isToday
                        ? "border-2 border-blue-500 text-blue-600 font-semibold"
                        : "text-gray-700 hover:bg-gray-100",
                    ].join(" ")}
                  >
                    {day}
                    {isBusy && !isSel && (
                      <span className="absolute bottom-0.5 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-blue-500" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Day slots */}
          <div className="flex-1 min-w-0 bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-sm font-semibold text-gray-800">{formatDateHeader(selectedDate)}</h2>
                <p className="text-xs text-gray-400">Daily schedule</p>
              </div>
              <div className="flex items-center gap-3 text-xs text-gray-500">
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-400 inline-block"/>Free</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-400 inline-block"/>Busy</span>
              </div>
            </div>

            {slotsLoading ? (
              <div className="flex items-center justify-center h-40 text-gray-400 text-sm">Loading…</div>
            ) : slots.length === 0 ? (
              <div className="flex items-center justify-center h-40 text-gray-400 text-sm">No slot data available</div>
            ) : (
              <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                {slots.map((slot) => (
                  <div
                    key={slot.time}
                    className={[
                      "flex items-center gap-3 px-4 py-3 rounded-xl text-sm transition",
                      slot.status === "busy"
                        ? "bg-red-50 border border-red-100"
                        : "bg-emerald-50 border border-emerald-100",
                    ].join(" ")}
                  >
                    <span className="text-gray-500 w-14 shrink-0 font-mono text-xs">
                      {pad(slot.hour)}:00
                    </span>
                    <span
                      className={[
                        "w-2 h-2 rounded-full shrink-0",
                        slot.status === "busy" ? "bg-red-400" : "bg-emerald-400",
                      ].join(" ")}
                    />
                    <span className={slot.status === "busy" ? "text-red-600" : "text-emerald-700"}>
                      {slot.status === "busy" ? "Busy" : "Available"}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Upcoming events */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-sm font-semibold text-gray-800">Upcoming Calendar Events</h2>
              <p className="text-xs text-gray-400">Events created by MailFlow AI</p>
            </div>
            <button
              onClick={fetchEvents}
              disabled={evLoading}
              className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 border border-gray-200 rounded-lg px-3 py-1.5 hover:bg-gray-50 transition disabled:opacity-50"
            >
              <RefreshCw size={13} className={evLoading ? "animate-spin" : ""} />
              Refresh
            </button>
          </div>

          {evError ? (
            <div className="bg-red-50 border border-red-100 text-red-600 text-sm rounded-xl px-4 py-3">
              {evError}
            </div>
          ) : evLoading ? (
            <div className="text-center text-gray-400 text-sm py-6">Loading events…</div>
          ) : events.length === 0 ? (
            <div className="text-center text-gray-400 text-sm py-6">No upcoming AI-scheduled events</div>
          ) : (
            <div className="space-y-3">
              {events.map((ev) => (
                <div
                  key={ev.id}
                  className="flex items-start justify-between gap-4 p-4 rounded-xl bg-emerald-50 border border-emerald-100"
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 w-5 h-5 rounded-full bg-emerald-500 flex items-center justify-center shrink-0">
                      <svg viewBox="0 0 12 12" className="w-3 h-3 text-white fill-current">
                        <path d="M1 6l3.5 3.5L11 2" stroke="white" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-800">{ev.summary}</p>
                      <p className="text-xs text-gray-500 mt-0.5">
                        {formatEventTime(ev.start)} — {formatEventTime(ev.end)}
                      </p>
                      {ev.attendees && ev.attendees.length > 0 && (
                        <p className="text-xs text-blue-500 mt-0.5">
                          With: {ev.attendees.join(", ")}
                        </p>
                      )}
                    </div>
                  </div>
                  <a
                    href={`https://calendar.google.com/calendar/r`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs text-blue-500 hover:underline whitespace-nowrap shrink-0 flex items-center gap-1"
                  >
                    ↗ Open in Calendar
                  </a>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer banner */}
        <div className="flex items-center gap-2 text-xs text-blue-600 bg-blue-50 border border-blue-100 rounded-xl px-4 py-3">
          <RefreshCw size={13} className="shrink-0" />
          <span>
            <strong>AI Scheduler active</strong> — MailFlow automatically detects meeting requests in your inbox and books calendar events. Blue dots mark days with existing events.
          </span>
        </div>

      </main>
    </div>
  );
}