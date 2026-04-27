"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

import {
  getClientProfile,
  addNote,
  editNote,
  deleteNote,
  addReminder,
  markReminderDone,
  logCall,
  ClientProfile,
} from "@/lib/api";
import {
  ArrowLeft,
  Phone,
  Plus,
  Check,
  X,
  Pencil,
  Trash2,
  CalendarClock,
  Clock,
} from "lucide-react";

const OUTCOMES = [
  { value: "interested", label: "Interested" },
  { value: "callback", label: "Callback" },
  { value: "voicemail", label: "Voicemail" },
  { value: "no_answer", label: "No Answer" },
  { value: "not_interested", label: "Not Interested" },
];

function outcomeColor(outcome: string) {
  switch (outcome) {
    case "interested": return "text-success";
    case "callback": return "text-warning";
    case "not_interested": return "text-danger";
    default: return "text-muted";
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

function formatDate(iso: string | null | undefined) {
  if (!iso) return "--";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
  } catch { return iso; }
}

function formatDateTime(iso: string | null | undefined) {
  if (!iso) return "--";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) +
      " " + d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}

function isOverdue(iso: string) {
  try {
    return new Date(iso) < new Date();
  } catch { return false; }
}

export default function ClientProfilePage() {
  const { authenticated, loading: authLoading } = useAuth();
  const params = useParams();
  const router = useRouter();
  const clientId = params?.id as string;

  const [profile, setProfile] = useState<ClientProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Note form
  const [noteText, setNoteText] = useState("");
  const [editingNote, setEditingNote] = useState<string | null>(null);
  const [editNoteText, setEditNoteText] = useState("");

  // Reminder form
  const [showReminderForm, setShowReminderForm] = useState(false);
  const [reminderDate, setReminderDate] = useState("");
  const [reminderNote, setReminderNote] = useState("");

  // Mobile tab
  const [activeTab, setActiveTab] = useState<"notes" | "reminders" | "calls">("notes");

  // Call log form
  const [showCallForm, setShowCallForm] = useState(false);
  const [callOutcome, setCallOutcome] = useState("no_answer");
  const [callNotes, setCallNotes] = useState("");
  const [callReminderDate, setCallReminderDate] = useState("");
  const [callReminderNote, setCallReminderNote] = useState("");

  const refresh = useCallback(async () => {
    if (!clientId) return;
    try {
      const data = await getClientProfile(clientId);
      setProfile(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load profile");
    } finally {
      setLoading(false);
    }
  }, [clientId]);

  useEffect(() => {
    if (authenticated && clientId) refresh();
  }, [authenticated, clientId, refresh]);

  if (authLoading) return null;
  if (!authenticated) { router.replace("/"); return null; }

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center p-8">
        <p className="text-muted">Loading profile...</p>
      </div>
    );
  }

  if (error || !profile) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8">
        <p className="text-danger">{error || "Profile not found"}</p>
        <button onClick={() => router.push("/leads")} className="text-sm text-accent hover:underline">
          Back to leads
        </button>
      </div>
    );
  }

  const handleAddNote = async () => {
    if (!noteText.trim()) return;
    await addNote(clientId, noteText.trim());
    setNoteText("");
    refresh();
  };

  const handleEditNote = async (noteId: string) => {
    if (!editNoteText.trim()) return;
    await editNote(clientId, noteId, editNoteText.trim());
    setEditingNote(null);
    setEditNoteText("");
    refresh();
  };

  const handleDeleteNote = async (noteId: string) => {
    await deleteNote(clientId, noteId);
    refresh();
  };

  const handleAddReminder = async () => {
    if (!reminderDate || !reminderNote.trim()) return;
    await addReminder(clientId, {
      client_name: profile.owner_name || "Unknown",
      building: profile.building_name || "",
      unit: profile.unit_number || "",
      phone: profile.phone || "",
      datetime: new Date(reminderDate).toISOString(),
      note: reminderNote.trim(),
    });
    setShowReminderForm(false);
    setReminderDate("");
    setReminderNote("");
    refresh();
  };

  const handleMarkDone = async (reminderId: string) => {
    await markReminderDone(reminderId);
    refresh();
  };

  const handleLogCall = async () => {
    await logCall(clientId, {
      client_name: profile.owner_name || "Unknown",
      building: profile.building_name || "",
      unit: profile.unit_number || "",
      phone: profile.phone || "",
      outcome: callOutcome,
      notes: callNotes,
      reminder_dt: callReminderDate ? new Date(callReminderDate).toISOString() : undefined,
      reminder_note: callReminderNote || undefined,
    });
    setShowCallForm(false);
    setCallOutcome("no_answer");
    setCallNotes("");
    setCallReminderDate("");
    setCallReminderNote("");
    refresh();
  };

  const beds = profile.bedrooms !== null ? (profile.bedrooms === 0 ? "Studio" : `${profile.bedrooms} BR`) : "--";

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-mobile-nav max-w-5xl mx-auto w-full">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => router.push("/leads")}
          className="rounded-lg p-2 text-muted hover:bg-card-hover hover:text-foreground"
        >
          <ArrowLeft size={18} />
        </button>
        <div>
          <h1 className="text-lg font-semibold text-foreground">{profile.owner_name || "Unknown Owner"}</h1>
          <p className="text-sm text-muted">
            {profile.building_name || "--"} {profile.unit_number ? `| Unit ${profile.unit_number}` : ""}
          </p>
        </div>
      </div>

      {/* Info card */}
      <div className="grid grid-cols-2 gap-3 rounded-xl border border-border bg-card p-4 sm:grid-cols-4">
        <div>
          <p className="text-xs text-muted">Bedrooms</p>
          <p className="text-sm font-medium text-foreground">{beds}</p>
        </div>
        <div>
          <p className="text-xs text-muted">Size</p>
          <p className="text-sm font-medium text-foreground">
            {profile.size_sqft ? `${Math.round(profile.size_sqft).toLocaleString()} sqft` : "--"}
          </p>
        </div>
        <div>
          <p className="text-xs text-muted">Phone</p>
          {profile.phone ? (
            <p className="text-sm font-medium text-foreground flex items-center gap-1">
              <Phone size={12} className="text-success" />
              {profile.phone}
            </p>
          ) : (
            <p className="text-sm text-muted">--</p>
          )}
        </div>
        <div>
          <p className="text-xs text-muted">Last Transaction</p>
          <p className="text-sm font-medium text-foreground">{formatDate(profile.date)}</p>
        </div>
      </div>

      {/* Portfolio */}
      {profile.portfolio.length > 1 && (
        <div className="rounded-xl border border-border bg-card p-4">
          <h2 className="mb-3 text-sm font-semibold text-foreground">
            Portfolio ({profile.portfolio.length} properties)
          </h2>
          <div className="table-scroll">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted">
                  <th className="pb-2 pr-4">Building</th>
                  <th className="pb-2 pr-4">Unit</th>
                  <th className="pb-2 pr-4">Beds</th>
                  <th className="pb-2 pr-4">Size</th>
                  <th className="hidden sm:table-cell pb-2 pr-4">Date</th>
                  <th className="hidden sm:table-cell pb-2">Value</th>
                </tr>
              </thead>
              <tbody>
                {profile.portfolio.map((p, i) => (
                  <tr key={i} className="border-b border-border/30">
                    <td className="py-2 pr-4 text-foreground">{p.building_name || "--"}</td>
                    <td className="py-2 pr-4 font-mono text-xs">{p.unit_number || "--"}</td>
                    <td className="py-2 pr-4">{p.bedrooms !== null ? (p.bedrooms === 0 ? "S" : p.bedrooms) : "--"}</td>
                    <td className="py-2 pr-4 text-muted">{p.size_sqft ? `${Math.round(p.size_sqft).toLocaleString()}` : "--"}</td>
                    <td className="hidden sm:table-cell py-2 pr-4 text-muted">{formatDate(p.date)}</td>
                    <td className="hidden sm:table-cell py-2 text-muted">
                      {p.transaction_value ? `AED ${Math.round(p.transaction_value).toLocaleString()}` : "--"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setShowCallForm(!showCallForm)}
          className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground hover:bg-card-hover"
        >
          <Phone size={14} /> Log Call
        </button>
        <button
          onClick={() => setShowReminderForm(!showReminderForm)}
          className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground hover:bg-card-hover"
        >
          <CalendarClock size={14} /> Set Reminder
        </button>
      </div>

      {/* Log Call form */}
      {showCallForm && (
        <div className="rounded-xl border border-accent/30 bg-card p-4">
          <h3 className="mb-3 text-sm font-semibold text-foreground">Log Call</h3>
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap gap-2">
              {OUTCOMES.map((o) => (
                <button
                  key={o.value}
                  onClick={() => setCallOutcome(o.value)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors ${
                    callOutcome === o.value
                      ? "border-accent bg-accent/15 text-accent"
                      : "border-border text-muted hover:border-accent/50"
                  }`}
                >
                  {o.label}
                </button>
              ))}
            </div>
            <textarea
              value={callNotes}
              onChange={(e) => setCallNotes(e.target.value)}
              placeholder="Call notes..."
              className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted/50 focus:border-accent focus:outline-none"
              rows={2}
            />
            <div className="flex flex-col gap-2 sm:flex-row">
              <input
                type="datetime-local"
                value={callReminderDate}
                onChange={(e) => setCallReminderDate(e.target.value)}
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-accent focus:outline-none"
                placeholder="Follow-up date"
              />
              <input
                type="text"
                value={callReminderNote}
                onChange={(e) => setCallReminderNote(e.target.value)}
                placeholder="Follow-up reason"
                className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted/50 focus:border-accent focus:outline-none"
              />
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleLogCall}
                className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover"
              >
                Save Call
              </button>
              <button
                onClick={() => setShowCallForm(false)}
                className="rounded-lg border border-border px-4 py-2 text-sm text-muted hover:bg-card-hover"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reminder form */}
      {showReminderForm && (
        <div className="rounded-xl border border-accent/30 bg-card p-4">
          <h3 className="mb-3 text-sm font-semibold text-foreground">Set Reminder</h3>
          <div className="flex flex-col gap-3">
            <input
              type="datetime-local"
              value={reminderDate}
              onChange={(e) => setReminderDate(e.target.value)}
              className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-accent focus:outline-none"
            />
            <input
              type="text"
              value={reminderNote}
              onChange={(e) => setReminderNote(e.target.value)}
              placeholder="Reminder reason..."
              className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted/50 focus:border-accent focus:outline-none"
            />
            <div className="flex gap-2">
              <button
                onClick={handleAddReminder}
                disabled={!reminderDate || !reminderNote.trim()}
                className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-40"
              >
                Save Reminder
              </button>
              <button
                onClick={() => setShowReminderForm(false)}
                className="rounded-lg border border-border px-4 py-2 text-sm text-muted hover:bg-card-hover"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── Mobile: Tabbed layout ─── */}
      <div className="md:hidden flex flex-col gap-3">
        <div className="flex gap-1 rounded-lg border border-border bg-card p-1">
          {(["notes", "reminders", "calls"] as const).map((tab) => {
            const counts = { notes: profile.notes.length, reminders: profile.reminders.filter(r => r.status !== "done").length, calls: profile.calls.length };
            const labels = { notes: "Notes", reminders: "Reminders", calls: "Calls" };
            return (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`flex-1 rounded-md px-2 py-2 text-sm font-medium text-center transition-colors ${
                  activeTab === tab ? "bg-accent/15 text-accent" : "text-muted"
                }`}
              >
                {labels[tab]} ({counts[tab]})
              </button>
            );
          })}
        </div>

        {activeTab === "notes" && (
          <div className="rounded-xl border border-border bg-card p-4">
            <div className="mb-3 flex gap-2">
              <input type="text" value={noteText} onChange={(e) => setNoteText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleAddNote()} placeholder="Add a note..." className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted/50 focus:border-accent focus:outline-none" />
              <button onClick={handleAddNote} disabled={!noteText.trim()} className="rounded-lg bg-accent p-2 text-white hover:bg-accent-hover disabled:opacity-40"><Plus size={16} /></button>
            </div>
            <div className="flex flex-col gap-2">
              {profile.notes.length === 0 ? (
                <p className="text-xs text-muted py-4 text-center">No notes yet</p>
              ) : profile.notes.map((note) => (
                <div key={note.id} className="rounded-lg border border-border/50 bg-background p-3">
                  {editingNote === note.id ? (
                    <div className="flex gap-2">
                      <input type="text" value={editNoteText} onChange={(e) => setEditNoteText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleEditNote(note.id)} className="flex-1 rounded border border-border bg-card px-2 py-1 text-sm text-foreground focus:border-accent focus:outline-none" autoFocus />
                      <button onClick={() => handleEditNote(note.id)} className="text-success hover:text-accent-hover"><Check size={14} /></button>
                      <button onClick={() => setEditingNote(null)} className="text-muted hover:text-foreground"><X size={14} /></button>
                    </div>
                  ) : (
                    <>
                      <p className="text-sm text-foreground">{note.text}</p>
                      <div className="mt-1 flex items-center justify-between">
                        <span className="text-[10px] text-muted">{formatDateTime(note.timestamp)}{note.edited_at && " (edited)"}</span>
                        <div className="flex gap-1">
                          <button onClick={() => { setEditingNote(note.id); setEditNoteText(note.text); }} className="rounded p-2 text-muted hover:text-foreground"><Pencil size={12} /></button>
                          <button onClick={() => handleDeleteNote(note.id)} className="rounded p-2 text-muted hover:text-danger"><Trash2 size={12} /></button>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === "reminders" && (
          <div className="rounded-xl border border-border bg-card p-4">
            <div className="flex flex-col gap-2">
              {profile.reminders.length === 0 ? (
                <p className="text-xs text-muted py-4 text-center">No reminders</p>
              ) : profile.reminders.map((r) => (
                <div key={r.id} className={`flex items-start justify-between rounded-lg border p-3 ${r.status === "done" ? "border-border/30 opacity-50" : isOverdue(r.datetime) ? "border-danger/40 bg-danger/5" : "border-border/50 bg-background"}`}>
                  <div className="flex-1">
                    <p className="text-sm text-foreground">{r.note}</p>
                    <p className="text-[10px] text-muted flex items-center gap-1 mt-1"><Clock size={10} />{formatDateTime(r.datetime)}{r.status === "done" && " -- Done"}{r.status !== "done" && isOverdue(r.datetime) && " -- OVERDUE"}</p>
                  </div>
                  {r.status !== "done" && <button onClick={() => handleMarkDone(r.id)} className="ml-2 rounded p-2 text-muted hover:text-success" title="Mark done"><Check size={14} /></button>}
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === "calls" && (
          <div className="rounded-xl border border-border bg-card p-4">
            <div className="flex flex-col gap-2">
              {profile.calls.length === 0 ? (
                <p className="text-xs text-muted py-4 text-center">No calls logged</p>
              ) : profile.calls.map((c) => (
                <div key={c.id} className="rounded-lg border border-border/50 bg-background p-3">
                  <div className="flex items-center justify-between">
                    <span className={`text-sm font-medium ${outcomeColor(c.outcome)}`}>{outcomeSymbol(c.outcome)} {c.outcome.replace("_", " ")}</span>
                    <span className="text-[10px] text-muted">{formatDateTime(c.called_at)}</span>
                  </div>
                  {c.notes && <p className="mt-1 text-xs text-muted">{c.notes}</p>}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ─── Desktop: Two-column grid (unchanged) ─── */}
      <div className="hidden md:grid gap-4 md:grid-cols-2">
        {/* Notes */}
        <div className="rounded-xl border border-border bg-card p-4">
          <h2 className="mb-3 text-sm font-semibold text-foreground">Notes</h2>
          <div className="mb-3 flex gap-2">
            <input type="text" value={noteText} onChange={(e) => setNoteText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleAddNote()} placeholder="Add a note..." className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted/50 focus:border-accent focus:outline-none" />
            <button onClick={handleAddNote} disabled={!noteText.trim()} className="rounded-lg bg-accent p-2 text-white hover:bg-accent-hover disabled:opacity-40"><Plus size={16} /></button>
          </div>
          <div className="flex flex-col gap-2 max-h-80 overflow-y-auto">
            {profile.notes.length === 0 ? (
              <p className="text-xs text-muted py-4 text-center">No notes yet</p>
            ) : profile.notes.map((note) => (
              <div key={note.id} className="rounded-lg border border-border/50 bg-background p-3">
                {editingNote === note.id ? (
                  <div className="flex gap-2">
                    <input type="text" value={editNoteText} onChange={(e) => setEditNoteText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleEditNote(note.id)} className="flex-1 rounded border border-border bg-card px-2 py-1 text-sm text-foreground focus:border-accent focus:outline-none" autoFocus />
                    <button onClick={() => handleEditNote(note.id)} className="text-success hover:text-accent-hover"><Check size={14} /></button>
                    <button onClick={() => setEditingNote(null)} className="text-muted hover:text-foreground"><X size={14} /></button>
                  </div>
                ) : (
                  <>
                    <p className="text-sm text-foreground">{note.text}</p>
                    <div className="mt-1 flex items-center justify-between">
                      <span className="text-[10px] text-muted">{formatDateTime(note.timestamp)}{note.edited_at && " (edited)"}</span>
                      <div className="flex gap-1">
                        <button onClick={() => { setEditingNote(note.id); setEditNoteText(note.text); }} className="rounded p-2 text-muted hover:text-foreground"><Pencil size={12} /></button>
                        <button onClick={() => handleDeleteNote(note.id)} className="rounded p-2 text-muted hover:text-danger"><Trash2 size={12} /></button>
                      </div>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Reminders + Call History */}
        <div className="flex flex-col gap-4">
          <div className="rounded-xl border border-border bg-card p-4">
            <h2 className="mb-3 text-sm font-semibold text-foreground">Reminders</h2>
            <div className="flex flex-col gap-2 max-h-40 overflow-y-auto">
              {profile.reminders.length === 0 ? (
                <p className="text-xs text-muted py-4 text-center">No reminders</p>
              ) : profile.reminders.map((r) => (
                <div key={r.id} className={`flex items-start justify-between rounded-lg border p-3 ${r.status === "done" ? "border-border/30 opacity-50" : isOverdue(r.datetime) ? "border-danger/40 bg-danger/5" : "border-border/50 bg-background"}`}>
                  <div className="flex-1">
                    <p className="text-sm text-foreground">{r.note}</p>
                    <p className="text-[10px] text-muted flex items-center gap-1 mt-1"><Clock size={10} />{formatDateTime(r.datetime)}{r.status === "done" && " -- Done"}{r.status !== "done" && isOverdue(r.datetime) && " -- OVERDUE"}</p>
                  </div>
                  {r.status !== "done" && <button onClick={() => handleMarkDone(r.id)} className="ml-2 rounded p-2 text-muted hover:text-success" title="Mark done"><Check size={14} /></button>}
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <h2 className="mb-3 text-sm font-semibold text-foreground">Call History</h2>
            <div className="flex flex-col gap-2 max-h-40 overflow-y-auto">
              {profile.calls.length === 0 ? (
                <p className="text-xs text-muted py-4 text-center">No calls logged</p>
              ) : profile.calls.map((c) => (
                <div key={c.id} className="rounded-lg border border-border/50 bg-background p-3">
                  <div className="flex items-center justify-between">
                    <span className={`text-sm font-medium ${outcomeColor(c.outcome)}`}>{outcomeSymbol(c.outcome)} {c.outcome.replace("_", " ")}</span>
                    <span className="text-[10px] text-muted">{formatDateTime(c.called_at)}</span>
                  </div>
                  {c.notes && <p className="mt-1 text-xs text-muted">{c.notes}</p>}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
