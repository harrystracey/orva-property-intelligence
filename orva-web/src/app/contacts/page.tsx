"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Users, Search, Plus, ArrowRight, Phone, Mail } from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import {
  listContacts,
  createContact,
  CONTACT_TYPES,
  ContactRecord,
  ContactSearchParams,
} from "@/lib/api";

export default function ContactsPage() {
  const { authenticated } = useAuth();
  const router = useRouter();

  const [contacts, setContacts] = useState<ContactRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [newName, setNewName] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newType, setNewType] = useState<string>("");

  const refresh = useCallback(
    async (override?: ContactSearchParams) => {
      setLoading(true);
      setError("");
      try {
        const data = await listContacts(
          override ?? {
            query: query || undefined,
            contact_type: typeFilter || undefined,
            limit: 500,
          },
        );
        setContacts(data.contacts);
        setTotal(data.total);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load contacts");
      } finally {
        setLoading(false);
      }
    },
    [query, typeFilter],
  );

  useEffect(() => {
    if (authenticated) refresh();
    // We deliberately depend only on `authenticated` for the initial load.
    // Subsequent refreshes are driven by the search button / filter chips.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authenticated]);

  if (!authenticated) {
    router.replace("/");
    return null;
  }

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    refresh();
  };

  const handleTypeFilter = (t: string) => {
    const next = typeFilter === t ? "" : t;
    setTypeFilter(next);
    refresh({ query: query || undefined, contact_type: next || undefined, limit: 500 });
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setCreateError("");
    try {
      const created = await createContact({
        full_name: newName.trim() || null,
        phone: newPhone.trim() || null,
        email: newEmail.trim() || null,
        contact_type: newType || null,
      });
      // Reset form, close modal, jump to detail
      setNewName("");
      setNewPhone("");
      setNewEmail("");
      setNewType("");
      setShowCreate(false);
      router.push(`/contact/${created.id}`);
    } catch (err) {
      setCreateError(
        err instanceof Error ? err.message : "Failed to create contact",
      );
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-mobile-nav max-w-4xl mx-auto w-full">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Users size={20} className="text-accent" />
          <h1 className="text-lg font-semibold text-foreground">Contacts</h1>
          <span className="text-sm text-muted">({total})</span>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-1.5 rounded-lg bg-accent/15 px-3 py-1.5 text-sm font-medium text-accent transition-colors hover:bg-accent/25"
        >
          <Plus size={14} />
          New
        </button>
      </div>

      {/* Search */}
      <form onSubmit={handleSearch} className="flex gap-2">
        <div className="relative flex-1">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-muted"
          />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Name, phone, or email"
            className="w-full rounded-lg border border-border bg-card px-3 py-2 pl-9 text-sm text-foreground placeholder:text-muted focus:border-accent focus:outline-none"
          />
        </div>
        <button
          type="submit"
          className="rounded-lg border border-border bg-card px-4 py-2 text-sm text-foreground hover:bg-card-hover"
        >
          Search
        </button>
      </form>

      {/* Type filter chips */}
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {CONTACT_TYPES.map((t) => (
          <button
            key={t}
            onClick={() => handleTypeFilter(t)}
            className={`rounded-full border px-3 py-1 text-xs whitespace-nowrap transition-colors ${
              typeFilter === t
                ? "border-accent bg-accent/15 text-accent"
                : "border-border bg-card text-muted hover:text-foreground"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-2 text-sm text-danger">
          {error}
        </div>
      )}

      {/* List */}
      {loading ? (
        <div className="rounded-xl border border-border bg-card p-8 text-center text-muted">
          Loading contacts…
        </div>
      ) : contacts.length === 0 ? (
        <div className="rounded-xl border border-border bg-card p-8 text-center">
          <p className="text-muted">
            {query || typeFilter
              ? "No contacts match those filters."
              : "No contacts yet. Click 'New' to add one."}
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {contacts.map((c) => (
            <button
              key={c.id}
              onClick={() => router.push(`/contact/${c.id}`)}
              className="rounded-xl border border-border bg-card p-4 text-left transition-colors hover:bg-card-hover"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium text-foreground truncate">
                      {c.full_name || "(unnamed)"}
                    </span>
                    {c.contact_type && (
                      <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[11px] text-accent">
                        {c.contact_type}
                      </span>
                    )}
                  </div>
                  {(c.phone || c.email) && (
                    <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
                      {c.phone && (
                        <span className="flex items-center gap-1">
                          <Phone size={10} />
                          {c.phone}
                        </span>
                      )}
                      {c.email && (
                        <span className="flex items-center gap-1 truncate">
                          <Mail size={10} />
                          {c.email}
                        </span>
                      )}
                    </div>
                  )}
                  {c.agent_assigned && (
                    <p className="mt-1 text-[11px] text-muted">
                      Agent: {c.agent_assigned}
                    </p>
                  )}
                </div>
                <ArrowRight size={14} className="shrink-0 text-muted mt-1" />
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Create modal */}
      {showCreate && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 sm:items-center"
          onClick={() => !creating && setShowCreate(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md rounded-2xl border border-border bg-card p-5"
          >
            <h2 className="mb-4 text-base font-semibold text-foreground">
              New Contact
            </h2>
            <form onSubmit={handleCreate} className="flex flex-col gap-3">
              <div>
                <label className="text-xs text-muted">Full name</label>
                <input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
                />
              </div>
              <div>
                <label className="text-xs text-muted">Phone</label>
                <input
                  value={newPhone}
                  onChange={(e) => setNewPhone(e.target.value)}
                  inputMode="tel"
                  className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
                />
              </div>
              <div>
                <label className="text-xs text-muted">Email</label>
                <input
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  inputMode="email"
                  className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
                />
              </div>
              <div>
                <label className="text-xs text-muted">Type</label>
                <select
                  value={newType}
                  onChange={(e) => setNewType(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
                >
                  <option value="">--</option>
                  {CONTACT_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </div>
              {createError && (
                <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
                  {createError}
                </div>
              )}
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  disabled={creating}
                  onClick={() => setShowCreate(false)}
                  className="flex-1 rounded-lg border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-card-hover disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="flex-1 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-background disabled:opacity-50"
                >
                  {creating ? "Saving…" : "Create"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
