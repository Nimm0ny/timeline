# 20260625 Obsidian Implementation QA

- Task: `docs/obsidian-minimal-implementation-spec.md` 前后端落地后的固定视口视觉验收
- Viewport: `1920×1080`
- Primary URLs:
  - `http://127.0.0.1:8798/?topic=1`
  - `http://127.0.0.1:8798/?topic=1&event=1&mode=edit`
- Commands:
  - `cmd /c npm run agent:check`
  - `cmd /c npm run build`
  - `cmd /c npm run test:ui`
  - `python -m pytest tests/test_timeline_api.py tests/test_date_utils.py`
  - `cmd /c npm run qa:visual-fixture`

## Screenshots

- `1920-two-column.png`: 默认两栏，右栏关闭态
- `1920-read-view.png`: 点击事件后的右栏阅读态
- `1920-edit-view.png`: 固定 fixture 的右栏编辑态
- `1920-attachment-modal.png`: 临时 QA 附件注入后的附件 Modal 态

## Notes

- `1920-two-column.png`、`1920-read-view.png`、`1920-edit-view.png` 均由 headless Chrome 在 `1920×1080` 固定视口直接导出。
- `1920-attachment-modal.png` 使用了本地临时 QA 附件（`qa-inline.svg`）验证内联图片与 Modal；截图完成后已恢复数据库并删除临时源文件。
- `1920-attachment-modal.png` 为交互态局部截图：Modal 依赖真实点击展开，主验证点是图片内联与放大弹层行为。
