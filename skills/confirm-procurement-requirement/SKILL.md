---
name: confirm-procurement-requirement
description: 指导采购Agent查看、列出、提交或取消员工采购申请，并严格依据后端结果描述状态。
keywords: 查看草稿,查看采购单,采购单,确认提交,提交审批,信息无误,确认无误,采购进度,申请状态,审批进度
agents: general
enabled: true
---

# 采购草稿查看与确认

## 目标

用户要求查看、核对、查询状态或确认提交时，先调用`get_requirement_detail`读取当前会话草稿的最新事实，再进行回复。

## 展示要求

- 展示后端返回的需求编号、状态、版本、需求人和时间。
- 展示已有的采购原因、地点、设备、品牌、型号、规格、数量、供应商、单价和总金额。
- 分开展示`missing_fields`、`conflicts`和`warnings`。
- 不用Redis状态或历史对话替代后端详情。

## 正式提交

当用户明确说“确认提交”“直接提交”或类似表达时：

1. 本轮同时补充字段时，先调用`update_requirement_draft`。
2. 调用`get_requirement_detail`获取最新草稿。
3. `missing_fields`或`conflicts`不为空时停止并说明阻塞项。
4. 信息完整后调用`submit_requirement`，只有返回`PENDING_APPROVAL`才能声称提交成功。

## 取消草稿

- 用户必须明确确认取消并提供原因，缺少原因时先追问。
- 调用`get_requirement_detail`读取最新状态，再调用`cancel_requirement`。
- 只有返回`CANCELLED`才能声称取消成功；非`DRAFT`状态不得取消。

## 本人申请列表

- 用户要求“列出我的采购申请”时调用`list_my_requirements`，可按状态分页筛选。
- 结果只代表当前员工本人数据，不自动切换当前活动草稿。

## 禁止事项

- 不修改申请人、状态、版本、总金额或审批字段。
- 不直接访问数据库，不绕过后端权限。
- 不因为用户说“确认”就调用创建或更新工具。
- 不把未成功的提交或取消描述为已完成。
