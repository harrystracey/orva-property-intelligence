"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  CheckCircle2,
  XCircle,
  AlertCircle,
  RefreshCw,
} from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import { getHealthCheck, FileInfo, HealthCheckResponse } from "@/lib/api";

function fmtMB(mb: number | null): string {
  return mb != null ? `${mb.toFixed(2)} MB` : "--";
}

function fmtTime(iso: string | null): string {
  if (!iso) return "--";
  try {
    return new Date(iso).toLocaleString("en-GB", {
      day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

export default function HealthPage() {
  const { authenticated, loading: authLoading } = useAuth();
  const router = useRouter();

  const [data, setData] = useState<HealthCheckResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await getHealthCheck());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authenticated) refresh();
  }, [authenticated, refresh]);

  if (authLoading) return null;
  if (!authenticated) {
    router.replace("/");
    return null;
  }

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-mobile-nav max-w-5xl mx-auto w-full">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity size={20} className="text-accent" />
          <h1 className="text-lg font-semibold text-foreground">System Health</h1>
          {data && (
            <Badge tone={data.overall.status === "ok" ? "ok" : "warn"}>
              {data.overall.status.toUpperCase()}
            </Badge>
          )}
        </div>
        <button
          onClick={refresh}
          disabled={loading}
          className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm text-muted hover:bg-card-hover hover:text-foreground disabled:opacity-50"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {data?.overall.checked_at && (
        <p className="text-xs text-muted">Checked at {fmtTime(data.overall.checked_at)}</p>
      )}

      {error && (
        <div className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-2 text-sm text-danger">
          {error}
        </div>
      )}

      {loading && !data ? (
        <div className="rounded-xl border border-border bg-card p-8 text-center text-muted">
          Loading...
        </div>
      ) : !data ? null : (
        <>
          <Section title="Environment">
            <Row label="Anthropic API key">
              <BoolBadge ok={data.environment.anthropic_api_key_set} />
              {data.environment.anthropic_api_key_preview && (
                <span className="ml-2 text-xs text-muted font-mono">
                  {data.environment.anthropic_api_key_preview}
                </span>
              )}
            </Row>
            <Row label="JWT secret">
              <BoolBadge ok={data.environment.jwt_secret_set && data.environment.jwt_secret_strong} />
              {!data.environment.jwt_secret_strong && data.environment.jwt_secret_set && (
                <span className="ml-2 text-xs text-warning">weak (&lt; 32 chars)</span>
              )}
            </Row>
            <Row label="Claude model">
              <span className="text-sm text-foreground font-mono">{data.environment.claude_model}</span>
            </Row>
            <Row label="Log level">
              <span className="text-sm text-foreground font-mono">{data.environment.log_level}</span>
            </Row>
          </Section>

          <Section title="SQLite database">
            <Row label="Initialized">
              <BoolBadge ok={data.sqlite.initialized} />
              <span className="ml-2 text-xs text-muted">{data.sqlite.path}</span>
            </Row>
            {data.sqlite.initialized && (
              <Row label="Size">{fmtMB(data.sqlite.size_mb)}</Row>
            )}
            {data.sqlite.initialized && Object.keys(data.sqlite.table_counts).length > 0 && (
              <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 sm:grid-cols-3">
                {Object.entries(data.sqlite.table_counts).map(([t, n]) => (
                  <div key={t} className="flex items-center justify-between text-xs">
                    <span className="text-muted truncate">{t}</span>
                    <span className="text-foreground font-medium">{n.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            )}
          </Section>

          <Section title="Lead database">
            <FileRow label="leads_master.xlsx" info={data.lead_database.xlsx} />
            <FileRow
              label="leads_master.csv"
              info={data.lead_database.csv}
              extra={
                data.lead_database.csv_rows != null
                  ? `${data.lead_database.csv_rows.toLocaleString()} rows`
                  : undefined
              }
            />
          </Section>

          <Section title="Reference / DLD sales">
            <FileRow
              label="reference_master.csv"
              info={data.reference_data.reference_master}
              extra={
                data.reference_data.reference_master_rows != null
                  ? `${data.reference_data.reference_master_rows.toLocaleString()} rows`
                  : undefined
              }
            />
            <FileRow
              label="reference_master_with_units.csv"
              info={data.reference_data.reference_master_with_units}
            />
          </Section>

          <Section title="Reidin DLD (historical)">
            <FileRow label="reidin_master.parquet" info={data.reidin.parquet} />
            <FileRow label="reidin_master.csv" info={data.reidin.csv} />
          </Section>

          <Section title="Public scrapers">
            <FileRow
              label="bayut_palm_listings.csv"
              info={data.public_scrapers.bayut_listings}
              extra={
                data.public_scrapers.bayut_rows != null
                  ? `${data.public_scrapers.bayut_rows.toLocaleString()} rows`
                  : undefined
              }
            />
            <FileRow
              label="propertyfinder_scraped_leads.csv"
              info={data.public_scrapers.pf_listings}
              extra={
                data.public_scrapers.pf_rows != null
                  ? `${data.public_scrapers.pf_rows.toLocaleString()} rows`
                  : undefined
              }
            />
          </Section>

          <Section title="Python modules">
            <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
              {Object.entries(data.modules).map(([m, ok]) => (
                <Row key={m} label={m}>
                  <BoolBadge ok={ok} />
                </Row>
              ))}
            </div>
          </Section>

          <Section title="Building intelligence">
            <Row label="Loaded">
              <BoolBadge ok={data.building_intelligence.loaded} />
            </Row>
            {data.building_intelligence.loaded ? (
              <>
                <Row label="Shoreline towers">
                  {data.building_intelligence.shoreline_towers}
                </Row>
                <Row label="Building aliases">
                  {data.building_intelligence.building_aliases}
                </Row>
              </>
            ) : (
              data.building_intelligence.error && (
                <p className="text-xs text-danger">{data.building_intelligence.error}</p>
              )
            )}
          </Section>
        </>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <h2 className="mb-3 text-sm font-semibold text-foreground">{title}</h2>
      <div className="flex flex-col gap-1.5">{children}</div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <span className="text-muted truncate">{label}</span>
      <div className="flex items-center text-foreground">{children}</div>
    </div>
  );
}

function BoolBadge({ ok }: { ok: boolean }) {
  return ok ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-success/15 px-2 py-0.5 text-xs text-success">
      <CheckCircle2 size={10} />
      OK
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-full bg-danger/15 px-2 py-0.5 text-xs text-danger">
      <XCircle size={10} />
      MISSING
    </span>
  );
}

function FileRow({ label, info, extra }: { label: string; info: FileInfo; extra?: string }) {
  return (
    <div className="flex items-start justify-between gap-3 text-sm">
      <span className="text-muted truncate font-mono text-xs">{label}</span>
      <div className="flex flex-col items-end gap-0.5">
        <BoolBadge ok={info.present} />
        {info.present && (
          <span className="text-[11px] text-muted">
            {fmtMB(info.size_mb)}
            {extra && <span className="ml-1.5">| {extra}</span>}
          </span>
        )}
        {info.present && info.modified && (
          <span className="text-[10px] text-muted">{fmtTime(info.modified)}</span>
        )}
      </div>
    </div>
  );
}

function Badge({ tone, children }: { tone: "ok" | "warn" | "err"; children: React.ReactNode }) {
  const cls =
    tone === "ok"
      ? "bg-success/15 text-success"
      : tone === "warn"
        ? "bg-warning/15 text-warning"
        : "bg-danger/15 text-danger";
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-bold ${cls}`}>
      {tone === "ok" ? <CheckCircle2 size={10} /> : <AlertCircle size={10} />}
      {children}
    </span>
  );
}
