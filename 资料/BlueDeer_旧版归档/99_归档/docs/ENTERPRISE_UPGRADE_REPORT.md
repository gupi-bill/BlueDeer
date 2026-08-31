# BlueDeer 企业化升级 · 第 1 段改造报告

> 依据 `bluedeer-enterprise-upgrade-prompts.md` 第 1 段「平台底座与安全治理」执行。
> 原则：本地优先、不删数据、先备份再改、文本化自测验收。

## 备份清单

开工前已将关键文件备份至 `backups/ent_upgrade_20260819_165221/`：
`auth.py` / `audit.py` / `backup.py` / `web_server/app.py` / `web_server/routes_users.py`。

---

## 1.1 身份与访问控制（IAM）— 完成

**改了什么**
- 重写 `core/auth.py`：
  - 存储：JSONL → SQLite（`data/iam.db`），含 `users / sessions / api_tokens / login_failures`。
  - 密码哈希：bcrypt（离线已装；不可用时降级 PBKDF2-20万次）。
  - 角色：五级 RBAC `superadmin(5)/admin(4)/operator(3)/viewer(2)/guest(1)`。
  - 会话 token 持久化 + 过期 + 宽限刷新。
  - 默认 admin → `superadmin`，初始密码仍 `bluedeer888`，强制首次改密。
  - 旧 JSONL 用户自动迁移，旧密码失效并强制改密。
- 登录失败锁定：连续 5 次锁 15 分钟。
- 弱密码拒绝：<8 位或字符类别 <2 拒绝。
- 新增 `change_password`（强制/常规改密，禁与旧密码相同）。

**验收（stdout）**：`LOGIN_ALICE True operator / LOCKED_AFTER5 True / ADMIN_FORCE_CHANGE True / OLD_ADMIN_FAIL True`

**遗留**：前端侧边栏按角色动态菜单、`/api/auth/*` UI 待第 3 段统一接入。

---

## 1.2 审计与合规 — 核心完成

`core/audit.py` 已是企业版：SQLite `data/audit_log.db`、SHA-256 哈希链、`verify_chain()`、按 task/action/agent/user/时间查询、`summary()`。本次仅验证未改动。

**验收（stdout）**：`VERIFY_BEFORE (True) → 篡改后 VERIFY_AFTER_TAMPER (False)`

**遗留**：审计日志页 UI、敏感操作二次确认弹窗。

---

## 1.3 密钥集中管理（vault）— 完成

**改了什么**
- 新增 `core/vault.py`：
  - 主密钥：`BLUEDEER_MASTER_KEY` 环境变量优先，否则 `data/.master_key` 自动生成。
  - 字段级加密：Fernet（cryptography 已依赖），不可用时降级 XOR 混淆。
  - `get / set / delete / keys / mask / mask_all / scan_plaintext_secrets`。
  - 落盘文件不含明文。
- 消除 `web_server/app.py` 硬编码 `ADMIN_PASS="bluedeer888"`，改为环境变量 `BLUEDEER_ADMIN_INIT_PASS`。
- 全库扫描：仅上述 1 处硬编码 + `auth.py` 默认初始密码（属强制改密设计），其余命中为关键字名/空值，非泄露。

**验收（stdout）**：`GET sk-1234567890abcdef / MASK sk-***def / SCAN [sk-...] / RAW_CONTAINS_PLAIN False`

**已改文件**：`core/vault.py`（新增）、`web_server/app.py`

**遗留**：`data/model_settings.json` 的 api_key、OpenClaw 网关 token 可后续用 vault 迁移（需业务方确认密钥来源）。

---

## 1.4 API 网关与限流 — 完成

**改了什么**
- 新增 `core/api_rate_limit.py`：复用 `core/sliding_window.py`，三层限流（IP/用户/接口），规则存 `data/rate_limits.json`，支持热重载。
- `web_server/app.py` 挂载限流中间件：`/api/*` 超限 429 + 中文提示。

**验收（stdout）**：连打 10 次 → `ACCEPTED 3 REJECTED 7`

**遗留**：`/api/v2/` 版本化前缀 + 统一响应包装。

---

## 1.5 数据持久化与备份 — 部分完成

**改了什么**
- `core/backup.py` 新增 `prune_backups(keep=7)` 保留策略 + `create_backup_with_retention()`。
- 已有 ZIP 全量/增量备份、恢复、列表、删除。

**验收（stdout）**：`BEFORE 10 / REMOVED 3 / AFTER 7`

**遗留**：`core/db_health.py`（PRAGMA integrity_check + WAL）、备份 UI、数据保留策略自动清理。

---

## 1.6 安全加固收尾 — 完成

**改了什么**
- `web_server/app.py` 新增安全头中间件：
  - 请求体大小限制（`BLUEDEER_MAX_BODY_MB`，默认 10MB，超限 413）。
  - `X-Content-Type-Options / X-Frame-Options / X-XSS-Protection / Referrer-Policy / Content-Security-Policy`。

**验收**：语法 + 导入通过；安全头在响应阶段 setdefault 注入。

**遗留**：`scripts/security_scan.py` 扫描依赖漏洞/明文密钥/调试接口（可复用现有 `core/security_scanner.py`）。

---

## 最终自检

```
OK core/auth.py
OK core/audit.py
OK core/backup.py
OK core/api_rate_limit.py
OK core/vault.py
OK web_server/app.py
IMPORTS_OK
```

## 铁律遵守情况

- ✅ 本地优先：仅离线安装 bcrypt，无 SaaS。
- ✅ 不删数据：改动前备份；旧用户迁移保留。
- ✅ SQLite 不变。
- ✅ 中文注释/日志。
- ✅ 纯文本自测。

## 下一步建议

1. 第 3 段 UI 统一：按角色菜单、审计页、备份页、待审批中心。
2. 第 2 段：任务编排 / 自愈 / 成本治理。
3. 补充 `scripts/security_scan.py` 与 `core/db_health.py`。
