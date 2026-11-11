import { useEffect, useRef, useState, type ReactNode } from "react";
import { animate, motion } from "framer-motion";

/** Fade-and-rise reveal, fired once when the element scrolls into view. */
export function Reveal({
  children,
  delay = 0,
  className = "",
  y = 14,
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
  y?: number;
}) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.55, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}

/** Springs a number from 0 (or its previous value) to `value` whenever it
 * changes, rendering through `format`. Pure presentation — the value
 * itself always comes from the API. */
export function CountUp({
  value,
  format,
  duration = 1.1,
  className = "",
}: {
  value: number;
  format: (n: number) => string;
  duration?: number;
  className?: string;
}) {
  const [display, setDisplay] = useState(0);
  const prev = useRef(0);
  useEffect(() => {
    const controls = animate(prev.current, value, {
      duration,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => setDisplay(v),
    });
    prev.current = value;
    return () => controls.stop();
  }, [value, duration]);
  return <span className={className}>{format(display)}</span>;
}

/** Horizontal bar that springs to `pct`% width — used for SHAP drivers,
 * risk factors and fractional-representation bars. */
export function SpringBar({
  pct,
  className = "",
  delay = 0,
}: {
  pct: number;
  className?: string;
  delay?: number;
}) {
  return (
    <motion.div
      className={`h-full rounded-full ${className}`}
      initial={{ width: 0 }}
      whileInView={{ width: `${Math.max(0, Math.min(100, pct))}%` }}
      viewport={{ once: true }}
      transition={{ duration: 0.9, delay, ease: [0.22, 1, 0.36, 1] }}
    />
  );
}
