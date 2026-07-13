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
python tools/qstheory_scheduled_run.py --source web
```

每周一运行，扫描 12 个专题当前列表并追加新文章。

### 求是杂志

```powershell
python tools/qstheory_scheduled_run.py --source magazine
```

建议每天检查一次；没有新期或新文章时同步结果为零写入。

统一运行器固定执行：跨进程加锁、严格抓取、增量 dry-run、仅在有新增时执行 SQLite online backup、实际追加、清理超出保留数的运行目录和专项备份。默认保留每类最近 `5` 次抓取结果和 `16` 份变更前备份。

SQLite 备份先写隐藏临时文件，通过 `PRAGMA quick_check` 后再原子发布为最终 `.db`。运行器最多等待本机 API `120` 秒；连续失败也会保留当前失败现场并修剪更早的运行目录。

只读预演仍可分两步执行：

```powershell
python tools/qstheory_batch_scraper.py --source web --strict --output-dir .tmp-qa/qstheory-web
python tools/qstheory_sync.py --source web --input-dir .tmp-qa/qstheory-web --base-url http://127.0.0.1 --dry-run
```

也可以验证完整统一入口而不写入：

```powershell
python tools/qstheory_scheduled_run.py --source magazine --dry-run --state-dir .tmp-qa/qstheory-scheduled
```

## 4. 失败边界

- `--strict` 下任何未处理抓取错误都返回非零退出码，后续同步不得执行。
- 同步器会再次检查 `manifest.errors`，非空时拒绝写入。
- 目标书架不存在、同名笔记本位于错误书架、JSON 契约异常时同步立即失败。
- 单篇写入失败时命令返回非零；已成功追加的笔记保留，重跑会跳过它们并继续缺失项。
- systemd 将 stdout/stderr 写入 journal；任何阶段非零退出都会让 service 失败，保留当次抓取目录供排查。

## 5. systemd 定时器

模板位于 `tools/systemd/`。当前生产环境固定为：

- 求是网：每周一 `04:30`，附加最多 `5` 分钟随机延迟。
- 求是杂志：每天 `06:00` 检查最新一期，附加最多 `5` 分钟随机延迟。
- 两个日历均显式使用 `Asia/Shanghai`；远端当前时区也已核对为 `Asia/Shanghai`。

安装必须作为单独投产操作执行，不随代码部署自动启用：

```bash
sudo install -m 0644 tools/systemd/qstheory-*-sync.service tools/systemd/qstheory-*-sync.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now qstheory-web-sync.timer qstheory-magazine-sync.timer
systemctl list-timers 'qstheory-*-sync.timer' --no-pager
```

首次启用前分别手动执行 service，并检查结果：

```bash
sudo systemctl start qstheory-web-sync.service
sudo systemctl start qstheory-magazine-sync.service
journalctl -u qstheory-web-sync.service -u qstheory-magazine-sync.service --since today --no-pager
```

禁用时只停止 timer，不删除已抓取笔记：

```bash
sudo systemctl disable --now qstheory-web-sync.timer qstheory-magazine-sync.timer
```
