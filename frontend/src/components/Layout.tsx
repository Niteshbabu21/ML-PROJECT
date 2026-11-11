import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  BarChart3,
  Blocks,
  BrainCircuit,
  Building2,
  Coins,
  History,
  LayoutDashboard,
  Menu,
  ShieldAlert,
  X,
} from "lucide-react";
import { healthService } from "../api/services";
import { AnimatePresence, motion } from "framer-motion";

const NAV = [
  { to: "/", label: "Executive Dashboard", short: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/valuation", label: "Property Valuation", short: "Valuation", icon: Building2 },
  { to: "/explainability", label: "AI Explainability", short: "Explainability", icon: BrainCircuit },
  { to: "/risk", label: "Risk Assessment", short: "Risk", icon: ShieldAlert },
  { to: "/tokenisation", label: "Tokenisation", short: "Tokenisation", icon: Coins },
  { to: "/models", label: "Model Performance", short: "Models", icon: BarChart3 },
  { to: "/blockchain", label: "Blockchain Explorer", short: "Explorer", icon: Blocks },
  { to: "/history", label: "Prediction History", short: "History", icon: History },
];

function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return now.toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "Asia/Kolkata",
  });
}

export default function Layout() {
  const [open, setOpen] = useState(false);
  const [apiUp, setApiUp] = useState<boolean | null>(null);
  const [modelOk, setModelOk] = useState<boolean | null>(null);
  const location = useLocation();
  const clock = useClock();

  useEffect(() => {
    let alive = true;
    const check = () =>
      healthService
        .get()
        .then((h) => {
          if (!alive) return;
          setApiUp(true);
          setModelOk(h.model_loaded);
        })
        .catch(() => {
          if (!alive) return;
          setApiUp(false);
          setModelOk(null);
        });
    check();
    const t = setInterval(check, 30000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const status = {
    dot:
      apiUp == null
        ? "bg-slate-500 text-slate-500"
        : apiUp && modelOk
          ? "bg-emerald-400 text-emerald-400"
          : "bg-amber-400 text-amber-400",
    text:
      apiUp == null
        ? "Checking API…"
        : apiUp
          ? modelOk
            ? "Live · model loaded"
            : "API up · model unavailable"
          : "API unreachable",
  };

  const current =
    NAV.find((n) =>
      n.end ? location.pathname === n.to : location.pathname.startsWith(n.to),
    ) ?? NAV[0];

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 px-5 pb-6 pt-6">
        <div className="relative flex h-10 w-10 items-center justify-center">
          <span className="absolute inset-0 rotate-6 rounded-xl border border-accent-500/50" />
          <span className="absolute inset-0 -rotate-3 rounded-xl bg-accent-500/15" />
          <Building2 className="relative h-5 w-5 text-accent-400" />
        </div>
        <div>
          <p className="font-display text-[17px] font-semibold leading-none tracking-tight text-slate-50">
            PropVal<span className="text-accent-400"> AI</span>
          </p>
          <p className="eyebrow mt-1.5 text-[9px] text-slate-500">
            Value · Risk · Tokenise
          </p>
        </div>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-3">
        {NAV.map(({ to, label, icon: Icon, end }, i) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={() => setOpen(false)}
            className={({ isActive }) =>
              `group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-[13px] transition-colors duration-200 ${
                isActive
                  ? "font-medium text-white"
                  : "text-slate-400 hover:text-slate-100"
              }`
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <motion.span
                    layoutId="nav-pill"
                    className="absolute inset-0 rounded-lg border border-accent-500/35 bg-accent-500/15"
                    transition={{ type: "spring", stiffness: 420, damping: 34 }}
                  />
                )}
                <span className="font-mono relative text-[10px] text-slate-600 transition-colors group-hover:text-slate-400">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <Icon className="relative h-4 w-4 shrink-0 transition-transform duration-300 group-hover:-translate-y-px" />
                <span className="relative">{label}</span>
                {isActive && (
                  <motion.span
                    layoutId="nav-dot"
                    className="relative ml-auto h-1.5 w-1.5 rounded-full bg-teal-450"
                    transition={{ type: "spring", stiffness: 420, damping: 30 }}
                  />
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-line/70 px-5 py-4">
        <div className="flex items-center gap-2.5 text-xs text-slate-300">
          <span className={`pulse-dot h-2 w-2 rounded-full ${status.dot}`} />
          {status.text}
        </div>
        <p className="mt-2.5 text-[11px] leading-relaxed text-slate-500">
          Academic prototype. Valuations are model estimates, not certified
          appraisals; tokens are not legal proof of ownership.
        </p>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen">
      <div className="bg-scene" aria-hidden />
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-line/80 bg-ink-900/80 backdrop-blur-md lg:block">
        {sidebar}
      </aside>
      {/* Mobile drawer */}
      <AnimatePresence>
        {open && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/70 backdrop-blur-sm"
              onClick={() => setOpen(false)}
            />
            <motion.aside
              initial={{ x: -300 }}
              animate={{ x: 0 }}
              exit={{ x: -300 }}
              transition={{ type: "spring", stiffness: 320, damping: 32 }}
              className="absolute inset-y-0 left-0 w-64 border-r border-line bg-ink-900"
            >
              {sidebar}
            </motion.aside>
          </div>
        )}
      </AnimatePresence>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 border-b border-line/70 bg-ink-950/75 backdrop-blur-md">
          <div className="mx-auto flex w-full max-w-7xl items-center gap-3 px-4 py-3 sm:px-6 lg:px-8">
            <button
              onClick={() => setOpen(!open)}
              className="rounded-md border border-line p-2 text-slate-300 lg:hidden"
              aria-label="Toggle navigation"
            >
              {open ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
            </button>
            <div className="flex items-baseline gap-3">
              <span className="eyebrow hidden text-slate-500 sm:block">
                Section
              </span>
              <span className="font-display text-sm font-semibold text-slate-100">
                {current.short}
              </span>
            </div>
            <div className="ml-auto flex items-center gap-4">
              <span className="hidden items-center gap-2 rounded-full border border-line bg-ink-900/80 py-1 pl-2.5 pr-3 text-[11px] text-slate-300 sm:flex">
                <span className={`pulse-dot h-1.5 w-1.5 rounded-full ${status.dot}`} />
                {status.text}
              </span>
              <span className="num hidden text-[13px] text-slate-400 md:block">
                {clock} <span className="font-mono text-[10px] text-slate-600">IST</span>
              </span>
            </div>
          </div>
        </header>

        <motion.main
          key={location.pathname}
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
          className="mx-auto w-full max-w-7xl px-4 py-7 sm:px-6 lg:px-8 lg:py-9"
        >
          <Outlet />
        </motion.main>
      </div>
    </div>
  );
}
