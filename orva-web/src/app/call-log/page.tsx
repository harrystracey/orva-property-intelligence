"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

import { getAllCalls, CallRecord } from "@/lib/api";
import { Phone, ArrowRight, Search } from "lucide-react";
import { SkeletonCallEntry } from "@/components/skeleton";

function formatDateTime(iso: string | null | undefined) {
  if (!iso) return "--";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) +
      " " + d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}

function outcomeColor(outcome: string) {
  switch (outcome) {
    case "interested": return "text-success bg-success/10 border-success/30";
    case "callback": return "text-warning bg-warning/10 border-warning/30";
    case "not_interested": return "text-danger bg-danger/10 border-danger/30";
    default: return "text-muted bg-card border-border";
  }
}

function outcomeSymbol(outcome: string) {
  switch (outcome) {
    case "interested": return "[+]";
    case "callback": return "[>]";
    case "voicemail": return "[v]";
    case "no_answer": return "[x]";
    case "not_interested": return "[-]";
    default: return "[?]";
  }
}

export default function CallLogPage() {
  const { authenticated, loading: authLoading } = useAuth();
  const router = useRouter();
  const [calls, setCalls] = useState<CallRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [outcomeFilter, setOutcomeFilter] = useState<string>("all");

  const refresh = useCallback(async () => {
    try {
      const data = await getAllCalls();
      setCalls(data);
    } catch {
      // fail silently
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authenticated) refresh();
  }, [authenticated, refresh]);

  if (authLoading) return null;
  if (!authenticated) { router.replace("/"); return null; }

  const filtered = calls.filter((c) => {
    if (outcomeFilter !== "all" && c.outcome !== outcomeFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      return (
        (c.client_name || "").toLowerCase().includes(q) ||
        (c.building || "").toLowerCase().includes(q) ||
        (c.phone || "").toLowerCase().includes(q)
      );
    }
    return true;
  });

  // Stats
  const outcomes = ["interested", "callback", "voicemail", "no_answer", "not_interested"];
  const counts: Record<string, number> = {};
  for (const o of outcomes) counts[o] = calls.filter((c) => c.outcome === o).length;

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-mobile-nav max-w-4xl mx-auto w-full">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Phone size={20} className="text-accent" />
        <h1 className="text-lg font-semibold text-foreground">Call Log</h1>
        <span className="ml-auto text-sm text-muted">{calls.length} calls</span>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
        {outcomes.map((o) => (
          <button
            key={o}
            onClick={() => setOutcomeFilter(outcomeFilter === o ? "all" : o)}
            className={`rounded-lg border p-2 text-center transition-colors ${
              outcomeFilter === o
                ? outcomeColor(o)
                : "border-border bg-card hover:bg-card-hover"
            }`}
          >
            <p className="text-lg font-bold">{counts[o]}</p>
            <p className="text-[10px] capitalize">{o.replace("_", " ")}</p>
          </button>
        ))}
      </div>

      {/* Search */}
      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name, building, or phone..."
          className="w-full rounded-lg border border-border bg-card py-2 pl-9 pr-3 text-sm text-foreground placeholder:text-muted/50 focus:border-accent focus:outline-none"
        />
      </div>

      {/* Call list */}
      {loading ? (
        <div className="flex flex-col gap-1.5">
          {Array.from({ length: 3 }, (_, i) => <SkeletonCallEntry key={i} />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-border bg-card p-8 text-center">
          <p className="text-muted">No calls found</p>
        </div>
      ) : (
        <div className="flex flex-col gap-1.5">
          {filtered.map((c) => (
            <div
              key={c.id}
              className="flex items-center gap-3 rounded-xl border border-border bg-card p-3 transition-colors hover:bg-card-hover"
            >
              {/* Outcome badge */}
              <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border text-xs font-mono font-bold ${outcomeColor(c.outcome)}`}>
                {outcomeSymbol(c.outcome)}
              </div>

              {/* Info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-foreground truncate">
                    {c.client_name || "Unknown"}
                  </span>
                  {c.building && (
                    <span className="text-xs text-muted truncate hidden sm:inline">
                      {c.building}{c.unit ? ` | ${c.unit}` : ""}
                    </span>
                  )}
                </div>
                {c.notes && (
                  <p className="text-xs text-muted truncate mt-0.5">{c.notes}</p>
                )}
              </div>

              {/* Time + link */}
              <div className="flex items-center gap-2 shrink-0">
                <span className="text-[11px] text-muted hidden sm:inline">{formatDateTime(c.called_at)}</span>
                <button
                  onClick={() => router.push(`/client/${c.client_id}`)}
                  className="rounded p-2 min-w-[40px] min-h-[40px] flex items-center justify-center text-muted hover:text-accent"
                  title="View profile"
                >
                  <ArrowRight size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
