const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });
const inr0 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const num = new Intl.NumberFormat("en-IN");

export const fmtLacs = (v: number | null | undefined): string =>
  v == null ? "—" : `₹${inr.format(v)} L`;

export const fmtINR = (v: number | null | undefined): string =>
  v == null ? "—" : `₹${inr0.format(v)}`;

export const fmtNum = (v: number | null | undefined, digits = 0): string =>
  v == null
    ? "—"
    : new Intl.NumberFormat("en-IN", {
        maximumFractionDigits: digits,
        minimumFractionDigits: digits,
      }).format(v);

export const fmtInt = (v: number | null | undefined): string =>
  v == null ? "—" : num.format(Math.round(v));

export const fmtDateTime = (iso: string): string =>
  new Date(iso).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

export const fmtDate = (iso: string): string =>
  new Date(iso).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
