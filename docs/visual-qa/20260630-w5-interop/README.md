# Visual QA — 2026-06-30 W5 interop

- **Task**: W5 interop 收口：mindmap `.xmind` / Markdown 导入导出入口、次要新建路径类型选择器、undated mindmap 展示与 mindmap 搜索/收藏/回收一致性。
- **Server**:
  - app / API: `http://127.0.0.1:8000`
  - visual server: `http://127.0.0.1:8798`
- **Viewport**:
  - desktop `1920×1080`
  - mobile `390×844`
- **QA data discipline**: 使用临时 notebook `zzW5InteropQA` 和临时 mindmap note；截图后已删除，不触碰用户现有笔记本。

## Flows checked

1. `?topic=6&event=1139` -> 点中唯一 row -> 进入 mindmap canvas -> 头部出现收藏/回收按钮、导入导出菜单、无 console error。
2. `?topic=6` 桌面左栏 -> 点击笔记本行 `⊕` -> 弹出 `条目 / 思维导图` 类型选择。
3. `?topic=6` 移动端 -> 顶栏 `+` -> 弹出 `条目 / 思维导图` 类型选择。
4. 固定 fixture `http://127.0.0.1:8798/?topic=1&event=1&mode=edit` -> 首屏正常渲染，无 overlay / 无 console error。

## Commands

```bash
cmd /c npm run qa:visual-fixture
cmd /c npm run agent:check
cmd /c npm run build
cmd /c npm run test:ui
python -m pytest tests/test_timeline_api.py tests/test_note_types_capabilities.py tests/test_date_utils.py
```

## Screenshots

- `1920-mindmap-bridge-menu.png`: desktop mindmap canvas + 导入导出菜单
- `1920-sidebar-create-menu.png`: desktop 左栏笔记本行 `⊕` 类型选择
- `390-mobile-create-picker.png`: mobile 顶栏 `+` 类型选择
- `1920-fixture-regression.png`: 固定 fixture 回归截图

## Notes

- in-app browser runtime 在补充额外 DOM 证据时发生超时重置；已获得的截图和先前 console 检查不受影响。
