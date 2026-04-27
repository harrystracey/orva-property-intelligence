"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Home, Building2, ExternalLink } from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import { getBayutListings, BayutListing, BayutListingsResponse } from "@/lib/api";

const TYPE_OPTS = ["", "sale", "rent"] as const;
const BED_OPTS = ["", "0", "1", "2", "3", "4", "5", "6"] as const;

function fmtPrice(p: number | null): string {
  return p != null ? `${Math.round(p).toLocaleString()} AED` : "--";
}

export default function BayutPage() {
  const { authenticated, loading: authLoading } = useAuth();
  const router = useRouter();

  const [data, setData] = useState<BayutListingsResponse | null>(null);
  const [type, setType] = useState("");
  const [building, setBuilding] = useState("");
  const [beds, setBeds] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(
        await getBayutListings({
          listing_type: type || undefined,
          building: building || undefined,
          bedrooms: beds || undefined,
          limit: 200,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [type, building, beds]);

  useEffect(() => {
    if (authenticated) refresh();
  }, [authenticated, refresh]);

  if (authLoading) return null;
  if (!authenticated) {
    router.replace("/");
    return null;
  }

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-mobile-nav max-w-6xl mx-auto w-full">
      <div className="flex items-center gap-2">
        <Home size={20} className="text-accent" />
        <h1 className="text-lg font-semibold text-foreground">Active Bayut Listings</h1>
        {data && (
          <span className="text-sm text-muted">({data.total} shown)</span>
        )}
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <div>
          <label className="text-xs text-muted">Type</label>
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="mt-1 w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground"
          >
            {TYPE_OPTS.map((t) => (
              <option key={t} value={t}>{t ? t.toUpperCase() : "All"}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs text-muted">Building (substring)</label>
          <input
            value={building}
            onChange={(e) => setBuilding(e.target.value)}
            placeholder="e.g. Shoreline"
            className="mt-1 w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground placeholder:text-muted"
          />
        </div>
        <div>
          <label className="text-xs text-muted">Bedrooms</label>
          <select
            value={beds}
            onChange={(e) => setBeds(e.target.value)}
            className="mt-1 w-full rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground"
          >
            {BED_OPTS.map((b) => (
              <option key={b} value={b}>{b || "Any"}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Stats */}
      {data && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label="Listings" value={data.total} />
          <Stat label="For Sale" value={data.sale_count} />
          <Stat label="For Rent" value={data.rent_count} />
          <Stat label="Buildings" value={data.unique_buildings} />
        </div>
      )}

      {data && data.last_scraped && (
        <p className="text-xs text-muted">
          Last scraped: {data.last_scraped}
        </p>
      )}

      {error && (
        <div className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-2 text-sm text-danger">
          {error}
        </div>
      )}

      {/* Per-building summary */}
      {data && data.building_summary.length > 0 && (
        <div className="rounded-xl border border-border bg-card p-4">
          <h2 className="mb-3 text-sm font-semibold text-foreground">By building</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-left uppercase text-muted">
                <tr>
                  <th className="px-2 py-1">Building</th>
                  <th className="px-2 py-1">Listings</th>
                  <th className="px-2 py-1">Avg Beds</th>
                  <th className="px-2 py-1">Avg Size</th>
                  <th className="px-2 py-1">Avg Price</th>
                  <th className="px-2 py-1">Types</th>
                </tr>
              </thead>
              <tbody>
                {data.building_summary.map((b) => (
                  <tr key={b.building_name} className="border-t border-border">
                    <td className="px-2 py-1.5 text-foreground">{b.building_name}</td>
                    <td className="px-2 py-1.5 text-foreground">{b.listings}</td>
                    <td className="px-2 py-1.5 text-foreground">
                      {b.avg_beds != null ? b.avg_beds.toFixed(1) : "--"}
                    </td>
                    <td className="px-2 py-1.5 text-foreground">
                      {b.avg_size != null ? Math.round(b.avg_size).toLocaleString() : "--"}
                    </td>
                    <td className="px-2 py-1.5 text-foreground">
                      {b.avg_price != null ? Math.round(b.avg_price).toLocaleString() : "--"}
                    </td>
                    <td className="px-2 py-1.5 text-muted">{b.types}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Listings */}
      {loading ? (
        <div className="rounded-xl border border-border bg-card p-8 text-center text-muted">
          Loading...
        </div>
      ) : !data || data.listings.length === 0 ? (
        <div className="rounded-xl border border-border bg-card p-8 text-center text-muted text-sm">
          No listings (the public Bayut scraper writes to data/bayut_palm_listings.csv).
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {data.listings.map((L, idx) => (
            <ListingCard key={`${L.listing_url}-${idx}`} listing={L} />
          ))}
        </div>
      )}
    </div>
  );
}

function ListingCard({ listing }: { listing: BayutListing }) {
  return (
    <div className="rounded-xl border border-border bg-card p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Building2 size={12} className="text-accent" />
            <span className="text-sm font-medium text-foreground truncate">
              {listing.building_name || "(no building)"}
            </span>
            {listing.listing_type && (
              <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] text-accent uppercase">
                {listing.listing_type}
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted">
            {listing.unit_number && <span>Unit {listing.unit_number}</span>}
            {listing.bedrooms && <span>{listing.bedrooms} BR</span>}
            {listing.size_sqft && (
              <span>{Math.round(listing.size_sqft).toLocaleString()} sqft</span>
            )}
            <span className="font-medium text-foreground">
              {fmtPrice(listing.price_aed)}
              {listing.rent_period ? `/${listing.rent_period}` : ""}
            </span>
          </div>
          {(listing.agent_name || listing.agency) && (
            <p className="mt-1 text-[11px] text-muted">
              {[listing.agent_name, listing.agency].filter(Boolean).join(" / ")}
            </p>
          )}
        </div>
        {listing.listing_url && (
          <a
            href={listing.listing_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 rounded-lg border border-border px-2 py-1 text-xs text-muted hover:text-accent shrink-0"
          >
            <ExternalLink size={10} />
            Open
          </a>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-border bg-card p-3 text-center">
      <p className="text-xl font-bold text-foreground">{value.toLocaleString()}</p>
      <p className="text-[11px] text-muted">{label}</p>
    </div>
  );
}
