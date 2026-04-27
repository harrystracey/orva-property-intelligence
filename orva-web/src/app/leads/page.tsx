"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { FilterPanel } from "@/components/filter-panel";
import { LeadTable } from "@/components/lead-table";
import { searchLeads, lookupClientId, LeadFilters, LeadSearchResponse, LeadRecord } from "@/lib/api";
import { Download } from "lucide-react";

export default function LeadSearchPage() {
  const { authenticated, loading: authLoading } = useAuth();
  const router = useRouter();
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

  // /leads is the authenticated lead-search page. Unauthenticated users
  // get sent to "/" which nginx serves as the marketing landing.
  if (authLoading) return null;
  if (!authenticated) {
    if (typeof window !== "undefined") window.location.href = "/";
    return null;
  }

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-mobile-nav">
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
