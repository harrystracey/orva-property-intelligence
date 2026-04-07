"use client";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { LoginForm } from "@/components/login-form";
import { matchListing, scrapeAndMatch, MatchResult, ScrapedListing } from "@/lib/api";
import { Crosshair, Search, Phone, User, Link2, Loader2 } from "lucide-react";

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

function MatcherForm() {
  const searchParams = useSearchParams();
  const [building, setBuilding] = useState(searchParams.get("building") || "");
  const [unit, setUnit] = useState(searchParams.get("unit") || "");
  const [size, setSize] = useState(searchParams.get("size") || "");
  const [bedrooms, setBedrooms] = useState(searchParams.get("beds") || "");
  const [url, setUrl] = useState("");
  const [results, setResults] = useState<MatchResult[]>([]);
  const [scrapedListing, setScrapedListing] = useState<ScrapedListing | null>(null);
  const [loading, setLoading] = useState(false);
  const [scraping, setScraping] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState("");

  // Auto-run if we arrived with pre-filled params from Bayut page
  useEffect(() => {
    if (searchParams.get("building") && searchParams.get("size")) {
      handleMatch();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleScrapeAndMatch = async () => {
    const u = url.trim();
    if (!u) return;
    if (!u.includes("bayut.com") && !u.includes("propertyfinder")) {
      setError("Only Bayut and PropertyFinder URLs are supported");
      return;
    }
    setError("");
    setScraping(true);
    setSearched(false);
    setScrapedListing(null);
    try {
      const res = await scrapeAndMatch(u);
      setScrapedListing(res.listing);
      setResults(res.matches);
      // Auto-fill the manual fields from scraped data
      if (res.listing.building) setBuilding(res.listing.building);
      if (res.listing.bedrooms != null) setBedrooms(String(res.listing.bedrooms === 0 ? "Studio" : res.listing.bedrooms));
      if (res.listing.size_sqft) setSize(String(Math.round(res.listing.size_sqft)));
      setSearched(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Scrape failed");
    } finally { setScraping(false); }
  };

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
      });
      setResults(res.results);
      setSearched(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Match failed");
    } finally { setLoading(false); }
  };

  return (
    <>
      {/* URL Paste — Primary Action */}
      <div className="rounded-xl border-2 border-accent/30 bg-accent/5 p-4">
        <div className="flex items-center gap-2 mb-2">
          <Link2 size={16} className="text-accent" />
          <span className="text-sm font-medium text-foreground">Paste listing URL</span>
        </div>
        <div className="flex gap-2">
          <input type="text" placeholder="https://www.bayut.com/property/details-... or propertyfinder.ae/..."
            value={url} onChange={e => setUrl(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleScrapeAndMatch()}
            className="flex-1 rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none focus:border-accent" />
          <button onClick={handleScrapeAndMatch} disabled={scraping || !url.trim()}
            className="flex items-center gap-2 rounded-lg bg-accent px-5 py-2.5 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-40">
            {scraping ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
            {scraping ? "Scraping..." : "Find Owner"}
          </button>
        </div>
        {scrapedListing && (
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted">
            <span className="rounded bg-background px-2 py-0.5">{scrapedListing.portal}</span>
            {scrapedListing.building && <span className="rounded bg-background px-2 py-0.5">{scrapedListing.building}</span>}
            {scrapedListing.bedrooms != null && <span className="rounded bg-background px-2 py-0.5">{scrapedListing.bedrooms === 0 ? "Studio" : `${scrapedListing.bedrooms} BR`}</span>}
            {scrapedListing.size_sqft && <span className="rounded bg-background px-2 py-0.5">{Math.round(scrapedListing.size_sqft).toLocaleString()} sqft</span>}
            {scrapedListing.price && <span className="rounded bg-background px-2 py-0.5">AED {scrapedListing.price.toLocaleString()}</span>}
            {scrapedListing.listing_type && <span className="rounded bg-background px-2 py-0.5">{scrapedListing.listing_type}</span>}
            {scrapedListing.view && <span className="rounded bg-background px-2 py-0.5">{scrapedListing.view}</span>}
          </div>
        )}
      </div>

      {/* Manual Entry — Fallback */}
      <details className="rounded-xl border border-border bg-card">
        <summary className="cursor-pointer px-4 py-3 text-xs text-muted hover:text-foreground">
          Or enter details manually
        </summary>
        <div className="px-4 pb-4">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className="mb-1 block text-xs text-muted">Building *</label>
              <input type="text" placeholder="e.g. Shoreline 5" value={building}
                onChange={e => setBuilding(e.target.value)} onKeyDown={e => e.key === "Enter" && handleMatch()}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent" />
            </div>
            <div>
              <label className="mb-1 block text-xs text-muted">Unit Number</label>
              <input type="text" placeholder="e.g. 204" value={unit}
                onChange={e => setUnit(e.target.value)} onKeyDown={e => e.key === "Enter" && handleMatch()}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent" />
            </div>
            <div>
              <label className="mb-1 block text-xs text-muted">Size (sqft)</label>
              <input type="number" placeholder="e.g. 1250" value={size} onChange={e => setSize(e.target.value)}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent" />
            </div>
            <div>
              <label className="mb-1 block text-xs text-muted">Bedrooms</label>
              <select value={bedrooms} onChange={e => setBedrooms(e.target.value)}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent">
                <option value="">Any</option>
                <option value="Studio">Studio</option>
                <option value="1">1 BR</option>
                <option value="2">2 BR</option>
                <option value="3">3 BR</option>
                <option value="4">4 BR</option>
                <option value="5">5 BR</option>
              </select>
            </div>
          </div>
          <button onClick={handleMatch} disabled={loading}
            className="mt-3 flex items-center gap-2 rounded-lg bg-accent px-5 py-2 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-50">
            <Search size={14} />
            {loading ? "Matching..." : "Find Owner"}
          </button>
        </div>
      </details>

      {error && <p className="text-xs text-danger px-1">{error}</p>}

      {/* Results */}
      {searched && (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          <div className="border-b border-border px-4 py-2">
            <span className="text-sm text-muted">{results.length} match{results.length !== 1 ? "es" : ""} found</span>
          </div>
          {results.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-muted">No matches — try removing unit number or adjusting size</div>
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
    </>
  );
}

export default function MatcherPage() {
  const { authenticated } = useAuth();
  if (!authenticated) return <LoginForm />;

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-20 md:pb-4">
      <div className="flex items-center gap-2">
        <Crosshair size={20} className="text-accent" />
        <h1 className="text-lg font-semibold text-foreground">Listing Matcher</h1>
      </div>
      <Suspense fallback={<div className="text-sm text-muted">Loading...</div>}>
        <MatcherForm />
      </Suspense>
    </div>
  );
}
