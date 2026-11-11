import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Contribution } from "../types/api";

/** SHAP waterfall in log-price space, built from the API's actual
 * per-feature contributions: baseline → each step → final prediction. */
export default function Waterfall({
  baseValueLog,
  contributions,
  topN = 8,
}: {
  baseValueLog: number;
  contributions: Contribution[];
  topN?: number;
}) {
  const sorted = [...contributions].sort(
    (a, b) => Math.abs(b.shap_log) - Math.abs(a.shap_log),
  );
  const shown = sorted.slice(0, topN);
  const rest = sorted.slice(topN);
  const restSum = rest.reduce((s, c) => s + c.shap_log, 0);

  type Step = {
    name: string;
    bottom: number;
    height: number;
    color: string;
    shap: number;
    full?: boolean;
  };
  const steps: Step[] = [
    {
      name: "Baseline",
      bottom: 0,
      height: baseValueLog,
      color: "#64748b",
      shap: baseValueLog,
      full: true,
    },
  ];
  let cum = baseValueLog;
  for (const c of shown) {
    const after = cum + c.shap_log;
    steps.push({
      name: c.feature,
      bottom: Math.min(cum, after),
      height: Math.abs(c.shap_log),
      color: c.shap_log >= 0 ? "#1fbfa8" : "#f87171",
      shap: c.shap_log,
    });
    cum = after;
  }
  if (rest.length) {
    const after = cum + restSum;
    steps.push({
      name: `${rest.length} other features`,
      bottom: Math.min(cum, after),
      height: Math.abs(restSum),
      color: restSum >= 0 ? "#1fbfa8" : "#f87171",
      shap: restSum,
    });
    cum = after;
  }
  steps.push({
    name: "Prediction",
    bottom: 0,
    height: cum,
    color: "#2f6fed",
    shap: cum,
    full: true,
  });

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={steps} margin={{ top: 8, right: 12, left: 0, bottom: 40 }}>
          <CartesianGrid stroke="#22304f" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ fill: "#94a3b8", fontSize: 10 }}
            angle={-32}
            textAnchor="end"
            interval={0}
            height={56}
          />
          <YAxis
            tick={{ fill: "#94a3b8", fontSize: 11 }}
            domain={["dataMin - 0.4", "dataMax + 0.4"]}
            tickFormatter={(v: number) => v.toFixed(1)}
            label={{
              value: "log price",
              angle: -90,
              position: "insideLeft",
              fill: "#64748b",
              fontSize: 11,
            }}
          />
          <Tooltip
            contentStyle={{
              background: "#101a30",
              border: "1px solid #22304f",
              borderRadius: 8,
              fontSize: 12,
            }}
            formatter={(_v, _n, item) => {
              const s = item.payload as Step;
              return [
                s.full
                  ? `${s.shap.toFixed(3)} (level)`
                  : `${s.shap >= 0 ? "+" : ""}${s.shap.toFixed(3)}`,
                s.name,
              ];
            }}
          />
          <Bar dataKey="bottom" stackId="w" fill="transparent" isAnimationActive={false} />
          <Bar dataKey="height" stackId="w" radius={[3, 3, 0, 0]} animationDuration={900}>
            {steps.map((s, i) => (
              <Cell key={i} fill={s.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
