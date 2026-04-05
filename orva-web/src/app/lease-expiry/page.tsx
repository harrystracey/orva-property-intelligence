"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { LoginForm } from "@/components/login-form";
import { getExpiringLeases, getRentalsStats, lookupClientId, ExpiringLease, RentalsStatsResponse } from "@/lib/api";
import { Home, AlertTriangle, Clock, ChevronLeft, ChevronRight } from "lucide-react";

const PAGE_SIZE = 50;

function formatDate(iso: string | null | undefined) {
  if (!iso) return "--";
  try { return new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }); }
  catch { return iso; }
}

function formatAED(n: number | null | undefined) {
  if (!n) return "--";
  return "AED " + Math.round(n).toLocaleString();
}

function urgencyColor(days: number) {
  if (days <= 30) return "text-danger";
  if (days <= 60) return "text-warning";
  return "text-success";
}

export default function LeaseExpiryPage() {
  const { authenticated } = useAuth();
  const router = useRouter();
  const [stats, setStats] = useState<RentalsStatsResponse | null>(null);
  const [leases, setLeases] = useState<ExpiringLease[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [days, setDays] = useState(90);
  const [building, setBuilding] = useState("");
  const [bedrooms, setBedrooms] = useState("");
  const [loading, setLoading] = useState(true);

  const loadStats = useCallback(async () => {
    try { setStats(await getRentalsStats()); } catch { /* ignore */ }
  }, []);

  const loadLeases = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getExpiringLeases({ days, building: building || undefined, bedrooms: bedrooms || undefined, page, page_size: PAGE_SIZE });
      setLeases(res.leases);
      setTotal(res.total);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [days, building, bedrooms, page]);

  useEffect(() => { if (authenticated) { loadStats(); loadLeases(); } }, [authenticated, loadStats, loadLeases]);

  const handleViewOwner = async (lease: ExpiringLease) => {
    if (!lease.owner_name && !lease.building_name) return;
    try {
      const { client_id } = await lookupClientId(lease.owner_name || "", lease.building_name || "", lease.unit_number || "");
      router.push(`/client/${client_id}`);
    } catch { /* ignore */ }
  };

  if (!authenticated) return <LoginForm />;

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-20 md:pb-4">
      <div className="flex items-center gap-2">
        <Home size={20} className="text-accent" />
        <h1 className="text-lg font-semibold text-foreground">Rentals / Lease Expiry</h1>
      </div>

      {/* Stats cards */}
      {stats && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatCard label="Active leases" value={stats.active_count.toLocaleString()} color="text-success" />
          <StatCard label="Expiring ≤30 days" value={stats.expiring_30.toLocaleString()} color="text-danger" />
          <StatCard label="Expiring ≤60 days" value={stats.expiring_60.toLocaleString()} color="text-warning" />
          <StatCard label="Expiring ≤90 days" value={stats.expiring_90.toLocaleString()} color="text-foreground" />
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3 rounded-xl border border-border bg-card px-4 py-3">
        <div className="flex items-center gap-2">
          <label className="text-xs text-muted">Expiring within</label>
          <select
            value={days}
            onChange={(e) => { setDays(Number(e.target.value)); setPage(1); }}
            className="rounded-lg border border-border bg-background px-2 py-1 text-sm text-foreground outline-none focus:border-accent"
          >
            <option value={30}>30 days</option>
            <option value={60}>60 days</option>
            <option value={90}>90 days</option>
            <option value={180}>6 months</option>
            <option value={365}>1 year</option>
          </select>
        </div>
        <input
          type="text"
          placeholder="Building..."
          value={building}
          onChange={(e) => { setBuilding(e.target.value); setPage(1); }}
          className="rounded-lg border border-border bg-background px-3 py-1 text-sm text-foreground outline-none focus:border-accent"
        />
        <select
          value={bedrooms}
          onChange={(e) => { setBedrooms(e.target.value); setPage(1); }}
          className="rounded-lg border border-border bg-background px-2 py-1 text-sm text-foreground outline-none focus:border-accent"
        >
          <option value="">All beds</option>
          <option value="Studio">Studio</option>
          <option value="1">1 BR</option>
          <option value="2">2 BR</option>
          <option value="3">3 BR</option>
          <option value="4">4 BR</option>
        </select>
        <span className="ml-auto text-sm text-muted">{total.toLocaleString()} leases</span>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-border bg-card">
        <div className="table-scroll overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border bg-background/50">
                {["Building", "Unit", "Beds", "Size", "Annual Rent", "Expires", "Days Left", "Owner"].map(h => (
                  <th key={h} className="whitespace-nowrap px-4 py-2 text-left text-xs font-medium text-muted">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-sm text-muted">Loading...</td></tr>
              ) : leases.length === 0 ? (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-sm text-muted">No expiring leases found</td></tr>
              ) : leases.map((lease, i) => (
                <tr key={i} className="border-b border-border/50 hover:bg-card-hover">
                  <td className="px-4 py-2 text-sm text-foreground">{lease.building_name || "--"}</td>
                  <td className="px-4 py-2 text-sm text-muted">{lease.unit_number || "--"}</td>
                  <td className="px-4 py-2 text-sm text-muted">{lease.bedrooms !== null ? (lease.bedrooms === 0 ? "Studio" : `${lease.bedrooms} BR`) : "--"}</td>
                  <td className="px-4 py-2 text-sm text-muted">{lease.size_sqft ? `${Math.round(lease.size_sqft).toLocaleString()} sqft` : "--"}</td>
                  <td className="px-4 py-2 text-sm font-medium text-foreground">{formatAED(lease.annualized_rent)}</td>
                  <td className="px-4 py-2 text-sm text-muted">{formatDate(lease.contract_end)}</td>
                  <td className={`px-4 py-2 text-sm font-semibold ${urgencyColor(lease.days_remaining)}`}>
                    <span className="flex items-center gap-1">
                      {lease.days_remaining <= 30 && <AlertTriangle size={12} />}
                      {lease.days_remaining} d
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    {lease.owner_name || lease.building_name ? (
                      <button
                        onClick={() => handleViewOwner(lease)}
                        className="text-xs text-accent hover:underline"
                      >
                        {lease.owner_name || "View"}
                      </button>
                    ) : <span className="text-xs text-muted">--</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t border-border px-4 py-2">
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} className="flex items-center gap-1 rounded px-2 py-1 text-sm text-muted hover:text-foreground disabled:opacity-40">
              <ChevronLeft size={14} /> Prev
            </button>
            <span className="text-xs text-muted">Page {page} of {totalPages}</span>
            <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages} className="flex items-center gap-1 rounded px-2 py-1 text-sm text-muted hover:text-foreground disabled:opacity-40">
              Next <ChevronRight size={14} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
      <div className="text-xs text-muted mt-1">{label}</div>
    </div>
  );
}
