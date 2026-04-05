"use client";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { LoginForm } from "@/components/login-form";
import { findClientMatches, ClientMatchResult } from "@/lib/api";
import { Crosshair, Search, ExternalLink } from "lucide-react";

function formatAED(n: number | null | undefined) {
  if (!n) return "--";
  return "AED " + Math.round(n).toLocaleString();
}

function ClientMatchForm() {
  const searchParams = useSearchParams();
  const [listingType, setListingType] = useState(searchParams.get("type") || "rent");
  const [bedrooms, setBedrooms] = useState(searchParams.get("beds") || "");
  const [budgetMin, setBudgetMin] = useState(searchParams.get("budget_min") || "");
  const [budgetMax, setBudgetMax] = useState(searchParams.get("budget_max") || "");
  const [building, setBuilding] = useState(searchParams.get("building") || "");
  const [sizeMin, setSizeMin] = useState("");
  const [sizeMax, setSizeMax] = useState("");
  const [results, setResults] = useState<ClientMatchResult[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState("");

  // Auto-search if we arrived with pre-filled params from Contacts page
  useEffect(() => {
    if (searchParams.get("budget_max") || searchParams.get("beds")) {
      handleSearch();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSearch = async () => {
    setError("");
    setLoading(true);
    setSearched(false);
    try {
      const res = await findClientMatches({
        listing_type: listingType || undefined,
        bedrooms: bedrooms ? (bedrooms === "studio" ? "studio" : Number(bedrooms)) : undefined,
        budget_min: budgetMin ? Number(budgetMin) : undefined,
        budget_max: budgetMax ? Number(budgetMax) : undefined,
        building: building.trim() || undefined,
        size_min: sizeMin ? Number(sizeMin) : undefined,
        size_max: sizeMax ? Number(sizeMax) : undefined,
      });
      setResults(res.results);
      setTotal(res.total);
      setSearched(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Search failed");
    } finally { setLoading(false); }
  };

  return (
    <>
      <div className="rounded-xl border border-border bg-card p-4">
        <p className="mb-3 text-xs text-muted">Enter your client&apos;s requirements to find matching Bayut listings</p>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
          <div>
            <label className="mb-1 block text-xs text-muted">Type</label>
            <select value={listingType} onChange={e => setListingType(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent">
              <option value="">Any</option>
              <option value="rent">Rent</option>
              <option value="sale">Sale / Buy</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">Bedrooms</label>
            <select value={bedrooms} onChange={e => setBedrooms(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent">
              <option value="">Any</option>
              <option value="studio">Studio</option>
              <option value="1">1 BR</option>
              <option value="2">2 BR</option>
              <option value="3">3 BR</option>
              <option value="4">4 BR</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">Budget min (AED)</label>
            <input type="number" placeholder="e.g. 100000" value={budgetMin} onChange={e => setBudgetMin(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">Budget max (AED)</label>
            <input type="number" placeholder="e.g. 200000" value={budgetMax} onChange={e => setBudgetMax(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">Building (optional)</label>
            <input type="text" placeholder="e.g. Shoreline" value={building} onChange={e => setBuilding(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">Size min (sqft)</label>
            <input type="number" placeholder="e.g. 800" value={sizeMin} onChange={e => setSizeMin(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">Size max (sqft)</label>
            <input type="number" placeholder="e.g. 1500" value={sizeMax} onChange={e => setSizeMax(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent" />
          </div>
        </div>
        {error && <p className="mt-2 text-xs text-danger">{error}</p>}
        <button onClick={handleSearch} disabled={loading}
          className="mt-4 flex items-center gap-2 rounded-lg bg-accent px-5 py-2 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-50">
          <Search size={14} />
          {loading ? "Searching..." : "Find Matches"}
        </button>
      </div>

      {searched && (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <div className="border-b border-border px-4 py-2">
            <span className="text-sm text-muted">
              {total} listing{total !== 1 ? "s" : ""} match{total === 1 ? "es" : ""} this brief
              {total > 100 && " (showing top 100)"}
            </span>
          </div>
          {results.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-muted">No listings found — try relaxing the budget or size filters</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border bg-background/50">
                    {["Building", "Beds", "Size", "Price", "Type", "View", "Link"].map(h => (
                      <th key={h} className="whitespace-nowrap px-4 py-2 text-left text-xs font-medium text-muted">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {results.map((r, i) => (
                    <tr key={i} className="border-b border-border/50 hover:bg-card-hover">
                      <td className="px-4 py-2 text-sm text-foreground">{r.building_name || "--"}</td>
                      <td className="px-4 py-2 text-sm text-muted">
                        {r.bedrooms != null ? (r.bedrooms === 0 ? "Studio" : `${r.bedrooms} BR`) : "--"}
                      </td>
                      <td className="px-4 py-2 text-sm text-muted">
                        {r.size_sqft ? `${Math.round(r.size_sqft).toLocaleString()} sqft` : "--"}
                      </td>
                      <td className="px-4 py-2 text-sm font-semibold text-foreground">{formatAED(r.price_aed)}</td>
                      <td className="px-4 py-2">
                        <span className={`rounded-full px-2 py-0.5 text-xs ${r.listing_type === "rent" ? "bg-accent/10 text-accent" : "bg-warning/10 text-warning"}`}>
                          {r.listing_type === "rent" ? "Rent" : "Sale"}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-xs text-muted">{r.view || "--"}</td>
                      <td className="px-4 py-2">
                        {r.listing_url ? (
                          <a href={r.listing_url} target="_blank" rel="noopener noreferrer"
                            className="flex items-center gap-1 text-xs text-accent hover:underline">
                            <ExternalLink size={12} /> View
                          </a>
                        ) : <span className="text-xs text-muted">--</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </>
  );
}

export default function ClientMatchPage() {
  const { authenticated } = useAuth();
  if (!authenticated) return <LoginForm />;

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-20 md:pb-4">
      <div className="flex items-center gap-2">
        <Crosshair size={20} className="text-accent" />
        <h1 className="text-lg font-semibold text-foreground">Client Match</h1>
        <span className="text-xs text-muted">Find available listings that match a client brief</span>
      </div>
      <Suspense fallback={<div className="text-sm text-muted">Loading...</div>}>
        <ClientMatchForm />
      </Suspense>
    </div>
  );
}
