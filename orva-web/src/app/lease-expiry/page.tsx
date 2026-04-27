"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CalendarX, Phone, Download, Search } from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import { getLeaseExpiry, ExpiringLease, LeaseExpiryResponse } from "@/lib/api";

const WINDOWS = [30, 60, 90, 180] as const;
const BEDROOMS_OPTS = ["", "Studio", "1", "2", "3", "4", "5"] as const;

function fmtDate(s: string | null): string {
  if (!s) return "--";
  try {
    return new Date(s).toLocaleDateString("en-GB", {
      day: "2-digit", month: "short", year: "numeric",
    });
  } catch {
    return s;
  }
}

function fmtRent(r: number | null): string {
  return r != null ? `${Math.round(r).toLocaleString()} AED` : "--";
}

export default function LeaseExpiryPage() {
  const { authenticated, loading: authLoading } = useAuth();
  const router = useRouter();

  const [data, setData] = useState<LeaseExpiryResponse | null>(null);
  const [days, setDays] = useState<number>(90);
  const [building, setBuilding] = useState("");
  const [bedrooms, setBedrooms] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(
        await getLeaseExpiry(days, building || undefined, bedrooms || undefined),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [days, building, bedrooms]);

  useEffect(() => {
    if (authenticated) refresh();
  }, [authenticated, refresh]);

  if (authLoading) return null;
  if (!authenticated) {
    router.replace("/");
    return null;
  }

  const handleExport = () => {
    if (!data) return;
    const headers = [
      "Building", "Unit", "Beds", "Lease Expiry", "Days",
      "Annual Rent", "Has Contact", "Owner", "Phone", "Email",
    ];
    const rows = data.leases.map((L) => [
      L.building_name || "", L.unit_number || "", L.bedrooms || "",
      L.contract_end || "", String(L.days_remaining ?? ""),
      L.annual_rent != null ? String(L.annual_rent) : "",
      L.has_owner_contact ? "Y" : "N",
      L.owner_name || "", L.owner_phone || "", L.owner_email || "",
    ]);
    const csv = [headers, ...rows].map((r) =>
      r.map((c) => `"${(c || "").replace(/"/g, '""')}"`).join(","),
    ).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `expiring_leases_${days}days_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-mobile-nav max-w-6xl mx-auto w-full">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <CalendarX size={20} className="text-accent" />
          <h1 className="text-lg font-semibold text-foreground">Lease Expiry</h1>
        </div>
        {data && data.total > 0 && (
          <button
            onClick={handleExport}
            className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm text-muted hover:bg-card-hover hover:text-foreground"
          >
            <Download size={14} />
            Export CSV
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <div>
          <label className="text-xs text-muted">Expiry window</label>
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="mt-1 w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground"
          >
            {WINDOWS.map((w) => (
              <option key={w} value={w}>{w} days</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs text-muted">Building (substring)</label>
          <div className="relative mt-1">
            <Search
              size={12}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-muted"
            />
            <input
              value={building}
              onChange={(e) => setBuilding(e.target.value)}
              placeholder="e.g. Shoreline"
              className="w-full rounded-lg border border-border bg-card px-3 py-2 pl-8 text-sm text-foreground placeholder:text-muted"
            />
          </div>
        </div>
        <div>
          <label className="text-xs text-muted">Bedrooms</label>
          <select
            value={bedrooms}
            onChange={(e) => setBedrooms(e.target.value)}
            className="mt-1 w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground"
          >
            {BEDROOMS_OPTS.map((b) => (
              <option key={b} value={b}>{b || "Any"}</option>
            ))}
          </select>
        </div>
      </div>

      {data && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label={`Expiring <= ${data.expiry_window_days}d`} value={data.total} />
          <Stat
            label="With Contact"
            value={data.with_contact}
            sub={data.total > 0 ? `${Math.round((data.with_contact / data.total) * 100)}%` : "0%"}
            highlight
          />
          <Stat label="Active Rentals" value={data.active_rentals_total.toLocaleString()} />
          <Stat label="Unique Buildings" value={data.unique_buildings} />
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-2 text-sm text-danger">
          {error}
        </div>
      )}

      {loading ? (
        <div className="rounded-xl border border-border bg-card p-8 text-center text-muted">
          Loading...
        </div>
      ) : !data || data.leases.length === 0 ? (
        <div className="rounded-xl border border-border bg-card p-8 text-center">
          <p className="text-muted">
            No leases match those filters
            {data && data.active_rentals_total === 0 && " (no rental data on disk yet)"}
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border bg-card">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-background text-left text-xs uppercase text-muted">
              <tr>
                <Th>Building / Unit</Th>
                <Th>Beds</Th>
                <Th>Expiry</Th>
                <Th>Days</Th>
                <Th>Annual rent</Th>
                <Th>Owner</Th>
                <Th>Phone</Th>
              </tr>
            </thead>
            <tbody>
              {data.leases.map((L, idx) => (
                <LeaseRow lease={L} key={`${L.building_name}-${L.unit_number}-${idx}`} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Stat({
  label, value, sub, highlight = false,
}: {
  label: string;
  value: string | number;
  sub?: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`rounded-xl border p-3 text-center ${
        highlight ? "border-accent/30 bg-accent/5" : "border-border bg-card"
      }`}
    >
      <p className={`text-xl font-bold ${highlight ? "text-accent" : "text-foreground"}`}>
        {value}
      </p>
      <p className="text-[11px] text-muted">
        {label}
        {sub && <span className="ml-1">({sub})</span>}
      </p>
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return <th className="px-3 py-2 font-medium">{children}</th>;
}

function LeaseRow({ lease }: { lease: ExpiringLease }) {
  const days = lease.days_remaining ?? 0;
  const urgent = days <= 30;
  const soon = days > 30 && days <= 60;

  return (
    <tr
      className={`border-b border-border last:border-0 ${
        urgent ? "bg-danger/5" : soon ? "bg-warning/5" : ""
      }`}
    >
      <td className="px-3 py-2">
        <div className="font-medium text-foreground">{lease.building_name || "--"}</div>
        {lease.unit_number && (
          <div className="text-xs text-muted">Unit {lease.unit_number}</div>
        )}
      </td>
      <td className="px-3 py-2 text-foreground">{lease.bedrooms || "--"}</td>
      <td className="px-3 py-2 text-foreground">{fmtDate(lease.contract_end)}</td>
      <td className="px-3 py-2">
        <span
          className={`rounded px-2 py-0.5 text-xs font-medium ${
            urgent
              ? "bg-danger/15 text-danger"
              : soon
                ? "bg-warning/15 text-warning"
                : "text-muted"
          }`}
        >
          {days}d
        </span>
      </td>
      <td className="px-3 py-2 text-foreground">{fmtRent(lease.annual_rent)}</td>
      <td className="px-3 py-2 text-foreground">
        {lease.has_owner_contact ? (
          <span>{lease.owner_name || "--"}</span>
        ) : (
          <span className="text-muted">no match</span>
        )}
      </td>
      <td className="px-3 py-2">
        {lease.owner_phone ? (
          <a
            href={`tel:${lease.owner_phone}`}
            className="flex items-center gap-1 text-accent hover:underline"
          >
            <Phone size={10} />
            {lease.owner_phone}
          </a>
        ) : (
          <span className="text-muted">--</span>
        )}
      </td>
    </tr>
  );
}
