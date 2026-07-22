export type RequirementStatus = "DRAFT" | "PENDING_APPROVAL" | "CANCELLED" | string;

export interface CurrentUser {
  account_id: number; employee_id: number; employee_no: string; name: string;
  phone: string | null; roles: string[]; building_ids: number[]; must_change_password: boolean;
}

export interface Applicant { employee_no: string | null; name: string; phone: string | null; }
export interface RequirementFormValues {
  category_name?: string; application_reason?: string; application_location?: string;
  device_type?: string; product_name?: string; product_full_name?: string;
  brand?: string; model?: string; specification?: string; quantity?: number;
  unit?: string; supplier_name?: string; unit_price?: number; currency?: string;
}
export interface RequirementDetail {
  requirement_id: number; requirement_no: string; status: RequirementStatus; version: number;
  applicant: Applicant; session_id: string | null; category_id: number | null;
  category_name: string | null; application_reason: string | null;
  application_location: string | null; device_type: string | null; product_id: number | null;
  product_name: string | null; product_full_name: string | null; brand: string | null;
  model: string | null; specification: string | null; quantity: string | null;
  unit: string | null; supplier_id: number | null; supplier_name: string | null;
  unit_price: string | null; total_amount: string | null; currency: string;
  new_product: boolean; new_supplier: boolean; missing_fields: string[];
  conflicts: Array<{ field: string; message: string }>;
  warnings: Array<{ code: string; message: string }>;
  requested_at: string | null; submitted_at: string | null; updated_at: string;
}
export interface RequirementSummary {
  requirement_id: number; requirement_no: string; product_name: string | null;
  status: RequirementStatus; total_amount: string | null; currency: string;
  updated_at: string; version: number;
}
export interface Recommendation {
  rank: number; match_score: string; matched_fields: string[]; supplier_id: number | null;
  supplier_name: string; historical_order_count: number;
  latest_purchase: {
    requirement_id: number; requirement_no: string; order_id: number; order_no: string;
    product_name: string | null; brand: string | null; model: string | null;
    quantity: string; unit: string | null; unit_price: string | null; currency: string;
    purchased_at: string | null; received_at: string | null; status: string;
  };
  reason: string; warnings: string[];
}
export interface RecommendationResult {
  query_summary: string; result_code: "OK" | "NO_HISTORY_MATCH";
  recommendations: Recommendation[];
}
