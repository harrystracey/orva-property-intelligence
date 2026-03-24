"use client";

import { useState } from "react";
import { LeadFilters } from "@/lib/api";
import { SlidersHorizontal, ChevronDown, ChevronUp, RotateCw } from "lucide-react";

interface FilterPanelProps {
  filters: LeadFilters;
  onChange: (filters: LeadFilters) => void;
  onSearch: () => void;
  totalResults: number;
}

export function FilterPanel({
  filters,
  onChange,
  onSearch,
  totalResults,
}: FilterPanelProps) {
  const [expanded, setExpanded] = useState(false);

  const update = (patch: Partial<LeadFilters>) => {
    onChange({ ...filters, ...patch, page: 1 });
  };

  const reset = () => {
    onChange({ page: 1, page_size: 250, sort_by: "completeness" });
    onSearch();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") onSearch();
  };

  const inputClass =
    "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent placeholder:text-muted/50";

  const activeCount = [
    filters.owner_name,
    filters.building_search,
    filters.bedrooms,
    filters.unit_number,
    filters.phone,
    filters.date_start,
    filters.date_end,
    filters.min_size_sqft,
    filters.max_size_sqft,
    filters.source_filter,
    (filters.min_completeness ?? 0) > 0 ? "yes" : "",
  ].filter(Boolean).length;

  return (
    <div className="rounded-xl border border-border bg-card">
      {/* Header row — always visible */}
      <div className="flex flex-wrap items-center gap-3 px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-medium text-foreground">
          <SlidersHorizontal size={16} className="text-accent" />
          Filters
          {activeCount > 0 && (
            <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-accent/20 px-1.5 text-xs font-semibold text-accent">
              {activeCount}
            </span>
          )}
        </div>

        {/* Quick filters — always visible */}
        <input
          type="text"
          placeholder="Owner name"
          value={filters.owner_name || ""}
          onChange={(e) => update({ owner_name: e.target.value })}
          onKeyDown={handleKeyDown}
          className={`${inputClass} max-w-48`}
        />
        <input
          type="text"
          placeholder="Building"
          value={filters.building_search || ""}
          onChange={(e) => update({ building_search: e.target.value })}
          onKeyDown={handleKeyDown}
          className={`${inputClass} max-w-40`}
        />
        <select
          value={filters.bedrooms || ""}
          onChange={(e) => update({ bedrooms: e.target.value || undefined })}
          className={`${inputClass} max-w-28`}
        >
          <option value="">All beds</option>
          <option value="Studio">Studio</option>
          <option value="1">1 BR</option>
          <option value="2">2 BR</option>
          <option value="3">3 BR</option>
          <option value="4">4 BR</option>
          <option value="5">5+ BR</option>
        </select>

        <button
          onClick={onSearch}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-hover"
        >
          Search
        </button>

        <button
          onClick={() => setExpanded(!expanded)}
          className="ml-auto flex items-center gap-1 rounded-lg px-2 py-2 text-sm text-muted hover:text-foreground"
        >
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          <span className="hidden sm:inline">
            {expanded ? "Less" : "More"}
          </span>
        </button>

        {activeCount > 0 && (
          <button
            onClick={reset}
            className="flex items-center gap-1 rounded-lg px-2 py-2 text-sm text-muted hover:text-foreground"
          >
            <RotateCw size={14} />
            <span className="hidden sm:inline">Reset</span>
          </button>
        )}
      </div>

      {/* Expanded filters */}
      {expanded && (
        <div className="border-t border-border px-4 py-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className="mb-1 block text-xs text-muted">Unit number</label>
              <input
                type="text"
                placeholder="e.g. 1205"
                value={filters.unit_number || ""}
                onChange={(e) => update({ unit_number: e.target.value })}
                onKeyDown={handleKeyDown}
                className={inputClass}
              />
            </div>

            <div>
              <label className="mb-1 block text-xs text-muted">Phone</label>
              <input
                type="text"
                placeholder="e.g. 971..."
                value={filters.phone || ""}
                onChange={(e) => update({ phone: e.target.value })}
                onKeyDown={handleKeyDown}
                className={inputClass}
              />
            </div>

            <div>
              <label className="mb-1 block text-xs text-muted">Date from</label>
              <input
                type="date"
                value={filters.date_start || ""}
                onChange={(e) => update({ date_start: e.target.value })}
                className={inputClass}
              />
            </div>

            <div>
              <label className="mb-1 block text-xs text-muted">Date to</label>
              <input
                type="date"
                value={filters.date_end || ""}
                onChange={(e) => update({ date_end: e.target.value })}
                className={inputClass}
              />
            </div>

            <div>
              <label className="mb-1 block text-xs text-muted">Min size (sqft)</label>
              <input
                type="number"
                placeholder="0"
                value={filters.min_size_sqft ?? ""}
                onChange={(e) =>
                  update({
                    min_size_sqft: e.target.value
                      ? Number(e.target.value)
                      : undefined,
                  })
                }
                className={inputClass}
              />
            </div>

            <div>
              <label className="mb-1 block text-xs text-muted">Max size (sqft)</label>
              <input
                type="number"
                placeholder="any"
                value={filters.max_size_sqft ?? ""}
                onChange={(e) =>
                  update({
                    max_size_sqft: e.target.value
                      ? Number(e.target.value)
                      : undefined,
                  })
                }
                className={inputClass}
              />
            </div>

            <div>
              <label className="mb-1 block text-xs text-muted">
                Min completeness (%)
              </label>
              <input
                type="number"
                min={0}
                max={100}
                placeholder="0"
                value={filters.min_completeness ?? ""}
                onChange={(e) =>
                  update({
                    min_completeness: e.target.value
                      ? Number(e.target.value)
                      : 0,
                  })
                }
                className={inputClass}
              />
            </div>

            <div>
              <label className="mb-1 block text-xs text-muted">Source</label>
              <select
                value={filters.source_filter || ""}
                onChange={(e) =>
                  update({ source_filter: e.target.value || undefined })
                }
                className={inputClass}
              >
                <option value="">All sources</option>
                <option value="crm">CRM</option>
                <option value="propertyfinder">PropertyFinder</option>
              </select>
            </div>
          </div>
        </div>
      )}

      {/* Result count + sort */}
      <div className="flex items-center justify-between border-t border-border px-4 py-2">
        <span className="text-sm text-muted">
          {totalResults.toLocaleString()} leads
        </span>
        <div className="flex items-center gap-2">
          <label className="text-xs text-muted">Sort:</label>
          <select
            value={filters.sort_by || "completeness"}
            onChange={(e) => {
              update({ sort_by: e.target.value });
              // Auto-search on sort change
              setTimeout(onSearch, 0);
            }}
            className="rounded-lg border border-border bg-background px-2 py-1 text-xs text-foreground outline-none focus:border-accent"
          >
            <option value="completeness">Completeness</option>
            <option value="newest">Newest</option>
            <option value="oldest">Oldest</option>
          </select>
        </div>
      </div>
    </div>
  );
}
