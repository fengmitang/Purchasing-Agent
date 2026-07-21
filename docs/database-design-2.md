# 数据库设计文档（Demo版）

> 项目：数据中心采购流程自动化 Agent\
> 数据库：MySQL 8.0+\
> 版本：Demo MVP v1.0

------------------------------------------------------------------------

# 1. 数据库设计目标

本数据库用于支撑数据中心采购流程自动化 Agent Demo。

相比生产级采购系统，本版本重点保证：

-   采购白名单数据可存储和检索；
-   Agent 可以理解用户采购需求；
-   Agent 可以基于白名单和供应商信息生成推荐；
-   用户确认后形成采购订单；
-   完整跑通"需求提出 → 智能推荐 → 采购生成"的流程。

本 Demo 不实现复杂企业功能，例如：

-   多级审批体系；
-   复杂权限管理；
-   库存管理；
-   验收管理；
-   完整审计体系。

------------------------------------------------------------------------

# 2. 数据库整体结构

数据库名称：

    purchasing-agent

共包含 13 张核心业务表：

  编号   表名                   作用
  ------ ---------------------- ----------------
  1      product_category       产品分类
  2      product_whitelist      采购白名单产品
  3      supplier               供应商信息
  4      product_supplier       产品供应商关系
  5      agent_session          Agent会话
  6      agent_message          Agent消息记录
  7      purchase_requirement   采购需求
  8      recommendation         Agent推荐结果
  9      purchase_order         采购订单
  10     operation_log          操作日志
  11     employee               员工及流程参与人
  12     purchase_approval      采购申请审批记录
  13     purchase_status_history 采购申请和采购单状态历史

------------------------------------------------------------------------

# 3. 数据表设计

## 3.1 product_category 产品分类表

### 作用

保存数据中心采购物品分类。

例如：

-   电气
-   暖通
-   弱电
-   机房环境
-   工器具
-   算力服务器

作为白名单产品的分类基础。

### 字段

  字段          类型       说明
  ------------- ---------- ----------
  id            BIGINT     分类ID
  name          VARCHAR    分类名称
  description   VARCHAR    分类描述
  created_at    DATETIME   创建时间

------------------------------------------------------------------------

## 3.2 product_whitelist 产品白名单表

### 作用

保存允许采购的数据中心配件。

这是 Agent 推荐系统最核心的数据表。

数据来源：

-   数据中心配件采购白名单 Excel
-   后续人工维护数据

### 存储内容

包括：

-   产品名称
-   品牌
-   型号
-   规格参数
-   单位
-   分类

### 字段

  字段            说明
  --------------- ----------
  id              产品ID
  category_id     所属分类
  product_name    产品名称
  brand           品牌
  model           型号
  specification   规格参数
  unit            采购单位
  status          状态
  created_at      创建时间
  updated_at      更新时间

------------------------------------------------------------------------

## 3.3 supplier 供应商表

### 作用

保存供应商基础信息。

### 字段

  字段            说明
  --------------- ------------
  id              供应商ID
  supplier_name   供应商名称
  contact         联系人
  phone           联系电话
  level           供应商等级
  status          状态
  created_at      创建时间

------------------------------------------------------------------------

## 3.4 product_supplier 产品供应商关系表

### 作用

描述产品和供应商之间的供应关系。

支持：

一个产品多个供应商。

保存：

-   参考价格；
-   交付周期。

### 字段

  字段            说明
  --------------- ----------
  id              关系ID
  product_id      产品ID
  supplier_id     供应商ID
  price           参考价格
  delivery_days   交付周期
  created_at      创建时间

------------------------------------------------------------------------

## 3.5 agent_session Agent会话表

### 作用

保存一次用户与采购 Agent 的交互过程。

例如：

用户： \> 我要采购10块8T硬盘

创建一个 Session。

### 字段

  字段         说明
  ------------ ----------
  id           主键
  session_id   会话编号
  user_id      用户ID
  status       会话状态
  created_at   创建时间

------------------------------------------------------------------------

## 3.6 agent_message Agent消息表

### 作用

保存 Agent 对话上下文。

包括：

-   用户输入；
-   Agent回复；
-   系统消息。

### 字段

  字段         说明
  ------------ ----------
  id           消息ID
  session_id   所属会话
  role         消息角色
  content      消息内容
  created_at   时间

------------------------------------------------------------------------

## 3.7 purchase_requirement 采购需求表

### 作用

保存 Agent 从自然语言中抽取出的结构化采购需求。

例如：

用户输入：

"采购10块希捷8T硬盘"

Agent抽取：

``` json
{
"product":"硬盘",
"brand":"希捷",
"capacity":"8T",
"quantity":10
}
```

保存到该表。

### 字段

  字段            说明
  --------------- ----------
  id              需求ID
  session_id      来源会话
  product_name    产品名称
  brand           品牌要求
  model           型号要求
  specification   规格
  quantity        数量
  unit            单位
  status          需求状态
  created_at      创建时间

------------------------------------------------------------------------

## 3.8 recommendation 推荐结果表

### 作用

保存 Agent 推荐结果。

记录：

-   推荐哪个产品；
-   推荐哪个供应商；
-   推荐理由；
-   用户是否选择。

### 字段

  字段             说明
  ---------------- ----------
  id               推荐ID
  requirement_id   需求ID
  product_id       产品ID
  supplier_id      供应商ID
  score            推荐评分
  reason           推荐原因
  selected         是否选择
  created_at       时间

------------------------------------------------------------------------

## 3.9 purchase_order 采购订单表

### 作用

模拟采购执行结果。

用户确认推荐后生成订单。

### 字段

  字段             说明
  ---------------- ----------
  id               订单ID
  order_no         订单编号
  requirement_id   需求ID
  product_id       产品ID
  supplier_id      供应商ID
  quantity         数量
  amount           金额
  status           订单状态
  created_at       时间

------------------------------------------------------------------------

## 3.10 operation_log 操作日志表

### 作用

记录关键操作。

例如：

-   创建需求；
-   Agent生成推荐；
-   用户确认采购。

### 字段

  字段         说明
  ------------ ----------
  id           日志ID
  action       操作类型
  operator     操作人
  content      操作内容
  created_at   时间

------------------------------------------------------------------------

# 4. Agent流程与数据库对应关系

## 4.1 整体流程

    用户提出采购需求

            |
            v

    agent_session
    创建会话

            |
            v

    agent_message
    保存用户输入

            |
            v

    LLM理解需求

            |
            v

    purchase_requirement
    保存结构化需求

            |
            v

    查询:

    product_whitelist
    product_supplier
    supplier

            |
            v

    Agent生成推荐

            |
            v

    recommendation
    保存推荐结果

            |
            v

    用户确认

            |
            v

    purchase_order
    生成采购订单

            |
            v

    operation_log
    记录流程

------------------------------------------------------------------------

# 5. Agent模块与数据表映射

  Agent功能            对应表
  -------------------- ----------------------------
  保存聊天上下文       agent_session
  保存历史消息         agent_message
  需求理解与参数抽取   purchase_requirement
  白名单检索           product_whitelist
  供应商匹配           product_supplier、supplier
  推荐生成             recommendation
  用户确认采购         purchase_order
  流程追踪             operation_log

------------------------------------------------------------------------

# 6. Demo开发重点

数据库实现优先级：

## 第一阶段：数据基础

完成：

-   product_category
-   product_whitelist
-   supplier
-   product_supplier

目标：

让 Agent 可以查询采购知识库。

## 第二阶段：Agent流程

完成：

-   agent_session
-   agent_message
-   purchase_requirement

目标：

实现：

自然语言 → 结构化采购需求。

## 第三阶段：推荐和采购

完成：

-   recommendation
-   purchase_order

目标：

实现：

需求 → 推荐 → 下单。

## 第四阶段

完成：

-   operation_log

目标：

增强 Demo 展示效果。

------------------------------------------------------------------------

# 7. 员工申请、楼长审批与采购完成流程扩展

本节是 `0003_procurement_workflow` 迁移对应的正式设计。M1 阶段采用
“一张采购申请对应一种设备”，与历史 Excel 一行一条采购记录保持一致。申请人、
楼长（专业工程师）和采购人员统一使用员工主数据，不建立独立申请人表。

流程如下：

    员工提交采购申请
          |
          v
    楼长/专业工程师审批
          |
          +-- 驳回/退回 -> 员工修改并形成新版本后重新提交
          |
          +-- 通过 -> 生成采购单并交给采购人员
                              |
                              v
                    询价核价 -> 签合同 -> 验收入库
                              |
                              v
                    入库完成，采购单完成

询价核价、签合同和验收入库的详细业务过程不在当前系统展开，只记录状态和关键
时间；入库时间必须重点记录。审批、采购和状态变化采用追加记录或版本方式，禁止
静默覆盖历史事实。

## 7.1 employee 员工表

### 作用

统一保存申请员工、审批人和采购人员。员工工号是正式业务唯一标识；历史导入数据
缺少工号时允许为空，后续人工补充。姓名不能作为全局唯一键。

| 字段 | 类型 | 是否必填 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | 是 | 员工 ID |
| employee_no | VARCHAR(50) | 否 | 工号，非空时唯一 |
| name | VARCHAR(100) | 是 | 姓名 |
| phone | VARCHAR(50) | 否 | 联系方式 |
| role | VARCHAR(50) | 否 | 员工、楼长/专业工程师、采购人员等角色 |
| status | VARCHAR(20) | 是 | 默认 `ACTIVE` |
| created_at | DATETIME(6) | 是 | 创建时间（UTC） |
| updated_at | DATETIME(6) | 是 | 更新时间（UTC） |
| version | INT | 是 | 乐观锁版本，默认 1 |

索引与约束：`employee_no` 唯一；姓名、电话建立普通索引。

## 7.2 purchase_requirement 采购申请单

### 作用

在原采购需求表基础上承载正式采购申请。表中同时保存员工外键和申请时的工号、
姓名、联系方式快照，确保员工主数据变更后历史申请仍可还原。被驳回或退回的申请
修改重提时形成新版本，通过 `previous_requirement_id` 串联，不覆盖原申请。

### 主要字段

| 字段 | 类型 | 是否必填 | 说明 |
| --- | --- | --- | --- |
| requirement_no | VARCHAR(100) | 是 | 申请单号，唯一 |
| session_id | VARCHAR(100) | 否 | 来源 Agent 会话；历史导入可空 |
| employee_id | BIGINT UNSIGNED | 否 | 申请员工外键 |
| applicant_employee_no | VARCHAR(50) | 否 | 申请人工号快照 |
| applicant_name | VARCHAR(100) | 否 | 申请人姓名快照 |
| applicant_phone | VARCHAR(50) | 否 | 申请人联系方式快照 |
| requested_at | DATETIME(6) | 否 | 员工首次提出申请的时间 |
| submitted_at | DATETIME(6) | 否 | 当前版本提交审批时间 |
| revision_no | INT | 是 | 版本号，默认 1 |
| previous_requirement_id | BIGINT UNSIGNED | 否 | 上一版本申请外键 |
| category_id | BIGINT UNSIGNED | 否 | 产品分类外键 |
| category_name | VARCHAR(100) | 否 | 申请时分类名称快照 |
| application_reason | TEXT | 否 | 采购原因 |
| application_location | VARCHAR(200) | 否 | 申请地点 |
| device_type | VARCHAR(100) | 否 | 设备类型 |
| product_id | BIGINT UNSIGNED | 否 | 白名单产品外键 |
| product_name | VARCHAR(200) | 是 | 设备名称 |
| product_full_name | VARCHAR(500) | 否 | 具体设备全称 |
| brand | VARCHAR(100) | 否 | 品牌 |
| model | VARCHAR(200) | 否 | 设备型号 |
| specification | TEXT | 否 | 规格参数 |
| quantity | DECIMAL(18,4) | 否 | 可计算的采购数量 |
| quantity_raw | VARCHAR(100) | 否 | 无法直接数值化的原始数量 |
| unit | VARCHAR(20) | 否 | 单位 |
| supplier_id | BIGINT UNSIGNED | 否 | 供应商外键 |
| supplier_name | VARCHAR(200) | 否 | 申请时供应商名称快照 |
| unit_price | DECIMAL(18,2) | 否 | 单价 |
| unit_price_raw | VARCHAR(100) | 否 | 无法直接数值化的原始价格 |
| total_amount | DECIMAL(18,2) | 否 | 总价 |
| currency | VARCHAR(3) | 是 | 币种，默认 `CNY` |
| status | VARCHAR(30) | 否 | 当前申请状态 |
| source_reference | VARCHAR(255) | 否 | 导入来源唯一引用，防止重复导入 |
| created_at / updated_at | DATETIME | 是 | 创建和更新时间 |
| version | INT | 是 | 乐观锁版本，默认 1 |

历史 Excel 中分类、会话、数量、时间或联系方式缺失时允许保存为空，禁止使用占位
值编造业务数据。`product_whitelist.category_id` 同步调整为可空。

申请状态建议使用：`DRAFT`、`PENDING_APPROVAL`、`REJECTED`、`APPROVED`、
`PURCHASING`、`QUOTED`、`CONTRACTED`、`RECEIVED`、`COMPLETED`、
`CANCELLED`。状态是否合法由 Service 状态机校验，数据库使用字符串保存以便后续扩展。

## 7.3 purchase_approval 采购审批记录表

### 作用

每一次提交、重新提交和审批动作都形成独立记录。审批人必须关联员工表，同时保存
审批当时的工号、姓名和联系方式快照。楼长端通过 `requirement_id` 读取完整申请单。

| 字段 | 类型 | 是否必填 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | 是 | 审批记录 ID |
| requirement_id | BIGINT UNSIGNED | 是 | 采购申请外键 |
| revision_no | INT | 是 | 被审批的申请版本 |
| approver_id | BIGINT UNSIGNED | 是 | 审批人员工外键 |
| approver_employee_no | VARCHAR(50) | 否 | 审批人工号快照 |
| approver_name | VARCHAR(100) | 是 | 审批人姓名快照 |
| approver_phone | VARCHAR(50) | 否 | 审批人联系方式快照 |
| action | VARCHAR(30) | 是 | `APPROVED`、`REJECTED`、`RETURNED`、`TRANSFERRED` |
| comment | TEXT | 否 | 审批评价或拒绝/退回原因 |
| submitted_at | DATETIME(6) | 是 | 送审时间 |
| acted_at | DATETIME(6) | 是 | 审批动作时间 |
| idempotency_key | VARCHAR(128) | 否 | 防止重复审批，非空时唯一 |
| created_at | DATETIME(6) | 是 | 记录创建时间 |

审批结果写入本表后，在同一事务中更新采购申请当前状态并追加状态历史。员工端通过
申请状态及最新审批记录获得反馈。禁止申请人审批自己的申请，该规则由 Service 校验。

## 7.4 purchase_order 采购单扩展

审批通过后生成采购单并交给采购人员。原有产品、供应商、数量和金额字段继续保留，
新增采购人员快照和关键节点时间。

| 新增字段 | 类型 | 是否必填 | 说明 |
| --- | --- | --- | --- |
| supplier_name | VARCHAR(200) | 否 | 选定供应商名称快照 |
| unit_price | DECIMAL(18,2) | 否 | 实际采购单价 |
| purchaser_id | BIGINT UNSIGNED | 否 | 采购人员工外键 |
| purchaser_employee_no | VARCHAR(50) | 否 | 采购人员工号快照 |
| purchaser_name | VARCHAR(100) | 否 | 采购人员姓名快照 |
| purchaser_phone | VARCHAR(50) | 否 | 采购人员联系方式快照 |
| purchasing_started_at | DATETIME(6) | 否 | 开始采购时间 |
| quoted_at | DATETIME(6) | 否 | 询价核价完成时间 |
| contracted_at | DATETIME(6) | 否 | 合同签订时间 |
| received_at | DATETIME(6) | 否 | 验收入库时间，重点记录 |
| completed_at | DATETIME(6) | 否 | 采购完成时间 |
| updated_at | DATETIME(6) | 是 | 更新时间 |
| version | INT | 是 | 乐观锁版本，默认 1 |

入库完成时必须在同一事务中写入 `received_at` 和 `completed_at`，将采购单状态更新为
`COMPLETED`，并追加状态历史。询价核价和合同不建立独立业务表。

## 7.5 purchase_status_history 状态历史表

### 作用

以追加方式记录采购申请和采购单的每一次状态变化，用于流程展示、员工反馈和审计。

| 字段 | 类型 | 是否必填 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | 是 | 状态记录 ID |
| requirement_id | BIGINT UNSIGNED | 条件必填 | 采购申请外键 |
| order_id | BIGINT UNSIGNED | 条件必填 | 采购单外键 |
| from_status | VARCHAR(30) | 否 | 变化前状态；首次状态可空 |
| to_status | VARCHAR(30) | 是 | 变化后状态 |
| operator_id | BIGINT UNSIGNED | 否 | 操作员工外键 |
| operator_employee_no | VARCHAR(50) | 否 | 操作人工号快照 |
| operator_name | VARCHAR(100) | 否 | 操作人姓名快照 |
| operator_phone | VARCHAR(50) | 否 | 操作人联系方式快照 |
| remark | TEXT | 否 | 状态变化说明 |
| changed_at | DATETIME(6) | 是 | 状态变化时间 |
| request_id | VARCHAR(128) | 否 | 请求追踪 ID |
| created_at | DATETIME(6) | 是 | 记录创建时间 |

`requirement_id` 与 `order_id` 至少一个非空。状态历史只追加、不修改、不物理删除。

## 7.6 关键关联与数据一致性

- 一个员工可以发起多张采购申请，也可以作为审批人或采购人员参与多张单据；
- 一张采购申请可以有多条审批记录和多条状态历史；
- 修改重提通过新申请版本和 `previous_requirement_id` 保留完整历史；
- 审批通过后才允许生成采购单；一个需求只允许一个活动采购任务；
- 申请人、审批人、采购人员均保存“员工外键 + 当时信息快照”；
- 金额使用 `DECIMAL`，时间按 UTC 保存；
- 状态变化、审批和采购完成必须在 Service 的同一事务中写入主表及历史表；
- 所有写操作必须校验角色、楼宇数据范围、当前状态、并发版本和幂等键。
