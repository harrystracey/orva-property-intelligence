"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/lib/auth-context";
import { LoginForm } from "@/components/login-form";
import { getHealth, reloadData, HealthResponse } from "@/lib/api";
import { Wrench, RefreshCw, CheckCircle, XCircle, AlertCircle, Database } from "lucide-react";

function StatusDot({ status }: { status: string }) {
  if (status === "ok") return <CheckCircle size={16} className="text-success" />;
  if (status === "failed" || status === "not_loaded") return <XCircle size={16} className="text-danger" />;
  return <AlertCircle size={16} className="text-warning" />;
}

function formatNumber(n: number) {
  return n.toLocaleString();
}

export default function HealthPage() {
  const { authenticated } = useAuth();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloading, setReloading] = useState(false);
  const [reloadMsg, setReloadMsg] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await getHealth();
      setHealth(data);
    } catch {
      // fail silently
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authenticated) refresh();
  }, [authenticated, refresh]);

  if (!authenticated) return <LoginForm />;

  const handleReload = async () => {
    setReloading(true);
    setReloadMsg(null);
    try {
      const res = await reloadData();
      setReloadMsg(`Reloaded — ${formatNumber(res.total_leads)} leads`);
      await refresh();
    } catch (e: unknown) {
      setReloadMsg("Reload failed: " + (e instanceof Error ? e.message : String(e)));
    } finally {
      setReloading(false);
    }
  };

  const pfLabel: Record<string, string> = {
    ok: "Merged",
    empty: "Empty file",
    failed: "Parse error",
    not_found: "File not found",
    not_loaded: "Not loaded",
  };

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-20 md:pb-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Wrench size={20} className="text-accent" />
          <h1 className="text-lg font-semibold text-foreground">System Health</h1>
        </div>
        <button
          onClick={handleReload}
          disabled={reloading}
          className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-50"
        >
          <RefreshCw size={14} className={reloading ? "animate-spin" : ""} />
          {reloading ? "Reloading..." : "Reload Data"}
        </button>
      </div>

      {reloadMsg && (
        <div className={`rounded-lg border px-4 py-2 text-sm ${reloadMsg.startsWith("Reload failed") ? "border-danger/30 bg-danger/10 text-danger" : "border-success/30 bg-success/10 text-success"}`}>
          {reloadMsg}
        </div>
      )}

      {loading ? (
        <div className="text-muted text-sm">Loading...</div>
      ) : !health ? (
        <div className="rounded-lg border border-danger/30 bg-danger/10 p-4 text-danger text-sm">
          Could not reach the API. Is the backend running?
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {/* Overall status */}
          <div className="rounded-lg border border-border bg-card p-4">
            <div className="flex items-center gap-2 mb-3">
              <Database size={16} className="text-accent" />
              <span className="text-sm font-medium text-foreground">Data Status</span>
            </div>
            <div className="space-y-2">
              <Row label="API" value={health.status === "ok" ? "Running" : "Error"} ok={health.status === "ok"} />
              <Row label="Data loaded" value={health.data_loaded ? "Yes" : "No"} ok={health.data_loaded} />
            </div>
          </div>

          {/* Leads */}
          <div className="rounded-lg border border-border bg-card p-4">
            <div className="flex items-center gap-2 mb-3">
              <Database size={16} className="text-accent" />
              <span className="text-sm font-medium text-foreground">Lead Database</span>
            </div>
            <div className="space-y-2">
              <Row label="Total leads" value={formatNumber(health.total_leads)} ok />
              <Row label="Buildings" value={formatNumber(health.total_buildings)} ok />
              <Row label="Client index" value={formatNumber(health.client_id_index_size ?? 0)} ok />
            </div>
          </div>

          {/* Data sources */}
          <div className="rounded-lg border border-border bg-card p-4">
            <div className="flex items-center gap-2 mb-3">
              <Database size={16} className="text-accent" />
              <span className="text-sm font-medium text-foreground">Data Sources</span>
            </div>
            <div className="space-y-2">
              <Row
                label="PropertyFinder CSV"
                value={pfLabel[health.pf_merge_status ?? "not_loaded"] ?? health.pf_merge_status}
                ok={health.pf_merge_status === "ok"}
                warn={health.pf_merge_status === "empty" || health.pf_merge_status === "not_found"}
              />
              {health.rentals_loaded !== undefined && (
                <Row label="Rentals data" value={health.rentals_loaded ? `${formatNumber(health.total_rentals ?? 0)} records` : "Not loaded"} ok={health.rentals_loaded} />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, value, ok, warn }: { label: string; value: string; ok?: boolean; warn?: boolean }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted">{label}</span>
      <span className={`flex items-center gap-1 font-medium ${ok ? "text-success" : warn ? "text-warning" : "text-danger"}`}>
        {ok ? <CheckCircle size={12} /> : warn ? <AlertCircle size={12} /> : <XCircle size={12} />}
        {value}
      </span>
    </div>
  );
}
