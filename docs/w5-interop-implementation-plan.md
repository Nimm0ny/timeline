# W5 Interop · Define-First 实现计划

## Goal

- 打通 `mindmap` 笔记的 W5 互通能力：`.xmind` 导入导出、markdown ↔ 导图桥、跨类型搜索/收藏/回收一致性、`undated` 思维导图，以及次要新建路径的类型选择。

## Non-goals

- 不改三栏整体视觉基准，不重做导图画布样式。
- 不新增除现有 `simple-mind-map` 之外的依赖。
- 不扩成通用多文件导入中心，不做批量导入导出。
- 不顺手重构条目编辑器、属性系统或主题系统。

## Scope

1. 后端
   - 放开 `mindmap` 的无日期创建/更新路径，并让 DTO/排序/筛选对 `undated` 可判别。
   - 把导图树文本桥接进搜索索引与轻量搜索文本，保证命令面板/本地筛选可命中。
   - 保持现有 JSON 主题导入导出契约不破。
2. 前端
   - 在导图画布提供 `.xmind` / markdown 的导入导出与 markdown↔导图桥接。
   - 给次要新建入口补 note-type picker，至少覆盖左栏笔记本 `⊕` 与移动端 `+`。
   - 收口 mindmap 在搜索、收藏、回收路径中的行为一致性。
3. 测试
   - 后端契约测试覆盖 `undated`、导图搜索桥接。
   - 前端单测覆盖导图文本桥接/搜索与次要新建路径选择。

## Acceptance

- mindmap 可不带日期保存；不再强制 today-dated。
- `.xmind` 与 markdown 可在 mindmap 画布内导入/导出。
- markdown 可转换成导图树，导图可导出为 markdown。
- mindmap 节点文本能被当前搜索链路命中。
- 收藏/回收站/搜索结果对 mindmap 不出现类型特例或失联路径。
- 次要新建入口不再强制落 `entry`，而是先选类型。

## Verification

```bash
cmd /c npm run agent:check
cmd /c npm run build
cmd /c npm run test:ui
python -m pytest tests/test_timeline_api.py tests/test_note_types_capabilities.py tests/test_date_utils.py
```
