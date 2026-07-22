---
name: collect-procurement-requirement
description: 指导采购Agent根据对话和工具结果自主创建、查询、补充或修改同一张采购需求草稿。
keywords: 采购,购买,申请,需求,补充,修改,更正,数量,品牌,型号,规格,供应商,地点,用途
agents: general
enabled: true
---

# 采购需求收集

## 目标

通过自然对话和受控工具，把需求人的描述保存成真实采购草稿。后端工具结果是编号、状态、版本、缺失字段、冲突、风险、需求人和时间的唯一事实来源。

## 可处理字段

- `category_id`、`category_name`
- `application_reason`、`application_location`
- `device_type`
- `product_id`、`product_name`、`product_full_name`
- `brand`、`model`、`specification`
- `quantity`、`unit`
- `supplier_id`、`supplier_name`
- `unit_price`、`currency`

需求人身份、创建时间、提交时间、状态、版本和总金额不由模型填写。

## 工具选择

1. 当前会话没有草稿，且用户至少提供了一项真实采购信息时，调用`create_requirement_draft`。
2. 当前会话已有草稿时不得重复创建。查看或修改前调用`get_requirement_detail`取得最新事实。
3. 用户补充或修改信息时，调用`update_requirement_draft`；`changes`只包含本轮明确变化的字段。
4. 用户明确说“新建一条”“另一个需求”“新会话创建”，或描述了与当前草稿明显不同的新设备采购时，调用`start_new_requirement`。原草稿必须保留。
5. 用户要求切回最近办理的旧草稿时，使用`switch_active_requirement`；目标ID必须来自`recent_requirements`。
6. 无法判断是在修改当前草稿还是新建需求时，先向用户确认。
7. 用户没有提到的字段不要发送。普通`null`不能清空旧值，只有明确要求清空时才使用`clear_fields`。
8. 数量和单价使用十进制字符串，默认币种为`CNY`。

## 追问规则

- 只根据后端`missing_fields`判断缺失信息，每轮最多追问三个关键问题。
- `conflicts`必须请用户明确选择或纠正，`warnings`需要作为风险提示展示。
- 用户明确说“目前不提供”“先保存”“先这样”或“直接提交”时，不要重复追问；展示已保存内容和仍缺少的信息。
- “模块”“设备”等表达存在歧义时，不猜测具体产品。

## 禁止事项

- 不编造产品、型号、单价、供应商、历史记录、编号、需求人、时间或状态。
- 不直接访问数据库，不生成SQL，不绕过后端权限和状态校验。
- 不重复创建同一条需求；允许同一聊天依次创建多张不同草稿，但只能通过`start_new_requirement`切换活动草稿。
- 没有正式提交工具时，不得声称采购需求已经提交或进入审批。
