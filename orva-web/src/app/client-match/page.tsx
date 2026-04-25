"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Crosshair, Phone, Building2, ExternalLink, ArrowRight } from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import {
  findClientMatches,
  ClientMatchResponse,
  OwnerMatchResult,
} from "@/lib/api";

const BED_OPTS = ["", "Studio", "1", "2", "3", "4", "5", "5+"] as const;

export default function ClientMatchPage() {
  const { authenticated } = useAuth();
  const router = useRouter();

  const [txnType, setTxnType] = useState<"sale" | "rent">("sale");
  const [beds, setBeds] = useState("");
  const [buildingsCsv, setBuildingsCsv] = useState("");
  const [seaView, setSeaView] = useState(false);
  const [budgetMin, setBudgetMin] = useState(
    txnType === "sale" ? "1000000" : "50000",
  );
  const [budgetMax, setBudgetMax] = useState(
    txnType === "sale" ? "5000000" : "250000",
  );
  const [data, setData] = useState<ClientMatchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  if (!authenticated) {
    router.replace("/");
    return null;
  }

  const handleTxnChange = (next: "sale" | "rent") => {
    setTxnType(next);
    if (next === "sale") {
      setBudgetMin("1000000");
      setBudgetMax("5000000");
    } else {
      setBudgetMin("50000");
      setBudgetMax("250000");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const buildings = buildingsCsv
        .split(",")
        .map((b) => b.trim())
        .filter(Boolean);
      setData(
        await findClientMatches({
          transaction_type: txnType,
          bedrooms: beds || null,
          buildings,
          sea_view_only: seaView,
          budget_min: budgetMin ? Number(budgetMin) : null,
          budget_max: budgetMax ? Number(budgetMax) : null,
          limit: 100,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-mobile-nav max-w-4xl mx-auto w-full">
      <div className="flex items-center gap-2">
        <Crosshair size={20} className="text-accent" />
        <h1 className="text-lg font-semibold text-foreground">
          Find Owners for My Client
        </h1>
      </div>
      <p className="text-xs text-muted">
        Enter a buyer / tenant&apos;s requirements; we rank owners in your
        database by match quality + active listings.
      </p>

      {/* Form */}
      <form
        onSubmit={handleSubmit}
        className="rounded-xl border border-border bg-card p-4 flex flex-col gap-3"
      >
        {/* Sale / Rent toggle */}
        <div className="flex gap-1 rounded-lg border border-border bg-background p-1">
          {(["sale", "rent"] as const).map((t) => (
            <button
              type="button"
              key={t}
              onClick={() => handleTxnChange(t)}
              className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                txnType === t
                  ? "bg-accent/15 text-accent"
                  : "text-muted hover:text-foreground"
              }`}
            >
              {t === "sale" ? "Sale" : "Rent"}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <div>
            <label className="text-xs text-muted">Bedrooms</label>
            <select
              value={beds}
              onChange={(e) => setBeds(e.target.value)}
              className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
            >
              {BED_OPTS.map((b) => (
                <option key={b} value={b}>{b || "Any"}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted">
              Building(s) (comma-separated, blank = all)
            </label>
            <input
              value={buildingsCsv}
              onChange={(e) => setBuildingsCsv(e.target.value)}
              placeholder="e.g. Shoreline 9, Oceana"
              className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted"
            />
          </div>
          <div>
            <label className="text-xs text-muted">
              Budget min ({txnType === "sale" ? "AED" : "AED/yr"})
            </label>
            <input
              type="number"
              value={budgetMin}
              onChange={(e) => setBudgetMin(e.target.value)}
              className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
            />
          </div>
          <div>
            <label className="text-xs text-muted">
              Budget max ({txnType === "sale" ? "AED" : "AED/yr"})
            </label>
            <input
              type="number"
              value={budgetMax}
              onChange={(e) => setBudgetMax(e.target.value)}
              className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
            />
          </div>
        </div>

        <label className="flex items-center gap-2 text-sm text-foreground">
          <input
            type="checkbox"
            checked={seaView}
            onChange={(e) => setSeaView(e.target.checked)}
            className="accent-accent"
          />
          Sea view preferred
        </label>

        {error && (
          <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-background disabled:opacity-50"
        >
          {loading ? "Searching..." : "Find owners"}
        </button>
      </form>

      {/* Results */}
      {data && (
        <>
          <div className="text-xs text-muted">
            {data.matches.length} of {data.total} matching owners (sorted by score)
          </div>
          {data.matches.length === 0 ? (
            <div className="rounded-xl border border-border bg-card p-6 text-center text-muted text-sm">
              No matches. Try widening the bedroom range or budget, or removing
              the sea-view filter.
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {data.matches.map((m) => (
                <OwnerMatchCard
                  key={m.client_id}
                  match={m}
                  onClick={() => router.push(`/client/${m.client_id}`)}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function OwnerMatchCard({
  match,
  onClick,
}: {
  match: OwnerMatchResult;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="rounded-xl border border-border bg-card p-3 text-left transition-colors hover:bg-card-hover"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Building2 size={12} className="text-accent" />
            <span className="text-sm font-medium text-foreground truncate">
              {match.owner_name || "(unknown)"}
            </span>
            {match.has_active_listing && (
              <span className="rounded-full bg-success/15 px-2 py-0.5 text-[10px] text-success">
                LIVE LISTING
              </span>
            )}
          </div>
          <div className="text-xs text-muted">
            {match.building_name || "--"}
            {match.unit_number && ` / ${match.unit_number}`}
            {match.bedrooms && ` / ${match.bedrooms} BR`}
            {match.size_sqft && ` / ${Math.round(match.size_sqft)} sqft`}
          </div>

          <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs">
            {match.phone && (
              <span className="flex items-center gap-1 text-accent">
                <Phone size={10} />
                {match.phone}
              </span>
            )}
            {match.last_sale_price && (
              <span className="text-muted">
                Last sale: {Math.round(match.last_sale_price).toLocaleString()} AED
              </span>
            )}
            {match.active_listing_price && (
              <span className="text-success">
                Listed: {Math.round(match.active_listing_price).toLocaleString()} AED
              </span>
            )}
          </div>

          {match.score_factors.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {match.score_factors.map((f) => (
                <span
                  key={f}
                  className="rounded bg-accent/10 px-1.5 py-0.5 text-[10px] text-accent"
                >
                  {f}
                </span>
              ))}
            </div>
          )}

          {match.active_listing_url && (
            <a
              href={match.active_listing_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="mt-1 inline-flex items-center gap-1 text-[11px] text-accent hover:underline"
            >
              <ExternalLink size={10} />
              View listing
            </a>
          )}
        </div>

        <div className="shrink-0 flex flex-col items-end gap-1">
          <div className="rounded-full bg-accent/15 px-2.5 py-1 text-xs font-bold text-accent">
            {Math.round(match.score)}
          </div>
          <ArrowRight size={14} className="text-muted" />
        </div>
      </div>
    </button>
  );
}
