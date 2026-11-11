import { useEffect, useMemo, useState } from "react";
import { Info } from "lucide-react";
import { modelService } from "../api/services";
import type { PropertyFeatures, SchemaData } from "../types/api";

/** A realistic sample listing (Bengaluru) used only as editable form
 * prefill so the workflow can be tried immediately — never as a result. */
export const SAMPLE_PROPERTY: PropertyFeatures = {
  POSTED_BY: "Owner",
  UNDER_CONSTRUCTION: 0,
  RERA: 1,
  "BHK_NO.": 3,
  BHK_OR_RK: "BHK",
  SQUARE_FT: 1200,
  RESALE: 0,
  CITY: "Bangalore",
  LOCALITY: "Koramangala",
  LATITUDE: 12.935,
  LONGITUDE: 77.624,
  SQUARE_FT_PER_BHK: 400,
  LOG_SQUARE_FT: 7.0901,
  DIST_TO_CITY_CENTROID: 3.2,
  CITY_FREQ: 3298,
  LOCALITY_FREQ: 450,
  SQFT_BAND: "M",
  BHK_CONFIG: "3BHK",
  GEO_CLUSTER: "C04",
  LAT_LON_INTERACTION: 1003.42,
};

type Values = Record<string, string>;

function toValues(p: PropertyFeatures): Values {
  const v: Values = {};
  for (const [k, val] of Object.entries(p)) {
    v[k] = val == null ? "" : String(val);
  }
  return v;
}

const inputCls =
  "w-full rounded-md border border-line bg-ink-850 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 outline-none transition focus:border-accent-500 focus:ring-1 focus:ring-accent-500/40";
const labelCls =
  "mb-1.5 block text-[11px] font-medium uppercase tracking-[0.12em] text-slate-400";

function Field({
  label,
  error,
  children,
  hint,
}: {
  label: string;
  error?: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className={labelCls}>{label}</span>
      {children}
      {hint && !error && <span className="mt-1 block text-[11px] text-slate-500">{hint}</span>}
      {error && <span className="mt-1 block text-[11px] text-red-400">{error}</span>}
    </label>
  );
}

export default function PropertyForm({
  initial,
  onSubmit,
  submitting,
  submitLabel,
}: {
  initial?: PropertyFeatures | null;
  onSubmit: (features: PropertyFeatures) => void;
  submitting: boolean;
  submitLabel: string;
}) {
  const [values, setValues] = useState<Values>(() =>
    toValues(initial ?? SAMPLE_PROPERTY),
  );
  const [touched, setTouched] = useState<Set<string>>(new Set());
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [schema, setSchema] = useState<SchemaData | null>(null);

  useEffect(() => {
    modelService.schema().then(setSchema).catch(() => setSchema(null));
  }, []);

  useEffect(() => {
    if (initial) {
      setValues(toValues(initial));
      setTouched(new Set());
    }
  }, [initial]);

  const levels = useMemo(() => {
    const map: Record<string, string[]> = {};
    for (const f of schema?.features ?? []) {
      if (f.known_levels) map[f.name] = f.known_levels;
    }
    return map;
  }, [schema]);

  const set = (name: string, raw: string, manual = true) => {
    setValues((prev) => {
      const next = { ...prev, [name]: raw };
      if (manual) {
        // Auto-derive dependent features unless the user overrode them.
        const sqft = parseFloat(next.SQUARE_FT);
        const bhk = parseFloat(next["BHK_NO."]);
        const lat = parseFloat(next.LATITUDE);
        const lon = parseFloat(next.LONGITUDE);
        if (!touched.has("SQUARE_FT_PER_BHK") && sqft > 0 && bhk > 0)
          next.SQUARE_FT_PER_BHK = (sqft / bhk).toFixed(2);
        if (!touched.has("LOG_SQUARE_FT") && sqft > 0)
          next.LOG_SQUARE_FT = Math.log(sqft).toFixed(4);
        if (!touched.has("LAT_LON_INTERACTION") && !Number.isNaN(lat * lon))
          next.LAT_LON_INTERACTION = (lat * lon).toFixed(2);
        if (!touched.has("BHK_CONFIG") && bhk > 0)
          next.BHK_CONFIG = `${bhk}${next.BHK_OR_RK === "RK" ? "RK" : "BHK"}`;
      }
      return next;
    });
    if (manual) setTouched((t) => new Set(t).add(name));
  };

  const num = (name: string) => values[name] ?? "";

  function validate(): PropertyFeatures | null {
    const errs: Record<string, string> = {};
    const need = (name: string) => {
      if (!values[name]?.trim()) errs[name] = "Required";
    };
    const numIn = (name: string, min: number, max: number) => {
      const v = parseFloat(values[name]);
      if (Number.isNaN(v)) errs[name] = "Enter a number";
      else if (v < min || v > max) errs[name] = `Between ${min} and ${max}`;
    };
    ["POSTED_BY", "BHK_OR_RK", "CITY", "LOCALITY", "SQFT_BAND", "BHK_CONFIG",
     "GEO_CLUSTER"].forEach(need);
    numIn("SQUARE_FT", 0.01, 1_000_000);
    if (!errs.SQUARE_FT && parseFloat(values.SQUARE_FT) <= 0)
      errs.SQUARE_FT = "Must be positive";
    numIn("BHK_NO.", 1, 20);
    numIn("LATITUDE", 5, 40);
    numIn("LONGITUDE", 65, 100);
    numIn("SQUARE_FT_PER_BHK", 0.01, 1_000_000);
    numIn("LOG_SQUARE_FT", 0, 20);
    numIn("CITY_FREQ", 0, 1_000_000);
    numIn("LOCALITY_FREQ", 0, 1_000_000);
    numIn("LAT_LON_INTERACTION", -10000, 10000);
    setErrors(errs);
    if (Object.keys(errs).length) return null;
    const dist = values.DIST_TO_CITY_CENTROID?.trim();
    return {
      POSTED_BY: values.POSTED_BY,
      UNDER_CONSTRUCTION: Number(values.UNDER_CONSTRUCTION),
      RERA: Number(values.RERA),
      "BHK_NO.": Number(values["BHK_NO."]),
      BHK_OR_RK: values.BHK_OR_RK,
      SQUARE_FT: Number(values.SQUARE_FT),
      RESALE: Number(values.RESALE),
      CITY: values.CITY,
      LOCALITY: values.LOCALITY,
      LATITUDE: Number(values.LATITUDE),
      LONGITUDE: Number(values.LONGITUDE),
      SQUARE_FT_PER_BHK: Number(values.SQUARE_FT_PER_BHK),
      LOG_SQUARE_FT: Number(values.LOG_SQUARE_FT),
      DIST_TO_CITY_CENTROID: dist ? Number(dist) : null,
      CITY_FREQ: Number(values.CITY_FREQ),
      LOCALITY_FREQ: Number(values.LOCALITY_FREQ),
      SQFT_BAND: values.SQFT_BAND,
      BHK_CONFIG: values.BHK_CONFIG,
      GEO_CLUSTER: values.GEO_CLUSTER,
      LAT_LON_INTERACTION: Number(values.LAT_LON_INTERACTION),
    };
  }

  const select = (
    name: string,
    options: string[],
    label: string,
  ) => (
    <Field label={label} error={errors[name]}>
      <select
        className={inputCls}
        value={values[name] ?? ""}
        onChange={(e) => set(name, e.target.value)}
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </Field>
  );

  const number = (name: string, label: string, hint?: string, step = "any") => (
    <Field label={label} error={errors[name]} hint={hint}>
      <input
        type="number"
        step={step}
        className={inputCls}
        value={num(name)}
        onChange={(e) => set(name, e.target.value)}
      />
    </Field>
  );

  const toggle = (name: string, label: string) => (
    <Field label={label}>
      <div className="flex overflow-hidden rounded-md border border-line">
        {[
          ["1", "Yes"],
          ["0", "No"],
        ].map(([v, text]) => (
          <button
            type="button"
            key={v}
            onClick={() => set(name, v)}
            className={`flex-1 px-3 py-2 text-sm transition ${
              values[name] === v
                ? "bg-accent-500/90 font-medium text-white"
                : "bg-ink-850 text-slate-400 hover:bg-ink-800"
            }`}
          >
            {text}
          </button>
        ))}
      </div>
    </Field>
  );

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const out = validate();
        if (out) onSubmit(out);
      }}
      className="space-y-6"
    >
      <div>
        <h4 className="mb-3 text-xs font-semibold uppercase tracking-[0.16em] text-slate-300">
          Location
        </h4>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {select("CITY", levels.CITY ?? ["Bangalore"], "City")}
          <Field label="Locality" error={errors.LOCALITY}>
            <input
              className={inputCls}
              value={values.LOCALITY ?? ""}
              onChange={(e) => set("LOCALITY", e.target.value)}
              placeholder="e.g. Koramangala"
            />
          </Field>
          {number("LATITUDE", "Latitude", "India: 5 – 40")}
          {number("LONGITUDE", "Longitude", "India: 65 – 100")}
          {number("DIST_TO_CITY_CENTROID", "Distance to city centre (km)",
            "Leave empty if unknown")}
        </div>
      </div>

      <div>
        <h4 className="mb-3 text-xs font-semibold uppercase tracking-[0.16em] text-slate-300">
          Configuration &amp; size
        </h4>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {number("BHK_NO.", "Bedrooms (BHK)", "1 – 20", "1")}
          {select("BHK_OR_RK", ["BHK", "RK"], "Configuration type")}
          {select("BHK_CONFIG", levels.BHK_CONFIG ?? ["1BHK", "2BHK", "3BHK", "4BHK"],
            "BHK configuration")}
          {number("SQUARE_FT", "Area (sq ft)")}
          {select("SQFT_BAND", levels.SQFT_BAND ?? ["XS", "S", "M", "L", "XL"],
            "Size band")}
          {number("SQUARE_FT_PER_BHK", "Sq ft per BHK", "Auto-derived; editable")}
          {number("LOG_SQUARE_FT", "Log of area", "Auto-derived; editable")}
        </div>
      </div>

      <div>
        <h4 className="mb-3 text-xs font-semibold uppercase tracking-[0.16em] text-slate-300">
          Listing &amp; status
        </h4>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {select("POSTED_BY", levels.POSTED_BY ?? ["Owner", "Dealer", "Builder"],
            "Posted by")}
          {toggle("UNDER_CONSTRUCTION", "Under construction")}
          {toggle("RERA", "RERA registered (per listing)")}
          {toggle("RESALE", "Resale property")}
          <Field label="Ready to move" hint="Derived from construction status — not a separate model input">
            <div className="rounded-md border border-line/70 bg-ink-900 px-3 py-2 text-sm text-slate-300">
              {values.UNDER_CONSTRUCTION === "0" ? "Yes" : "No"}
            </div>
          </Field>
        </div>
      </div>

      <div>
        <h4 className="mb-3 text-xs font-semibold uppercase tracking-[0.16em] text-slate-300">
          Market evidence (model features)
        </h4>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {number("CITY_FREQ", "City listing frequency", "Listings for this city in training data", "1")}
          {number("LOCALITY_FREQ", "Locality frequency", "Listings for this locality in training data", "1")}
          {select("GEO_CLUSTER", levels.GEO_CLUSTER ?? ["C00"], "Geographic cluster")}
          {number("LAT_LON_INTERACTION", "Latitude × longitude", "Auto-derived; editable")}
        </div>
        <p className="mt-3 flex items-start gap-2 text-[11px] leading-relaxed text-slate-500">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          These fields are the exact inputs of the trained model — including
          the evidence features its preprocessing pipeline derived from the
          training data. Values are validated again by the backend against
          the model schema.
        </p>
      </div>

      <div className="flex items-center justify-end gap-3 border-t border-line/70 pt-4">
        <button
          type="submit"
          disabled={submitting}
          className="btn-shine rounded-lg bg-accent-500 px-6 py-2.5 text-sm font-semibold text-white shadow-[0_8px_24px_-10px_rgba(47,111,237,0.7)] transition hover:bg-accent-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Working…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
