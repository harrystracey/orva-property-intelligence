"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { LoginForm } from "@/components/login-form";
import { matchListing, MatchResult } from "@/lib/api";
import { Crosshair, Search, Phone, User } from "lucide-react";

function confidenceBadge(c: number) {
  const pct = Math.round(c * 100);
  const color = c >= 0.9 ? "text-success bg-success/10" : c >= 0.6 ? "text-warning bg-warning/10" : "text-muted bg-muted/10";
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${color}`}>{pct}%</span>;
}

const MATCH_TYPE_LABEL: Record<string, string> = {
  exact_unit: "Exact Unit",
  exact_size: "Exact Size",
  beds_range: "Beds + Size",
};

export default function MatcherPage() {
  const { authenticated } = useAuth();
  const [building, setBuilding] = useState("");
  const [unit, setUnit] = useState("");
  const [size, setSize] = useState("");
  const [bedrooms, setBedrooms] = useState("");
  const [url, setUrl] = useState("");
  const [results, setResults] = useState<MatchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState("");

  const handleMatch = async () => {
    if (!building.trim()) { setError("Building name is required"); return; }
    setError("");
    setLoading(true);
    setSearched(false);
    try {
      const res = await matchListing({
        building_name: building.trim(),
        unit_number: unit.trim() || undefined,
        size_sqft: size ? Number(size) : undefined,
        bedrooms: bedrooms || undefined,
        listing_url: url.trim() || undefined,
      });
      setResults(res.results);
      setSearched(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Match failed");
    } finally { setLoading(false); }
  };

  if (!authenticated) return <LoginForm />;

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-20 md:pb-4">
      <div className="flex items-center gap-2">
        <Crosshair size={20} className="text-accent" />
        <h1 className="text-lg font-semibold text-foreground">Listing Matcher</h1>
      </div>

      {/* Input form */}
      <div className="rounded-xl border border-border bg-card p-4">
        <p className="mb-3 text-xs text-muted">Enter listing details to find the owner in the database</p>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          <div>
            <label className="mb-1 block text-xs text-muted">Building *</label>
            <input
              type="text"
              placeholder="e.g. Shoreline 5"
              value={building}
              onChange={e => setBuilding(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleMatch()}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">Unit Number</label>
            <input
              type="text"
              placeholder="e.g. 204"
              value={unit}
              onChange={e => setUnit(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleMatch()}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">Size (sqft)</label>
            <input
              type="number"
              placeholder="e.g. 1250"
              value={size}
              onChange={e => setSize(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">Bedrooms</label>
            <select
              value={bedrooms}
              onChange={e => setBedrooms(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent"
            >
              <option value="">Any</option>
              <option value="Studio">Studio</option>
              <option value="1">1 BR</option>
              <option value="2">2 BR</option>
              <option value="3">3 BR</option>
              <option value="4">4 BR</option>
              <option value="5">5 BR</option>
            </select>
          </div>
          <div className="md:col-span-2">
            <label className="mb-1 block text-xs text-muted">Listing URL (optional)</label>
            <input
              type="text"
              placeholder="https://bayut.com/..."
              value={url}
              onChange={e => setUrl(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent"
            />
          </div>
        </div>
        {error && <p className="mt-2 text-xs text-danger">{error}</p>}
        <button
          onClick={handleMatch}
          disabled={loading}
          className="mt-4 flex items-center gap-2 rounded-lg bg-accent px-5 py-2 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-50"
        >
          <Search size={14} />
          {loading ? "Matching..." : "Find Owner"}
        </button>
      </div>

      {/* Results */}
      {searched && (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <div className="border-b border-border px-4 py-2">
            <span className="text-sm text-muted">{results.length} match{results.length !== 1 ? "es" : ""} found</span>
          </div>
          {results.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-muted">No matches found — try removing unit number or adjusting size</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border bg-background/50">
                    {["Confidence", "Match", "Owner", "Phone", "Unit", "Size", "Source"].map(h => (
                      <th key={h} className="whitespace-nowrap px-4 py-2 text-left text-xs font-medium text-muted">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {results.map((r, i) => (
                    <tr key={i} className="border-b border-border/50 hover:bg-card-hover">
                      <td className="px-4 py-2">{confidenceBadge(r.confidence)}</td>
                      <td className="px-4 py-2 text-xs text-muted">{MATCH_TYPE_LABEL[r.match_type] ?? r.match_type}</td>
                      <td className="px-4 py-2">
                        <span className="flex items-center gap-1 text-sm text-foreground">
                          <User size={12} className="text-muted" />{r.owner_name || "--"}
                        </span>
                      </td>
                      <td className="px-4 py-2">
                        <span className="flex items-center gap-1 text-sm font-mono text-accent">
                          <Phone size={12} />{r.phone_display || r.phone || "--"}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-sm text-muted">{r.unit || "--"}</td>
                      <td className="px-4 py-2 text-sm text-muted">{r.size_sqft ? `${Math.round(r.size_sqft).toLocaleString()} sqft` : "--"}</td>
                      <td className="px-4 py-2 text-xs text-muted">{r.source_file || "--"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
