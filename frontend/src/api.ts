import type { RecommendationResult, RequirementDetail, RequirementFormValues, RequirementSummary } from "./types";

interface SuccessResponse<T> { data: T; meta: { request_id: string }; }
interface PageResponse<T> extends SuccessResponse<T[]> { page: { number: number; size: number; total: number }; }

const errorMessages: Record<string, string> = {
  VALIDATION_ERROR: "填写内容不符合要求，请检查输入内容。",
  NOT_FOUND: "没有找到这张采购申请。",
  FORBIDDEN: "你没有权限操作这张采购申请。",
  CONFLICT: "数据已被更新，请刷新后重试。",
  INVALID_STATE: "当前状态不允许执行此操作。",
  IDEMPOTENCY_CONFLICT: "本次操作标识已被用于其他请求，请重试。",
};

function operationKey() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

async function request<T>(path: string, employeeCode: string, options: RequestInit = {}, isWrite = false): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...options,
      headers: {
        "Content-Type": "application/json", "X-User-Code": employeeCode,
        ...(isWrite ? { "Idempotency-Key": operationKey() } : {}), ...options.headers,
      },
    });
  } catch {
    throw new Error("无法连接后端服务，请确认 8000 端口的后端已经启动。");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const code = body?.error?.code as string | undefined;
    throw new Error(errorMessages[code ?? ""] ?? body?.error?.message ?? "操作失败，请稍后重试。");
  }
  return body as T;
}

function draftPayload(values: RequirementFormValues) {
  return {
    session_id: null, category_id: null, category_name: values.category_name || null,
    application_reason: values.application_reason || null,
    application_location: values.application_location || null,
    device_type: values.device_type || null, product_id: null,
    product_name: values.product_name || null, product_full_name: values.product_full_name || null,
    brand: values.brand || null, model: values.model || null,
    specification: values.specification || null,
    quantity: values.quantity == null ? null : values.quantity.toFixed(0),
    unit: values.unit || null, supplier_id: null, supplier_name: values.supplier_name || null,
    unit_price: values.unit_price == null ? null : values.unit_price.toFixed(2),
    currency: values.currency || "CNY",
  };
}

export const api = {
  async createDraft(employeeCode: string, values: RequirementFormValues) {
    const result = await request<SuccessResponse<RequirementDetail>>("/api/v1/purchase-requirements/drafts", employeeCode,
      { method: "POST", body: JSON.stringify(draftPayload(values)) }, true);
    return result.data;
  },
  async updateDraft(employeeCode: string, current: RequirementDetail, values: RequirementFormValues) {
    const result = await request<SuccessResponse<RequirementDetail>>(`/api/v1/purchase-requirements/${current.requirement_id}`, employeeCode,
      { method: "PATCH", body: JSON.stringify({ ...draftPayload(values), version: current.version }) }, true);
    return result.data;
  },
  async getDetail(employeeCode: string, requirementId: number) {
    return (await request<SuccessResponse<RequirementDetail>>(`/api/v1/purchase-requirements/${requirementId}`, employeeCode)).data;
  },
  async listMine(employeeCode: string, page = 1, pageSize = 20) {
    return request<PageResponse<RequirementSummary>>(`/api/v1/purchase-requirements?mine=true&page=${page}&page_size=${pageSize}`, employeeCode);
  },
  async submit(employeeCode: string, current: RequirementDetail) {
    return (await request<SuccessResponse<{ status: string; version: number }>>(
      `/api/v1/purchase-requirements/${current.requirement_id}/submit`, employeeCode,
      { method: "POST", body: JSON.stringify({ version: current.version, confirmed: true }) }, true)).data;
  },
  async cancel(employeeCode: string, current: RequirementDetail, reason: string) {
    return (await request<SuccessResponse<RequirementDetail>>(
      `/api/v1/purchase-requirements/${current.requirement_id}/cancel`, employeeCode,
      { method: "POST", body: JSON.stringify({ version: current.version, confirmed: true, reason }) }, true)).data;
  },
  async recommendations(employeeCode: string, current: RequirementDetail) {
    return (await request<SuccessResponse<RecommendationResult>>("/api/v1/recommendations/historical-suppliers/search", employeeCode, {
      method: "POST", body: JSON.stringify({
        requirement_id: current.requirement_id, product_id: current.product_id,
        device_type: current.device_type, product_name: current.product_name,
        product_full_name: current.product_full_name, brand: current.brand, model: current.model,
        specification: current.specification, application_location: current.application_location, limit: 5,
      }),
    })).data;
  },
};
