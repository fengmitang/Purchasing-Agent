# 采购白名单 Agent：最小协作规范

> 目标：两人使用 Vibe Coding 时，仍能稳定开发、容易合并，并让 `main` 分支始终可以演示。

## 1. 角色与代码边界

| 负责人 | 主责目录/模块 | 主要工作 |
| --- | --- | --- |
| A：业务流程与数据 | `backend/app/infrastructure/`、`backend/app/workflow/`、`backend/app/catalog/`、`backend/app/contracts/` | 数据库、导入、需求单、审批、采购、交付、入库、权限、审计和状态机 |
| B：Agent 与前端 | `backend/app/agent/`、`frontend/` | 对话、字段提取、追问、检索、推荐、Agent 测试，以及用于演示的薄前端 |

共同规则：

- Agent 只能读取产品、供应商、白名单和黑名单数据；不得直接写数据库。
- Agent 的固定输出为：`extracted_fields`、`missing_fields`、`recommendations`、`risks`、`evidence`、`requires_confirmation`。
- `backend/app/contracts/` 中的接口字段和状态枚举由 A 维护；B 需要变更时，先在 Issue 或 PR 中说明。
- 前端保持薄层：只显示、提交和确认；黑名单、审批、入库和状态变化均由后端校验。

## 2. 分支与 Pull Request

- `main`：稳定演示分支，禁止直接提交。
- 每项任务从最新 `main` 新建一个短分支；一个分支只做一个小目标。

```text
feat/workflow-request       # A：需求流程
feat/catalog-import         # A：产品/供应商导入
feat/agent-recommendation   # B：推荐和风险解释
feat/ui-approval            # B：审批页面
fix/receipt-quantity        # 修复问题
```

- 完成一个小目标后：提交 → 推送 → 创建 Pull Request（PR）→ 请对方检查 → 合并。
- A 是 `main` 的集成负责人：
  - A 的业务 PR：B 快速检查，A 合并；
  - B 的 Agent/UI PR：A 快速检查，A 合并。
- 合并前必须写清楚：做了什么、怎么验证、影响的接口/页面、已知限制。
- 不传压缩包、不复制粘贴文件、不让两个人在同一个分支上同时开发。

## 3. 每天的固定节奏

1. 开始前 10 分钟：同步昨天完成、今天目标、阻塞点、需要确认的字段或规则。
2. 下午 15 分钟：用真实接口联调一次；发现问题创建 Issue，不在聊天记录里遗忘。
3. 收工前：每个人推送当前分支；A 确保 `main` 至少保留一个可启动的演示版本。

超过 15 分钟仍无法确认的业务规则、接口字段或代码冲突，立即语音/屏幕共享决定，不各自猜测。

## 4. 最小开发流程

```text
同步 main → 新建分支 → 只改自己负责模块 → 本地验证 → 提交并推送 → PR → 对方检查 → 合并 main
```

常用命令：

```bash
# 开始任务
git switch main
git pull origin main
git switch -c feat/agent-recommendation

# 完成任务
git status
git add backend/app/agent
git commit -m "feat(agent): add whitelist recommendation"
git push -u origin feat/agent-recommendation

# 合并前同步主分支；有冲突时由该分支作者解决
git fetch origin
git merge origin/main
git push
```

## 5. 冲突与 Vibe Coding 规则

- 谁的分支产生冲突，谁负责解决；不要让 AI 在不了解业务的情况下自动选“保留左边/右边”。
- 发生冲突后，先找出两边要实现的业务目标，再保留同时满足两边目标的代码；解决后重新启动并走一次对应流程。
- 使用 Vibe Coding 时，每次提示词写明：允许修改的目录、禁止修改的目录、验收条件和不允许绕过的业务规则。
- 每次提交前至少验证：服务能启动、改动涉及的接口可调用、没有把密钥或本地配置提交进去。
- `.env` 只保留在本地；仓库只提交 `.env.example`。

## 6. 本周任务切分

| 日期 | A：业务流程与数据 | B：Agent 与前端 |
| --- | --- | --- |
| Day 1 | FastAPI/MySQL 骨架、表结构、导入、状态枚举 | Agents SDK、字段提取、追问、模拟检索 |
| Day 2 | 需求单、状态机、审批基础接口 | 黑白名单校验、候选检索、推荐说明 |
| Day 3 | 审批、采购单、审计 | 停产/未知处理、推荐快照、需求/审批页面 |
| Day 4 | 交付、到货、入库及数量校验 | Agent 联调、提示词防护、采购/入库页面 |
| Day 5 | 权限、异常修复、回归 | Agent 评测、演示数据和演示脚本 |

## 7. PR 模板

复制以下内容到每个 PR：

```markdown
## 做了什么

## 如何验证

## 影响的接口或页面

## 已知限制/待确认项
```
