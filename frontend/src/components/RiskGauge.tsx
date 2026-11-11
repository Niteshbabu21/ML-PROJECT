import { motion } from "framer-motion";
import { CountUp } from "./motion";

/** Semicircular gauge for a 0–100 risk score. The arc springs to the
 * score and the number counts up — pure presentation of whatever the
 * risk API returned. */
export default function RiskGauge({ score }: { score: number }) {
  const clamped = Math.max(0, Math.min(100, score));
  const color =
    clamped < 30 ? "#34d399" : clamped < 60 ? "#fbbf24" : "#f87171";
  const glow =
    clamped < 30
      ? "rgba(52,211,153,0.35)"
      : clamped < 60
        ? "rgba(251,191,36,0.35)"
        : "rgba(248,113,113,0.35)";
  return (
    <div className="flex flex-col items-center">
      <div className="relative w-full max-w-[280px]">
        <svg viewBox="0 0 200 112" className="w-full">
          <path
            d="M 22 100 A 78 78 0 0 1 178 100"
            fill="none"
            stroke="#1d2c52"
            strokeWidth="13"
            strokeLinecap="round"
          />
          <motion.path
            d="M 22 100 A 78 78 0 0 1 178 100"
            fill="none"
            stroke={color}
            strokeWidth="13"
            strokeLinecap="round"
            style={{ filter: `drop-shadow(0 0 10px ${glow})` }}
            initial={{ pathLength: 0 }}
            animate={{ pathLength: clamped / 100 }}
            transition={{ duration: 1.3, ease: [0.22, 1, 0.36, 1], delay: 0.15 }}
          />
        </svg>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 text-center">
          <p className="num text-[34px] font-semibold leading-none text-slate-50">
            <CountUp value={clamped} format={(v) => v.toFixed(1)} duration={1.3} />
          </p>
          <p className="eyebrow mt-1.5 text-[9px] text-slate-500">Out of 100</p>
        </div>
      </div>
      <div className="mt-3 flex w-full max-w-[280px] justify-between font-mono text-[10px] tracking-wide text-slate-500">
        <span className="text-emerald-400/80">LOW 0–29</span>
        <span className="text-amber-400/80">MED 30–59</span>
        <span className="text-red-400/80">HIGH 60–100</span>
      </div>
    </div>
  );
}
