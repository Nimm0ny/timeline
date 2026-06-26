# Production Deployment Runbook

本文件记录当前 host 的真实投产环境和可重复部署流程。不要在本文写入主机地址、密码、token、API key 或私钥内容；这些值只允许存在于本地忽略文件 `.env/host`。

## 1. Goal

- 将当前仓库的已验证代码和本地构建产物发布到远端 host。
- 保留远端持久化数据、主题文件和 Python 虚拟环境。
- 每次发布都留下可回滚备份和部署版本标记。
- 发布后执行远端本机 smoke test，确认 systemd 服务、API 和前端首页可用。

## 2. Non-goals

- 不通过 `git push` 或远端 `git pull` 发布。当前远端 `~/timeline` 不是 git 仓库。
- 不覆盖远端 `data/`、`theme/`、`.venv/`。
- 不在文档、日志或命令输出中打印 `.env/host` 的敏感值。
- 不变更 systemd unit、云厂商安全组、反向代理或公网域名配置，除非后续任务明确要求。

## 3. Current Environment

本节来自 2026-06-25 的远端只读探测和本次部署验证。

- 本地环境文件：`.env/host`，已被 `.gitignore` 覆盖。
- 远端应用目录：`/home/$CLAW_HOST_USER/timeline`。
- 远端服务：`timeline.service`。
- systemd unit：`/etc/systemd/system/timeline.service`。
- 远端启动命令：`/home/$CLAW_HOST_USER/timeline/.venv/bin/python /home/$CLAW_HOST_USER/timeline/backend/server.py`。
- 工作目录：`/home/$CLAW_HOST_USER/timeline`。
- 内部监听端口：`0.0.0.0:8000`。
- 生产访问端口：`80`。
- 端口转发：系统网络层将 `tcp dport 80` redirect 到 `:8000`，包含公网入口和本机回环入口。
- Python：`3.12.3`。
- Node：`v22.22.2`。
- npm：`10.9.7`。
- 远端持久化目录：`data/`、`theme/`、`.venv/`。
- 远端数据文件：`data/timeline.db`。
- 远端上传目录：`data/images/`。
- 远端备份目录：`~/timeline_backups/`。
- 远端版本标记：`~/timeline/.deploy-revision`。

## 4. Preflight

在本地仓库根目录执行：

```powershell
git status --short --branch
git log --oneline -8
Test-Path -LiteralPath ".env\host"
```

要求：

- 确认本次要发布的 commit。
- 工作区如果有并行改动，只能发布已经提交到 HEAD 的内容。
- `.env/host` 必须存在，不得纳入 git。
- 不把 `.env/host` 内容打印到终端或文档。

远端只读检查：

```powershell
$envPath = ".env\host"
# 在当前 shell 中加载 .env/host，禁止输出具体值。
# 然后用 ssh 执行只读命令：
ssh -i $env:CLAW_HOST_KEY $env:CLAW_HOST_USER@$env:CLAW_HOST_ADDRESS `
  "systemctl is-active timeline.service; ss -ltnp 2>/dev/null | grep ':8000' || true"
```

期望：

- `timeline.service` 为 `active`。
- `8000` 端口由 Python 进程监听。
- `http://127.0.0.1/` 可访问项目，说明本机 80 到 8000 的 redirect 有效。

如需核对 80 转发规则：

```bash
sudo iptables -t nat -S | grep -E 'dport 80|to-ports 8000'
sudo nft list ruleset | grep -Ei 'dport 80|redirect to :8000'
```

## 5. Local Verification

每次发布前必须运行：

```powershell
cmd /c npm run agent:check
cmd /c npm run build
cmd /c npm run test:ui
python -m pytest tests/test_timeline_api.py tests/test_date_utils.py
```

说明：

- `npm run build` 会生成要发布的 `frontend/`。
- 只有文档-only 变更可以跳过构建和测试，但不能发布运行时代码。

## 6. Package

部署包必须从当前 HEAD 生成，显式排除 `data/` 和 `theme/`，再加入本地 `frontend/` 构建产物。

```powershell
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$head = (git rev-parse --short HEAD).Trim()
$stage = Join-Path $env:TEMP "timeline-deploy-$stamp-$head"
$archive = Join-Path $env:TEMP "timeline-deploy-$stamp-$head.tar.gz"
$trackedTar = Join-Path $env:TEMP "timeline-tracked-$stamp-$head.tar"

Remove-Item -LiteralPath $stage,$archive,$trackedTar -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $stage | Out-Null

$paths = @(
  ".gitattributes",
  ".gitignore",
  "AGENTS.md",
  "README.md",
  "backend",
  "docs",
  "make_transparent.js",
  "package.json",
  "package-lock.json",
  "prototypes",
  "run.bat",
  "tests",
  "tools",
  "ui",
  "timeline_notes_pixel_perfect_1920x1080_one_view.html"
)

git archive HEAD -o $trackedTar -- @paths
tar -xf $trackedTar -C $stage
Copy-Item -LiteralPath "frontend" -Destination (Join-Path $stage "frontend") -Recurse -Force
Set-Content -LiteralPath (Join-Path $stage ".deploy-revision") -Value "commit=$head`nbuiltAt=$((Get-Date).ToString('s'))`n" -Encoding UTF8
tar -czf $archive -C $stage .
```

部署包检查：

```powershell
Test-Path -LiteralPath (Join-Path $stage "backend/server.py")
Test-Path -LiteralPath (Join-Path $stage "frontend/index.html")
Test-Path -LiteralPath (Join-Path $stage "data")   # 必须是 False
Test-Path -LiteralPath (Join-Path $stage "theme")  # 必须是 False
```

## 7. Upload

```powershell
scp -i $env:CLAW_HOST_KEY $archive "$($env:CLAW_HOST_USER)@$($env:CLAW_HOST_ADDRESS):~/"
```

上传后，远端包名应能通过以下形式匹配：

```bash
ls -t ~/timeline-deploy-*<commit>*.tar.gz
```

如果本地上传时为了避免重名调整了文件名，远端切换脚本里的 `ARCHIVE` glob 必须同步调整。

## 8. Switch

远端切换原则：

- 先解压到临时 release 目录并做结构检查。
- 再备份当前应用目录，备份排除 `.venv`、`data`、`theme`。
- 停止 `timeline.service`。
- 删除并替换代码目录与前端产物。
- 启动 `timeline.service`。
- 执行 smoke test；失败则用刚创建的备份回滚。

远端切换时需要 sudo。不要把 sudo 密码写进脚本文件；从 `.env/host` 读取后以进程内变量传给远端一次性脚本。

核心远端步骤：

```bash
APP="$HOME/timeline"
BACKUP_DIR="$HOME/timeline_backups"
STAMP="$(date +%Y%m%d_%H%M%S)"
ARCHIVE="$(ls -t "$HOME"/timeline-deploy-*<commit>*.tar.gz | head -1)"
RELEASE="$HOME/.timeline_release_$STAMP"
BACKUP="$BACKUP_DIR/timeline_predeploy_$STAMP.tar.gz"

mkdir -p "$BACKUP_DIR" "$RELEASE"
tar -xzf "$ARCHIVE" -C "$RELEASE"
test -f "$RELEASE/backend/server.py"
test -f "$RELEASE/frontend/index.html"
test ! -d "$RELEASE/data"
test ! -d "$RELEASE/theme"

tar -czf "$BACKUP" --exclude=.venv --exclude=data --exclude=theme -C "$APP" .
sudo systemctl stop timeline.service

rm -rf "$APP/backend" "$APP/docs" "$APP/frontend" "$APP/prototypes" "$APP/tests" "$APP/tools" "$APP/ui"
rm -f "$APP/.deploy-revision" "$APP/.gitattributes" "$APP/.gitignore" "$APP/AGENTS.md" "$APP/README.md"
rm -f "$APP/make_transparent.js" "$APP/package.json" "$APP/package-lock.json" "$APP/run.bat"
rm -f "$APP/timeline_notes_pixel_perfect_1920x1080_one_view.html"

tar -xzf "$ARCHIVE" -C "$APP"
sudo systemctl start timeline.service
```

## 9. Smoke Test

远端本机 smoke 使用生产入口 `80`：

```bash
systemctl is-active timeline.service
cat ~/timeline/.deploy-revision
curl -fsS http://127.0.0.1/api/topics >/tmp/timeline_topics_smoke.json
curl -fsS http://127.0.0.1/ >/tmp/timeline_index_smoke.html
python3 - <<'PY'
import json
from pathlib import Path
topics = json.loads(Path('/tmp/timeline_topics_smoke.json').read_text())
html = Path('/tmp/timeline_index_smoke.html').read_text(errors='ignore')
assert isinstance(topics, list)
assert '<div id="app"></div>' in html
print('topics_count=' + str(len(topics)))
print('index_has_app=true')
PY
```

内部端口 smoke 可作为辅助检查：

```bash
curl -fsS http://127.0.0.1:8000/api/topics >/dev/null
curl -fsS http://127.0.0.1:8000/ >/dev/null
```

公网 smoke 使用生产入口 `80`：

```powershell
curl.exe --noproxy "*" -sS -o NUL -w "topics_http=%{http_code}`n" "http://$($env:CLAW_HOST_ADDRESS)/api/topics"
curl.exe --noproxy "*" -sS -o NUL -w "index_http=%{http_code}`n" "http://$($env:CLAW_HOST_ADDRESS)/"
```

公网 smoke 失败时，先看远端日志是否收到请求：

```bash
journalctl -u timeline.service --since '5 minutes ago' --no-pager
```

如果日志没有外部来源请求，问题在公网入口、云安全组、防火墙或本地网络代理层，不在 FastAPI 进程。

## 10. Rollback

回滚只恢复代码和构建产物，不动 `data/`、`theme/`、`.venv/`。

```bash
APP="$HOME/timeline"
BACKUP="$HOME/timeline_backups/<backup-file>.tar.gz"

sudo systemctl stop timeline.service
rm -rf "$APP/backend" "$APP/docs" "$APP/frontend" "$APP/prototypes" "$APP/tests" "$APP/tools" "$APP/ui"
rm -f "$APP/.deploy-revision" "$APP/.gitattributes" "$APP/.gitignore" "$APP/AGENTS.md" "$APP/README.md"
rm -f "$APP/make_transparent.js" "$APP/package.json" "$APP/package-lock.json" "$APP/run.bat"
rm -f "$APP/timeline_notes_pixel_perfect_1920x1080_one_view.html"
tar -xzf "$BACKUP" -C "$APP"
sudo systemctl start timeline.service
```

回滚后必须重新执行第 9 节 smoke test。

## 11. Cleanup

本地清理：

- 删除 `$stage`。
- 删除 `$trackedTar`。
- 删除 `$archive`。
- 保留 `.env/host`，但确认它仍是 ignored。

远端清理：

- 成功部署后删除上传的部署包。
- 删除临时 release 目录。
- 保留 `~/timeline_backups/timeline_predeploy_*.tar.gz`。
- 保留 `~/timeline/.deploy-revision`。

## 12. Deployment Record: 2026-06-25

- 已部署 commit：`d7e598f`。
- 远端备份：`~/timeline_backups/timeline_predeploy_20260625_105102.tar.gz`。
- 远端服务状态：`timeline.service` active/running。
- 远端本机 smoke：通过。
- 远端 API smoke：`topics_count=3`。
- 远端首页 smoke：`index_has_app=true`。
- 持久化数据：`data/` 保留，`data/timeline.db` 保留。
- 依赖状态：远端 `backend/requirements.txt` 和 `package-lock.json` 与本地一致，本次未安装依赖。
- 入口端口确认：生产入口使用 `80`，系统网络层 redirect 到内部 `8000`。
- 公网 80 smoke：`/` 和 `/api/topics` 均返回 HTTP `200`。
- 说明：公网 `:8000` 不是生产入口，不作为投产验收目标。

## 13. Deployment Record: 2026-06-26

- 已部署 commit：`e68fbd8`（前值 `32847e1`；本次 forward 13 commits：P1–P5 + 价值闭环 + 列表操作/弹层/组件系统统一规范）。
- 远端备份：`~/timeline_backups/timeline_predeploy_20260626_135301.tar.gz`。
- 远端服务状态：`timeline.service` active/running。
- 远端本机 smoke：通过（`service=active`，`revision=commit=e68fbd8`）。
- 远端 API smoke：`topics_http=200`，`topics_count=3`，`is_list=true`。
- 远端首页 smoke：`index_http=200`，`index_has_app=true`。
- 公网 80 smoke：`/api/topics` 返回 HTTP `200`。
- 持久化数据：`data/`、`data/timeline.db` 保留；启动期 `init_database()` 幂等 `ALTER TABLE ADD COLUMN`（`columns_json`/`extra_json` 等）将旧库前向迁移，无数据丢失。
- 依赖状态：`backend/requirements.txt` 自 `32847e1` 未变，远端 `.venv` 未改动、未安装依赖。
- 入口端口确认：生产入口 `80` → 内部 `8000`。
- 本地验证：`agent:check` / `build` / `test:ui`(30) / `pytest`(9) 全通过。
