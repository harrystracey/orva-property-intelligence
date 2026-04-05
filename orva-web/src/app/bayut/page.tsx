"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { LoginForm } from "@/components/login-form";
import { getBayutListings, getBayutStats, BayutListing } from "@/lib/api";
import { Home, ChevronLeft, ChevronRight, ExternalLink, Crosshair, RefreshCw } from "lucide-react";

const PAGE_SIZE = 50;

function formatAED(n: number | null | undefined) {
  if (!n) return "--";
  return "AED " + Math.round(n).toLocaleString();
}

export default function BayutPage() {
  const { authenticated } = useAuth();
  const router = useRouter();
  const [listings, setListings] = useState<BayutListing[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<{ total: number; for_rent: number; for_sale: number; buildings: number } | null>(null);
  const [listingType, setListingType] = useState("rent");
  const [building, setBuilding] = useState("");
  const [bedrooms, setBedrooms] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMsg, setRefreshMsg] = useState("");

  const loadStats = useCallback(async () => {
    try { setStats(await getBayutStats()); } catch { /* ignore */ }
  }, []);

  const loadListings = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getBayutListings({
        listing_type: listingType || undefined,
        building: building || undefined,
        bedrooms: bedrooms || undefined,
        page,
        page_size: PAGE_SIZE,
      });
      setListings(res.listings);
      setTotal(res.total);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [listingType, building, bedrooms, page]);

  useEffect(() => { if (authenticated) { loadStats(); loadListings(); } }, [authenticated, loadStats, loadListings]);

  const handleMatchOwner = (l: BayutListing) => {
    const params = new URLSearchParams();
    if (l.building_name) params.set("building", l.building_name);
    if (l.size_sqft) params.set("size", String(Math.round(l.size_sqft)));
    if (l.bedrooms != null) params.set("beds", l.bedrooms === 0 ? "Studio" : String(l.bedrooms));
    router.push(`/matcher?${params.toString()}`);
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    setRefreshMsg("");
    try {
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const token = localStorage.getItem("orva_token");
      const res = await fetch(`${API_BASE}/api/bayut/refresh`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      setRefreshMsg(data.message || "Scrape started in background");
    } catch {
      setRefreshMsg("Failed to start scrape — is Chrome running with --remote-debugging-port=9222?");
    } finally { setRefreshing(false); }
  };

  if (!authenticated) return <LoginForm />;

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-20 md:pb-4">
      <div className="flex items-center gap-2">
        <Home size={20} className="text-accent" />
        <h1 className="text-lg font-semibold text-foreground">Bayut Listings</h1>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="ml-auto flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-xs text-muted hover:text-foreground disabled:opacity-50"
        >
          <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
          {refreshing ? "Starting..." : "Refresh Data"}
        </button>
      </div>

      {refreshMsg && (
        <div className="rounded-lg border border-border bg-card px-4 py-2 text-xs text-muted">{refreshMsg}</div>
      )}

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatCard label="Total listings" value={stats.total.toLocaleString()} />
          <StatCard label="For rent" value={stats.for_rent.toLocaleString()} color="text-accent" />
          <StatCard label="For sale" value={stats.for_sale.toLocaleString()} color="text-warning" />
          <StatCard label="Buildings" value={stats.buildings.toLocaleString()} />
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3 rounded-xl border border-border bg-card px-4 py-3">
        <select value={listingType} onChange={e => { setListingType(e.target.value); setPage(1); }}
          className="rounded-lg border border-border bg-background px-2 py-1 text-sm text-foreground outline-none focus:border-accent">
          <option value="">All types</option>
          <option value="rent">Rent</option>
          <option value="sale">Sale</option>
        </select>
        <input
          type="text"
          placeholder="Building..."
          value={building}
          onChange={e => { setBuilding(e.target.value); setPage(1); }}
          className="rounded-lg border border-border bg-background px-3 py-1 text-sm text-foreground outline-none focus:border-accent"
        />
        <select value={bedrooms} onChange={e => { setBedrooms(e.target.value); setPage(1); }}
          className="rounded-lg border border-border bg-background px-2 py-1 text-sm text-foreground outline-none focus:border-accent">
          <option value="">All beds</option>
          <option value="studio">Studio</option>
          <option value="1">1 BR</option>
          <option value="2">2 BR</option>
          <option value="3">3 BR</option>
          <option value="4">4 BR</option>
        </select>
        <span className="ml-auto text-sm text-muted">{total.toLocaleString()} listings</span>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-border bg-card">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border bg-background/50">
                {["Building", "Beds", "Size", "Price", "Type", "View", "Link", ""].map(h => (
                  <th key={h} className="whitespace-nowrap px-4 py-2 text-left text-xs font-medium text-muted">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-sm text-muted">Loading...</td></tr>
              ) : listings.length === 0 ? (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-sm text-muted">No listings found</td></tr>
              ) : listings.map((l, i) => (
                <tr key={i} className="border-b border-border/50 hover:bg-card-hover">
                  <td className="px-4 py-2 text-sm text-foreground">{l.building_name || "--"}</td>
                  <td className="px-4 py-2 text-sm text-muted">
                    {l.bedrooms != null ? (l.bedrooms === 0 ? "Studio" : `${l.bedrooms} BR`) : "--"}
                  </td>
                  <td className="px-4 py-2 text-sm text-muted">
                    {l.size_sqft ? `${Math.round(l.size_sqft).toLocaleString()} sqft` : "--"}
                  </td>
                  <td className="px-4 py-2 text-sm font-medium text-foreground">{formatAED(l.price_aed)}</td>
                  <td className="px-4 py-2">
                    <span className={`rounded-full px-2 py-0.5 text-xs ${l.listing_type === "rent" ? "bg-accent/10 text-accent" : "bg-warning/10 text-warning"}`}>
                      {l.listing_type === "rent" ? "Rent" : "Sale"}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-xs text-muted">{l.view || "--"}</td>
                  <td className="px-4 py-2">
                    {l.listing_url ? (
                      <a href={l.listing_url} target="_blank" rel="noopener noreferrer"
                        className="flex items-center gap-1 text-xs text-accent hover:underline">
                        <ExternalLink size={12} /> View
                      </a>
                    ) : <span className="text-xs text-muted">--</span>}
                  </td>
                  <td className="px-4 py-2">
                    <button
                      onClick={() => handleMatchOwner(l)}
                      className="flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-muted hover:border-accent hover:text-accent"
                    >
                      <Crosshair size={11} /> Match Owner
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t border-border px-4 py-2">
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
              className="flex items-center gap-1 rounded px-2 py-1 text-sm text-muted hover:text-foreground disabled:opacity-40">
              <ChevronLeft size={14} /> Prev
            </button>
            <span className="text-xs text-muted">Page {page} of {totalPages}</span>
            <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
              className="flex items-center gap-1 rounded px-2 py-1 text-sm text-muted hover:text-foreground disabled:opacity-40">
              Next <ChevronRight size={14} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, color = "text-foreground" }: { label: string; value: string; color?: string }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
      <div className="mt-1 text-xs text-muted">{label}</div>
    </div>
  );
}
