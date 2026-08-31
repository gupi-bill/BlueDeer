# Odysseus 工具使用规范（强制）

你已通过 **odysseus MCP 桥接**连接本地自托管 AI 工作台 Odysseus（地址 http://127.0.0.1:7000）。这是已接好的原生工具，不是让你去翻代码或自己拼 HTTP。

## 可用工具（odysseus_* 开头的 MCP 工具）
- `odysseus_capabilities`：先调它确认当前 token 能干啥
- `odysseus_todos_list` / `odysseus_todo_add` / `odysseus_todo_update` / `odysseus_todo_toggle` / `odysseus_todo_delete`：待办/笔记
- `odysseus_memory_list` / `odysseus_memory_add`：长期记忆
- `odysseus_calendar_list` / `odysseus_calendar_create` / `odysseus_calendar_delete`：日历事件
- `odysseus_documents_list` / `odysseus_document_read` / `odysseus_document_create` / `odysseus_document_delete`：文档库
- `odysseus_emails_list` / `odysseus_email_read` / `odysseus_email_draft` / `odysseus_email_send`：邮件
- `odysseus_cookbook_tasks` / `odysseus_cookbook_servers` / `odysseus_cookbook_output` / `odysseus_cookbook_cached`：模型厨房（只读）

## 强制规则
1. **当用户要查看或操作其 Odysseus 数据（待办 / 记忆 / 日历 / 文档 / 邮件）时，必须优先调用上面的 odysseus_* 工具。**
2. **严禁**使用 `webfetch`、浏览器工具或 `curl`/shell 直接访问 `127.0.0.1:7000` 或 `/api/codex/*`——odysseus_* 工具就是为此封装好的，重复造轮子一律禁止。
3. 涉及发邮件（`odysseus_email_send`）必须先得到用户明确确认，并在调用时传 `confirm=true`，否则桥会拒绝。
4. 首次对接不确定能力范围时，先调 `odysseus_capabilities`。
