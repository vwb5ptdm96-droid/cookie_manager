import { apiRequest } from "@/api/http";

export interface RepairTicketItem {
  ticket_code: string;
  task_code: string;
  task_name: string;
  profile_key: string;
  profile_path: string;
  risk_type: string;
  risk_message: string;
  status: string;
  repaired_by: string | null;
  browser_artifact_dir: string | null;
  browser_opened_at: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string | null;
}

interface RepairTicketListResponse {
  items: RepairTicketItem[];
}

interface RepairActionPayload {
  repaired_by: string | null;
}

export function fetchRepairTickets(): Promise<RepairTicketListResponse> {
  return apiRequest<RepairTicketListResponse>("/repairs");
}

export function openRepairBrowser(ticketCode: string, repairedBy: string | null): Promise<RepairTicketItem> {
  return apiRequest<RepairTicketItem>(`/repairs/${ticketCode}/open`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repaired_by: repairedBy } satisfies RepairActionPayload),
  });
}

export function verifyRepairTicket(ticketCode: string, repairedBy: string | null): Promise<RepairTicketItem> {
  return apiRequest<RepairTicketItem>(`/repairs/${ticketCode}/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repaired_by: repairedBy } satisfies RepairActionPayload),
  });
}

export function closeRepairTicket(ticketCode: string, repairedBy: string | null): Promise<RepairTicketItem> {
  return apiRequest<RepairTicketItem>(`/repairs/${ticketCode}/close`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repaired_by: repairedBy } satisfies RepairActionPayload),
  });
}
