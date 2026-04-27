"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Globe,
  Download,
  RefreshCw,
  Search,
  Terminal,
} from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import { getPfLeads, PfLeadsResponse } from "@/lib/api";

function fmtTime(iso: string | null): string {
  if (!iso) return "--";
  try {
    return new Date(iso).toLocaleString("en-GB", {
      day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

const PREFERRED_COLUMNS = [
  "owner_name",
  "phone",
  "building_name",
  "unit_number",
  "bedrooms",
  "size_sqft",
  "listing_type",
  "listing_price",
  "permit_number",
  "listing_url",
];

export default function PfScraperPage() {
  const { authenticated } = useAuth();
  const router = useRouter();

  const [data, setData] = useState<PfLeadsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await getPfLeads(500));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authenticated) refresh();
  }, [authenticated, refresh]);

  const filteredRows = useMemo(() => {
    if (!data) return [];
    if (!query.trim()) return data.rows;
    const q = query.trim().toLowerCase();
    return data.rows.filter((row) =>
      Object.values(row).some((v) => String(v ?? "").toLowerCase().includes(q)),
    );
  }, [data, query]);

  const columns = useMemo(() => {
    if (!data || data.rows.length === 0) return [];
    const present = new Set(Object.keys(data.rows[0]));
    const ordered = PREFERRED_COLUMNS.filter((c) => present.has(c));
    const rest = (data.columns || Object.keys(data.rows[0])).filter(
      (c) => !PREFERRED_COLUMNS.includes(c),
    );
    return [...ordered, ...rest];
  }, [data]);

  if (!authenticated) {
    router.replace("/");
    return null;
  }

  const handleDownload = () => {
    if (!data || data.rows.length === 0) return;
    const cols = columns;
    const headers = cols.join(",");
    const lines = data.rows.map((r) =>
      cols.map((c) => `"${String(r[c] ?? "").replace(/"/g, '""')}"`).join(","),
    );
    const csv = [headers, ...lines].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `pf_leads_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-mobile-nav max-w-6xl mx-auto w-full">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Globe size={20} className="text-accent" />
          <h1 className="text-lg font-semibold text-foreground">PropertyFinder Scraper</h1>
          {data && (
            <span className="text-sm text-muted">
              ({data.total.toLocaleString()} rows)
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={refresh}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm text-muted hover:bg-card-hover hover:text-foreground disabled:opacity-50"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
          {data && data.rows.length > 0 && (
            <button
              onClick={handleDownload}
              className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm text-muted hover:bg-card-hover hover:text-foreground"
            >
              <Download size={14} />
              CSV
            </button>
          )}
        </div>
      </div>

      {/* Status banner */}
      <div className="rounded-xl border border-border bg-card p-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div>
            <p className="text-xs text-muted">CSV path</p>
            <p className="font-mono text-xs text-foreground truncate">
              {data?.csv_path ?? "--"}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted">Last scraped</p>
            <p className="text-sm text-foreground">{fmtTime(data?.last_scraped ?? null)}</p>
          </div>
          <div>
            <p className="text-xs text-muted">Total rows</p>
            <p className="text-sm text-foreground font-medium">
              {data?.total.toLocaleString() ?? "--"}
            </p>
          </div>
        </div>
      </div>

      {/* Run instructions */}
      <details className="rounded-xl border border-border bg-card p-4">
        <summary className="flex cursor-pointer items-center gap-2 text-sm font-medium text-foreground">
          <Terminal size={14} className="text-accent" />
          How to run the scraper (CLI only)
        </summary>
        <div className="mt-3 flex flex-col gap-2 text-xs text-muted">
          <p>
            Live scraping requires Chrome on port 9222 with a logged-in
            PropertyFinder + Replit session, so it runs from the host
            machine -- not from this web UI.
          </p>
          <p>From the project root on the scrape host:</p>
          <pre className="overflow-x-auto rounded-lg border border-border bg-background p-3 text-foreground">
{`# 1. Launch Chrome with the right tabs
powershell -ExecutionPolicy Bypass -File propertyfinder_scraper/start_pf_chrome.ps1

# 2. Log in to Replit. Search Palm Jumeirah / Rent on PropertyFinder.

# 3. Run the scraper
python propertyfinder_scraper/scraper.py --max-pages 5 --max-listings 50

# Output appends to scraped_data/propertyfinder_scraped_leads.csv
# (resume with --resume; it dedupes by listing_url)`}
          </pre>
          <p>
            After it finishes, refresh this page to see the new rows.
          </p>
        </div>
      </details>

      {/* Empty / missing CSV */}
      {data && !data.csv_present && (
        <div className="rounded-xl border border-warning/30 bg-warning/5 p-6 text-center text-sm text-foreground">
          No PropertyFinder data yet. The CSV at <code>{data.csv_path}</code> doesn&apos;t exist.
          Run the scraper (instructions above) to populate it.
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-2 text-sm text-danger">
          {error}
        </div>
      )}

      {/* Data table */}
      {data && data.rows.length > 0 && (
        <>
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter rows (substring search)"
              className="w-full rounded-lg border border-border bg-card px-3 py-2 pl-9 text-sm text-foreground placeholder:text-muted focus:border-accent focus:outline-none"
            />
          </div>
          <p className="text-xs text-muted">
            Showing {filteredRows.length.toLocaleString()} of {data.total.toLocaleString()}
            {data.rows.length < data.total && ` (loaded first ${data.rows.length})`}
          </p>
          <div className="overflow-x-auto rounded-xl border border-border bg-card">
            <table className="w-full text-xs">
              <thead className="border-b border-border bg-background text-left uppercase text-muted">
                <tr>
                  {columns.map((c) => (
                    <th key={c} className="whitespace-nowrap px-3 py-2 font-medium">
                      {c.replace(/_/g, " ")}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredRows.slice(0, 200).map((row, idx) => (
                  <tr key={idx} className="border-b border-border last:border-0">
                    {columns.map((c) => {
                      const val = row[c];
                      const isUrl = c === "listing_url" && val;
                      return (
                        <td
                          key={c}
                          className="whitespace-nowrap px-3 py-1.5 text-foreground max-w-[240px] truncate"
                        >
                          {isUrl ? (
                            <a
                              href={val}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-accent hover:underline"
                            >
                              open
                            </a>
                          ) : (
                            String(val ?? "")
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
            {filteredRows.length > 200 && (
              <div className="border-t border-border p-3 text-center text-xs text-muted">
                Showing first 200 of {filteredRows.length.toLocaleString()} matching rows.
                Use the filter to narrow down, or download CSV for the full set.
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
