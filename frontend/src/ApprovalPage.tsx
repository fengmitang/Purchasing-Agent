import { CheckCircleOutlined, CloseCircleOutlined, EyeOutlined, ReloadOutlined } from "@ant-design/icons";
import { App, Button, Card, Descriptions, Drawer, Flex, Input, Segmented, Table, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { ApprovalTask } from "./types";

const { Title, Text, Paragraph } = Typography;
function money(value: string | null, currency: string) { return value == null ? "—" : new Intl.NumberFormat("zh-CN", { style: "currency", currency }).format(Number(value)); }
function dateTime(value: string | null) { return value ? new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—"; }
function approvalTag(task: ApprovalTask) {
  if (task.approval_action === "APPROVED" || task.status === "APPROVED") return <Tag color="cyan">审批通过</Tag>;
  if (task.approval_action === "REJECTED" || task.status === "REJECTED") return <Tag color="red">审批退回</Tag>;
  return <Tag color="blue">待审批</Tag>;
}

export function ApprovalPage() {
  const { message, modal } = App.useApp();
  const [tasks, setTasks] = useState<ApprovalTask[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<ApprovalTask | null>(null);
  const [view, setView] = useState<"pending" | "history">("pending");
  const load = useCallback(async () => { setLoading(true); try { const result = await api.listApprovalTasks(view); setTasks(result.data); setTotal(result.page.total); } catch (error) { message.error((error as Error).message); } finally { setLoading(false); } }, [message, view]);
  useEffect(() => { void load(); }, [load]);

  async function approve() {
    if (!selected) return;
    let comment = "";
    modal.confirm({ title: "确认审批通过？", content: <Input.TextArea rows={3} placeholder="审批意见（可选）" onChange={event => { comment = event.target.value; }} />, okText: "通过", cancelText: "返回",
      async onOk() { await api.approvalDecision(selected, "APPROVED", comment); setSelected(null); await load(); message.success("审批已通过，申请已进入采购员队列"); },
    });
  }
  function reject() {
    if (!selected) return;
    let comment = "";
    modal.confirm({ title: "驳回采购申请", content: <Input.TextArea rows={4} placeholder="请填写驳回原因" onChange={event => { comment = event.target.value; }} />, okText: "确认驳回", okButtonProps: { danger: true }, cancelText: "返回",
      async onOk() { if (!comment.trim()) { message.warning("驳回时必须填写审批意见"); throw new Error("missing comment"); } await api.approvalDecision(selected, "REJECTED", comment.trim()); setSelected(null); await load(); message.success("申请已驳回，员工可以查看审批结果"); },
    });
  }
  const columns = [
    { title: "申请单号", dataIndex: "requirement_no", render: (value: string, row: ApprovalTask) => <Button type="link" onClick={() => setSelected(row)}>{value}</Button> },
    { title: "申请人", render: (_: unknown, row: ApprovalTask) => `${row.applicant.name}（${row.applicant.employee_no || "无工号"}）` },
    { title: "所属楼宇", dataIndex: "building_name" },
    { title: "采购设备", dataIndex: "product_name", render: (value: string | null) => value || "未填写" },
    { title: "数量", render: (_: unknown, row: ApprovalTask) => `${row.quantity || "—"}${row.unit || ""}` },
    { title: "金额", render: (_: unknown, row: ApprovalTask) => money(row.total_amount, row.currency) },
    ...(view === "history" ? [{ title: "审批结果", render: (_: unknown, row: ApprovalTask) => approvalTag(row) }] : []),
    { title: view === "history" ? "审批时间" : "提交时间", render: (_: unknown, row: ApprovalTask) => dateTime(view === "history" ? row.acted_at : row.submitted_at) },
    { title: "操作", render: (_: unknown, row: ApprovalTask) => <Button icon={<EyeOutlined />} onClick={() => setSelected(row)}>{view === "history" ? "查看记录" : "查看审批"}</Button> },
  ];
  return <section><div className="page-heading"><div><Title level={2}>楼长审批</Title><Text type="secondary">{view === "pending" ? `你负责楼宇内等待处理的申请，共 ${total} 张` : `你本人已经处理的审批记录，共 ${total} 张`}</Text></div><Flex gap={12}><Segmented value={view} options={[{ label: "待审批", value: "pending" }, { label: "审批记录", value: "history" }]} onChange={value => { setSelected(null); setView(value as "pending" | "history"); }} /><Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button></Flex></div>
    <Card className="surface-card" bordered={false}><Table rowKey="requirement_id" loading={loading} columns={columns} dataSource={tasks} pagination={false} scroll={{ x: 1050 }} /></Card>
    <Drawer title={selected ? `审批申请 ${selected.requirement_no}` : "审批详情"} width={720} open={Boolean(selected)} onClose={() => setSelected(null)} extra={selected ? approvalTag(selected) : null}>
      {selected && <><Descriptions bordered column={2} size="small">
        <Descriptions.Item label="申请人">{selected.applicant.name}</Descriptions.Item><Descriptions.Item label="联系电话">{selected.applicant.phone || "—"}</Descriptions.Item>
        <Descriptions.Item label="工号">{selected.applicant.employee_no || "—"}</Descriptions.Item><Descriptions.Item label="所属楼宇">{selected.building_name}</Descriptions.Item>
        <Descriptions.Item label="申请地点">{selected.application_location || "—"}</Descriptions.Item><Descriptions.Item label="申请类别">{selected.category_name || "—"}</Descriptions.Item>
        <Descriptions.Item label="设备名称">{selected.product_name || "—"}</Descriptions.Item><Descriptions.Item label="品牌型号">{[selected.brand, selected.model].filter(Boolean).join(" ") || "—"}</Descriptions.Item>
        <Descriptions.Item label="设备全称" span={2}>{selected.product_full_name || "—"}</Descriptions.Item><Descriptions.Item label="规格参数" span={2}>{selected.specification || "—"}</Descriptions.Item>
        <Descriptions.Item label="数量">{selected.quantity}{selected.unit}</Descriptions.Item><Descriptions.Item label="供应商">{selected.supplier_name || "—"}</Descriptions.Item>
        <Descriptions.Item label="单价">{money(selected.unit_price, selected.currency)}</Descriptions.Item><Descriptions.Item label="总价">{money(selected.total_amount, selected.currency)}</Descriptions.Item>
      </Descriptions><Card size="small" title="申请原因" className="decision-reason"><Paragraph>{selected.application_reason || "未填写"}</Paragraph></Card>
      {view === "history" ? <Card size="small" title="审批记录" className="decision-reason"><Descriptions column={1} size="small"><Descriptions.Item label="审批结果">{approvalTag(selected)}</Descriptions.Item><Descriptions.Item label="审批人">{selected.approver_name || "—"}（{selected.approver_employee_no || "无工号"}）</Descriptions.Item><Descriptions.Item label="联系电话">{selected.approver_phone || "—"}</Descriptions.Item><Descriptions.Item label="审批时间">{dateTime(selected.acted_at)}</Descriptions.Item><Descriptions.Item label="审批意见">{selected.approval_comment || "无"}</Descriptions.Item></Descriptions></Card> :
      <Flex justify="flex-end" gap={12}><Button danger icon={<CloseCircleOutlined />} onClick={reject}>驳回</Button><Button type="primary" icon={<CheckCircleOutlined />} onClick={() => void approve()}>审批通过</Button></Flex>}</>}
    </Drawer>
  </section>;
}
