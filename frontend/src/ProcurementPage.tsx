import { CheckCircleOutlined, FileDoneOutlined, PlayCircleOutlined, ReloadOutlined, UndoOutlined } from "@ant-design/icons";
import { App, Button, Card, Descriptions, Drawer, Flex, Table, Tag, Timeline, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { ProcurementTask } from "./types";

const { Title, Text } = Typography;
const statusText: Record<string, string> = { APPROVED: "待采购", PURCHASING: "采购中", QUOTED: "已询价核价", CONTRACTED: "已签合同", COMPLETED: "已入库完成" };
function money(value: string | null, currency: string) { return value == null ? "—" : new Intl.NumberFormat("zh-CN", { style: "currency", currency }).format(Number(value)); }
function dateTime(value: string | null) { return value ? new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—"; }
const rollbackText: Record<string, string> = { PURCHASING: "取消领取", QUOTED: "撤回询价核价", CONTRACTED: "撤回合同签订", COMPLETED: "撤回验收入库" };

export function ProcurementPage() {
  const { message, modal } = App.useApp();
  const [tasks, setTasks] = useState<ProcurementTask[]>([]);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<ProcurementTask | null>(null);
  const [loading, setLoading] = useState(false);
  const load = useCallback(async () => { setLoading(true); try { const result = await api.listProcurementTasks(); setTasks(result.data); setTotal(result.page.total); setSelected(current => current ? result.data.find(item => item.requirement_id === current.requirement_id) || null : null); } catch (error) { message.error((error as Error).message); } finally { setLoading(false); } }, [message]);
  useEffect(() => { void load(); }, [load]);
  async function run(action: () => Promise<ProcurementTask>, success: string) { try { setSelected(await action()); await load(); message.success(success); } catch (error) { message.error((error as Error).message); } }
  function confirmAdvance(targetStatus: "QUOTED" | "CONTRACTED", label: string) { if (!selected) return; modal.confirm({ title: `确认${label}？`, okText: "确认完成", cancelText: "返回", async onOk() { await run(() => api.advanceProcurement(selected, targetStatus), `已记录${label}`); } }); }
  function complete() { if (!selected) return; modal.confirm({ title: "确认验收入库并完成采购？", okText: "确认完成", cancelText: "返回", async onOk() { await run(() => api.completeProcurement(selected), "已记录入库时间，本单采购完成"); } }); }
  function rollback() { if (!selected) return; const label = rollbackText[selected.status]; modal.confirm({ title: `确认${label}？`, content: "确认后采购任务将退回上一个状态，并清除当前节点的完成时间。", okText: "确认撤回", okButtonProps: { danger: true }, cancelText: "返回", async onOk() { await run(() => api.rollbackProcurement(selected), "已撤回到上一个采购节点"); } }); }
  const columns = [
    { title: "申请单号", dataIndex: "requirement_no", render: (value: string, row: ProcurementTask) => <Button type="link" onClick={() => setSelected(row)}>{value}</Button> },
    { title: "设备", dataIndex: "product_name", render: (value: string | null) => value || "—" },
    { title: "供应商", dataIndex: "supplier_name", render: (value: string | null) => value || "—" },
    { title: "金额", render: (_: unknown, row: ProcurementTask) => money(row.total_amount, row.currency) },
    { title: "状态", dataIndex: "status", render: (value: string) => <Tag color={value === "COMPLETED" ? "green" : value === "APPROVED" ? "blue" : "purple"}>{statusText[value] || value}</Tag> },
    { title: "负责人", dataIndex: "purchaser_name", render: (value: string | null) => value || "尚未领取" },
    { title: "操作", render: (_: unknown, row: ProcurementTask) => <Button onClick={() => setSelected(row)}>查看处理</Button> },
  ];
  return <section><div className="page-heading"><div><Title level={2}>采购任务</Title><Text type="secondary">审批通过的申请会自动进入这里，共 {total} 张</Text></div><Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button></div>
    <Card className="surface-card" bordered={false}><Table rowKey="requirement_id" loading={loading} columns={columns} dataSource={tasks} pagination={false} scroll={{ x: 920 }} /></Card>
    <Drawer title={selected ? `采购任务 ${selected.requirement_no}` : "采购任务"} width={700} open={Boolean(selected)} onClose={() => setSelected(null)}>
      {selected && <><Descriptions bordered column={2} size="small"><Descriptions.Item label="申请人">{selected.applicant_name}（{selected.applicant_employee_no || "无工号"}）</Descriptions.Item><Descriptions.Item label="申请人电话">{selected.applicant_phone || "—"}</Descriptions.Item><Descriptions.Item label="所属楼宇">{selected.building_name || "—"}</Descriptions.Item><Descriptions.Item label="审批人">{selected.approver_name || "—"}（{selected.approver_employee_no || "无工号"}）</Descriptions.Item><Descriptions.Item label="审批人电话">{selected.approver_phone || "—"}</Descriptions.Item><Descriptions.Item label="审批时间">{dateTime(selected.approved_at)}</Descriptions.Item><Descriptions.Item label="审批意见" span={2}>{selected.approval_comment || "无"}</Descriptions.Item><Descriptions.Item label="设备名称">{selected.product_name || "—"}</Descriptions.Item><Descriptions.Item label="品牌型号">{[selected.brand, selected.model].filter(Boolean).join(" ") || "—"}</Descriptions.Item><Descriptions.Item label="设备全称" span={2}>{selected.product_full_name || "—"}</Descriptions.Item><Descriptions.Item label="规格参数" span={2}>{selected.specification || "—"}</Descriptions.Item><Descriptions.Item label="数量">{selected.quantity}{selected.unit}</Descriptions.Item><Descriptions.Item label="供应商">{selected.supplier_name || "—"}</Descriptions.Item><Descriptions.Item label="单价">{money(selected.unit_price, selected.currency)}</Descriptions.Item><Descriptions.Item label="总价">{money(selected.total_amount, selected.currency)}</Descriptions.Item><Descriptions.Item label="采购单号">{selected.order_no || "开始采购后生成"}</Descriptions.Item><Descriptions.Item label="采购负责人">{selected.purchaser_name || "尚未领取"}（{selected.purchaser_employee_no || "无工号"}）</Descriptions.Item><Descriptions.Item label="采购负责人电话" span={2}>{selected.purchaser_phone || "尚未领取任务"}</Descriptions.Item></Descriptions>
      <Card size="small" title="采购进度" className="decision-reason"><Timeline items={[{ color: selected.purchasing_started_at ? "green" : "gray", children: `开始采购：${dateTime(selected.purchasing_started_at)}` }, { color: selected.quoted_at ? "green" : "gray", children: `询价核价：${dateTime(selected.quoted_at)}` }, { color: selected.contracted_at ? "green" : "gray", children: `合同签订：${dateTime(selected.contracted_at)}` }, { color: selected.received_at ? "green" : "gray", children: `验收入库：${dateTime(selected.received_at)}` }]} /></Card>
      <Flex justify="flex-end" gap={10} wrap>{rollbackText[selected.status] && <Button danger icon={<UndoOutlined />} onClick={rollback}>{rollbackText[selected.status]}</Button>}{selected.status === "APPROVED" && <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => void run(() => api.startProcurement(selected), "已领取任务并开始采购")}>开始采购</Button>}{selected.status === "PURCHASING" && <Button type="primary" icon={<FileDoneOutlined />} onClick={() => confirmAdvance("QUOTED", "询价核价")}>完成询价核价</Button>}{selected.status === "QUOTED" && <Button type="primary" icon={<FileDoneOutlined />} onClick={() => confirmAdvance("CONTRACTED", "合同签订")}>完成合同签订</Button>}{selected.status === "CONTRACTED" && <Button type="primary" icon={<CheckCircleOutlined />} onClick={complete}>验收入库并完成</Button>}</Flex></>}
    </Drawer>
  </section>;
}
