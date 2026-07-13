# 求是资料定期同步

## 0. Define-First

- **Goal**：把求是网和《求是》杂志固化为两条可独立运行、可安全重跑的增量同步流程。
- **Non-goals**：不覆盖已导入笔记，不同步删除，不改用户收藏、正文修改或关联关系，本阶段不直接部署生产定时器。
- **Scope**：抓取模式、最新期检测、候选去重、远端增量追加、专项测试和运行说明。
- **Acceptance**：同一份抓取结果连续同步两次，第二次新增笔记数必须为 `0`；两个来源只能写入各自书架。
- **Verification**：专项 pytest、项目标准测试、本地官网抓取、同批数据重复 dry-run。

## 1. 固定数据映射

| 来源 | 书架稳定键 | 笔记本 | 第三层 | 笔记正文 |
| --- | --- | --- | --- | --- |
| 求是网 | `qstheory_web` | `理论`、`经济`等专题 | 栏目 `era` | `bodyMarkdown` |
| 求是杂志 | `qstheory_magazine` | `YYYY年第N期` | 文章标题 `era` | `bodyMarkdown` |

书架通过稳定键查询，禁止硬编码数据库 id。求是网专题名称和求是杂志期号均保持无来源前缀。

## 2. 去重契约

同步候选按以下顺序生成稳定身份键：

1. `extra.source_url` 规范化后的 URL；忽略 query、fragment，并统一 `qstheory.cn` 为 `www.qstheory.cn`。
2. URL 缺失时，使用 `发布日期 + 规范化标题`。

去重分两层：

- 抓取层：同一列表、同一专题内只保留一个来源 URL；同一文章允许归入不同专题。
- 同步层：先读取目标笔记本导出，候选身份键已存在则跳过；候选自身重复也跳过。

同步只调用新增笔记接口，不使用会整本替换的 `/api/topics/{id}/import`。因此重复运行不会改变既有笔记 id，也不会清除收藏、用户编辑或关联关系。

## 3. 两条运行流程

### 求是网

```powershell
python tools/qstheory_batch_scraper.py --source web --strict --output-dir .tmp-qstheory/web
python tools/qstheory_sync.py --source web --input-dir .tmp-qstheory/web --base-url http://127.0.0.1 --dry-run
```

正式同步移除 `--dry-run`，并传入稳定的 `--lock-file data/qstheory-sync/web.lock`。每周一运行，扫描 12 个专题当前列表并追加新文章。

### 求是杂志

```powershell
python tools/qstheory_batch_scraper.py --source magazine --latest-issue --strict --output-dir .tmp-qstheory/magazine
python tools/qstheory_sync.py --source magazine --input-dir .tmp-qstheory/magazine --base-url http://127.0.0.1 --dry-run
```

正式同步移除 `--dry-run`，并传入稳定的 `--lock-file data/qstheory-sync/magazine.lock`。建议每天检查一次；没有新期或新文章时同步结果为零写入。

## 4. 失败边界

- `--strict` 下任何未处理抓取错误都返回非零退出码，后续同步不得执行。
- 同步器会再次检查 `manifest.errors`，非空时拒绝写入。
- 目标书架不存在、同名笔记本位于错误书架、JSON 契约异常时同步立即失败。
- 单篇写入失败时命令返回非零；已成功追加的笔记保留，重跑会跳过它们并继续缺失项。
- 正式定时任务需要运行锁、写入前数据库备份、结构化日志和失败告警；在部署阶段按生产 runbook 单独实施。
