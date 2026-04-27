/**
 * API client for ORVA FastAPI backend.
 */

// Default to empty (relative URLs) so fetches go through the current origin
// and nginx proxies /api/* to the API container. Set NEXT_PUBLIC_API_URL
// to "http://localhost:8000" only when running orva-web in dev against a
// local API without nginx in front.
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("orva_token");
}

export function setToken(token: string) {
  localStorage.setItem("orva_token", token);
}

export function clearToken() {
  localStorage.removeItem("orva_token");
}

export function isAuthenticated(): boolean {
  return !!getToken();
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined") {
      window.location.href = "/";
    }
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body}`);
  }

  if (res.headers.get("content-type")?.includes("text/csv")) {
    return (await res.text()) as unknown as T;
  }

  return res.json();
}

// --- Auth ---

export interface LoginResponse {
  token: string;
  name: string;
  username: string;
}

export async function login(
  username: string,
  password: string
): Promise<LoginResponse> {
  return request<LoginResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

// --- Leads ---

export interface LeadRecord {
  owner_name: string | null;
  phone: string | null;
  building_name: string | null;
  unit_number: string | null;
  bedrooms: number | null;
  size_sqft: number | null;
  floor: string | null;
  date: string | null;
  completeness: number | null;
  source: string | null;
  listing_type: string | null;
  transaction_value: number | null;
  bedroom_method: string | null;
  bedroom_confidence: string | null;
}

export interface LeadSearchResponse {
  leads: LeadRecord[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface LeadFilters {
  date_start?: string;
  date_end?: string;
  owner_name?: string;
  building_search?: string;
  bedrooms?: string;
  unit_number?: string;
  phone?: string;
  phone_required?: boolean;
  min_completeness?: number;
  min_size_sqft?: number;
  max_size_sqft?: number;
  hide_flagged?: boolean;
  source_filter?: string;
  sort_by?: string;
  page?: number;
  page_size?: number;
}

export async function searchLeads(
  filters: LeadFilters = {}
): Promise<LeadSearchResponse> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  return request<LeadSearchResponse>(`/api/leads?${params.toString()}`);
}

export interface BuildingListResponse {
  buildings: string[];
  count: number;
}

export async function getBuildings(): Promise<BuildingListResponse> {
  return request<BuildingListResponse>("/api/leads/buildings");
}

export async function exportLeads(filters: LeadFilters): Promise<string> {
  return request<string>("/api/leads/export", {
    method: "POST",
    body: JSON.stringify(filters),
  });
}

// --- Client Profile ---

export interface NoteRecord {
  id: string;
  text: string;
  timestamp: string;
  edited_at?: string | null;
}

export interface ReminderRecord {
  id: string;
  client_id: string;
  client_name: string;
  building: string;
  unit: string;
  phone: string;
  datetime: string;
  note: string;
  status: string;
  created_at: string;
  completed_at?: string | null;
}

export interface CallRecord {
  id: string;
  client_id: string;
  client_name: string;
  building: string;
  unit: string;
  phone: string;
  called_at: string;
  outcome: string;
  notes: string;
  reminder_dt?: string | null;
  reminder_note?: string | null;
}

export interface ClientProfile {
  client_id: string;
  owner_name: string | null;
  building_name: string | null;
  unit_number: string | null;
  bedrooms: number | null;
  size_sqft: number | null;
  phone: string | null;
  date: string | null;
  completeness: number | null;
  notes: NoteRecord[];
  reminders: ReminderRecord[];
  calls: CallRecord[];
  portfolio: {
    building_name: string | null;
    unit_number: string | null;
    bedrooms: number | null;
    size_sqft: number | null;
    date: string | null;
    transaction_value: number | null;
  }[];
}

export async function lookupClientId(
  owner_name: string,
  building_name: string,
  unit_number: string
): Promise<{ client_id: string }> {
  const params = new URLSearchParams({ owner_name, building_name, unit_number });
  return request<{ client_id: string }>(`/api/clients/lookup/id?${params}`);
}

export async function getClientProfile(clientId: string): Promise<ClientProfile> {
  return request<ClientProfile>(`/api/clients/${clientId}`);
}

// Notes
export async function addNote(clientId: string, text: string): Promise<void> {
  await request(`/api/clients/${clientId}/notes`, {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

export async function editNote(clientId: string, noteId: string, text: string): Promise<void> {
  await request(`/api/clients/${clientId}/notes/${noteId}`, {
    method: "PUT",
    body: JSON.stringify({ text }),
  });
}

export async function deleteNote(clientId: string, noteId: string): Promise<void> {
  await request(`/api/clients/${clientId}/notes/${noteId}`, {
    method: "DELETE",
  });
}

// Reminders
export async function getAllReminders(): Promise<ReminderRecord[]> {
  return request<ReminderRecord[]>("/api/clients/reminders/all");
}

export async function getReminderCount(): Promise<{ count: number }> {
  return request<{ count: number }>("/api/clients/reminders/count");
}

export async function addReminder(
  clientId: string,
  data: { client_name: string; building?: string; unit?: string; phone?: string; datetime: string; note: string }
): Promise<void> {
  await request(`/api/clients/${clientId}/reminders`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function markReminderDone(reminderId: string): Promise<void> {
  await request(`/api/clients/reminders/${reminderId}/done`, { method: "POST" });
}

export async function deleteReminder(reminderId: string): Promise<void> {
  await request(`/api/clients/reminders/${reminderId}`, { method: "DELETE" });
}

// Call Log
export async function getAllCalls(): Promise<CallRecord[]> {
  return request<CallRecord[]>("/api/clients/calls/all");
}

export async function logCall(
  clientId: string,
  data: {
    client_name: string;
    building?: string;
    unit?: string;
    phone?: string;
    outcome: string;
    notes?: string;
    reminder_dt?: string;
    reminder_note?: string;
  }
): Promise<void> {
  await request(`/api/clients/${clientId}/calls`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// --- WhatsApp ---

export interface WAStatus {
  connected: boolean;
  qr_available: boolean;
  phone: string | null;
  qr_b64: string | null;
  error?: string;
}

export interface QueueContact {
  phone: string;
  owner_name: string | null;
  building: string | null;
  unit: string | null;
  bedrooms: string | null;
  message_preview: string | null;
  template_type: string | null;
  is_portfolio: boolean;
}

export interface CampaignPreviewResponse {
  queue: QueueContact[];
  total: number;
}

export interface CampaignProgress {
  status: string;
  sent: number;
  failed: number;
  not_on_wa: number;
  skipped: number;
  total: number;
  current_contact: QueueContact | null;
  daily_cap: number;
  messages_today: number;
  elapsed_seconds: number;
  error: string | null;
}

export interface SendStats {
  today: { sent: number; failed: number; not_on_whatsapp: number; total: number; replies: number };
  week: { sent: number; failed: number; not_on_whatsapp: number; total: number; replies: number };
  all_time: { sent: number; failed: number; not_on_whatsapp: number; total: number; replies: number };
}

export interface MessageLogEntry {
  timestamp: string | null;
  campaign_id: string | null;
  wa_account: string | null;
  phone: string | null;
  owner_name: string | null;
  building: string | null;
  unit: string | null;
  template_type: string | null;
  message: string | null;
  status: string | null;
  error: string | null;
}

export async function getWAStatus(account: string): Promise<WAStatus> {
  return request<WAStatus>(`/api/whatsapp/status/${account}`);
}

export async function startLink(account: string, phone: string): Promise<void> {
  await request(`/api/whatsapp/link/start/${account}`, {
    method: "POST",
    body: JSON.stringify({ phone_number: phone }),
  });
}

export async function getLinkStatus(account: string): Promise<{ pending: boolean; link_code: string | null; error: string | null }> {
  return request(`/api/whatsapp/link/status/${account}`);
}

// Mirrors orva_api/schemas/whatsapp.py CampaignPreviewRequest. Keep in sync
// when backend fields change.
export interface CampaignPreviewParams {
  campaign_type: string;
  building?: string;
  bedrooms?: string;
  area?: string;
  days_ahead?: number;
  portfolio_only?: boolean;
  min_units?: number;
  limit?: number;
  lead_type?: string;
  not_yet_contacted?: boolean;
  custom_message?: string;
  account?: string;
}

// Mirrors orva_api/schemas/whatsapp.py CampaignStartRequest.
export interface CampaignStartParams extends CampaignPreviewParams {
  dry_run?: boolean;
  override_limit?: boolean;
  no_limits?: boolean;
  excluded_phones?: string[];
}

export async function previewCampaign(params: CampaignPreviewParams): Promise<CampaignPreviewResponse> {
  return request<CampaignPreviewResponse>("/api/whatsapp/campaign/preview", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function startCampaign(params: CampaignStartParams): Promise<void> {
  await request("/api/whatsapp/campaign/start", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function stopCampaign(): Promise<void> {
  await request("/api/whatsapp/campaign/stop", { method: "POST" });
}

export async function getCampaignStatus(): Promise<CampaignProgress> {
  return request<CampaignProgress>("/api/whatsapp/campaign/status");
}

export function subscribeCampaignProgress(onProgress: (p: CampaignProgress) => void): EventSource {
  const token = getToken();
  const url = `${API_BASE}/api/whatsapp/campaign/progress?token=${token}`;
  const es = new EventSource(url);
  es.onmessage = (ev) => {
    try {
      onProgress(JSON.parse(ev.data));
    } catch { /* ignore parse errors */ }
  };
  return es;
}

export async function getWAStats(): Promise<SendStats> {
  return request<SendStats>("/api/whatsapp/stats");
}

export async function getWAMessages(limit: number = 100, search?: string): Promise<{ messages: MessageLogEntry[]; total: number }> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (search) params.set("search", search);
  return request(`/api/whatsapp/messages?${params}`);
}

export async function exportWAMessages(): Promise<string> {
  return request<string>("/api/whatsapp/messages/export");
}

export async function markRestriction(): Promise<void> {
  await request("/api/whatsapp/restriction", { method: "POST" });
}

// --- Health ---

export interface HealthResponse {
  status: string;
  data_loaded: boolean;
  total_leads: number;
  total_buildings: number;
}

export async function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health");
}

// --- Chat (HLM Intelligence) ---

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
}

export interface ChatListItem {
  id: string;
  name: string;
  last_updated: string;
  message_count: number;
}

export async function getChatList(): Promise<ChatListItem[]> {
  const res = await request<{ chats: ChatListItem[] }>("/api/chat/list");
  return res.chats;
}

export async function getChatHistory(
  chatId: string
): Promise<{ chat_id: string; name: string; messages: ChatMessage[] }> {
  return request(`/api/chat/${chatId}/history`);
}

export async function createNewChat(): Promise<{ chat_id: string }> {
  return request("/api/chat/new", { method: "POST" });
}

export async function deleteChat(chatId: string): Promise<void> {
  await request(`/api/chat/${chatId}`, { method: "DELETE" });
}

/**
 * Send a message to HLM via SSE (POST-based streaming).
 * Returns an AbortController to cancel the request.
 */
export function sendChatMessage(
  message: string,
  chatId: string | null,
  onStatus: (text: string) => void,
  onDone: (content: string, chatId: string) => void,
  onError: (error: string) => void
): AbortController {
  const controller = new AbortController();
  const token = getToken();

  (async () => {
    try {
      const res = await fetch(`${API_BASE}/api/chat/send`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ message, chat_id: chatId }),
        signal: controller.signal,
      });

      if (res.status === 401) {
        clearToken();
        if (typeof window !== "undefined") window.location.reload();
        return;
      }

      if (!res.ok) {
        onError(`Server error (${res.status})`);
        return;
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === "status") {
              onStatus(event.text);
            } else if (event.type === "done") {
              onDone(event.content, event.chat_id);
            } else if (event.type === "error") {
              onError(event.text);
            }
          } catch {
            /* ignore parse errors */
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") return;
      onError("Connection lost. Please try again.");
    }
  })();

  return controller;
}

// --- Contacts ---

export const CONTACT_TYPES = [
  "Owner",
  "Buyer",
  "Investor",
  "Broker",
  "Tenant",
  "Other",
] as const;
export type ContactType = (typeof CONTACT_TYPES)[number];

export const INTENT_VALUES = [
  "selling",
  "renting",
  "buying",
  "renting_looking",
] as const;
export type Intent = (typeof INTENT_VALUES)[number];

export interface ContactRecord {
  id: number;
  full_name: string | null;
  phone: string | null;
  email: string | null;
  contact_type: string | null;
  source: string | null;
  budget_min: number | null;
  budget_max: number | null;
  agent_assigned: string | null;
  last_contact_date: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ContactProperty {
  id: number;
  contact_id: number;
  building_name: string | null;
  unit_number: string | null;
  bedrooms: string | null;
  bathrooms: string | null;
  price_aed: number | null;
  intent: string | null;
  view_type: string | null;
  notes: string | null;
  lead_id: number | null;
  is_scraped_listing: boolean;
  scraped_listing_url: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface LinkedLead {
  link_id: number;
  lead_id: number;
  match_confidence: number | null;
  match_method: string | null;
  building_name: string | null;
  unit_number: string | null;
  bedrooms: string | null;
  phone: string | null;
}

export interface ContactDetail extends ContactRecord {
  properties: ContactProperty[];
  linked_leads: LinkedLead[];
}

export interface ContactListResponse {
  contacts: ContactRecord[];
  total: number;
}

export interface CreateContactPayload {
  full_name?: string | null;
  phone?: string | null;
  email?: string | null;
  contact_type?: string | null;
  source?: string | null;
  budget_min?: number | null;
  budget_max?: number | null;
  agent_assigned?: string | null;
}

export type UpdateContactPayload = CreateContactPayload;

export interface ContactSearchParams {
  query?: string;
  contact_type?: string;
  agent_assigned?: string;
  limit?: number;
}

export interface AddPropertyPayload {
  building_name?: string | null;
  unit_number?: string | null;
  bedrooms?: string | null;
  bathrooms?: string | null;
  price_aed?: number | null;
  intent?: string | null;
  view_type?: string | null;
  notes?: string | null;
  lead_id?: number | null;
}

export type UpdatePropertyPayload = Omit<AddPropertyPayload, "lead_id">;

export interface ResolveUnitSpecsResponse {
  bedrooms: string | null;
  bathrooms: string | null;
  view_type: string | null;
}

// Accepts any plain object -- TypeScript interfaces (e.g. ContactSearchParams,
// BayutFilters) don't satisfy Record<string, ...> because of structural typing
// rules, so we accept `unknown` values and stringify defensively.
function buildQuery(params: Record<string, unknown>): string {
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null && v !== "",
  );
  if (entries.length === 0) return "";
  const sp = new URLSearchParams();
  for (const [k, v] of entries) sp.set(k, String(v));
  return `?${sp.toString()}`;
}

export async function listContacts(
  params: ContactSearchParams = {},
): Promise<ContactListResponse> {
  return request<ContactListResponse>(
    `/api/contacts${buildQuery({ ...params })}`,
  );
}

export async function getContact(contactId: number): Promise<ContactDetail> {
  return request<ContactDetail>(`/api/contacts/${contactId}`);
}

export async function createContact(
  payload: CreateContactPayload,
): Promise<ContactRecord> {
  return request<ContactRecord>(`/api/contacts`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateContact(
  contactId: number,
  payload: UpdateContactPayload,
): Promise<ContactRecord> {
  return request<ContactRecord>(`/api/contacts/${contactId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function deleteContact(contactId: number): Promise<void> {
  await request<void>(`/api/contacts/${contactId}`, { method: "DELETE" });
}

export async function addContactProperty(
  contactId: number,
  payload: AddPropertyPayload,
): Promise<ContactProperty> {
  return request<ContactProperty>(`/api/contacts/${contactId}/properties`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateContactProperty(
  contactId: number,
  propertyId: number,
  payload: UpdatePropertyPayload,
): Promise<ContactProperty> {
  return request<ContactProperty>(
    `/api/contacts/${contactId}/properties/${propertyId}`,
    { method: "PUT", body: JSON.stringify(payload) },
  );
}

export async function deleteContactProperty(
  contactId: number,
  propertyId: number,
): Promise<void> {
  await request<void>(`/api/contacts/${contactId}/properties/${propertyId}`, {
    method: "DELETE",
  });
}

export async function resolveUnitSpecs(
  contactId: number,
  buildingName: string,
  unitNumber: string,
): Promise<ResolveUnitSpecsResponse> {
  const qs = buildQuery({
    building_name: buildingName,
    unit_number: unitNumber,
  });
  return request<ResolveUnitSpecsResponse>(
    `/api/contacts/${contactId}/resolve-unit-specs${qs}`,
  );
}

// --- Lease expiry ---

export interface ExpiringLease {
  building_name: string | null;
  unit_number: string | null;
  bedrooms: string | null;
  size_sqft: number | null;
  contract_end: string | null;
  days_remaining: number | null;
  annual_rent: number | null;
  has_owner_contact: boolean;
  owner_name: string | null;
  owner_phone: string | null;
  owner_email: string | null;
}

export interface LeaseExpiryResponse {
  leases: ExpiringLease[];
  total: number;
  with_contact: number;
  active_rentals_total: number;
  unique_buildings: number;
  expiry_window_days: number;
}

export async function getLeaseExpiry(
  daysAhead: number,
  building?: string,
  bedrooms?: string,
): Promise<LeaseExpiryResponse> {
  const qs = buildQuery({ days_ahead: daysAhead, building, bedrooms });
  return request<LeaseExpiryResponse>(`/api/lease-expiry${qs}`);
}

// --- Listing matcher ---

export interface MatchedOwner {
  building: string;
  unit: string;
  size_sqft: number | null;
  beds: string | null;
  owner_name: string;
  phone: string;
  phone_display: string;
  email: string | null;
  transaction_date: string | null;
  transaction_value: number | null;
  confidence: number;
  match_type: string;
}

export interface MatchListingResponse {
  matches: MatchedOwner[];
  coverage: Record<string, unknown>;
}

export interface MatchListingPayload {
  building_name: string;
  unit_number?: string | null;
  size_sqft?: number | null;
  bedrooms?: string | null;
}

export async function matchListing(
  payload: MatchListingPayload,
): Promise<MatchListingResponse> {
  return request<MatchListingResponse>(`/api/match/listing`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// --- Bayut listings ---

export interface BayutListing {
  listing_url: string | null;
  listing_type: string | null;
  building_name: string | null;
  unit_number: string | null;
  bedrooms: string | null;
  bathrooms: string | null;
  size_sqft: number | null;
  price_aed: number | null;
  rent_period: string | null;
  view_type: string | null;
  agent_name: string | null;
  agency: string | null;
  listed_date: string | null;
  scraped_at: string | null;
}

export interface BuildingSummary {
  building_name: string;
  listings: number;
  avg_beds: number | null;
  avg_size: number | null;
  avg_price: number | null;
  types: string;
}

export interface BayutListingsResponse {
  listings: BayutListing[];
  total: number;
  sale_count: number;
  rent_count: number;
  unique_buildings: number;
  building_summary: BuildingSummary[];
  last_scraped: string | null;
}

export interface BayutFilters {
  listing_type?: string;
  building?: string;
  bedrooms?: string;
  price_min?: number;
  price_max?: number;
  limit?: number;
}

export async function getBayutListings(
  filters: BayutFilters = {},
): Promise<BayutListingsResponse> {
  return request<BayutListingsResponse>(
    `/api/bayut/listings${buildQuery({ ...filters })}`,
  );
}

// --- Client match ---

export interface OwnerMatchResult {
  client_id: string;
  owner_name: string | null;
  phone: string | null;
  building_name: string | null;
  unit_number: string | null;
  bedrooms: string | null;
  size_sqft: number | null;
  last_sale_price: number | null;
  last_sale_date: string | null;
  last_annual_rent: number | null;
  has_active_listing: boolean;
  active_listing_url: string | null;
  active_listing_price: number | null;
  score: number;
  score_factors: string[];
}

export interface ClientMatchResponse {
  matches: OwnerMatchResult[];
  total: number;
}

export interface ClientMatchPayload {
  transaction_type: "sale" | "rent";
  bedrooms?: string | null;
  buildings?: string[];
  sea_view_only?: boolean;
  budget_min?: number | null;
  budget_max?: number | null;
  limit?: number;
}

export async function findClientMatches(
  payload: ClientMatchPayload,
): Promise<ClientMatchResponse> {
  return request<ClientMatchResponse>(`/api/client-match`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// --- Admin: health + PF scraper ---

export interface FileInfo {
  present: boolean;
  size_mb: number | null;
  modified: string | null;
}

export interface HealthCheckResponse {
  lead_database: {
    xlsx: FileInfo;
    csv: FileInfo;
    csv_rows: number | null;
  };
  reference_data: {
    reference_master: FileInfo;
    reference_master_with_units: FileInfo;
    reference_master_rows: number | null;
  };
  reidin: { parquet: FileInfo; csv: FileInfo };
  public_scrapers: {
    bayut_listings: FileInfo;
    bayut_rows: number | null;
    pf_listings: FileInfo;
    pf_rows: number | null;
  };
  sqlite: {
    initialized: boolean;
    path: string;
    size_mb: number | null;
    table_counts: Record<string, number>;
  };
  environment: {
    anthropic_api_key_set: boolean;
    anthropic_api_key_preview: string | null;
    jwt_secret_set: boolean;
    jwt_secret_strong: boolean;
    claude_model: string;
    log_level: string;
  };
  modules: Record<string, boolean>;
  building_intelligence: {
    loaded: boolean;
    shoreline_towers?: number;
    building_aliases?: number;
    error?: string;
  };
  overall: { status: "ok" | "degraded"; checked_at: string };
}

export async function getHealthCheck(): Promise<HealthCheckResponse> {
  return request<HealthCheckResponse>(`/api/admin/health`);
}

export interface PfLeadsResponse {
  rows: Record<string, string>[];
  total: number;
  columns?: string[];
  last_scraped: string | null;
  csv_path: string;
  csv_present: boolean;
}

export async function getPfLeads(limit = 200): Promise<PfLeadsResponse> {
  return request<PfLeadsResponse>(`/api/admin/pf-leads?limit=${limit}`);
}
