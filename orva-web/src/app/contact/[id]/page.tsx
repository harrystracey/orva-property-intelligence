"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  User,
  Phone,
  Mail,
  Edit2,
  Trash2,
  Plus,
  Building2,
  Save,
  X,
  Link as LinkIcon,
} from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import {
  getContact,
  updateContact,
  deleteContact,
  addContactProperty,
  deleteContactProperty,
  resolveUnitSpecs,
  CONTACT_TYPES,
  INTENT_VALUES,
  ContactDetail,
  ContactProperty,
  LinkedLead,
} from "@/lib/api";

function fmtBudget(min: number | null, max: number | null): string {
  if (min == null && max == null) return "--";
  if (min != null && max != null)
    return `${min.toLocaleString()} - ${max.toLocaleString()} AED`;
  if (min != null) return `${min.toLocaleString()}+ AED`;
  return `<= ${max!.toLocaleString()} AED`;
}

export default function ContactDetailPage() {
  const params = useParams<{ id: string }>();
  const contactId = Number(params.id);
  const router = useRouter();
  const { authenticated } = useAuth();

  const [contact, setContact] = useState<ContactDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);

  const refresh = useCallback(async () => {
    if (Number.isNaN(contactId)) {
      setError("Invalid contact id");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      setContact(await getContact(contactId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load contact");
    } finally {
      setLoading(false);
    }
  }, [contactId]);

  useEffect(() => {
    if (authenticated) refresh();
  }, [authenticated, refresh]);

  if (!authenticated) {
    router.replace("/");
    return null;
  }

  const handleDelete = async () => {
    if (!contact) return;
    if (!confirm(`Delete ${contact.full_name || "this contact"}? This cannot be undone.`))
      return;
    try {
      await deleteContact(contact.id);
      router.push("/contacts");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete contact");
    }
  };

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-mobile-nav max-w-4xl mx-auto w-full">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <button
          onClick={() => router.push("/contacts")}
          className="flex items-center gap-1 rounded-lg border border-border bg-card px-3 py-1.5 text-sm text-foreground hover:bg-card-hover"
        >
          <ArrowLeft size={14} />
          Back
        </button>
        <div className="flex items-center gap-2">
          <User size={20} className="text-accent" />
          <h1 className="text-lg font-semibold text-foreground truncate">
            {contact?.full_name || "Contact"}
          </h1>
        </div>
        <div className="flex items-center gap-1">
          {contact && !editing && (
            <button
              onClick={() => setEditing(true)}
              className="flex items-center gap-1 rounded-lg border border-border bg-card px-3 py-1.5 text-sm text-foreground hover:bg-card-hover"
            >
              <Edit2 size={14} />
              Edit
            </button>
          )}
          {contact && (
            <button
              onClick={handleDelete}
              className="flex items-center gap-1 rounded-lg border border-danger/30 bg-card px-3 py-1.5 text-sm text-danger hover:bg-danger/10"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-2 text-sm text-danger">
          {error}
        </div>
      )}

      {loading ? (
        <div className="rounded-xl border border-border bg-card p-8 text-center text-muted">
          Loading…
        </div>
      ) : !contact ? null : editing ? (
        <ContactEditForm
          contact={contact}
          onSave={async () => {
            setEditing(false);
            await refresh();
          }}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <ContactInfoCard contact={contact} />
      )}

      {contact && !editing && (
        <>
          <PropertiesSection contact={contact} onChange={refresh} />
          <LinkedLeadsSection linkedLeads={contact.linked_leads} />
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------

function ContactInfoCard({ contact }: { contact: ContactDetail }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <h2 className="mb-3 text-sm font-semibold text-foreground">
        Contact info
      </h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <InfoRow label="Phone" value={contact.phone} icon={<Phone size={12} />} />
        <InfoRow label="Email" value={contact.email} icon={<Mail size={12} />} />
        <InfoRow label="Type" value={contact.contact_type} />
        <InfoRow label="Source" value={contact.source} />
        <InfoRow
          label="Budget"
          value={fmtBudget(contact.budget_min, contact.budget_max)}
        />
        <InfoRow label="Agent" value={contact.agent_assigned} />
        <InfoRow
          label="Last contact"
          value={contact.last_contact_date?.slice(0, 10)}
        />
      </div>
    </div>
  );
}

function InfoRow({
  label,
  value,
  icon,
}: {
  label: string;
  value: string | null | undefined;
  icon?: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="text-xs text-muted whitespace-nowrap flex items-center gap-1">
        {icon}
        {label}:
      </span>
      <span className="text-sm text-foreground truncate">
        {value || "--"}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------

function ContactEditForm({
  contact,
  onSave,
  onCancel,
}: {
  contact: ContactDetail;
  onSave: () => Promise<void>;
  onCancel: () => void;
}) {
  const [fullName, setFullName] = useState(contact.full_name ?? "");
  const [phone, setPhone] = useState(contact.phone ?? "");
  const [email, setEmail] = useState(contact.email ?? "");
  const [contactType, setContactType] = useState(contact.contact_type ?? "");
  const [source, setSource] = useState(contact.source ?? "");
  const [budgetMin, setBudgetMin] = useState(
    contact.budget_min != null ? String(contact.budget_min) : "",
  );
  const [budgetMax, setBudgetMax] = useState(
    contact.budget_max != null ? String(contact.budget_max) : "",
  );
  const [agent, setAgent] = useState(contact.agent_assigned ?? "");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setErr("");
    try {
      await updateContact(contact.id, {
        full_name: fullName || null,
        phone: phone || null,
        email: email || null,
        contact_type: contactType || null,
        source: source || null,
        budget_min: budgetMin ? Number(budgetMin) : null,
        budget_max: budgetMax ? Number(budgetMax) : null,
        agent_assigned: agent || null,
      });
      await onSave();
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      onSubmit={handleSave}
      className="rounded-xl border border-border bg-card p-4 flex flex-col gap-3"
    >
      <h2 className="text-sm font-semibold text-foreground">Edit contact</h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Full name" value={fullName} onChange={setFullName} />
        <Field label="Phone" value={phone} onChange={setPhone} />
        <Field label="Email" value={email} onChange={setEmail} />
        <FieldSelect
          label="Type"
          value={contactType}
          onChange={setContactType}
          options={["", ...CONTACT_TYPES]}
        />
        <Field label="Source" value={source} onChange={setSource} />
        <Field label="Agent" value={agent} onChange={setAgent} />
        <Field
          label="Budget min (AED)"
          value={budgetMin}
          onChange={setBudgetMin}
          type="number"
        />
        <Field
          label="Budget max (AED)"
          value={budgetMax}
          onChange={setBudgetMax}
          type="number"
        />
      </div>

      {err && (
        <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
          {err}
        </div>
      )}

      <div className="flex gap-2">
        <button
          type="button"
          disabled={saving}
          onClick={onCancel}
          className="flex flex-1 items-center justify-center gap-1 rounded-lg border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-card-hover disabled:opacity-50"
        >
          <X size={14} />
          Cancel
        </button>
        <button
          type="submit"
          disabled={saving}
          className="flex flex-1 items-center justify-center gap-1 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-background disabled:opacity-50"
        >
          <Save size={14} />
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </form>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
}) {
  return (
    <div>
      <label className="text-xs text-muted">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
      />
    </div>
  );
}

function FieldSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: readonly string[];
}) {
  return (
    <div>
      <label className="text-xs text-muted">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o || "--"}
          </option>
        ))}
      </select>
    </div>
  );
}

// ---------------------------------------------------------------------------

function PropertiesSection({
  contact,
  onChange,
}: {
  contact: ContactDetail;
  onChange: () => Promise<void>;
}) {
  const [showAdd, setShowAdd] = useState(false);

  const handleDelete = async (propId: number) => {
    if (!confirm("Remove this property?")) return;
    await deleteContactProperty(contact.id, propId);
    await onChange();
  };

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">Properties</h2>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-1 rounded-lg bg-accent/15 px-2.5 py-1 text-xs font-medium text-accent hover:bg-accent/25"
        >
          <Plus size={12} />
          Add
        </button>
      </div>

      {contact.properties.length === 0 && !showAdd ? (
        <p className="text-sm text-muted">No properties added yet.</p>
      ) : (
        <div className="flex flex-col gap-2">
          {contact.properties.map((p) => (
            <PropertyCard key={p.id} property={p} onDelete={() => handleDelete(p.id)} />
          ))}
        </div>
      )}

      {showAdd && (
        <AddPropertyForm
          contactId={contact.id}
          onCancel={() => setShowAdd(false)}
          onSaved={async () => {
            setShowAdd(false);
            await onChange();
          }}
        />
      )}
    </div>
  );
}

function PropertyCard({
  property,
  onDelete,
}: {
  property: ContactProperty;
  onDelete: () => void;
}) {
  return (
    <div className="rounded-lg border border-border bg-background p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Building2 size={12} className="text-accent" />
            <span className="text-sm font-medium text-foreground truncate">
              {property.building_name || "(no building)"}
            </span>
            {property.unit_number && (
              <span className="text-xs text-muted">/ {property.unit_number}</span>
            )}
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted">
            {property.bedrooms && <span>{property.bedrooms} BR</span>}
            {property.bathrooms && <span>{property.bathrooms} bath</span>}
            {property.price_aed && (
              <span>{Number(property.price_aed).toLocaleString()} AED</span>
            )}
            {property.intent && <span>Intent: {property.intent}</span>}
            {property.view_type && <span>{property.view_type}</span>}
          </div>
          {property.is_scraped_listing && property.scraped_listing_url && (
            <a
              href={property.scraped_listing_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1 inline-flex items-center gap-1 text-[11px] text-accent hover:underline"
            >
              <LinkIcon size={10} />
              View listing
            </a>
          )}
          {property.notes && (
            <p className="mt-1 text-xs text-muted italic">{property.notes}</p>
          )}
        </div>
        <button
          onClick={onDelete}
          className="rounded p-1.5 text-muted hover:text-danger"
          title="Remove"
        >
          <Trash2 size={12} />
        </button>
      </div>
    </div>
  );
}

function AddPropertyForm({
  contactId,
  onCancel,
  onSaved,
}: {
  contactId: number;
  onCancel: () => void;
  onSaved: () => Promise<void>;
}) {
  const [building, setBuilding] = useState("");
  const [unit, setUnit] = useState("");
  const [beds, setBeds] = useState("");
  const [baths, setBaths] = useState("");
  const [price, setPrice] = useState("");
  const [intent, setIntent] = useState("");
  const [view, setView] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  const handleResolve = async () => {
    if (!building.trim() || !unit.trim()) return;
    try {
      const res = await resolveUnitSpecs(contactId, building, unit);
      if (res.bedrooms && !beds) setBeds(res.bedrooms);
      if (res.bathrooms && !baths) setBaths(res.bathrooms);
      if (res.view_type && !view) setView(res.view_type);
    } catch {
      // fall through silently -- resolution is best-effort
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setErr("");
    try {
      await addContactProperty(contactId, {
        building_name: building || null,
        unit_number: unit || null,
        bedrooms: beds || null,
        bathrooms: baths || null,
        price_aed: price ? Number(price) : null,
        intent: intent || null,
        view_type: view || null,
        notes: notes || null,
      });
      await onSaved();
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : "Failed to add property");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-3 rounded-lg border border-accent/30 bg-background p-3 flex flex-col gap-2"
    >
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Field label="Building" value={building} onChange={setBuilding} />
        <Field label="Unit number" value={unit} onChange={setUnit} />
        <Field label="Bedrooms" value={beds} onChange={setBeds} />
        <Field label="Bathrooms" value={baths} onChange={setBaths} />
        <Field
          label="Price (AED)"
          value={price}
          onChange={setPrice}
          type="number"
        />
        <FieldSelect
          label="Intent"
          value={intent}
          onChange={setIntent}
          options={["", ...INTENT_VALUES]}
        />
        <Field label="View" value={view} onChange={setView} />
        <Field label="Notes" value={notes} onChange={setNotes} />
      </div>

      {err && (
        <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
          {err}
        </div>
      )}

      <div className="flex gap-2">
        <button
          type="button"
          onClick={handleResolve}
          disabled={!building.trim() || !unit.trim()}
          className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted hover:text-foreground disabled:opacity-50"
        >
          Auto-fill BR/Bath/View
        </button>
        <div className="flex-1" />
        <button
          type="button"
          disabled={saving}
          onClick={onCancel}
          className="rounded-lg border border-border bg-background px-3 py-1.5 text-xs text-foreground hover:bg-card-hover disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={saving}
          className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-background disabled:opacity-50"
        >
          {saving ? "Adding…" : "Add property"}
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------

function LinkedLeadsSection({ linkedLeads }: { linkedLeads: LinkedLead[] }) {
  if (linkedLeads.length === 0) return null;
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <h2 className="mb-3 text-sm font-semibold text-foreground">
        Linked portfolio (from leads database)
      </h2>
      <div className="flex flex-col gap-1.5">
        {linkedLeads.map((l) => (
          <div
            key={l.link_id}
            className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
          >
            <span className="font-medium">{l.building_name || "--"}</span>
            {l.unit_number && (
              <span className="text-muted">  /  {l.unit_number}</span>
            )}
            {l.bedrooms && (
              <span className="text-muted">  /  {l.bedrooms} BR</span>
            )}
            {l.phone && (
              <span className="text-muted">  /  {l.phone}</span>
            )}
            {l.match_method && (
              <span className="ml-2 rounded-full bg-accent/10 px-2 py-0.5 text-[10px] text-accent">
                {l.match_method}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
