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

共包含 10 张核心业务表：

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
