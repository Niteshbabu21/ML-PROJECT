import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { dashboardService, riskService } from "../api/services";
import { useFetch } from "../hooks/useAsync";
import {
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  PageHeader,
  RiskBadge,
  Skeleton,
} from "../components/ui";
import { fmtDateTime, fmtInt, fmtLacs } from "../utils/format";

const PAGE_SIZE = 10;

export default function HistoryPage() {
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [city, setCity] = useState("all");
  const [riskById, setRiskById] = useState<Record<string, "LOW" | "MEDIUM" | "HIGH">>({});
  const history = useFetch(() => dashboardService.history(page, PAGE_SIZE), [page]);

  const items = history.data?.items ?? [];
  const pagination = history.data?.pagination;

  // Risk category per visible record, from the real risk API using the
  // stored predicted price (history records themselves don't store risk).
  useEffect(() => {
    let alive = true;
    const missing = items.filter((it) => !(it.request_id in riskById));
    if (!missing.length) return;
    Promise.all(
      missing.map((it) =>
        riskService
          .assess(it.property, it.predicted_price_lacs)
          .then((r) => [it.request_id, r.risk_category] as const)
          .catch(() => null),
      ),
    ).then((pairs) => {
      if (!alive) return;
      setRiskById((prev) => {
        const next = { ...prev };
        pairs.forEach((p) => {
          if (p) next[p[0]] = p[1];
        });
        return next;
      });
    });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [history.data]);

  const cities = useMemo(
    () => [...new Set(items.map((it) => it.property.CITY))].sort(),
    [items],
  );

  const visible = items.filter((it) => {
    if (city !== "all" && it.property.CITY !== city) return false;
    if (!query.trim()) return true;
    const q = query.toLowerCase();
    return (
      it.property.LOCALITY.toLowerCase().includes(q) ||
      it.property.CITY.toLowerCase().includes(q) ||
      it.request_id.toLowerCase().includes(q)
    );
  });

  return (
    <div>
      <PageHeader
        eyebrow="07 · Stored Records"
        title="Prediction History"
        description="Stored valuations from GET /api/dashboard/history (server-side pagination). Risk categories are scored per record by the risk API from the stored features and price; search and city filters apply to the loaded page."
      />
      <Card>
        <CardHeader
          title="Valuation records"
          subtitle={
            pagination
              ? `${pagination.total} records · page ${pagination.page} of ${Math.max(pagination.pages, 1)}`
              : "Loading…"
          }
          action={
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search locality, city, ID…"
                  className="w-52 rounded-md border border-line bg-ink-850 py-1.5 pl-8 pr-3 text-xs text-slate-100 outline-none placeholder:text-slate-500 focus:border-accent-500"
                />
              </div>
              <select
                value={city}
                onChange={(e) => setCity(e.target.value)}
                className="rounded-md border border-line bg-ink-850 px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-accent-500"
              >
                <option value="all">All cities</option>
                {cities.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          }
        />
        {history.error && (
          <div className="px-5 py-5">
            <ErrorState message={history.error} onRetry={history.reload} />
          </div>
        )}
        {history.loading && (
          <div className="space-y-3 px-5 py-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        )}
        {!history.loading && !history.error && items.length === 0 && (
          <div className="px-5 py-5">
            <EmptyState
              title="No valuation history"
              message="No records are stored yet — or the history database is unavailable. Run a valuation from the Property Valuation page."
            />
          </div>
        )}
        {!history.loading && items.length > 0 && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] text-left text-sm">
                <thead>
                  <tr className="border-b border-line/70 text-[11px] uppercase tracking-wider text-slate-500">
                    <th className="px-5 py-3 font-medium">Property</th>
                    <th className="px-5 py-3 font-medium">Configuration</th>
                    <th className="px-5 py-3 font-medium">Predicted price</th>
                    <th className="px-5 py-3 font-medium">Risk</th>
                    <th className="px-5 py-3 font-medium">Source</th>
                    <th className="px-5 py-3 font-medium">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((it) => (
                    <tr key={it.request_id} className="border-b border-line/40 last:border-0">
                      <td className="px-5 py-3 text-slate-100">
                        {it.property.LOCALITY}
                        <span className="block text-xs text-slate-500">{it.property.CITY}</span>
                      </td>
                      <td className="px-5 py-3 text-slate-300">
                        {it.property.BHK_CONFIG} · {fmtInt(it.property.SQUARE_FT)} sq ft
                      </td>
                      <td className="px-5 py-3 font-medium text-slate-100">
                        {fmtLacs(it.predicted_price_lacs)}
                      </td>
                      <td className="px-5 py-3">
                        {riskById[it.request_id] ? (
                          <RiskBadge category={riskById[it.request_id]} />
                        ) : (
                          <span className="text-xs text-slate-500">scoring…</span>
                        )}
                      </td>
                      <td className="px-5 py-3 text-slate-400">
                        {it.endpoint.replace("valuation/", "")}
                      </td>
                      <td className="px-5 py-3 text-slate-400">
                        {fmtDateTime(it.timestamp)}
                      </td>
                    </tr>
                  ))}
                  {visible.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-5 py-8 text-center text-sm text-slate-500">
                        No records on this page match the current filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between border-t border-line/70 px-5 py-3">
              <p className="text-xs text-slate-500">
                Showing {visible.length} of {items.length} loaded records
              </p>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="inline-flex items-center gap-1 rounded-md border border-line px-2.5 py-1.5 text-xs text-slate-200 transition hover:bg-ink-800 disabled:opacity-40"
                >
                  <ChevronLeft className="h-3.5 w-3.5" /> Previous
                </button>
                <button
                  onClick={() =>
                    setPage((p) =>
                      pagination ? Math.min(pagination.pages, p + 1) : p + 1,
                    )
                  }
                  disabled={!pagination || page >= pagination.pages}
                  className="inline-flex items-center gap-1 rounded-md border border-line px-2.5 py-1.5 text-xs text-slate-200 transition hover:bg-ink-800 disabled:opacity-40"
                >
                  Next <ChevronRight className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
