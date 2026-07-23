import { ApartmentOutlined, AuditOutlined, CheckCircleOutlined, FileAddOutlined, HistoryOutlined, InboxOutlined, LockOutlined, LogoutOutlined, RobotOutlined, SaveOutlined, SearchOutlined, ShoppingCartOutlined, UserOutlined } from "@ant-design/icons";
import { Alert, App as AntApp, Badge, Button, Card, Col, Descriptions, Drawer, Empty, Flex, Form, Input, InputNumber, Layout, Menu, Progress, Row, Select, Space, Spin, Statistic, Steps, Table, Tag, Typography } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApprovalPage } from "./ApprovalPage";
import { api } from "./api";
import { ProcurementPage } from "./ProcurementPage";
import type { BuildingOption, CurrentUser, Recommendation, RequirementDetail, RequirementFormValues, RequirementStatus, RequirementSummary } from "./types";

const { Header, Sider, Content } = Layout;
const { Title, Text, Paragraph } = Typography;
const statusMap: Record<string, { text: string; color: string }> = {
  DRAFT: { text: "草稿", color: "gold" }, PENDING_APPROVAL: { text: "待审批", color: "blue" },
  APPROVED: { text: "审批通过", color: "cyan" }, REJECTED: { text: "审批退回", color: "red" },
  PURCHASING: { text: "采购中", color: "purple" }, QUOTED: { text: "已询价核价", color: "geekblue" },
  CONTRACTED: { text: "已签合同", color: "magenta" }, STOCKED_IN: { text: "已入库", color: "green" },
  COMPLETED: { text: "已完成", color: "green" }, CANCELLED: { text: "已取消", color: "default" },
};
const fieldNames: Record<string, string> = {
  building_id: "所属楼宇", category_name: "申请类别", application_reason: "申请原因", application_location: "申请地点",
  device_type: "设备类型", product_name: "设备名称", product_full_name: "具体设备全称",
  brand: "品牌", model: "设备型号", specification: "规格参数", quantity: "数量",
  unit: "单位", supplier_name: "供应商", unit_price: "单价",
};
const submissionRequiredFields: Array<keyof RequirementFormValues> = [
  "building_id", "category_name", "application_reason", "application_location", "device_type",
  "product_name", "product_full_name", "brand", "model", "specification", "quantity", "unit",
  "supplier_name", "unit_price", "currency",
];
function statusTag(status: RequirementStatus) {
  const item = statusMap[status] ?? { text: status, color: "default" };
  return <Tag color={item.color}>{item.text}</Tag>;
}
function money(value: string | null, currency = "CNY") {
  if (value == null) return "—";
  return new Intl.NumberFormat("zh-CN", { style: "currency", currency, minimumFractionDigits: 2 }).format(Number(value));
}
function dateTime(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}
function detailToForm(detail: RequirementDetail): RequirementFormValues {
  return {
    building_id: detail.building_id ?? undefined, category_name: detail.category_name ?? undefined, application_reason: detail.application_reason ?? undefined,
    application_location: detail.application_location ?? undefined, device_type: detail.device_type ?? undefined,
    product_name: detail.product_name ?? undefined, product_full_name: detail.product_full_name ?? undefined,
    brand: detail.brand ?? undefined, model: detail.model ?? undefined, specification: detail.specification ?? undefined,
    quantity: detail.quantity == null ? undefined : Number(detail.quantity), unit: detail.unit ?? undefined,
    supplier_name: detail.supplier_name ?? undefined,
    unit_price: detail.unit_price == null ? undefined : Number(detail.unit_price), currency: detail.currency,
  };
}

function AppContent({ user, onLogout }: { user: CurrentUser; onLogout: () => Promise<void> }) {
  const { message, modal } = AntApp.useApp();
  const [form] = Form.useForm<RequirementFormValues>();
  const employeeCode = user.employee_no;
  const [activeMenu, setActiveMenu] = useState("new");
  const [current, setCurrent] = useState<RequirementDetail | null>(null);
  const [list, setList] = useState<RequirementSummary[]>([]);
  const [listTotal, setListTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [listLoading, setListLoading] = useState(false);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [recommendationOpen, setRecommendationOpen] = useState(false);
  const [buildings, setBuildings] = useState<BuildingOption[]>([]);
  const [pendingApprovalCount, setPendingApprovalCount] = useState(0);
  const values = Form.useWatch([], form);
  const total = useMemo(() => Number(values?.quantity || 0) * Number(values?.unit_price || 0), [values?.quantity, values?.unit_price]);

  const refreshList = useCallback(async () => {
    setListLoading(true);
    try {
      const result = await api.listMine(employeeCode.trim()); setList(result.data); setListTotal(result.page.total);
    } catch (error) { message.error((error as Error).message); } finally { setListLoading(false); }
  }, [employeeCode, message]);
  useEffect(() => { void refreshList(); }, [refreshList]);
  useEffect(() => { api.listBuildings().then(setBuildings).catch(error => message.error((error as Error).message)); }, [message]);
  const refreshPendingApprovalCount = useCallback(async () => {
    if (!user.roles.includes("BUILDING_MANAGER")) return;
    try {
      const result = await api.listApprovalTasks("pending", 1, 1);
      setPendingApprovalCount(result.page.total);
    } catch {
      // The approval page will show request errors when the user opens it.
    }
  }, [user.roles]);
  useEffect(() => {
    if (!user.roles.includes("BUILDING_MANAGER")) return;
    void refreshPendingApprovalCount();
    const timer = window.setInterval(() => void refreshPendingApprovalCount(), 30_000);
    return () => window.clearInterval(timer);
  }, [refreshPendingApprovalCount, user.roles]);

  async function saveDraft() {
    const formValues = form.getFieldsValue();
    setLoading(true);
    try {
      const saved = current ? await api.updateDraft(employeeCode.trim(), current, formValues) : await api.createDraft(employeeCode.trim(), formValues);
      setCurrent(saved); form.setFieldsValue(detailToForm(saved)); message.success(current ? "草稿已更新" : "采购草稿已创建"); await refreshList();
    } catch (error) { message.error((error as Error).message); } finally { setLoading(false); }
  }
  async function openRequirement(id: number) {
    setLoading(true);
    try { const detail = await api.getDetail(employeeCode.trim(), id); setCurrent(detail); form.setFieldsValue(detailToForm(detail)); setRecommendations([]); setActiveMenu("new"); }
    catch (error) { message.error((error as Error).message); } finally { setLoading(false); }
  }
  function startNew() { setCurrent(null); setRecommendations([]); form.resetFields(); form.setFieldValue("currency", "CNY"); setActiveMenu("new"); }
  async function findRecommendations() {
    if (!current) return void message.info("请先保存草稿，再查询历史采购记录");
    setLoading(true);
    try { const result = await api.recommendations(employeeCode.trim(), current); setRecommendations(result.recommendations); setRecommendationOpen(true); if (!result.recommendations.length) message.info("暂未找到相似的历史采购记录"); }
    catch (error) { message.error((error as Error).message); } finally { setLoading(false); }
  }
  function chooseRecommendation(item: Recommendation) {
    form.setFieldsValue({ supplier_name: item.supplier_name, unit_price: item.latest_purchase.unit_price == null ? undefined : Number(item.latest_purchase.unit_price) });
    setRecommendationOpen(false); message.success("已填入历史供应商和参考单价，请核对后保存");
  }
  async function submit() {
    if (!current) return;
    const formValues = form.getFieldsValue();
    const missing = submissionRequiredFields.filter((field) => {
      const value = formValues[field];
      return value == null || (typeof value === "string" && !value.trim());
    });
    if (missing.length) {
      form.setFields(missing.map(field => ({ name: field, errors: ["提交审批前必须填写此项"] })));
      modal.warning({
        title: "还有必填信息没有填写",
        content: <div><p>请补充以下信息后再提交：</p><ul>{missing.map(field => <li key={field}>{fieldNames[field]}</li>)}</ul></div>,
        okText: "去填写",
        onOk() { form.scrollToField(missing[0], { behavior: "smooth", block: "center", focus: true }); },
      });
      return;
    }

    setLoading(true);
    let latest: RequirementDetail;
    try {
      latest = await api.updateDraft(employeeCode.trim(), current, formValues);
      setCurrent(latest);
      form.setFieldsValue(detailToForm(latest));
      await refreshList();
    } catch (error) {
      message.error((error as Error).message);
      return;
    } finally {
      setLoading(false);
    }
    modal.confirm({ title: "确认提交审批？", content: "提交后申请将进入楼长审批，当前草稿不能继续修改。", okText: "确认提交", cancelText: "继续检查",
      async onOk() { try { await api.submit(employeeCode.trim(), latest); const detail = await api.getDetail(employeeCode.trim(), latest.requirement_id); setCurrent(detail); await refreshList(); await refreshPendingApprovalCount(); message.success("已提交审批"); } catch (error) { message.error((error as Error).message); } },
    });
  }
  function cancelDraft() {
    if (!current) return; let reason = "";
    modal.confirm({ title: "取消这张采购草稿？", content: <Input.TextArea rows={3} placeholder="请输入取消原因" onChange={(event) => { reason = event.target.value; }} />, okText: "确认取消", okButtonProps: { danger: true }, cancelText: "返回",
      async onOk() { if (!reason.trim()) { message.warning("请填写取消原因"); throw new Error("missing reason"); } try { setCurrent(await api.cancel(employeeCode.trim(), current, reason.trim())); await refreshList(); message.success("草稿已取消"); } catch (error) { if ((error as Error).message !== "missing reason") message.error((error as Error).message); throw error; } },
    });
  }
  async function reviseRejected() {
    if (!current || current.status !== "REJECTED") return;
    setLoading(true);
    try {
      const revised = await api.revise(employeeCode, current);
      setCurrent(revised); form.setFieldsValue(detailToForm(revised)); await refreshList();
      message.success("已保留原审批记录并创建修改草稿，请修改后重新提交");
    } catch (error) { message.error((error as Error).message); } finally { setLoading(false); }
  }

  const editable = !current || current.status === "DRAFT";
  const completion = current ? Math.max(0, Math.round(((Object.keys(fieldNames).length - current.missing_fields.length) / Object.keys(fieldNames).length) * 100)) : 0;
  const columns = [
    { title: "申请单号", dataIndex: "requirement_no", render: (text: string, record: RequirementSummary) => <Button type="link" className="table-link" onClick={() => void openRequirement(record.requirement_id)}>{text}</Button> },
    { title: "采购设备", dataIndex: "product_name", render: (value: string | null) => value || "未填写" },
    { title: "状态", dataIndex: "status", render: statusTag },
    { title: "金额", dataIndex: "total_amount", render: (value: string | null, row: RequirementSummary) => money(value, row.currency) },
    { title: "最后更新", dataIndex: "updated_at", render: dateTime },
  ];
  const menuItems = [
    { key: "new", icon: <FileAddOutlined />, label: "新建采购申请" },
    { key: "mine", icon: <InboxOutlined />, label: "我的采购申请" },
    ...(user.roles.includes("BUILDING_MANAGER") ? [{ key: "approvals", icon: <AuditOutlined />, label: <span className="menu-label-with-badge"><span>待我审批</span><Badge count={pendingApprovalCount} overflowCount={99} /></span> }] : []),
    ...(user.roles.includes("PURCHASER") ? [{ key: "procurement", icon: <ShoppingCartOutlined />, label: "采购任务" }] : []),
  ];

  return <Layout className="app-shell">
    <Sider width={244} className="sidebar" breakpoint="lg" collapsedWidth="0">
      <div className="brand"><div className="brand-mark"><ApartmentOutlined /></div><div><strong>采购智管</strong><span>数据中心采购平台</span></div></div>
      <Menu mode="inline" selectedKeys={[activeMenu]} onClick={({ key }) => { setActiveMenu(key); if (key === "new") startNew(); if (key === "mine") void refreshList(); }} items={menuItems} />
      <div className="sidebar-note"><RobotOutlined /><div><b>Agent 辅助</b><span>后续可通过对话自动填写同一张表单，提交前仍由你确认。</span></div></div>
    </Sider>
    <Layout>
      <Header className="topbar"><div><Text type="secondary">当前员工</Text><strong>{user.name}（{employeeCode}）</strong><Space size={4}>{user.roles.map(role => <Tag key={role}>{role === "EMPLOYEE" ? "员工" : role === "BUILDING_MANAGER" ? "楼长" : role === "PURCHASER" ? "采购员" : "管理员"}</Tag>)}</Space></div><Button icon={<LogoutOutlined />} onClick={() => void onLogout()}>退出登录</Button></Header>
      <Content className="main-content">
        {activeMenu === "approvals" ? <ApprovalPage onPendingCountChange={setPendingApprovalCount} /> : activeMenu === "procurement" ? <ProcurementPage /> : activeMenu === "mine" ? <section>
          <div className="page-heading"><div><Title level={2}>我的采购申请</Title><Text type="secondary">查看草稿与已提交申请的当前进度</Text></div><Button type="primary" icon={<FileAddOutlined />} onClick={startNew}>新建申请</Button></div>
          <Card className="surface-card" bordered={false}><Table rowKey="requirement_id" loading={listLoading} columns={columns} dataSource={list} pagination={{ total: listTotal, pageSize: 20, hideOnSinglePage: true }} scroll={{ x: 760 }} /></Card>
        </section> : <Spin spinning={loading}><section>
          <div className="page-heading form-heading"><div><Space align="center"><Title level={2}>{current ? "编辑采购申请" : "新建采购申请"}</Title>{current && statusTag(current.status)}</Space><br/><Text type="secondary">{current ? `${current.requirement_no} · 版本 ${current.version}` : "填写采购需求，可随时保存为草稿"}</Text></div>
            <Space wrap>{current?.status === "DRAFT" && <Button danger onClick={cancelDraft}>取消草稿</Button>}{current?.status === "REJECTED" && <Button type="primary" onClick={() => void reviseRejected()}>修改后重新提交</Button>}<Button icon={<HistoryOutlined />} disabled={!current} onClick={() => void findRecommendations()}>查历史供应商</Button><Button icon={<SaveOutlined />} disabled={!editable} onClick={() => void saveDraft()}>{current ? "保存修改" : "保存草稿"}</Button><Button type="primary" icon={<CheckCircleOutlined />} disabled={!current || current.status !== "DRAFT"} onClick={submit}>提交审批</Button></Space>
          </div>
          {current && <Card className="overview-card" bordered={false}><Row gutter={[24,18]} align="middle"><Col xs={24} lg={8}><Space direction="vertical" size={2}><Text type="secondary">申请人信息（系统自动带入）</Text><Text strong>{current.applicant.name} · {current.applicant.employee_no || employeeCode}</Text><Text>{current.applicant.phone || "联系电话未登记"}</Text></Space></Col><Col xs={24} sm={8} lg={5}><Statistic title="预计总价" value={money(current.total_amount, current.currency)} /></Col><Col xs={24} sm={8} lg={5}><Statistic title="申请时间" value={dateTime(current.requested_at)} /></Col><Col xs={24} sm={8} lg={6}><Text type="secondary">信息完整度</Text><Progress percent={completion} status={current.missing_fields.length ? "active" : "success"} /></Col></Row></Card>}
          {current?.missing_fields.length ? <Alert className="missing-alert" type="warning" showIcon message="草稿还不能提交审批" description={`请补充：${current.missing_fields.map((field) => fieldNames[field] || field).join("、")}，然后先保存修改。`} /> : current?.status === "DRAFT" ? <Alert className="missing-alert" type="success" showIcon message="信息已完整，可以核对后提交审批" /> : null}
          <Form form={form} layout="vertical" initialValues={{ currency: "CNY", unit: "台" }} disabled={!editable} onValuesChange={(changed) => form.setFields((Object.keys(changed) as Array<keyof RequirementFormValues>).map(name => ({ name, errors: [] })))}>
            <Card className="surface-card form-section" bordered={false} title={<><span className="step-number">1</span>申请信息</>}><Row gutter={20}>
              <Col xs={24} md={6}><Form.Item name="building_id" label="所属楼宇" required><Select placeholder="请选择审批楼宇" options={buildings.map(item => ({ value: item.building_id, label: item.building_name }))} /></Form.Item></Col>
              <Col xs={24} md={6}><Form.Item name="category_name" label="申请类别" required><Select placeholder="请选择申请类别" options={["电气","暖通","弱电","机房环境","工器具","算力服务器","IDC网络","其他"].map(value => ({ value, label: value }))} /></Form.Item></Col>
              <Col xs={24} md={6}><Form.Item name="application_location" label="具体申请地点" required><Input placeholder="例如：3楼 A03 机房" /></Form.Item></Col>
              <Col xs={24} md={6}><Form.Item name="device_type" label="设备类型" required><Input placeholder="例如：服务器、交换机、UPS" /></Form.Item></Col>
              <Col span={24}><Form.Item name="application_reason" label="申请原因" required><Input.TextArea rows={3} maxLength={5000} showCount placeholder="请说明采购用途、业务背景及必要性" /></Form.Item></Col>
            </Row></Card>
            <Card className="surface-card form-section" bordered={false} title={<><span className="step-number">2</span>设备信息</>}><Row gutter={20}>
              <Col xs={24} md={8}><Form.Item name="product_name" label="设备名称" required><Input placeholder="例如：机架式服务器" /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="brand" label="品牌" required><Input placeholder="例如：浪潮" /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="model" label="设备型号" required><Input placeholder="请输入完整型号" /></Form.Item></Col>
              <Col span={24}><Form.Item name="product_full_name" label="具体设备全称" required><Input placeholder="例如：浪潮 2U 双路机架式服务器" /></Form.Item></Col><Col span={24}><Form.Item name="specification" label="规格参数" required><Input.TextArea rows={3} maxLength={5000} showCount placeholder="填写配置、尺寸、性能要求及其他技术参数" /></Form.Item></Col>
            </Row></Card>
            <Card className="surface-card form-section" bordered={false} title={<><span className="step-number">3</span>数量与供应商</>}><Row gutter={20}>
              <Col xs={12} md={5}><Form.Item name="quantity" label="数量" required><InputNumber min={1} step={1} precision={0} className="full-width" placeholder="请输入整数" /></Form.Item></Col><Col xs={12} md={4}><Form.Item name="unit" label="单位" required><Input placeholder="例如：台、套、批" /></Form.Item></Col><Col xs={24} md={7}><Form.Item name="unit_price" label="参考单价" required><InputNumber min={0} precision={2} className="full-width" addonBefore="¥" /></Form.Item></Col>
              <Col xs={24} md={8}><Form.Item label="预计总价"><div className="calculated-total">¥ {total.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}<span>系统自动计算</span></div></Form.Item></Col><Col xs={24} md={16}><Form.Item name="supplier_name" label="供应商" required extra="保存草稿时可以暂不填写；提交审批前必须填写。"><Input placeholder="可自行填写，也可先保存后查询历史供应商" /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="currency" label="币种" required><Select options={[{ value: "CNY", label: "人民币（CNY）" }]} /></Form.Item></Col>
            </Row>
              <div className="history-guide">
                <Steps size="small" current={current ? 1 : 0} items={[
                  { title: "保存草稿", description: current ? `已保存：${current.requirement_no}` : "先保存当前采购信息并生成申请单号" },
                  { title: "查询历史供应商", description: "系统根据已保存的设备信息匹配历史采购记录" },
                ]} />
                <Alert
                  type={current ? "success" : "info"}
                  showIcon
                  message={current ? "草稿已保存，现在可以查询历史供应商" : "请先保存草稿，再查询历史供应商"}
                  description={current ? "如果修改了设备名称、品牌、型号或规格，请先保存修改，再重新查询。" : "历史推荐必须关联一张已保存的采购申请，因此未保存时暂不能查询。"}
                />
                <Button type="dashed" block icon={<SearchOutlined />} disabled={!current} onClick={() => void findRecommendations()}>
                  {current ? "从历史采购记录中查找相似设备的供应商" : "请先保存草稿后再查询历史供应商"}
                </Button>
              </div>
            </Card>
          </Form>
          <Flex justify="flex-end" gap={12} className="bottom-actions" wrap><Button icon={<SaveOutlined />} disabled={!editable} onClick={() => void saveDraft()}>{current ? "保存修改" : "保存草稿"}</Button><Button type="primary" size="large" icon={<CheckCircleOutlined />} disabled={!current || current.status !== "DRAFT"} onClick={submit}>核对并提交审批</Button></Flex>
        </section></Spin>}
      </Content>
    </Layout>
    <Drawer title="历史供应商推荐" width={560} open={recommendationOpen} onClose={() => setRecommendationOpen(false)}>
      <Paragraph type="secondary">以下结果来自相似的已完成采购单，仅供参考。你仍可填写其他供应商。</Paragraph>
      {!recommendations.length ? <Empty description="暂未找到相似历史记录" /> : recommendations.map(item => <Card key={`${item.rank}-${item.latest_purchase.order_id}`} className="recommendation-card"><Flex justify="space-between" align="start"><div><Tag color="cyan">推荐 {item.rank}</Tag><Title level={4}>{item.supplier_name}</Title></div><Button type="primary" ghost onClick={() => chooseRecommendation(item)}>采用此参考</Button></Flex><Paragraph>{item.reason}</Paragraph><Descriptions size="small" column={2}><Descriptions.Item label="历史采购次数">{item.historical_order_count} 次</Descriptions.Item><Descriptions.Item label="最近订单">{item.latest_purchase.order_no}</Descriptions.Item><Descriptions.Item label="历史单价">{money(item.latest_purchase.unit_price, item.latest_purchase.currency)}</Descriptions.Item><Descriptions.Item label="入库时间">{dateTime(item.latest_purchase.received_at)}</Descriptions.Item><Descriptions.Item label="设备">{item.latest_purchase.product_name || "—"}</Descriptions.Item><Descriptions.Item label="品牌型号">{[item.latest_purchase.brand,item.latest_purchase.model].filter(Boolean).join(" ") || "—"}</Descriptions.Item></Descriptions></Card>)}
    </Drawer>
  </Layout>;
}
function LoginPage({ onLoggedIn }: { onLoggedIn: (user: CurrentUser) => void }) {
  const { message } = AntApp.useApp();
  const [loading, setLoading] = useState(false);
  async function submit(values: { identifier: string; password: string }) {
    setLoading(true);
    try { onLoggedIn(await api.login(values.identifier, values.password)); }
    catch (error) { message.error((error as Error).message); }
    finally { setLoading(false); }
  }
  return <main className="login-page"><Card className="login-card" bordered={false}>
    <div className="login-brand"><div className="brand-mark"><ApartmentOutlined /></div><div><Title level={2}>采购智管</Title><Text type="secondary">数据中心采购平台</Text></div></div>
    <Title level={3}>员工登录</Title><Paragraph type="secondary">使用员工工号或已登记的联系电话登录</Paragraph>
    <Form layout="vertical" size="large" onFinish={submit} requiredMark={false}>
      <Form.Item name="identifier" label="工号或联系电话" rules={[{ required: true, message: "请输入工号或联系电话" }]}><Input prefix={<UserOutlined />} autoComplete="username" placeholder="请输入员工工号或联系电话" /></Form.Item>
      <Form.Item name="password" label="密码" rules={[{ required: true, message: "请输入密码" }]}><Input.Password prefix={<LockOutlined />} autoComplete="current-password" placeholder="请输入登录密码" /></Form.Item>
      <Button type="primary" htmlType="submit" loading={loading} block>登录</Button>
    </Form>
    <Alert className="login-help" type="info" showIcon message="忘记密码？" description="当前版本请联系系统管理员核验身份并重置密码。" />
  </Card></main>;
}

function RootContent() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [restoring, setRestoring] = useState(true);
  useEffect(() => { api.me().then(setUser).catch(() => setUser(null)).finally(() => setRestoring(false)); }, []);
  if (restoring) return <div className="session-loading"><Spin size="large" tip="正在恢复登录状态" /></div>;
  if (!user) return <LoginPage onLoggedIn={setUser} />;
  return <AppContent user={user} onLogout={async () => { await api.logout(); setUser(null); }} />;
}

export default function App() { return <AntApp><RootContent /></AntApp>; }
