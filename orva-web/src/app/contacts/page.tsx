"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/lib/auth-context";
import { LoginForm } from "@/components/login-form";
import { getContacts, createContact, deleteContact, Contact } from "@/lib/api";
import { useRouter } from "next/navigation";
import { Users, Plus, Trash2, Phone, Mail, Search, X, Crosshair } from "lucide-react";

const TYPE_LABELS: Record<string, string> = {
  buyer: "Buyer",
  seller: "Seller",
  tenant: "Tenant",
  landlord: "Landlord",
  investor: "Investor",
};

function formatAED(n: number | null | undefined) {
  if (!n) return "--";
  return "AED " + Math.round(n).toLocaleString();
}

export default function ContactsPage() {
  const { authenticated } = useAuth();
  const router = useRouter();
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [selected, setSelected] = useState<Contact | null>(null);

  // New contact form state
  const [form, setForm] = useState({
    full_name: "", phone: "", email: "",
    contact_type: "buyer", budget_min: "", budget_max: "",
  });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getContacts({ q: query, contact_type: typeFilter });
      setContacts(res.contacts);
      setTotal(res.total);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [query, typeFilter]);

  useEffect(() => { if (authenticated) load(); }, [authenticated, load]);

  const handleAdd = async () => {
    setSaving(true);
    setSaveError("");
    try {
      await createContact({
        full_name: form.full_name || undefined,
        phone: form.phone || undefined,
        email: form.email || undefined,
        contact_type: form.contact_type || undefined,
        budget_min: form.budget_min ? Number(form.budget_min) : undefined,
        budget_max: form.budget_max ? Number(form.budget_max) : undefined,
      });
      setShowAdd(false);
      setForm({ full_name: "", phone: "", email: "", contact_type: "buyer", budget_min: "", budget_max: "" });
      load();
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : "Failed to save");
    } finally { setSaving(false); }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this contact?")) return;
    try {
      await deleteContact(id);
      if (selected?.id === id) setSelected(null);
      load();
    } catch { /* ignore */ }
  };

  if (!authenticated) return <LoginForm />;

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-20 md:pb-4">
      <div className="flex items-center gap-2">
        <Users size={20} className="text-accent" />
        <h1 className="text-lg font-semibold text-foreground">Contacts</h1>
        <span className="ml-2 text-sm text-muted">{total.toLocaleString()} total</span>
        <button
          onClick={() => setShowAdd(true)}
          className="ml-auto flex items-center gap-1 rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-accent/90"
        >
          <Plus size={14} /> Add Contact
        </button>
      </div>

      {/* Add contact modal */}
      {showAdd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-semibold text-foreground">New Contact</h2>
              <button onClick={() => setShowAdd(false)}><X size={18} className="text-muted" /></button>
            </div>
            <div className="flex flex-col gap-3">
              <input placeholder="Full name" value={form.full_name} onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))}
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent" />
              <input placeholder="Phone (e.g. +971...)" value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))}
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent" />
              <input placeholder="Email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent" />
              <select value={form.contact_type} onChange={e => setForm(f => ({ ...f, contact_type: e.target.value }))}
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent">
                {Object.entries(TYPE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <div className="flex gap-2">
                <input placeholder="Budget min (AED)" type="number" value={form.budget_min} onChange={e => setForm(f => ({ ...f, budget_min: e.target.value }))}
                  className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent" />
                <input placeholder="Budget max (AED)" type="number" value={form.budget_max} onChange={e => setForm(f => ({ ...f, budget_max: e.target.value }))}
                  className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent" />
              </div>
              {saveError && <p className="text-xs text-danger">{saveError}</p>}
              <button onClick={handleAdd} disabled={saving}
                className="rounded-lg bg-accent py-2 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-50">
                {saving ? "Saving..." : "Save Contact"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3 rounded-xl border border-border bg-card px-4 py-3">
        <div className="flex flex-1 items-center gap-2 rounded-lg border border-border bg-background px-3 py-1.5">
          <Search size={14} className="text-muted" />
          <input
            type="text"
            placeholder="Search name, phone, email..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            className="flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted"
          />
        </div>
        <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)}
          className="rounded-lg border border-border bg-background px-2 py-1 text-sm text-foreground outline-none focus:border-accent">
          <option value="">All types</option>
          {Object.entries(TYPE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-border bg-card">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border bg-background/50">
                {["Name", "Phone", "Email", "Type", "Budget", "Properties", ""].map(h => (
                  <th key={h} className="whitespace-nowrap px-4 py-2 text-left text-xs font-medium text-muted">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-sm text-muted">Loading...</td></tr>
              ) : contacts.length === 0 ? (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-sm text-muted">No contacts found</td></tr>
              ) : contacts.map(c => (
                <tr key={c.id} className="border-b border-border/50 hover:bg-card-hover cursor-pointer"
                  onClick={() => setSelected(c)}>
                  <td className="px-4 py-2 text-sm font-medium text-foreground">{c.full_name || "--"}</td>
                  <td className="px-4 py-2 text-sm text-muted">
                    {c.phone ? <span className="flex items-center gap-1"><Phone size={11} />{c.phone}</span> : "--"}
                  </td>
                  <td className="px-4 py-2 text-sm text-muted">
                    {c.email ? <span className="flex items-center gap-1"><Mail size={11} />{c.email}</span> : "--"}
                  </td>
                  <td className="px-4 py-2">
                    {c.contact_type ? (
                      <span className="rounded-full bg-accent/10 px-2 py-0.5 text-xs text-accent">
                        {TYPE_LABELS[c.contact_type] ?? c.contact_type}
                      </span>
                    ) : <span className="text-xs text-muted">--</span>}
                  </td>
                  <td className="px-4 py-2 text-xs text-muted">
                    {c.budget_min || c.budget_max
                      ? `${formatAED(c.budget_min)} – ${formatAED(c.budget_max)}`
                      : "--"}
                  </td>
                  <td className="px-4 py-2 text-xs text-muted">{c.properties?.length ?? 0}</td>
                  <td className="px-4 py-2" onClick={e => e.stopPropagation()}>
                    <button onClick={() => handleDelete(c.id)} className="text-muted hover:text-danger">
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Contact detail panel */}
      {selected && (
        <div className="fixed inset-y-0 right-0 z-40 w-full max-w-sm overflow-y-auto border-l border-border bg-card p-6 shadow-2xl md:w-96">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-semibold text-foreground">{selected.full_name || "Contact"}</h2>
            <button onClick={() => setSelected(null)}><X size={18} className="text-muted" /></button>
          </div>
          <div className="flex flex-col gap-3 text-sm">
            <Row label="Type" value={selected.contact_type ? (TYPE_LABELS[selected.contact_type] ?? selected.contact_type) : "--"} />
            <Row label="Phone" value={selected.phone ?? "--"} />
            <Row label="Email" value={selected.email ?? "--"} />
            <Row label="Budget" value={
              selected.budget_min || selected.budget_max
                ? `${formatAED(selected.budget_min)} – ${formatAED(selected.budget_max)}`
                : "--"
            } />
            <Row label="Source" value={selected.source ?? "--"} />
            <Row label="Agent" value={selected.agent_assigned ?? "--"} />

            {/* Find matching listings for this client */}
            {(selected.contact_type === "buyer" || selected.contact_type === "tenant") && (
              <button
                onClick={() => {
                  const p = new URLSearchParams();
                  p.set("type", selected.contact_type === "buyer" ? "sale" : "rent");
                  if (selected.budget_min) p.set("budget_min", String(selected.budget_min));
                  if (selected.budget_max) p.set("budget_max", String(selected.budget_max));
                  router.push(`/client-match?${p.toString()}`);
                }}
                className="flex items-center justify-center gap-2 rounded-lg bg-accent/10 py-2 text-sm font-medium text-accent hover:bg-accent/20"
              >
                <Crosshair size={14} /> Find Matching Listings
              </button>
            )}

            {selected.properties && selected.properties.length > 0 && (
              <div>
                <p className="mb-2 text-xs font-medium text-muted uppercase">Properties</p>
                {selected.properties.map((p, i) => (
                  <div key={i} className="mb-2 rounded-lg border border-border bg-background p-3 text-xs">
                    <p className="font-medium text-foreground">{p.building_name} {p.unit_number && `#${p.unit_number}`}</p>
                    <p className="text-muted">{p.bedrooms != null ? (p.bedrooms === 0 ? "Studio" : `${p.bedrooms} BR`) : ""}{p.intent ? ` · ${p.intent}` : ""}{p.price_aed ? ` · ${formatAED(p.price_aed)}` : ""}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-muted">{label}</span>
      <span className="text-right text-foreground">{value}</span>
    </div>
  );
}
