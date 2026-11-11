import type { ReactNode } from "react";
import { AlertTriangle, Inbox, RefreshCw } from "lucide-react";
import { CountUp } from "./motion";

export function Card({
  children,
  className = "",
  lift = false,
}: {
  children: ReactNode;
  className?: string;
  lift?: boolean;
}) {
  return (
    <section
      className={`card-sheen rounded-2xl border border-line shadow-[0_1px_0_rgba(255,255,255,0.03)_inset] ${lift ? "card-lift" : ""} ${className}`}
    >
      {children}
    </section>
  );
}

export function CardHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line/70 px-5 py-4">
      <div>
        <h3 className="text-sm font-semibold tracking-wide text-slate-100">
          {title}
        </h3>
        {subtitle && <p className="mt-0.5 text-xs text-slate-400">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function StatCard({
  label,
  value,
  hint,
  icon,
  countTo,
  formatCount,
}: {
  label: string;
  value: string;
  hint?: string;
  icon?: ReactNode;
  /** When set, the value counts up to this number through formatCount. */
  countTo?: number;
  formatCount?: (n: number) => string;
}) {
  return (
    <Card lift className="group px-5 py-4">
      <div className="flex items-center justify-between">
        <p className="eyebrow text-slate-400">{label}</p>
        {icon && (
          <span className="text-slate-500 transition-all duration-300 group-hover:-translate-y-0.5 group-hover:text-accent-400">
            {icon}
          </span>
        )}
      </div>
      <p className="num mt-2.5 text-[28px] font-semibold leading-none tracking-tight text-slate-50">
        {countTo != null && formatCount ? (
          <CountUp value={countTo} format={formatCount} />
        ) : (
          value
        )}
      </p>
      {hint && <p className="mt-1.5 text-xs leading-relaxed text-slate-400">{hint}</p>}
    </Card>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`shimmer rounded-md ${className}`} aria-hidden />;
}

export function CardSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <Card className="px-5 py-4">
      <Skeleton className="h-4 w-40" />
      <div className="mt-4 space-y-3">
        {Array.from({ length: rows }).map((_, i) => (
          <Skeleton key={i} className="h-3.5 w-full" />
        ))}
      </div>
    </Card>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-red-900/50 bg-red-950/20 px-6 py-10 text-center">
      <AlertTriangle className="h-6 w-6 text-red-400" />
      <p className="max-w-md text-sm text-red-200">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-1 inline-flex items-center gap-2 rounded-md border border-red-800 bg-red-950/40 px-3 py-1.5 text-xs font-medium text-red-100 transition hover:bg-red-950/70"
        >
          <RefreshCw className="h-3.5 w-3.5" /> Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  message,
}: {
  title: string;
  message: string;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-line bg-ink-900/60 px-6 py-10 text-center">
      <Inbox className="h-6 w-6 text-slate-500" />
      <p className="text-sm font-medium text-slate-200">{title}</p>
      <p className="max-w-md text-xs leading-relaxed text-slate-400">{message}</p>
    </div>
  );
}

export function RiskBadge({ category }: { category: "LOW" | "MEDIUM" | "HIGH" }) {
  const styles = {
    LOW: "border-emerald-800 bg-emerald-950/50 text-emerald-300",
    MEDIUM: "border-amber-800 bg-amber-950/50 text-amber-300",
    HIGH: "border-red-800 bg-red-950/50 text-red-300",
  } as const;
  const dots = {
    LOW: "bg-emerald-400",
    MEDIUM: "bg-amber-400",
    HIGH: "bg-red-400",
  } as const;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold tracking-wide ${styles[category]}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${dots[category]}`} />
      {category}
    </span>
  );
}

export function PageHeader({
  title,
  description,
  eyebrow,
}: {
  title: string;
  description: string;
  eyebrow?: string;
}) {
  return (
    <div className="mb-7">
      <p className="eyebrow flex items-center gap-2 text-accent-400">
        <span className="inline-block h-px w-8 bg-accent-500/70" />
        {eyebrow ?? "PropVal AI"}
      </p>
      <h1 className="font-display mt-2.5 text-[32px] font-semibold leading-[1.05] tracking-tight text-slate-50 sm:text-4xl">
        {title}
      </h1>
      <p className="mt-2.5 max-w-3xl text-sm leading-relaxed text-slate-400">
        {description}
      </p>
    </div>
  );
}
