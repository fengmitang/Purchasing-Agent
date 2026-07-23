import {
  CheckCircleFilled,
  CheckCircleOutlined,
  DeleteOutlined,
  FileTextOutlined,
  RobotOutlined,
  SendOutlined,
  UserOutlined,
} from "@ant-design/icons";
import {
  Alert,
  App as AntApp,
  Avatar,
  Button,
  Card,
  Descriptions,
  Empty,
  Flex,
  Input,
  Progress,
  Skeleton,
  Space,
  Tag,
  Typography,
} from "antd";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import type { AgentChatMessage, CurrentUser, RequirementDetail } from "./types";

const { Title, Text, Paragraph } = Typography;

const fieldNames: Record<string, string> = {
  application_reason: "申请原因",
  application_location: "申请地点",
  device_type: "设备类型",
  product_name: "设备名称",
  product_full_name: "设备全称",
  brand: "品牌",
  model: "型号",
  specification: "规格参数",
  quantity: "数量",
  unit: "单位",
  supplier_name: "供应商",
  unit_price: "参考单价",
  currency: "币种",
};
const requiredFieldCount = 4;

const quickPrompts = [
  "我要采购 2 台机架式服务器，用于新建测试环境",
  "帮我新建一张交换机采购申请",
  "我想采购一批机房环境监控设备",
];

function createConversationId() {
  return `web-${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;
}

function money(value: string | null, currency = "CNY") {
  if (value == null) return "待补充";
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
  }).format(Number(value));
}

function display(value: string | number | null | undefined) {
  return value == null || value === "" ? "待补充" : String(value);
}

interface AgentChatPageProps {
  user: CurrentUser;
  onOpenRequirement: (requirementId: number) => void;
  onSubmitted: () => void;
}

export function AgentChatPage({ user, onOpenRequirement, onSubmitted }: AgentChatPageProps) {
  const { message, modal } = AntApp.useApp();
  const storagePrefix = `procurement-agent:${user.employee_no}`;
  const [conversationId, setConversationId] = useState(
    () => localStorage.getItem(`${storagePrefix}:conversation`) || createConversationId(),
  );
  const [messages, setMessages] = useState<AgentChatMessage[]>([]);
  const [draft, setDraft] = useState<RequirementDetail | null>(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [loadingDraft, setLoadingDraft] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const loadDraft = useCallback(async (requirementId: number) => {
    setLoadingDraft(true);
    try {
      const detail = await api.getDetail(user.employee_no, requirementId);
      setDraft(detail);
      localStorage.setItem(`${storagePrefix}:requirement`, String(requirementId));
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setLoadingDraft(false);
    }
  }, [message, storagePrefix, user.employee_no]);

  useEffect(() => {
    localStorage.setItem(`${storagePrefix}:conversation`, conversationId);
    let alive = true;
    setLoadingHistory(true);
    api.listAgentMessages(conversationId)
      .then((result) => { if (alive) setMessages(result.data); })
      .catch((error) => { if (alive) message.error((error as Error).message); })
      .finally(() => { if (alive) setLoadingHistory(false); });
    const requirementId = Number(localStorage.getItem(`${storagePrefix}:requirement`));
    if (requirementId > 0) void loadDraft(requirementId);
    return () => { alive = false; };
  }, [conversationId, loadDraft, message, storagePrefix]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  const completion = useMemo(() => {
    if (!draft) return 0;
    return Math.max(0, Math.round(((requiredFieldCount - draft.missing_fields.length) / requiredFieldCount) * 100));
  }, [draft]);

  async function send(content = input) {
    const trimmed = content.trim();
    if (!trimmed || sending) return;
    const optimisticId = `local-${Date.now()}`;
    const optimistic: AgentChatMessage = {
      message_id: optimisticId,
      client_message_id: optimisticId,
      role: "USER",
      content: trimmed,
      status: "PROCESSING",
      created_at: new Date().toISOString(),
    };
    setMessages((current) => [...current, optimistic]);
    setInput("");
    setSending(true);
    try {
      const result = await api.sendAgentMessage(conversationId, trimmed);
      setMessages((current) => [
        ...current.map((item) => item.message_id === optimisticId ? { ...item, status: "COMPLETED" as const } : item),
        {
          message_id: result.message_id,
          role: "ASSISTANT",
          content: result.content,
          status: "COMPLETED",
          created_at: result.created_at,
        },
      ]);
      if (result.active_requirement) await loadDraft(result.active_requirement.requirement_id);
    } catch (error) {
      setMessages((current) => current.map((item) => (
        item.message_id === optimisticId ? { ...item, status: "FAILED" as const } : item
      )));
      message.error((error as Error).message);
    } finally {
      setSending(false);
    }
  }

  function resetConversation() {
    modal.confirm({
      title: "开始一段新对话？",
      content: "聊天记录和当前对话状态会清空；已经保存到后端的采购草稿不会被删除。",
      okText: "开始新对话",
      cancelText: "返回",
      async onOk() {
        await api.resetAgentConversation(conversationId);
        const nextId = createConversationId();
        localStorage.removeItem(`${storagePrefix}:requirement`);
        localStorage.setItem(`${storagePrefix}:conversation`, nextId);
        setMessages([]);
        setDraft(null);
        setConversationId(nextId);
        message.success("已开始新对话");
      },
    });
  }

  function confirmSubmission() {
    if (!draft) return;
    if (draft.status !== "DRAFT") {
      message.info("这张申请已不是可提交的草稿状态");
      return;
    }
    if (draft.missing_fields.length || draft.conflicts.length) {
      message.warning("请先在对话中补齐或确认所有信息");
      return;
    }
    modal.confirm({
      title: "确认提交采购申请？",
      content: (
        <div>
          <p>你即将提交 <strong>{draft.requirement_no}</strong>，提交后进入楼长审批，草稿不能继续修改。</p>
          <p>设备：{draft.product_full_name || draft.product_name}，数量：{draft.quantity}{draft.unit || ""}，预计总价：{money(draft.total_amount, draft.currency)}。</p>
        </div>
      ),
      okText: "确认提交审批",
      cancelText: "继续核对",
      async onOk() {
        await api.submit(user.employee_no, draft);
        const latest = await api.getDetail(user.employee_no, draft.requirement_id);
        setDraft(latest);
        onSubmitted();
        message.success(`采购申请 ${latest.requirement_no} 已提交审批`);
      },
    });
  }

  const canSubmit = Boolean(
    draft &&
    draft.status === "DRAFT" &&
    draft.missing_fields.length === 0 &&
    draft.conflicts.length === 0,
  );

  return (
    <section className="agent-page">
      <div className="agent-page-heading">
        <div>
          <Flex align="center" gap={10}>
            <span className="agent-heading-icon"><RobotOutlined /></span>
            <Title level={2}>智能采购助手</Title>
          </Flex>
          <Text type="secondary">说出采购需求，我会自动整理信息；提交前由你最终确认。</Text>
        </div>
        <Button icon={<DeleteOutlined />} onClick={resetConversation}>新建对话</Button>
      </div>

      <div className="agent-workspace">
        <Card className="chat-card" bordered={false}>
          <div className="chat-card-header">
            <Flex align="center" gap={9}>
              <span className="online-dot" />
              <Text strong>采购助手</Text>
              <Tag color="cyan">在线</Tag>
            </Flex>
            <Text type="secondary">所有正式数据以后端草稿为准</Text>
          </div>

          <div className="chat-messages" aria-live="polite">
            {loadingHistory ? <Skeleton active paragraph={{ rows: 5 }} /> : messages.length === 0 ? (
              <div className="chat-welcome">
                <Avatar size={56} icon={<RobotOutlined />} className="assistant-avatar" />
                <Title level={3}>你好，{user.name}</Title>
                <Paragraph type="secondary">告诉我想采购什么，我会逐步询问缺少的信息并生成采购草稿。</Paragraph>
                <div className="quick-prompts">
                  {quickPrompts.map((prompt) => (
                    <button type="button" key={prompt} onClick={() => void send(prompt)}>{prompt}</button>
                  ))}
                </div>
              </div>
            ) : messages.map((item) => (
              <div key={item.message_id} className={`chat-row ${item.role === "USER" ? "is-user" : "is-assistant"}`}>
                <Avatar
                  size={34}
                  icon={item.role === "USER" ? <UserOutlined /> : <RobotOutlined />}
                  className={item.role === "USER" ? "user-avatar" : "assistant-avatar"}
                />
                <div>
                  <div className={`chat-bubble ${item.status === "FAILED" ? "is-failed" : ""}`}>
                    {item.content}
                  </div>
                  {item.status === "FAILED" && <Text type="danger">发送失败，请重新发送</Text>}
                </div>
              </div>
            ))}
            {sending && (
              <div className="chat-row is-assistant">
                <Avatar size={34} icon={<RobotOutlined />} className="assistant-avatar" />
                <div className="chat-bubble typing-bubble"><i /><i /><i /></div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          <div className="chat-composer">
            <Input.TextArea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onPressEnter={(event) => {
                if (!event.shiftKey) {
                  event.preventDefault();
                  void send();
                }
              }}
              autoSize={{ minRows: 2, maxRows: 5 }}
              maxLength={10_000}
              placeholder="例如：需要采购 2 台浪潮机架式服务器，用于 A03 机房测试环境……"
              disabled={sending}
            />
            <Flex justify="space-between" align="center">
              <Text type="secondary">Enter 发送 · Shift + Enter 换行</Text>
              <Button type="primary" icon={<SendOutlined />} loading={sending} disabled={!input.trim()} onClick={() => void send()}>
                发送
              </Button>
            </Flex>
          </div>
        </Card>

        <Card className="draft-card" bordered={false}>
          <div className="draft-card-title">
            <div>
              <Text type="secondary">自动整理</Text>
              <Title level={4}>采购申请摘要</Title>
            </div>
            {draft && <Tag color={draft.status === "DRAFT" ? "gold" : "blue"}>{draft.status === "DRAFT" ? "草稿" : "已提交"}</Tag>}
          </div>

          {loadingDraft ? <Skeleton active /> : !draft ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="开始对话后，这里会实时整理采购信息" />
          ) : (
            <>
              <div className="draft-number">
                <FileTextOutlined />
                <div><Text type="secondary">申请单号</Text><strong>{draft.requirement_no}</strong></div>
                <Button type="link" onClick={() => onOpenRequirement(draft.requirement_id)}>查看完整表单</Button>
              </div>
              <div className="completion-block">
                <Flex justify="space-between"><Text strong>信息完整度</Text><Text strong>{completion}%</Text></Flex>
                <Progress percent={completion} showInfo={false} status={canSubmit ? "success" : "active"} />
              </div>
              {draft.missing_fields.length > 0 && (
                <Alert
                  type="warning"
                  showIcon
                  message="还需要补充"
                  description={draft.missing_fields.map((field) => fieldNames[field] || field).join("、")}
                />
              )}
              {draft.conflicts.length > 0 && (
                <Alert type="error" showIcon message="有信息需要确认" description={draft.conflicts.map((item) => item.message).join("；")} />
              )}
              <Descriptions column={1} size="small" className="draft-descriptions">
                <Descriptions.Item label="使用地点">{display(draft.application_location)}</Descriptions.Item>
                <Descriptions.Item label="采购设备">{display(draft.product_full_name || draft.product_name)}</Descriptions.Item>
                <Descriptions.Item label="品牌 / 型号">{[draft.brand, draft.model].filter(Boolean).join(" / ") || "待补充"}</Descriptions.Item>
                <Descriptions.Item label="规格参数">{display(draft.specification)}</Descriptions.Item>
                <Descriptions.Item label="数量">{draft.quantity ? `${draft.quantity} ${draft.unit || ""}` : "待补充"}</Descriptions.Item>
                <Descriptions.Item label="供应商">{display(draft.supplier_name)}</Descriptions.Item>
                <Descriptions.Item label="参考单价">{money(draft.unit_price, draft.currency)}</Descriptions.Item>
                <Descriptions.Item label="预计总价"><strong className="total-money">{money(draft.total_amount, draft.currency)}</strong></Descriptions.Item>
                <Descriptions.Item label="申请原因">{display(draft.application_reason)}</Descriptions.Item>
              </Descriptions>
              {draft.status === "PENDING_APPROVAL" ? (
                <Alert type="success" showIcon icon={<CheckCircleFilled />} message="已提交审批" description="申请已经进入楼长审批流程。" />
              ) : (
                <Space direction="vertical" className="submit-area" size={10}>
                  <Button type="primary" size="large" block icon={<CheckCircleOutlined />} disabled={!canSubmit} onClick={confirmSubmission}>
                    核对无误，提交审批
                  </Button>
                  <Text type="secondary">提交前请逐项核对；如需修改，直接在左侧对话中说明。</Text>
                </Space>
              )}
            </>
          )}
        </Card>
      </div>
    </section>
  );
}
