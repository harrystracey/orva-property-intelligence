"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useAuth } from "@/lib/auth-context";
import { LoginForm } from "@/components/login-form";
import {
  getWAStatus,
  previewCampaign,
  startCampaign,
  stopCampaign,
  getCampaignStatus,
  getWAStats,
  getWAMessages,
  exportWAMessages,
  markRestriction,
  startLink,
  getLinkStatus,
  WAStatus,
  QueueContact,
  CampaignProgress,
  SendStats,
  MessageLogEntry,
} from "@/lib/api";
import {
  MessageSquare,
  Wifi,
  WifiOff,
  Send,
  Square,
  Eye,
  BarChart3,
  List,
  Activity,
  Download,
  CheckCheck,
  XCircle,
  AlertTriangle,
  RotateCw,
  Search,
  Phone,
  Link2,
  CircleDot,
} from "lucide-react";

// ─── Helpers ────────────────────────────────────────────────────────────────

function fmtSeconds(s: number): string {
  const m = Math.floor(s / 60);
  const h = Math.floor(m / 60);
  if (h > 0) return `${h}h ${m % 60}m`;
  return `${m}m ${s % 60}s`;
}

const CAMPAIGN_TYPES = [
  { value: "landlord_lease_expiry", label: "Landlord Lease Expiry" },
  { value: "cold_owner", label: "Cold Owner Outreach" },
  { value: "recent_sale", label: "Recent Sale Follow-up" },
  { value: "portfolio_owner", label: "Portfolio Owner" },
  { value: "active_seller", label: "Actively Selling (PF)" },
  { value: "active_renter", label: "Actively Renting (PF)" },
  { value: "propspace_leads", label: "PropSpace Leads" },
];

// ─── Connection Status ──────────────────────────────────────────────────────

function ConnectionStatus() {
  const [account, setAccount] = useState("1");
  const [status, setStatus] = useState<WAStatus | null>(null);
  const [linkPhone, setLinkPhone] = useState("");
  const [linkCode, setLinkCode] = useState<string | null>(null);
  const [linking, setLinking] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const s = await getWAStatus(account);
      setStatus(s);
    } catch { /* ignore */ }
  }, [account]);

  useEffect(() => {
    refresh();
    const iv = setInterval(refresh, 5000);
    return () => clearInterval(iv);
  }, [refresh]);

  const handleLink = async () => {
    if (!linkPhone.trim()) return;
    setLinking(true);
    setLinkCode(null);
    try {
      await startLink(account, linkPhone.trim());
      // Poll for code
      for (let i = 0; i < 30; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        const ls = await getLinkStatus(account);
        if (ls.link_code) {
          setLinkCode(ls.link_code);
          break;
        }
        if (ls.error) break;
        if (!ls.pending) break;
      }
    } catch { /* ignore */ }
    setLinking(false);
  };

  const connected = status?.connected ?? false;

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3">
          {connected ? (
            <Wifi size={18} className="text-accent" />
          ) : (
            <WifiOff size={18} className="text-danger" />
          )}
          <span className="text-sm font-medium text-foreground">
            {connected
              ? `Connected -- ${status?.phone || "Unknown"}`
              : "Disconnected"}
          </span>
          <button onClick={refresh} className="rounded p-1 text-muted hover:text-foreground">
            <RotateCw size={14} />
          </button>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-xs text-muted">
            <input
              type="radio"
              name="wa-account"
              checked={account === "1"}
              onChange={() => setAccount("1")}
              className="accent-accent"
            />
            Account 1
          </label>
          <label className="flex items-center gap-1.5 text-xs text-muted">
            <input
              type="radio"
              name="wa-account"
              checked={account === "2"}
              onChange={() => setAccount("2")}
              className="accent-accent"
            />
            Account 2
          </label>
        </div>
      </div>

      {/* QR / Link code when disconnected */}
      {!connected && (
        <div className="mt-3 rounded-lg border border-border bg-background p-3">
          {status?.qr_b64 && (
            <div className="mb-3 flex justify-center">
              <img
                src={`data:image/png;base64,${status.qr_b64}`}
                alt="WhatsApp QR"
                className="h-40 w-40 sm:h-48 sm:w-48 max-w-full rounded-lg"
              />
            </div>
          )}
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              type="text"
              placeholder="Phone (e.g. 971501234567)"
              value={linkPhone}
              onChange={(e) => setLinkPhone(e.target.value)}
              className="flex-1 rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground placeholder:text-muted"
            />
            <button
              onClick={handleLink}
              disabled={linking}
              className="flex items-center justify-center gap-1.5 rounded-lg bg-accent/15 px-4 py-2 text-sm font-medium text-accent hover:bg-accent/25 disabled:opacity-50"
            >
              <Link2 size={14} />
              {linking ? "Linking..." : "Get Link Code"}
            </button>
          </div>
          {linkCode && (
            <div className="mt-3 rounded-lg border border-accent/30 bg-accent/10 p-4 text-center">
              <p className="mb-1 text-xs text-muted">Enter this code in WhatsApp &rarr; Linked Devices &rarr; Link with phone number</p>
              <p className="font-mono text-2xl font-bold tracking-[0.3em] text-accent">{linkCode}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Campaign Tab ───────────────────────────────────────────────────────────

function CampaignTab() {
  const [campaignType, setCampaignType] = useState("cold_owner");
  const [building, setBuilding] = useState("");
  const [bedrooms, setBedrooms] = useState("");
  const [area, setArea] = useState("");
  const [daysAhead, setDaysAhead] = useState(90);
  const [portfolioOnly, setPortfolioOnly] = useState(false);
  const [minUnits, setMinUnits] = useState(3);
  const [limit, setLimit] = useState("");
  const [dryRun, setDryRun] = useState(false);
  const [overrideLimit, setOverrideLimit] = useState(false);
  const [noLimits, setNoLimits] = useState(false);
  const [customMsg, setCustomMsg] = useState("");
  const [useCustomMsg, setUseCustomMsg] = useState(false);
  const [account, setAccount] = useState("1");

  const [queue, setQueue] = useState<QueueContact[]>([]);
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [previewing, setPreviewing] = useState(false);
  const [showQueue, setShowQueue] = useState(false);

  const [progress, setProgress] = useState<CampaignProgress | null>(null);
  const [running, setRunning] = useState(false);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  // Poll campaign status when running
  const pollProgress = useCallback(async () => {
    try {
      const p = await getCampaignStatus();
      setProgress(p);
      if (["done", "stopped", "error"].includes(p.status)) {
        setRunning(false);
        if (pollRef.current) clearInterval(pollRef.current);
      }
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    // Check if a campaign is already running on mount
    getCampaignStatus().then((p) => {
      if (p.status === "running" || p.status === "building" || p.status === "paused") {
        setProgress(p);
        setRunning(true);
        pollRef.current = setInterval(pollProgress, 2000);
      }
    }).catch(() => {});
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [pollProgress]);

  const buildParams = () => ({
    campaign_type: campaignType,
    building: building || undefined,
    bedrooms: bedrooms || undefined,
    area: area || undefined,
    days_ahead: daysAhead,
    portfolio_only: portfolioOnly,
    min_units: minUnits,
    limit: limit ? parseInt(limit) : undefined,
    account,
    custom_message: useCustomMsg ? customMsg : undefined,
  });

  const handlePreview = async () => {
    setPreviewing(true);
    try {
      const res = await previewCampaign(buildParams());
      setQueue(res.queue);
      setExcluded(new Set());
      setShowQueue(true);
    } catch (e) {
      alert(`Preview failed: ${e}`);
    }
    setPreviewing(false);
  };

  const handleStart = async () => {
    try {
      const excludedPhones = Array.from(excluded);
      await startCampaign({
        ...buildParams(),
        dry_run: dryRun,
        override_limit: overrideLimit,
        no_limits: noLimits,
        excluded_phones: excludedPhones,
      });
      setRunning(true);
      setShowQueue(false);
      pollRef.current = setInterval(pollProgress, 2000);
    } catch (e) {
      alert(`Start failed: ${e}`);
    }
  };

  const handleStop = async () => {
    try {
      await stopCampaign();
    } catch { /* ignore */ }
  };

  const toggleExclude = (phone: string) => {
    setExcluded((prev) => {
      const next = new Set(prev);
      if (next.has(phone)) next.delete(phone);
      else next.add(phone);
      return next;
    });
  };

  const selectAll = () => setExcluded(new Set());
  const deselectAll = () => setExcluded(new Set(queue.map((q) => q.phone)));

  const includedCount = queue.length - excluded.size;
  const showDays = ["landlord_lease_expiry", "recent_sale"].includes(campaignType);
  const showPortfolio = campaignType === "cold_owner";
  const showMinUnits = campaignType === "portfolio_owner";

  return (
    <div className="flex flex-col gap-4">
      {/* Campaign type */}
      <div className="rounded-xl border border-border bg-card p-4">
        <h3 className="mb-3 text-sm font-medium text-foreground">Campaign Type</h3>
        <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
          {CAMPAIGN_TYPES.map((t) => (
            <label
              key={t.value}
              className={`flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2.5 text-sm transition-colors ${
                campaignType === t.value
                  ? "bg-accent/15 text-accent font-medium"
                  : "text-muted hover:bg-card-hover hover:text-foreground"
              }`}
            >
              <input
                type="radio"
                name="campaign-type"
                value={t.value}
                checked={campaignType === t.value}
                onChange={(e) => setCampaignType(e.target.value)}
                className="accent-accent"
              />
              {t.label}
            </label>
          ))}
        </div>
      </div>

      {/* Filters */}
      <div className="rounded-xl border border-border bg-card p-4">
        <h3 className="mb-3 text-sm font-medium text-foreground">Filters</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div>
            <label className="mb-1 block text-xs text-muted">Building</label>
            <input
              type="text"
              value={building}
              onChange={(e) => setBuilding(e.target.value)}
              placeholder="e.g. Shoreline 12"
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">Bedrooms</label>
            <select
              value={bedrooms}
              onChange={(e) => setBedrooms(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
            >
              <option value="">All</option>
              <option value="0">Studio</option>
              <option value="1">1 BR</option>
              <option value="2">2 BR</option>
              <option value="3">3 BR</option>
              <option value="4">4 BR</option>
              <option value="5">5+ BR</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">Area</label>
            <select
              value={area}
              onChange={(e) => setArea(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
            >
              <option value="">All</option>
              <option value="Palm Jumeirah">Palm Jumeirah</option>
              <option value="Dubai Marina">Dubai Marina</option>
              <option value="JBR">JBR</option>
            </select>
          </div>
        </div>

        {/* Conditional options */}
        {showDays && (
          <div className="mt-3">
            <label className="mb-1 block text-xs text-muted">
              {campaignType === "landlord_lease_expiry" ? "Lease expiry window" : "Sales in last"} (days): {daysAhead}
            </label>
            <input
              type="range"
              min={30}
              max={365}
              value={daysAhead}
              onChange={(e) => setDaysAhead(parseInt(e.target.value))}
              className="w-full accent-accent"
            />
          </div>
        )}
        {showPortfolio && (
          <label className="mt-3 flex items-center gap-2 text-sm text-muted">
            <input type="checkbox" checked={portfolioOnly} onChange={(e) => setPortfolioOnly(e.target.checked)} className="accent-accent" />
            Portfolio investors only (2+ units)
          </label>
        )}
        {showMinUnits && (
          <div className="mt-3">
            <label className="mb-1 block text-xs text-muted">Min units per owner: {minUnits}</label>
            <input type="range" min={2} max={10} value={minUnits} onChange={(e) => setMinUnits(parseInt(e.target.value))} className="w-full accent-accent" />
          </div>
        )}
      </div>

      {/* Options */}
      <div className="rounded-xl border border-border bg-card p-4">
        <h3 className="mb-3 text-sm font-medium text-foreground">Options</h3>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs text-muted">Limit (optional)</label>
            <input
              type="number"
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
              placeholder="No limit"
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted">Account</label>
            <select value={account} onChange={(e) => setAccount(e.target.value)} className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground">
              <option value="1">Account 1</option>
              <option value="2">Account 2</option>
            </select>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-4">
          <label className="flex items-center gap-1.5 text-sm text-muted">
            <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} className="accent-accent" />
            Dry run
          </label>
          <label className="flex items-center gap-1.5 text-sm text-muted">
            <input type="checkbox" checked={overrideLimit} onChange={(e) => setOverrideLimit(e.target.checked)} className="accent-accent" />
            Override ramp-up
          </label>
          <label className="flex items-center gap-1.5 text-sm text-muted">
            <input type="checkbox" checked={noLimits} onChange={(e) => setNoLimits(e.target.checked)} className="accent-accent" />
            No limits
          </label>
        </div>

        {/* Custom message */}
        <label className="mt-3 flex items-center gap-1.5 text-sm text-muted">
          <input type="checkbox" checked={useCustomMsg} onChange={(e) => setUseCustomMsg(e.target.checked)} className="accent-accent" />
          Custom message (ignore templates)
        </label>
        {useCustomMsg && (
          <textarea
            value={customMsg}
            onChange={(e) => setCustomMsg(e.target.value)}
            rows={4}
            placeholder="Use {name}, {building}, {unit} for variables"
            className="mt-2 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted"
          />
        )}
      </div>

      {/* Action buttons */}
      <div className="flex flex-col gap-2 sm:flex-row">
        <button
          onClick={handlePreview}
          disabled={previewing || running}
          className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-border bg-card px-4 py-2.5 text-sm font-medium text-foreground hover:bg-card-hover disabled:opacity-50"
        >
          <Eye size={16} />
          {previewing ? "Building queue..." : "Preview Queue"}
        </button>
        {running ? (
          <button
            onClick={handleStop}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-danger/15 px-4 py-2.5 text-sm font-medium text-danger hover:bg-danger/25"
          >
            <Square size={16} />
            Stop Campaign
          </button>
        ) : (
          <button
            onClick={handleStart}
            disabled={showQueue && includedCount === 0}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-50"
          >
            <Send size={16} />
            Start Campaign
          </button>
        )}
      </div>

      {/* Queue preview */}
      {showQueue && queue.length > 0 && (
        <div className="rounded-xl border border-border bg-card p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-medium text-foreground">Queue -- {queue.length} contacts</h3>
            <div className="flex gap-2">
              <button onClick={selectAll} className="text-sm py-1 px-2 text-accent hover:underline">Select all</button>
              <button onClick={deselectAll} className="text-sm py-1 px-2 text-muted hover:underline">Deselect all</button>
            </div>
          </div>
          <div className="max-h-64 space-y-1 overflow-y-auto">
            {queue.map((c) => (
              <label
                key={c.phone}
                className="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm hover:bg-card-hover"
              >
                <input
                  type="checkbox"
                  checked={!excluded.has(c.phone)}
                  onChange={() => toggleExclude(c.phone)}
                  className="accent-accent"
                />
                <span className="text-foreground">{c.owner_name || "Unknown"}</span>
                <span className="text-muted">-- {c.building} {c.unit ? `Unit ${c.unit}` : ""}</span>
                <span className="ml-auto font-mono text-xs text-muted">{c.phone}</span>
              </label>
            ))}
          </div>
          <div className="mt-3 flex items-center justify-between border-t border-border pt-3">
            <span className="text-sm text-muted">
              <span className="font-medium text-accent">{includedCount}</span> will be sent | {excluded.size} excluded
            </span>
            <button
              onClick={handleStart}
              disabled={includedCount === 0}
              className="flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-50"
            >
              <Send size={14} />
              Confirm & Send ({includedCount})
            </button>
          </div>
        </div>
      )}

      {showQueue && queue.length === 0 && !previewing && (
        <div className="rounded-lg border border-border bg-card p-6 text-center text-sm text-muted">
          Queue is empty -- no contacts match your filters after dedup.
        </div>
      )}

      {/* Campaign progress */}
      {progress && progress.status !== "idle" && (
        <div className="rounded-xl border border-border bg-card p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-medium text-foreground">Campaign Progress</h3>
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
              progress.status === "running" || progress.status === "paused" ? "bg-accent/15 text-accent" :
              progress.status === "done" ? "bg-green-500/15 text-green-400" :
              progress.status === "error" ? "bg-danger/15 text-danger" :
              progress.status === "stopped" ? "bg-yellow-500/15 text-yellow-400" :
              "bg-muted/15 text-muted"
            }`}>
              {progress.status === "paused" ? "Batch pause" : progress.status}
            </span>
          </div>

          {/* Progress bar */}
          {progress.total > 0 && (
            <div className="mb-3 h-2 overflow-hidden rounded-full bg-border">
              <div
                className="h-full rounded-full bg-accent transition-all"
                style={{ width: `${Math.min(100, ((progress.sent + progress.failed + progress.not_on_wa + progress.skipped) / progress.total) * 100)}%` }}
              />
            </div>
          )}

          {/* Counter cards */}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
            <div className="rounded-lg bg-background p-2 text-center">
              <div className="text-lg font-bold text-accent">{progress.sent}</div>
              <div className="text-xs text-muted">Sent</div>
            </div>
            <div className="rounded-lg bg-background p-2 text-center">
              <div className="text-lg font-bold text-danger">{progress.failed}</div>
              <div className="text-xs text-muted">Failed</div>
            </div>
            <div className="rounded-lg bg-background p-2 text-center">
              <div className="text-lg font-bold text-yellow-400">{progress.not_on_wa}</div>
              <div className="text-xs text-muted">Not on WA</div>
            </div>
            <div className="rounded-lg bg-background p-2 text-center">
              <div className="text-lg font-bold text-muted">{progress.skipped}</div>
              <div className="text-xs text-muted">Skipped</div>
            </div>
            <div className="rounded-lg bg-background p-2 text-center">
              <div className="text-lg font-bold text-foreground">{progress.total}</div>
              <div className="text-xs text-muted">Total</div>
            </div>
          </div>

          {/* Current contact + meta */}
          <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted">
            {progress.current_contact && (
              <span>Current: {progress.current_contact.owner_name} -- {progress.current_contact.building}</span>
            )}
            <span>Cap: {progress.messages_today}/{progress.daily_cap}</span>
            <span>Elapsed: {fmtSeconds(progress.elapsed_seconds)}</span>
          </div>

          {progress.error && (
            <div className="mt-2 rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger">{progress.error}</div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Statistics Tab ─────────────────────────────────────────────────────────

function StatsTab() {
  const [stats, setStats] = useState<SendStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getWAStats().then(setStats).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="py-8 text-center text-sm text-muted">Loading stats...</div>;
  if (!stats) return <div className="py-8 text-center text-sm text-muted">Could not load stats</div>;

  const rows = [
    { label: "Today", data: stats.today },
    { label: "Last 7 Days", data: stats.week },
    { label: "All Time", data: stats.all_time },
  ];

  return (
    <div className="flex flex-col gap-4">
      {rows.map((row) => (
        <div key={row.label} className="rounded-xl border border-border bg-card p-4">
          <h3 className="mb-3 text-sm font-medium text-foreground">{row.label}</h3>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
            <div className="rounded-lg bg-background p-3 text-center">
              <div className="text-xl font-bold text-accent">{row.data.sent}</div>
              <div className="text-xs text-muted">Sent</div>
            </div>
            <div className="rounded-lg bg-background p-3 text-center">
              <div className="text-xl font-bold text-danger">{row.data.failed}</div>
              <div className="text-xs text-muted">Failed</div>
            </div>
            <div className="rounded-lg bg-background p-3 text-center">
              <div className="text-xl font-bold text-yellow-400">{row.data.not_on_whatsapp}</div>
              <div className="text-xs text-muted">Not on WA</div>
            </div>
            <div className="rounded-lg bg-background p-3 text-center">
              <div className="text-xl font-bold text-blue-400">{row.data.replies}</div>
              <div className="text-xs text-muted">Replies</div>
            </div>
            <div className="rounded-lg bg-background p-3 text-center">
              <div className="text-xl font-bold text-foreground">{row.data.total}</div>
              <div className="text-xs text-muted">Total</div>
            </div>
          </div>
        </div>
      ))}

      {/* Restriction button */}
      <div className="rounded-xl border border-border bg-card p-4">
        <h3 className="mb-2 text-sm font-medium text-foreground">Rate Limiting</h3>
        <p className="mb-3 text-xs text-muted">If WhatsApp restricts your account, record it here. This activates a 7-day cooldown with reduced daily caps and doubled delays.</p>
        <button
          onClick={() => markRestriction().then(() => alert("Restriction recorded"))}
          className="flex items-center gap-1.5 rounded-lg border border-danger/30 px-3 py-2 text-sm text-danger hover:bg-danger/10"
        >
          <AlertTriangle size={14} />
          Record Restriction
        </button>
      </div>
    </div>
  );
}

// ─── Message Log Tab ────────────────────────────────────────────────────────

function MessageLogTab() {
  const [messages, setMessages] = useState<MessageLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [limit, setLimit] = useState(100);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getWAMessages(limit, search || undefined);
      setMessages(res.messages);
      setTotal(res.total);
    } catch { /* ignore */ }
    setLoading(false);
  }, [limit, search]);

  useEffect(() => { refresh(); }, [refresh]);

  const handleExport = async () => {
    try {
      const csv = await exportWAMessages();
      const blob = new Blob([csv], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `whatsapp_log_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch { /* ignore */ }
  };

  const statusColor = (s: string | null) => {
    if (s === "sent") return "text-accent";
    if (s === "failed") return "text-danger";
    if (s === "not_on_whatsapp") return "text-yellow-400";
    return "text-muted";
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Controls */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name, building, phone..."
            className="w-full rounded-lg border border-border bg-card py-2 pl-9 pr-3 text-sm text-foreground placeholder:text-muted"
          />
        </div>
        <select
          value={limit}
          onChange={(e) => setLimit(parseInt(e.target.value))}
          className="rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground"
        >
          <option value={50}>Last 50</option>
          <option value={100}>Last 100</option>
          <option value={250}>Last 250</option>
          <option value={500}>Last 500</option>
        </select>
        <button onClick={handleExport} className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-2 text-sm text-muted hover:text-foreground">
          <Download size={14} />
          Export
        </button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-card">
              <th className="px-3 py-2 text-left text-xs font-medium text-muted">Time</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-muted">Name</th>
              <th className="hidden sm:table-cell px-3 py-2 text-left text-xs font-medium text-muted">Building</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-muted">Phone</th>
              <th className="hidden sm:table-cell px-3 py-2 text-left text-xs font-medium text-muted">Template</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-muted">Status</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="px-3 py-6 text-center text-muted">Loading...</td></tr>
            ) : messages.length === 0 ? (
              <tr><td colSpan={6} className="px-3 py-6 text-center text-muted">No messages found</td></tr>
            ) : (
              messages.map((m, i) => (
                <tr key={i} className="border-b border-border/50 hover:bg-card-hover">
                  <td className="whitespace-nowrap px-3 py-2 text-xs text-muted">
                    {m.timestamp ? new Date(m.timestamp).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "--"}
                  </td>
                  <td className="px-3 py-2 text-foreground">{m.owner_name || "--"}</td>
                  <td className="hidden sm:table-cell px-3 py-2 text-muted">{m.building || "--"}</td>
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-muted">{m.phone || "--"}</td>
                  <td className="hidden sm:table-cell px-3 py-2 text-xs text-muted">{m.template_type || "--"}</td>
                  <td className={`px-3 py-2 text-xs font-medium ${statusColor(m.status)}`}>
                    {m.status === "sent" && <CheckCheck size={13} className="inline mr-1" />}
                    {m.status === "failed" && <XCircle size={13} className="inline mr-1" />}
                    {m.status || "--"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div className="text-xs text-muted">{total} messages shown</div>
    </div>
  );
}

// ─── Activity Tab ───────────────────────────────────────────────────────────

function ActivityTab() {
  const [telemetry, setTelemetry] = useState<{ log?: string[]; messages_today?: number; last_action?: string; last_error?: string | null } | null>(null);
  const [account, setAccount] = useState("1");

  const refresh = useCallback(async () => {
    try {
      const data = await (await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/whatsapp/telemetry/${account}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem("orva_token")}` },
      })).json();
      setTelemetry(data);
    } catch { /* ignore */ }
  }, [account]);

  useEffect(() => {
    refresh();
    const iv = setInterval(refresh, 3000);
    return () => clearInterval(iv);
  }, [refresh]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <select value={account} onChange={(e) => setAccount(e.target.value)} className="rounded-lg border border-border bg-card px-3 py-1.5 text-sm text-foreground">
          <option value="1">Account 1</option>
          <option value="2">Account 2</option>
        </select>
        <button onClick={refresh} className="rounded p-1 text-muted hover:text-foreground"><RotateCw size={14} /></button>
        {telemetry?.messages_today !== undefined && (
          <span className="text-sm text-muted">Messages today: <span className="font-medium text-accent">{telemetry.messages_today}</span></span>
        )}
      </div>

      {telemetry?.last_action && (
        <div className="rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground">
          <span className="text-xs text-muted">Last action: </span>{telemetry.last_action}
        </div>
      )}

      {telemetry?.last_error && (
        <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
          <span className="text-xs">Error: </span>{telemetry.last_error}
        </div>
      )}

      <div className="rounded-xl border border-border bg-card">
        <div className="border-b border-border px-3 py-2 text-xs font-medium text-muted">Live Log</div>
        <div className="max-h-96 overflow-y-auto p-3">
          {telemetry?.log && telemetry.log.length > 0 ? (
            telemetry.log.map((entry, i) => (
              <div key={i} className="border-b border-border/30 py-1.5 font-mono text-xs text-muted last:border-0">
                {entry}
              </div>
            ))
          ) : (
            <div className="py-4 text-center text-sm text-muted">No activity yet</div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Main Page ──────────────────────────────────────────────────────────────

type TabId = "campaign" | "stats" | "messages" | "activity";

const TABS: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: "campaign", label: "Campaign", icon: <Send size={15} /> },
  { id: "stats", label: "Statistics", icon: <BarChart3 size={15} /> },
  { id: "messages", label: "Messages", icon: <List size={15} /> },
  { id: "activity", label: "Activity", icon: <Activity size={15} /> },
];

export default function WhatsAppPage() {
  const { authenticated } = useAuth();
  const [activeTab, setActiveTab] = useState<TabId>("campaign");

  if (!authenticated) return <LoginForm />;

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-20 md:pb-4 max-w-5xl mx-auto w-full">
      {/* Header */}
      <div className="flex items-center gap-2">
        <MessageSquare size={20} className="text-accent" />
        <h1 className="text-lg font-semibold text-foreground">WhatsApp Campaigns</h1>
      </div>

      {/* Connection status */}
      <ConnectionStatus />

      {/* Tabs */}
      <div className="flex gap-1 rounded-xl border border-border bg-card p-1">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? "bg-accent/15 text-accent"
                : "text-muted hover:text-foreground"
            }`}
          >
            {tab.icon}
            <span className="hidden sm:inline">{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "campaign" && <CampaignTab />}
      {activeTab === "stats" && <StatsTab />}
      {activeTab === "messages" && <MessageLogTab />}
      {activeTab === "activity" && <ActivityTab />}
    </div>
  );
}
