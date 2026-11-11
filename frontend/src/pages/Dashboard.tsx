import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Activity, Building2, IndianRupee, Sigma } from "lucide-react";
import { dashboardService, modelService, riskService } from "../api/services";
import { useFetch } from "../hooks/useAsync";
import type { HistoryItem } from "../types/api";
import {
  Card,
  CardHeader,
  CardSkeleton,
  EmptyState,
  ErrorState,
  PageHeader,
  RiskBadge,
  StatCard,
} from "../components/ui";
import { Reveal } from "../components/motion";
import { fmtDate, fmtDateTime, fmtInt, fmtLacs } from "../utils/format";

const RISK_COLORS = { LOW: "#34d399", MEDIUM: "#fbbf24", HIGH: "#f87171" };

export default function Dashboard() {
  const summary = useFetch(() => dashboardService.summary());
  const history = useFetch(() => dashboardService.history(1, 100));
  const metrics = useFetch(() => modelService.metrics());
  const [riskDist, setRiskDist] = useState<
    { name: string; value: number }[] | null
  >(null);

  // Risk distribution is computed from the real risk API over the most
  // recent stored valuations (each with its stored predicted price).
  useEffect(() => {
    const items = history.data?.items ?? [];
    if (!items.length) return;
    let alive = true;
    Promise.all(
      items.slice(0, 20).map((it) =>
        riskService
          .assess(it.property, it.predicted_price_lacs)
          .then((r) => r.risk_category)
          .catch(() => null),
      ),
    ).then((cats) => {
      if (!alive) return;
      const counts = { LOW: 0, MEDIUM: 0, HIGH: 0 };
      cats.forEach((c) => {
        if (c) counts[c] += 1;
      });
      setRiskDist(
        Object.entries(counts)
          .filter(([, v]) => v > 0)
          .map(([name, value]) => ({ name, value })),
      );
    });
    return () => {
      alive = false;
    };
  }, [history.data]);

  const activity = useMemo(() => {
    const items: HistoryItem[] = history.data?.items ?? [];
    const byDay = new Map<string, number>();
    for (const it of items) {
      const day = fmtDate(it.timestamp);
      byDay.set(day, (byDay.get(day) ?? 0) + 1);
    }
    return [...byDay.entries()]
      .map(([day, count]) => ({ day, count }))
      .reverse();
  }, [history.data]);

  const recent = (history.data?.items ?? []).slice(0, 6);
  const m = metrics.data?.metrics;

  return (
    <div>
      <PageHeader
        eyebrow="Overview · Live API data"
        title="Executive Dashboard"
        description="Live overview of valuation activity, model performance and risk profile — every figure on this page is served by the Flask API."
      />
      {summary.error && (
        <ErrorState message={summary.error} onRetry={summary.reload} />
      )}
      {summary.loading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <CardSkeleton key={i} rows={2} />
          ))}
        </div>
      )}
      {summary.data && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label="Total valuations"
            value={fmtInt(summary.data.total_valuations)}
            countTo={summary.data.total_valuations}
            formatCount={fmtInt}
            hint="Stored prediction records"
            icon={<Sigma className="h-4 w-4" />}
          />
          <StatCard
            label="Average predicted value"
            value={fmtLacs(summary.data.average_price_lacs)}
            countTo={summary.data.average_price_lacs ?? undefined}
            formatCount={fmtLacs}
            hint={
              summary.data.min_price_lacs != null
                ? `Range ${fmtLacs(summary.data.min_price_lacs)} – ${fmtLacs(summary.data.max_price_lacs)}`
                : undefined
            }
            icon={<IndianRupee className="h-4 w-4" />}
          />
          <StatCard
            label="Served model"
            value={summary.data.model_id}
            hint={summary.data.model_name}
            icon={<Building2 className="h-4 w-4" />}
          />
          <StatCard
            label="Model status"
            value={summary.data.model_loaded ? "Operational" : "Unavailable"}
            hint={`Database ${summary.data.database_connected ? "connected" : "unavailable"}`}
            icon={<Activity className="h-4 w-4" />}
          />
        </div>
      )}

      <Reveal delay={0.08}>
      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title="Valuation activity"
            subtitle="Predictions per day, from stored history"
          />
          <div className="h-64 px-3 py-4">
            {history.loading ? (
              <p className="px-2 text-sm text-slate-500">Loading…</p>
            ) : activity.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={activity}>
                  <defs>
                    <linearGradient id="activityFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#2f6fed" stopOpacity={0.45} />
                      <stop offset="100%" stopColor="#2f6fed" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#22304f" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="day" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{
                      background: "#101a30",
                      border: "1px solid #22304f",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="count"
                    name="Valuations"
                    stroke="#6ea8ff"
                    strokeWidth={2}
                    fill="url(#activityFill)"
                    animationDuration={1200}
                    dot={{ r: 3, fill: "#6ea8ff", strokeWidth: 0 }}
                    activeDot={{ r: 5 }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState
                title="No valuation activity yet"
                message="Run a property valuation and it will appear here."
              />
            )}
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Risk distribution"
            subtitle="Latest 20 valuations, scored by the risk API"
          />
          <div className="h-64 px-3 py-4">
            {riskDist == null ? (
              <p className="px-2 text-sm text-slate-500">
                {history.data?.items.length
                  ? "Scoring recent valuations…"
                  : "No valuations to score yet."}
              </p>
            ) : riskDist.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={riskDist}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={55}
                    outerRadius={85}
                    paddingAngle={3}
                    stroke="#0d1526"
                  >
                    {riskDist.map((d) => (
                      <Cell
                        key={d.name}
                        fill={RISK_COLORS[d.name as keyof typeof RISK_COLORS]}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      background: "#101a30",
                      border: "1px solid #22304f",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState title="No risk data" message="Risk scoring did not return results for the recent valuations." />
            )}
          </div>
          {riskDist && (
            <div className="flex justify-center gap-4 pb-4 text-xs text-slate-400">
              {riskDist.map((d) => (
                <span key={d.name} className="flex items-center gap-1.5">
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{
                      background:
                        RISK_COLORS[d.name as keyof typeof RISK_COLORS],
                    }}
                  />
                  {d.name} · {d.value}
                </span>
              ))}
            </div>
          )}
        </Card>
      </div>

      </Reveal>
      <Reveal delay={0.14}>
      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title="Recent valuations"
            subtitle="Most recent records from the history API"
            action={
              <Link to="/history" className="text-xs font-medium text-accent-400 hover:text-accent-500">
                View all
              </Link>
            }
          />
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-line/70 text-[11px] uppercase tracking-wider text-slate-500">
                  <th className="px-5 py-3 font-medium">Property</th>
                  <th className="px-5 py-3 font-medium">Predicted price</th>
                  <th className="px-5 py-3 font-medium">When</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((it) => (
                  <tr key={it.request_id} className="border-b border-line/40 transition-colors last:border-0 hover:bg-ink-800/60">
                    <td className="px-5 py-3 text-slate-200">
                      {it.property.LOCALITY}, {it.property.CITY}
                      <span className="block text-xs text-slate-500">
                        {it.property["BHK_NO."]} BHK · {fmtInt(it.property.SQUARE_FT)} sq ft
                      </span>
                    </td>
                    <td className="px-5 py-3 font-medium text-slate-100">
                      {fmtLacs(it.predicted_price_lacs)}
                    </td>
                    <td className="px-5 py-3 text-slate-400">
                      {fmtDateTime(it.timestamp)}
                    </td>
                  </tr>
                ))}
                {!recent.length && !history.loading && (
                  <tr>
                    <td colSpan={3} className="px-5 py-8 text-center text-sm text-slate-500">
                      No valuations recorded yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>

        <Card>
          <CardHeader title="Model performance" subtitle="Served model, measured metrics" />
          {metrics.loading && <p className="px-5 py-4 text-sm text-slate-500">Loading…</p>}
          {metrics.error && (
            <p className="px-5 py-4 text-sm text-red-300">{metrics.error}</p>
          )}
          {m && (
            <dl className="space-y-3 px-5 py-4 text-sm">
              <div className="flex justify-between">
                <dt className="text-slate-400">Validation R²</dt>
                <dd className="font-medium text-slate-100">{m.validation.r2.toFixed(4)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-400">Grouped CV R²</dt>
                <dd className="font-medium text-slate-100">
                  {m.grouped_cv.r2_mean.toFixed(4)} ± {m.grouped_cv.r2_std.toFixed(4)}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-400">Test R² (held-out, once)</dt>
                <dd className="font-medium text-slate-100">{m.test.r2.toFixed(4)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-400">Test MAE</dt>
                <dd className="font-medium text-slate-100">{fmtLacs(m.test.mae_lacs)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-400">Test RMSE</dt>
                <dd className="font-medium text-slate-100">{fmtLacs(m.test.rmse_lacs)}</dd>
              </div>
              <div className="pt-1">
                <Link to="/models" className="text-xs font-medium text-accent-400 hover:text-accent-500">
                  Full model comparison →
                </Link>
              </div>
            </dl>
          )}
        </Card>
      </div>
      </Reveal>
    </div>
  );
}
