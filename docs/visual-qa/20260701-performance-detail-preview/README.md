# Visual QA — Performance + Detail Preview

- Date: 2026-07-01
- Task: 验证首屏加载链优化、图片 lazy/async 解码、右栏属性区分割线调整高度、以及关联事件预览卡片贴底时不再溢出视口。
- URL:
  - `http://127.0.0.1:8798/?topic=6&event=1140`
- Viewport: `1920×1080`

Commands:

```bash
cmd /c npm run agent:check
cmd /c npm run build
cmd /c npm run test:ui
python -m pytest tests/test_timeline_api.py tests/test_date_utils.py
cmd /c npm run qa:visual-fixture
```

Checks:

- 首屏脚本/预加载资源只剩 `index` + 基础 vendor / vue / icons；不再提前 `modulepreload` `MindmapSurface`、`MarkdownLiveEditor`、`CommandPalette`、`SettingsModal`。
- 详情页内联 markdown 图片与附件缩略图都带 `loading="lazy" decoding="async" fetchpriority="low"`。
- 属性区分割线可拖拽，实际可见高度从 `176px` 调到 `266px`。
- 关联事件 pinned 预览卡片在接近窗口底部时仍留在视口内；本次实测 `bottom=1006 < viewportHeight=1080`。
- Browser console 无 error / warn。

Data discipline:

- QA 临时创建了 topic `zzPerfPreviewQA`（id `6`）和两条事件（其中一条带临时图片与 related link）。
- 截图完成后已删除临时 topic；图片随 topic 删除后已不可再访问。
- 本地临时文件 `.tmp-perf-qa.png` 已删除。

Artifacts:

- `1920-inline-image-and-preview.png` — 右栏详情的内联图片、附件缩略图与 dense 属性区
- `1920-detail-meta-resized.png` — 属性区分割线拖拽后的更高状态
- `1920-related-preview-fit.png` — pinned 关联事件预览卡片在底部附近仍未越出窗口
