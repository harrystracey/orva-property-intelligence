"use client";

import React, { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { LoginForm } from "@/components/login-form";
import { FilterPanel } from "@/components/filter-panel";
import { LeadTable } from "@/components/lead-table";
import { searchLeads, lookupClientId, LeadFilters, LeadSearchResponse, LeadRecord, getHealth, getRentalsStats, getBayutStats } from "@/lib/api";
import { Download, Database, AlertTriangle, Home, Users } from "lucide-react";

interface DashStats {
  totalLeads: number;
  expiring30: number;
  bayutListings: number;
}

export default function LeadSearchPage() {
  const { authenticated } = useAuth();
  const router = useRouter();
  const [dashStats, setDashStats] = useState<DashStats | null>(null);
  const [filters, setFilters] = useState<LeadFilters>({
    page: 1,
    page_size: 250,
    sort_by: "completeness",
  });
  const [data, setData] = useState<LeadSearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const doSearch = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await searchLeads(filters);
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  // Load dashboard stats
  useEffect(() => {
    if (!authenticated) return;
    Promise.allSettled([getHealth(), getRentalsStats(), getBayutStats()]).then(([h, r, b]) => {
      setDashStats({
        totalLeads: h.status === "fulfilled" ? (h.value.total_leads ?? 0) : 0,
        expiring30: r.status === "fulfilled" ? (r.value.expiring_30 ?? 0) : 0,
        bayutListings: b.status === "fulfilled" ? (b.value.total ?? 0) : 0,
      });
    });
  }, [authenticated]);

  // Initial load
  useEffect(() => {
    if (authenticated) {
      doSearch();
    }
  }, [authenticated]); // eslint-disable-line react-hooks/exhaustive-deps

  const handlePageChange = (page: number) => {
    const updated = { ...filters, page };
    setFilters(updated);
    // Search with updated page
    setLoading(true);
    searchLeads(updated)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  const handleExport = async () => {
    try {
      const { exportLeads } = await import("@/lib/api");
      const csv = await exportLeads(filters);
      const blob = new Blob([csv], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "orva_leads_export.csv";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("Export failed");
    }
  };

  const handleSelectLead = async (lead: LeadRecord) => {
    try {
      const { client_id } = await lookupClientId(
        lead.owner_name || "",
        lead.building_name || "",
        lead.unit_number || "",
      );
      router.push(`/client/${client_id}`);
    } catch {
      // fallback: stay on page
    }
  };

  if (!authenticated) {
    return <LoginForm />;
  }


  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-20 md:pb-4">
      {/* Dashboard stat cards */}
      {dashStats && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <DashCard icon={<Database size={16} />} label="Total Leads" value={dashStats.totalLeads.toLocaleString()} href="/" />
          <DashCard icon={<AlertTriangle size={16} />} label="Expiring ≤30d" value={dashStats.expiring30.toLocaleString()} href="/lease-expiry" urgent={dashStats.expiring30 > 0} />
          <DashCard icon={<Home size={16} />} label="Bayut Listings" value={dashStats.bayutListings.toLocaleString()} href="/bayut" />
          <DashCard icon={<Users size={16} />} label="Contacts" value="View" href="/contacts" />
        </div>
      )}

      {/* Page header */}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-foreground">Lead Search</h1>
        {data && data.total > 0 && (
          <button
            onClick={handleExport}
            className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm text-muted transition-colors hover:bg-card-hover hover:text-foreground"
          >
            <Download size={14} />
            Export CSV
          </button>
        )}
      </div>

      {/* Filters */}
      <FilterPanel
        filters={filters}
        onChange={setFilters}
        onSearch={doSearch}
        totalResults={data?.total ?? 0}
      />

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-2 text-sm text-danger">
          {error}
        </div>
      )}

      {/* Results table */}
      <LeadTable
        leads={data?.leads ?? []}
        total={data?.total ?? 0}
        page={data?.page ?? 1}
        totalPages={data?.total_pages ?? 1}
        onPageChange={handlePageChange}
        onSelectLead={handleSelectLead}
        loading={loading}
      />
    </div>
  );
}

function DashCard({ icon, label, value, href, urgent }: { icon: React.ReactNode; label: string; value: string; href: string; urgent?: boolean }) {
  const router = useRouter();
  return (
    <button
      onClick={() => router.push(href)}
      className="rounded-lg border border-border bg-card p-3 text-left hover:border-accent/50 hover:bg-card-hover transition-colors"
    >
      <div className={`flex items-center gap-1.5 text-xs mb-1 ${urgent ? "text-danger" : "text-muted"}`}>
        {icon}{label}
      </div>
      <div className={`text-2xl font-bold ${urgent ? "text-danger" : "text-foreground"}`}>{value}</div>
    </button>
  );
}
