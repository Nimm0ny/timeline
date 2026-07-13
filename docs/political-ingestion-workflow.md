# 时政信息源采集工作流

## 0. Define-First

- **Goal**：维护独立于求是抓取器的、配置驱动且可由人工、Agent 和 systemd 共用的中央/省级时政信息采集工作流。
- **Non-goals**：不修改求是流程，不一次性回填国家法律法规数据库全部历史记录，不下载或解析 PDF、WPS、Office、OFD 等附件。
- **Scope**：来源注册表、静态 HTML 与专用 JSON 适配器、正文标准化、跨来源候选去重、Chronicle 增量导入、SQLite 写前备份、Agent Skill、systemd 和专项测试。
- **Acceptance**：来源可枚举和审计；中央、省级、全国人大报告和法律库来源均可生成笔记；显式写入可安全重跑且第二次新增为 `0`；周任务只应用本次生成并校验的 manifest。
- **Verification**：专项 pytest、CLI 来源枚举、官方列表/API audit、受限与完整 dry-run、精确 manifest 导入、导入后重复规划和生产 smoke。

## 1. 分层设计

仓库工作流是唯一业务实现。Agent Skill 只负责选择命令和执行安全顺序，systemd 也直接调用同一 CLI。

```text
官方列表页 -> 链接发现 -> 正文抓取 -> 标准化 -> 候选去重 -> dry-run -> 备份 -> 增量写入
```

首批启用来源：

- `gov_cn_department_docs`：中国政府网国务院部门文件。
- `party_rules`：共产党员网党内法规近期更新。
- `beijing_government_docs`：北京市政府文件。
- `guangdong_government_docs`：广东省政府文件。
- `jiangsu_government_docs`：江苏省政府文件。
- `npc_reports`：中国人大网权威报告，HTML 页面抓正文，PDF 报告保留官方原文链接。
- `national_law_database`：国家法律法规数据库，使用官方 JSON 接口生成法规元数据、目录和官方标准文本入口。

三个省级来源组成 `province-pilot`；中央核心来源和三个省级来源共同组成周任务使用的 `weekly` 来源集。

中国人大网当前 HTTPS 在本项目运行环境中无法完成 TLS 握手，因此 `npc_reports` 仅对注册表中明确标记的 `http://www.npc.gov.cn` 启用受限 HTTP；其他 HTTP 来源一律拒绝加载。国家法律法规数据库正文由官方 OFD 阅读器承载，采集器不下载附件，仅在笔记中保存法规元数据、目录和官方阅读入口。

## 2. Chronicle 映射

| 数据层 | Chronicle 层级 |
| --- | --- |
| 权威层级 | 书架，例如 `党中央`、`中央国家机关` |
| 发布机构或稳定来源 | 笔记本，例如 `党内法规`、`国务院部门文件` |
| 文种 | 分组 `era`，例如 `政策文件`、`工作报告` |
| 文件标题 | 笔记标题 `headline` |
| 文件全文 | `bodyMarkdown` |

来源 URL、来源键、发文字号、发布机构和正文哈希写入 `extra`，并为目标笔记本补齐对应属性列。

## 3. 去重契约

候选按来源优先级排序，再依次生成以下身份键：

1. `发布机构 + 发文字号`；
2. 规范化后的原文 URL，删除 query 和 fragment；
3. `发布机构 + 发布日期 + 规范化标题`；
4. 正文 SHA-256。

任一身份键与更高优先级候选或任一时政书架中的既有笔记相同即跳过。草案、正式稿、修订和废止文件通过标题版本词保持独立；后续阶段再增加显式版本关系。

## 4. 安全边界

- `run` 只生成带校验和的 dry-run manifest；`apply --manifest` 只能写入该批已审阅候选。
- 写入前必须获取独占锁并对 SQLite 执行 online backup 和 `PRAGMA quick_check`。
- `apply` 只接受回环 API 和当前 checkout 的 `data/timeline.db`，远端导入必须登录目标 host 后本机执行。
- 写入前还必须比对 API 返回的数据库路径指纹，确保备份文件与 API 实际写入同一实例。
- manifest 固化来源注册契约；来源被禁用或目标书架/笔记本映射变化后必须重新生成计划。
- 抓取存在任何错误时拒绝写入；失败现场保留在状态目录。
- PDF、WPS、Office、OFD 和压缩包附件不下载、不解析；笔记正文统一保留“原文附件”可点击链接，并明确提示附件内容需在官方原文查看。
- 目标书架和笔记本可在 `apply` 时创建，dry-run 会提前校验全局同名冲突。
- 不同步删除，不覆盖用户编辑，不改变收藏和关联关系。
- 远端执行和定时器启用属于独立投产操作。

## 5. CLI

```powershell
python -m tools.political_ingestion.cli sources
python -m tools.political_ingestion.cli audit --set central-core
python -m tools.political_ingestion.cli run --set central-core --limit 3
python -m tools.political_ingestion.cli apply --manifest data/political-ingestion/runs/<run>/manifest.json
python tools/political_ingestion_scheduled_run.py --set weekly --dry-run --limit 3
```

省级扩展沿用相同注册表和适配器接口，按地区分批加入，不复制新的抓取器。累计列表通过来源级 `max_items` 限制周任务窗口，首批三省、人大报告和法律库默认分别最多抓最近 `30` 条；历史回填必须单独调整窗口并审阅 manifest。统一周任务固定在每周一 `05:15`（`Asia/Shanghai`）运行，最多随机延迟 `10` 分钟；法律库详情请求使用 `60` 秒超时，整个 service 最长运行 `60` 分钟。默认保留最近 `8` 次运行，只有不带 `--dry-run` 时才会应用已校验 manifest。

systemd 文件记录当前生产实例，固定使用现有 host 用户与 `/home/<user>/timeline` 部署路径；迁移到其他 host 时必须先替换 `User`、`WorkingDirectory` 和 `ExecStart`。模板必须作为独立投产操作安装，首次启用前先手动运行 service 并检查 journal：

```bash
sudo install -m 0644 tools/systemd/political-ingestion-sync.service tools/systemd/political-ingestion-sync.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start political-ingestion-sync.service
journalctl -u political-ingestion-sync.service --since today --no-pager
sudo systemctl enable --now political-ingestion-sync.timer
```
