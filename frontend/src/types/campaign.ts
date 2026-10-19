export interface Campaign {
  id: string;
  name: string;
  type: string;
  description?: string;
  status: "draft" | "active" | "completed";
  created_at: string;
}

export interface CampaignEmail {
  id: number;
  campaign_id: string;
  customer_id?: number;
  email: string;
  subject: string;
  body: string;
  sent_at: string;
  status: string;
  opened: boolean;
}

export interface CampaignRecipient {
  recipient_id: string;
  campaign_id: string;
  org_id: string;
  customer_name?: string | null;
  customer_email: string;
  subject?: string | null;
  body?: string | null;
  recommended_products: Array<Record<string, unknown>>;
  status: "pending" | "sent" | "failed";
  sent_at?: string | null;
  created_at?: string | null;
}
