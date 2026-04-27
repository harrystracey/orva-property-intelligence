"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Crosshair, Phone, Mail, Building2 } from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import { matchListing, MatchedOwner, MatchListingResponse } from "@/lib/api";

export default function MatcherPage() {
  const { authenticated, loading: authLoading } = useAuth();
  const router = useRouter();

  const [building, setBuilding] = useState("");
  const [unit, setUnit] = useState("");
  const [size, setSize] = useState("");
  const [beds, setBeds] = useState("");
  const [confThreshold, setConfThreshold] = useState(40);
  const [result, setResult] = useState<MatchListingResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  if (authLoading) return null;
  if (!authenticated) {
    router.replace("/");
    return null;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!building.trim()) {
      setError("Building is required");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await matchListing({
        building_name: building.trim(),
        unit_number: unit.trim() || null,
        size_sqft: size ? Number(size) : null,
        bedrooms: beds || null,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Match failed");
    } finally {
      setLoading(false);
    }
  };

  const matches = (result?.matches ?? []).filter(
    (m) => m.confidence * 100 >= confThreshold,
  );

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-mobile-nav max-w-4xl mx-auto w-full">
      <div className="flex items-center gap-2">
        <Crosshair size={20} className="text-accent" />
        <h1 className="text-lg font-semibold text-foreground">Listing Matcher</h1>
      </div>
      <p className="text-xs text-muted">
        Match a Bayut / PropertyFinder listing to an owner in your lead database.
        Provide building (required) plus unit / size / bedrooms to improve confidence.
      </p>

      <form
        onSubmit={handleSubmit}
        className="rounded-xl border border-border bg-card p-4 flex flex-col gap-3"
      >
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <Field label="Building (required)" value={building} onChange={setBuilding} />
          <Field label="Unit number" value={unit} onChange={setUnit} />
          <Field label="Size (sqft)" value={size} onChange={setSize} type="number" />
          <FieldSelect
            label="Bedrooms"
            value={beds}
            onChange={setBeds}
            options={["", "Studio", "1", "2", "3", "4", "5", "6"]}
          />
        </div>

        <div>
          <label className="text-xs text-muted">
            Min confidence: <span className="text-foreground">{confThreshold}%</span>
          </label>
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={confThreshold}
            onChange={(e) => setConfThreshold(Number(e.target.value))}
            className="mt-1 w-full accent-accent"
          />
        </div>

        {error && (
          <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading || !building.trim()}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-background disabled:opacity-50"
        >
          {loading ? "Matching..." : "Find owner"}
        </button>
      </form>

      {result && (
        <>
          <div className="text-xs text-muted">
            {matches.length} match{matches.length === 1 ? "" : "es"} (showing
            {" "}≥ {confThreshold}% confidence; total found: {result.matches.length})
          </div>
          {matches.length === 0 ? (
            <div className="rounded-xl border border-border bg-card p-6 text-center text-muted text-sm">
              No matches at that confidence. Try lowering the threshold or
              providing more listing details (size / unit number).
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {matches.map((m, idx) => (
                <MatchCard key={`${m.building}-${m.unit}-${idx}`} match={m} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function MatchCard({ match }: { match: MatchedOwner }) {
  const conf = Math.round(match.confidence * 100);
  const tone =
    conf >= 90
      ? "border-success/30 bg-success/5"
      : conf >= 60
        ? "border-accent/30 bg-card"
        : "border-warning/30 bg-warning/5";

  return (
    <div className={`rounded-xl border p-4 ${tone}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Building2 size={14} className="text-accent" />
            <span className="text-sm font-medium text-foreground">
              {match.owner_name || "(unknown owner)"}
            </span>
            <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[11px] text-accent">
              {match.match_type}
            </span>
          </div>
          <div className="text-xs text-muted">
            {match.building}{match.unit ? ` / ${match.unit}` : ""}
            {match.beds && ` / ${match.beds} BR`}
            {match.size_sqft && ` / ${Math.round(match.size_sqft)} sqft`}
          </div>
          <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs">
            {match.phone && (
              <a
                href={`tel:${match.phone}`}
                className="flex items-center gap-1 text-accent hover:underline"
              >
                <Phone size={10} />
                {match.phone}
              </a>
            )}
            {match.email && (
              <span className="flex items-center gap-1 text-muted">
                <Mail size={10} />
                {match.email}
              </span>
            )}
          </div>
          {match.transaction_value && (
            <p className="mt-1 text-[11px] text-muted">
              Last sale: {Math.round(match.transaction_value).toLocaleString()} AED
              {match.transaction_date && ` (${match.transaction_date.slice(0, 10)})`}
            </p>
          )}
        </div>
        <div
          className={`rounded-full px-2.5 py-1 text-xs font-bold ${
            conf >= 90 ? "bg-success/15 text-success"
              : conf >= 60 ? "bg-accent/15 text-accent"
                : "bg-warning/15 text-warning"
          }`}
        >
          {conf}%
        </div>
      </div>
    </div>
  );
}

function Field({
  label, value, onChange, type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
}) {
  return (
    <div>
      <label className="text-xs text-muted">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
      />
    </div>
  );
}

function FieldSelect({
  label, value, onChange, options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: readonly string[];
}) {
  return (
    <div>
      <label className="text-xs text-muted">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
      >
        {options.map((o) => (
          <option key={o} value={o}>{o || "--"}</option>
        ))}
      </select>
    </div>
  );
}
