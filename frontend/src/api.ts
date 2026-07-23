import type { AgentChatMessage, AgentMessageResult, ApprovalTask, BuildingOption, CurrentUser, ProcurementTask, RecommendationResult, RequirementDetail, RequirementFormValues, RequirementSummary } from "./types";

interface SuccessResponse<T> { data: T; meta: { request_id: string }; }
interface PageResponse<T> extends SuccessResponse<T[]> { page: { number: number; size: number; total: number }; }

const errorMessages: Record<string, string> = {
  UNAUTHENTICATED: "登录已失效，请重新登录。",
  VALIDATION_ERROR: "填写内容不符合要求，请检查输入内容。",
  NOT_FOUND: "没有找到这张采购申请。",
  FORBIDDEN: "你没有权限操作这张采购申请。",
  CONFLICT: "数据已被更新，请刷新后重试。",
  INVALID_STATE: "当前状态不允许执行此操作。",
  IDEMPOTENCY_CONFLICT: "本次操作标识已被用于其他请求，请重试。",
};

export class ApiError extends Error {
  constructor(message: string, public status: number, public code?: string) { super(message); }
}

function operationKey() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

async function request<T>(path: string, options: RequestInit = {}, isWrite = false): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...options,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(isWrite ? { "Idempotency-Key": operationKey() } : {}), ...options.headers,
      },
    });
  } catch {
    throw new Error("无法连接后端服务，请确认 8000 端口的后端已经启动。");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const code = body?.error?.code as string | undefined;
    throw new ApiError(errorMessages[code ?? ""] ?? body?.error?.message ?? "操作失败，请稍后重试。", response.status, code);
  }
  return body as T;
}

function draftPayload(values: RequirementFormValues) {
  return {
    session_id: null, application_reason: values.application_reason || null,
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
  async login(identifier: string, password: string) {
    return (await request<SuccessResponse<{ user: CurrentUser }>>("/api/v1/auth/login", {
      method: "POST", body: JSON.stringify({ identifier, password }),
    })).data.user;
  },
  async me() {
    return (await request<SuccessResponse<CurrentUser>>("/api/v1/auth/me")).data;
  },
  async logout() {
    await request<SuccessResponse<{ message: string }>>("/api/v1/auth/logout", { method: "POST" });
  },
  async changePassword(currentPassword: string, newPassword: string) {
    await request<SuccessResponse<{ message: string }>>("/api/v1/auth/change-password", {
      method: "POST", body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
  },
  async listBuildings() {
    return (await request<SuccessResponse<BuildingOption[]>>("/api/v1/buildings")).data;
  },
  async listApprovalTasks(view: "pending" | "history" = "pending", page = 1, pageSize = 20) {
    return request<PageResponse<ApprovalTask>>(`/api/v1/approvals/tasks?view=${view}&page=${page}&page_size=${pageSize}`);
  },
  async approvalDecision(task: ApprovalTask, action: "APPROVED" | "REJECTED", comment?: string) {
    return (await request<SuccessResponse<{ status: string; version: number }>>(
      `/api/v1/approvals/tasks/${task.requirement_id}/decision`,
      { method: "POST", body: JSON.stringify({ version: task.version, action, comment: comment || null }) }, true)).data;
  },
  async listProcurementTasks(page = 1, pageSize = 20) {
    return request<PageResponse<ProcurementTask>>(`/api/v1/procurement/tasks?page=${page}&page_size=${pageSize}`);
  },
  async startProcurement(task: ProcurementTask) {
    return (await request<SuccessResponse<ProcurementTask>>(
      `/api/v1/procurement/requirements/${task.requirement_id}/start`,
      { method: "POST", body: JSON.stringify({ version: task.requirement_version }) }, true)).data;
  },
  async advanceProcurement(task: ProcurementTask, targetStatus: "QUOTED" | "CONTRACTED") {
    return (await request<SuccessResponse<ProcurementTask>>(
      `/api/v1/procurement/orders/${task.order_id}/advance`,
      { method: "POST", body: JSON.stringify({ version: task.order_version, target_status: targetStatus, remark: null }) }, true)).data;
  },
  async completeProcurement(task: ProcurementTask, remark?: string) {
    return (await request<SuccessResponse<ProcurementTask>>(
      `/api/v1/procurement/orders/${task.order_id}/complete`,
      { method: "POST", body: JSON.stringify({ version: task.order_version, remark: remark || null }) }, true)).data;
  },
  async rollbackProcurement(task: ProcurementTask) {
    return (await request<SuccessResponse<ProcurementTask>>(
      `/api/v1/procurement/orders/${task.order_id}/rollback`,
      { method: "POST", body: JSON.stringify({ version: task.order_version }) }, true)).data;
  },
  async createDraft(employeeCode: string, values: RequirementFormValues) {
    void employeeCode;
    const result = await request<SuccessResponse<RequirementDetail>>("/api/v1/purchase-requirements/drafts",
      { method: "POST", body: JSON.stringify(draftPayload(values)) }, true);
    return result.data;
  },
  async updateDraft(employeeCode: string, current: RequirementDetail, values: RequirementFormValues) {
    void employeeCode;
    const result = await request<SuccessResponse<RequirementDetail>>(`/api/v1/purchase-requirements/${current.requirement_id}`,
      { method: "PATCH", body: JSON.stringify({ ...draftPayload(values), version: current.version }) }, true);
    return result.data;
  },
  async getDetail(employeeCode: string, requirementId: number) {
    void employeeCode;
    return (await request<SuccessResponse<RequirementDetail>>(`/api/v1/purchase-requirements/${requirementId}`)).data;
  },
  async listMine(employeeCode: string, page = 1, pageSize = 20) {
    void employeeCode;
    return request<PageResponse<RequirementSummary>>(`/api/v1/purchase-requirements?mine=true&page=${page}&page_size=${pageSize}`);
  },
  async submit(employeeCode: string, current: RequirementDetail) {
    void employeeCode;
    return (await request<SuccessResponse<{ status: string; version: number }>>(
      `/api/v1/purchase-requirements/${current.requirement_id}/submit`,
      { method: "POST", body: JSON.stringify({ version: current.version, confirmed: true }) }, true)).data;
  },
  async cancel(employeeCode: string, current: RequirementDetail, reason: string) {
    void employeeCode;
    return (await request<SuccessResponse<RequirementDetail>>(
      `/api/v1/purchase-requirements/${current.requirement_id}/cancel`,
      { method: "POST", body: JSON.stringify({ version: current.version, confirmed: true, reason }) }, true)).data;
  },
  async revise(employeeCode: string, current: RequirementDetail) {
    void employeeCode;
    return (await request<SuccessResponse<RequirementDetail>>(
      `/api/v1/purchase-requirements/${current.requirement_id}/revise`,
      { method: "POST", body: JSON.stringify({ version: current.version, confirmed: true }) }, true)).data;
  },
  async recommendations(employeeCode: string, current: RequirementDetail) {
    void employeeCode;
    return (await request<SuccessResponse<RecommendationResult>>("/api/v1/recommendations/historical-suppliers/search", {
      method: "POST", body: JSON.stringify({
        requirement_id: current.requirement_id, product_id: current.product_id,
        device_type: current.device_type, product_name: current.product_name,
        product_full_name: current.product_full_name, brand: current.brand, model: current.model,
        specification: current.specification, application_location: current.application_location, limit: 5,
      }),
    })).data;
  },
  async sendAgentMessage(conversationId: string, content: string) {
    return (await request<SuccessResponse<AgentMessageResult>>("/api/v1/agent/messages", {
      method: "POST",
      body: JSON.stringify({
        conversation_id: conversationId,
        client_message_id: operationKey(),
        content,
      }),
    }, true)).data;
  },
  async listAgentMessages(conversationId: string, page = 1, pageSize = 100) {
    return request<PageResponse<AgentChatMessage>>(
      `/api/v1/agent/conversations/${conversationId}/messages?page=${page}&page_size=${pageSize}`,
    );
  },
  async resetAgentConversation(conversationId: string) {
    await request<SuccessResponse<{ conversation_id: string; cleared: boolean }>>(
      `/api/v1/agent/conversations/${conversationId}`,
      { method: "DELETE" },
      true,
    );
  },
};
