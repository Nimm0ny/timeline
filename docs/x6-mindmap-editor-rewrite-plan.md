# X6 Mindmap Editor Rewrite · Define-First

## Goal

- 把 `mindmap` 画布内核从 `simple-mind-map` 切到 `AntV X6`，实现任意节点自由拖拽到任意坐标、连线自动跟随，并重建可持久化的 `undo/redo/import/export`。
- 保持现有页面壳、保存链、搜索桥接、`note_type=mindmap` 的打开路径不变，做到旧导图可读、新导图可写。

## Non-goals

- 不重做三栏整体视觉基准，不扩成新的独立 mindmap 产品。
- 本轮不保留 `.xmind` 兼容；X6 没有现成 `.xmind` 读写能力，伪保留只会制造假入口。
- 不顺手改条目编辑器、属性系统、主题系统或后端 DTO 结构。
- 不做多用户协作、版本管理、节点富文本工具栏。

## Scope

1. 依赖与文档
   - 把 mindmap 引擎例外从 `simple-mind-map` 切到 `@antv/x6` 及所需插件。
   - 更新 `AGENTS.md` / 相关设计文档里已经失真的依赖与互通声明。
2. 前端共享语义
   - 让 `mindmapRootData` / `mindmapPlainText` / root-title 提取同时兼容：
     - 旧 bare tree
     - 旧 `simple-mind-map` snapshot
     - 新 `x6-mindmap-v1` snapshot
   - 保证搜索、预览、标题同步、混合工作区列表不回归。
3. 编辑器内部
   - 重写 `MindmapEditor.vue` 为 X6 驱动。
   - 建立 app-native 快照格式：节点、连线、画布背景、视口状态。
   - 重建 `undo/redo`、节点编辑、布局切换、颜色/字号样式写回。
4. 导入导出
   - 导出：X6 JSON、Markdown。
   - 导入：X6 JSON、Markdown。
   - UI 菜单与文案同步，不保留失效的 `.xmind` 入口。
5. 测试
   - 更新 `timelineNotes` 相关测试，覆盖新快照的 root/text 提取与搜索桥接。
   - 补 `mindmapX6` 数据转换测试，覆盖 JSON/Markdown round-trip 的关键路径。

## Acceptance

- mindmap 节点可拖到任意坐标，节点移动后连线实时跟随。
- `undo/redo` 可回退与重做：节点移动、增删节点、文本修改、样式修改至少这四类操作。
- 新快照保存后重新打开，节点坐标、文本、背景、视口不丢失。
- 旧 `simple-mind-map` 数据仍可打开，并在第一次保存后迁移为 X6 快照。
- mindmap 节点文本仍能被当前搜索链路和预览链路命中。
- 导入导出菜单只暴露真实支持的格式，不出现“点了才报不支持”的假功能。

## Verification

```bash
cmd /c npm run agent:check
cmd /c npm run build
cmd /c npm run test:ui
python -m pytest tests/test_timeline_api.py tests/test_date_utils.py
```

## Risks

- 这是一次引擎替换，`bodyJson` 语义会从树模型转向“快照 + cells”；所有依赖 root/text 提取的地方都必须补兼容层。
- 旧文档与 QA 记录把 `.xmind` 和 `simple-mind-map` 写成既有事实；如果不同步更新，会继续误导后续任务。
- 该任务会触发 `AGENTS.md` review gate：依赖例外、前端行为改线、既有验证路径变化。
