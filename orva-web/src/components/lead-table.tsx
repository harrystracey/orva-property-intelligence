"use client";

import { LeadRecord } from "@/lib/api";
import { User, Building2, Phone, ChevronLeft, ChevronRight } from "lucide-react";

interface LeadTableProps {
  leads: LeadRecord[];
  total: number;
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  onSelectLead?: (lead: LeadRecord) => void;
  loading?: boolean;
}

function BedroomBadge({ bedrooms }: { bedrooms: number | null }) {
  if (bedrooms === null || bedrooms === undefined) {
    return <span className="text-muted">--</span>;
  }
  const label = bedrooms === 0 ? "S" : `${bedrooms}`;
  return (
    <span className="inline-flex h-6 min-w-6 items-center justify-center rounded bg-accent/15 px-1.5 text-xs font-semibold text-accent">
      {label}
    </span>
  );
}

function CompletenessBar({ value }: { value: number | null }) {
  const pct = value ?? 0;
  let color = "bg-danger";
  if (pct >= 80) color = "bg-success";
  else if (pct >= 50) color = "bg-warning";

  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 rounded-full bg-border">
        <div
          className={`h-full rounded-full ${color}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      <span className="text-xs text-muted">{pct}%</span>
    </div>
  );
}

export function LeadTable({
  leads,
  total,
  page,
  totalPages,
  onPageChange,
  onSelectLead,
  loading,
}: LeadTableProps) {
  return (
    <div className="flex flex-col rounded-xl border border-border bg-card">
      {/* Table */}
      <div className="table-scroll">
        <table className="w-full min-w-[800px] text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs font-medium uppercase tracking-wider text-muted">
              <th className="sticky left-0 z-10 bg-card px-4 py-3">Owner</th>
              <th className="px-4 py-3">Building</th>
              <th className="px-3 py-3">Unit</th>
              <th className="px-3 py-3">Beds</th>
              <th className="px-3 py-3">Size</th>
              <th className="px-3 py-3">Phone</th>
              <th className="px-3 py-3">Date</th>
              <th className="px-3 py-3">Score</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={8} className="px-4 py-12 text-center text-muted">
                  Loading leads...
                </td>
              </tr>
            ) : leads.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-12 text-center text-muted">
                  No leads match your filters
                </td>
              </tr>
            ) : (
              leads.map((lead, i) => (
                <tr
                  key={i}
                  onClick={() => onSelectLead?.(lead)}
                  className="border-b border-border/50 transition-colors hover:bg-card-hover cursor-pointer"
                >
                  <td className="sticky left-0 z-10 bg-card px-4 py-2.5 font-medium text-foreground hover:bg-card-hover">
                    <div className="flex items-center gap-2">
                      <User size={14} className="shrink-0 text-muted" />
                      <span className="truncate max-w-[180px]">
                        {lead.owner_name || "--"}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-1.5">
                      <Building2 size={14} className="shrink-0 text-muted" />
                      <span className="truncate max-w-[160px]">
                        {lead.building_name || "--"}
                      </span>
                    </div>
                  </td>
                  <td className="px-3 py-2.5 font-mono text-xs">
                    {lead.unit_number || "--"}
                  </td>
                  <td className="px-3 py-2.5">
                    <BedroomBadge bedrooms={lead.bedrooms} />
                  </td>
                  <td className="px-3 py-2.5 text-xs text-muted">
                    {lead.size_sqft
                      ? `${Math.round(lead.size_sqft).toLocaleString()} sqft`
                      : "--"}
                  </td>
                  <td className="px-3 py-2.5">
                    {lead.phone ? (
                      <div className="flex items-center gap-1">
                        <Phone size={12} className="text-success" />
                        <span className="font-mono text-xs">
                          {lead.phone}
                        </span>
                      </div>
                    ) : (
                      <span className="text-xs text-muted">--</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-xs text-muted">
                    {lead.date || "--"}
                  </td>
                  <td className="px-3 py-2.5">
                    <CompletenessBar value={lead.completeness} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between border-t border-border px-4 py-3">
          <span className="text-xs text-muted">
            Page {page} of {totalPages} ({total.toLocaleString()} total)
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => onPageChange(page - 1)}
              disabled={page <= 1}
              className="rounded-lg p-1.5 text-muted hover:bg-card-hover hover:text-foreground disabled:opacity-30"
            >
              <ChevronLeft size={18} />
            </button>

            {/* Page numbers */}
            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              let pageNum: number;
              if (totalPages <= 5) {
                pageNum = i + 1;
              } else if (page <= 3) {
                pageNum = i + 1;
              } else if (page >= totalPages - 2) {
                pageNum = totalPages - 4 + i;
              } else {
                pageNum = page - 2 + i;
              }
              return (
                <button
                  key={pageNum}
                  onClick={() => onPageChange(pageNum)}
                  className={`flex h-8 min-w-8 items-center justify-center rounded-lg text-xs font-medium ${
                    pageNum === page
                      ? "bg-accent text-white"
                      : "text-muted hover:bg-card-hover hover:text-foreground"
                  }`}
                >
                  {pageNum}
                </button>
              );
            })}

            <button
              onClick={() => onPageChange(page + 1)}
              disabled={page >= totalPages}
              className="rounded-lg p-1.5 text-muted hover:bg-card-hover hover:text-foreground disabled:opacity-30"
            >
              <ChevronRight size={18} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
