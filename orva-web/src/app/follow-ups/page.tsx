"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

import { getAllReminders, markReminderDone, deleteReminder, ReminderRecord } from "@/lib/api";
import { CalendarClock, Check, Trash2, Clock, ArrowRight } from "lucide-react";
import { SkeletonReminderCard } from "@/components/skeleton";

function formatDateTime(iso: string | null | undefined) {
  if (!iso) return "--";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) +
      " " + d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}

function isOverdue(iso: string) {
  try { return new Date(iso) < new Date(); } catch { return false; }
}

function isDueToday(iso: string) {
  try {
    const d = new Date(iso);
    const now = new Date();
    return d.toDateString() === now.toDateString();
  } catch { return false; }
}

export default function FollowUpsPage() {
  const { authenticated, loading: authLoading } = useAuth();
  const router = useRouter();
  const [reminders, setReminders] = useState<ReminderRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"pending" | "done" | "all">("pending");

  const refresh = useCallback(async () => {
    try {
      const data = await getAllReminders();
      setReminders(data);
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

  const handleDone = async (id: string) => {
    await markReminderDone(id);
    refresh();
  };

  const handleDelete = async (id: string) => {
    await deleteReminder(id);
    refresh();
  };

  const filtered = reminders.filter((r) => {
    if (filter === "pending") return r.status !== "done";
    if (filter === "done") return r.status === "done";
    return true;
  });

  const overdueCount = reminders.filter((r) => r.status !== "done" && isOverdue(r.datetime)).length;
  const todayCount = reminders.filter((r) => r.status !== "done" && isDueToday(r.datetime)).length;
  const pendingCount = reminders.filter((r) => r.status !== "done").length;

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-mobile-nav max-w-4xl mx-auto w-full">
      {/* Header */}
      <div className="flex items-center gap-2">
        <CalendarClock size={20} className="text-accent" />
        <h1 className="text-lg font-semibold text-foreground">Follow-Ups</h1>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-xl border border-danger/30 bg-card p-3 text-center">
          <p className="text-2xl font-bold text-danger">{overdueCount}</p>
          <p className="text-xs text-muted">Overdue</p>
        </div>
        <div className="rounded-xl border border-warning/30 bg-card p-3 text-center">
          <p className="text-2xl font-bold text-warning">{todayCount}</p>
          <p className="text-xs text-muted">Due Today</p>
        </div>
        <div className="rounded-xl border border-border bg-card p-3 text-center">
          <p className="text-2xl font-bold text-foreground">{pendingCount}</p>
          <p className="text-xs text-muted">Total Pending</p>
        </div>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-1 rounded-lg border border-border bg-card p-1">
        {(["pending", "done", "all"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              filter === f
                ? "bg-accent/15 text-accent"
                : "text-muted hover:text-foreground"
            }`}
          >
            {f === "pending" ? "Pending" : f === "done" ? "Completed" : "All"}
          </button>
        ))}
      </div>

      {/* List */}
      {loading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 3 }, (_, i) => <SkeletonReminderCard key={i} />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-border bg-card p-8 text-center">
          <p className="text-muted">
            {filter === "pending" ? "No pending follow-ups" : filter === "done" ? "No completed follow-ups" : "No follow-ups"}
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {filtered.map((r) => {
            const overdue = r.status !== "done" && isOverdue(r.datetime);
            const today = r.status !== "done" && isDueToday(r.datetime);

            return (
              <div
                key={r.id}
                className={`rounded-xl border p-4 transition-colors ${
                  r.status === "done"
                    ? "border-border/30 bg-card opacity-60"
                    : overdue
                      ? "border-danger/40 bg-danger/5"
                      : today
                        ? "border-warning/40 bg-warning/5"
                        : "border-border bg-card"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    {/* Client info */}
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-medium text-foreground truncate">
                        {r.client_name || "Unknown"}
                      </span>
                      {r.building && (
                        <span className="text-xs text-muted truncate">
                          {r.building}{r.unit ? ` | ${r.unit}` : ""}
                        </span>
                      )}
                    </div>

                    {/* Reminder note */}
                    <p className="text-sm text-foreground mb-1">{r.note}</p>

                    {/* Time */}
                    <p className="text-[11px] text-muted flex items-center gap-1">
                      <Clock size={10} />
                      {formatDateTime(r.datetime)}
                      {overdue && <span className="ml-1 text-danger font-medium">OVERDUE</span>}
                      {today && !overdue && <span className="ml-1 text-warning font-medium">TODAY</span>}
                      {r.status === "done" && <span className="ml-1 text-success">Done</span>}
                    </p>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => router.push(`/client/${r.client_id}`)}
                      className="rounded p-2 min-w-[40px] min-h-[40px] flex items-center justify-center text-muted hover:text-accent"
                      title="View profile"
                    >
                      <ArrowRight size={14} />
                    </button>
                    {r.status !== "done" && (
                      <button
                        onClick={() => handleDone(r.id)}
                        className="rounded p-2 min-w-[40px] min-h-[40px] flex items-center justify-center text-muted hover:text-success"
                        title="Mark done"
                      >
                        <Check size={14} />
                      </button>
                    )}
                    <button
                      onClick={() => handleDelete(r.id)}
                      className="rounded p-2 min-w-[40px] min-h-[40px] flex items-center justify-center text-muted hover:text-danger"
                      title="Delete"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
