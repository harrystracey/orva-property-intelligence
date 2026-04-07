/**
 * API client for ORVA FastAPI backend.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
      window.location.reload();
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
  rental_status: string | null;
  lease_end: string | null;
  annual_rent: number | null;
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

export async function previewCampaign(params: Record<string, unknown>): Promise<CampaignPreviewResponse> {
  return request<CampaignPreviewResponse>("/api/whatsapp/campaign/preview", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function startCampaign(params: Record<string, unknown>): Promise<void> {
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

// --- Chat (HLM) ---

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatResponse {
  response: string;
  tool_calls: number;
}

export async function sendChatMessage(
  message: string,
  history: ChatMessage[] = []
): Promise<ChatResponse> {
  return request<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify({ message, history }),
  });
}

// --- Reidin ---

export interface ReidinFileInfo {
  exists: boolean;
  rows: number;
  buildings: number;
  last_modified: string | null;
}

export interface ReidinStatus {
  sales: ReidinFileInfo;
  rentals: ReidinFileInfo;
}

export interface ReidinUploadResult {
  rows_in: number;
  rows_out: number;
  buildings: number;
  output_path: string | null;
  warnings: string[];
}

export async function getReidinStatus(): Promise<ReidinStatus> {
  return request<ReidinStatus>("/api/reidin/status");
}

export async function uploadReidinCSV(
  file: File,
  dataType: "sales" | "rentals"
): Promise<ReidinUploadResult> {
  const token = getToken();
  const formData = new FormData();
  formData.append("file", file);
  formData.append("data_type", dataType);

  const res = await fetch(`${API_BASE}/api/reidin/upload`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });

  if (res.status === 401) {
    clearToken();
    window.location.reload();
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Upload failed: ${body}`);
  }
  return res.json();
}

// --- Vacancy Intelligence ---

export interface ExpiringUnit {
  building_name: string;
  unit_number: string;
  bedrooms: string;
  floor: string;
  view: string;
  size_sqft: number | null;
  contract_end: string | null;
  contract_start: string | null;
  days_left: number;
  annual_rent: number | null;
  rent_type: string;
  parking: string;
  owner_name: string;
  phone: string;
  email: string;
  source: string;
  building_contacts: number;
}

export interface ExpiringSummary {
  expiring_30: number;
  expiring_60: number;
  expiring_90: number;
  vacant?: number;
  total_active?: number;
}

export interface ExpiringUnitsResponse {
  units: ExpiringUnit[];
  total: number;
  with_contact: number;
  summary: ExpiringSummary;
  sources: string[];
  buildings: string[];
}

export interface ExpiringFilters {
  days?: number;
  building?: string;
  bedrooms?: string;
  has_contact?: boolean;
}

export async function getExpiringUnits(
  filters: ExpiringFilters = {}
): Promise<ExpiringUnitsResponse> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  return request<ExpiringUnitsResponse>(`/api/reidin/expiring?${params.toString()}`);
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
