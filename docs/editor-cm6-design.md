# P6-F · CodeMirror 6 无感编辑器实现设计

> 本文是 P6-F 编辑器阶段的正式落地基准，补齐 `docs/p6-experience-overhaul-design.md` §8 要求的前置设计。
> 适用范围：右栏正文编辑器从现有 `contenteditable` 临时方案切到 CodeMirror 6，并实现 Obsidian/Typora 式 Live Preview。

## 0. Define-First

- **Goal**：把右栏正文编辑升级为 CodeMirror 6 驱动的 Markdown Live Preview，解决 `contenteditable` 的 DOM 往返、中文 IME、图片内联和后续扩展风险，同时保持当前三栏 Obsidian 基准不变量。
- **Non-goals**：本阶段不做完整文档产品、不新增编辑工具栏、不做双栏预览、不做协作/多光标/文件系统、不中断现有保存 DTO、不改变后端字段。
- **Scope**：前端编辑器依赖、`EventDetailPane.vue` 正文编辑入口、新增 CM6 Vue 组件、Markdown Live Preview 装饰、图片/附件插入、现有脏草稿和保存流对接、测试与视觉 QA。
- **Acceptance**：阅读态与编辑态无边框、无工具栏、右栏尺寸不变；编辑态图片内联可见；中文输入稳定；保存 payload 仍是 `bodyMarkdown` 源文；现有附件/关联/属性/未保存确认不回归。
- **Verification**：`cmd /c npm run agent:check`、`cmd /c npm run build`、`cmd /c npm run test:ui`、`python -m pytest tests/test_timeline_api.py tests/test_date_utils.py`；视觉改动按 `docs/agent-frontend-hardness.md` 归档 1920x1080 截图。

## 1. 设计裁决

1. **依赖只允许 CodeMirror 6**。实现阶段可修改 `package.json` / `package-lock.json`，但新增包必须限定在 CodeMirror 6 生态：
   - `@codemirror/state`
   - `@codemirror/view`
   - `@codemirror/commands`
   - `@codemirror/language`
   - `@codemirror/lang-markdown`
2. **不使用 Vue 包装器**。不引入 `vue-codemirror`、`@uiw/*` 或 UI 框架；自己封装一个窄的 Vue 组件，避免额外依赖和样式不可控。
3. **源文是唯一真相**。编辑器内部始终保存 Markdown 源文；Live Preview 只通过 CM6 decorations/widgets 改变展示，不把 HTML 回写为 Markdown。
4. **右栏零位移优先于功能花活**。任何装饰都必须服务于 `.markdown-body` 同款排版；不允许出现编辑框边框、工具栏、行号 gutter、状态栏或独立 preview 面板。
5. **分期实现，不一次吃完**。P6-F 改动预期超过 500 行，必须拆分提交。每个提交都能回滚、能独立验证，不把半成品留在主路径。

## 2. 现状契约

### 2.1 现有编辑器实现

- `ui/src/components/timeline-notes/EventDetailPane.vue`
  - 编辑态正文使用 `contenteditable` 的 `.body-editable`。
  - `syncEditableBody()` 把 Markdown 渲染为 HTML 后塞进 DOM。
  - `editableRootToMarkdown()` / `blockToMarkdown()` / `inlineToMarkdown()` 再把 DOM 反推 Markdown。
  - 粘贴/拖拽图片由 `handleEditablePaste` / `handleEditableDrop` 接管，上传后追加 Markdown 图片块。
- `ui/src/utils/markdownPreview.js`
  - 负责轻量 Markdown -> HTML 渲染，当前支持标题、引用、无序列表、链接、图片、粗斜体、行内 code。
- `ui/src/utils/editorMarkdown.js`
  - 负责附件类型识别、附件 Markdown 生成、文本插入辅助、关联事件搜索。

### 2.2 必须保留的交互契约

- `EventDetailPane` 对父级只通过 `save`、`dirty-change`、`preview-change` 等 emit 通信。
- `TimelinePage.vue` 仍负责未保存确认：保存 / 放弃 / 取消。
- `submit()` 输出 `SaveEventDto.bodyMarkdown`，后端不接收 HTML。
- 上传附件后：
  - 普通上传只进入附件列表。
  - 插入正文要生成 `![alt](/images/...)` 或 `[name](/images/...)`。
- 回收站事件不可编辑。
- 编辑态 title/date/era/property/attachment/related 的现有位置和行为不因换编辑器改变。

## 3. 目标架构

### 3.1 新增组件

新增 `ui/src/components/timeline-notes/MarkdownLiveEditor.vue`：

```vue
<MarkdownLiveEditor
  ref="bodyEditorRef"
  v-model="draft.bodyMarkdown"
  :document-key="editorDocumentKey"
  :disabled="!inEditMode"
  @open-image="openAttachment"
  @paste-files="uploadDroppedImages"
  @drop-files="uploadDroppedImages"
/>
```

组件职责：
- 创建和销毁 `EditorView`。
- 接收 `modelValue`，只在外部文档切换或重置草稿时同步到 CM6。
- `docChanged` 时 emit `update:modelValue`，让 `draft.bodyMarkdown` 保持源文同步。
- `document-key` 必须区分事件 id 和创建/重置会话：编辑既有事件用 `event:<id>:<resetSeq>`，创建态用 `create:<createSessionId>:<resetSeq>`。每次新建、放弃、切换事件或外部 reset 都递增会话/重置 key，从而清空 doc 与 undo history。
- 暴露：
  - `focus()`
  - `getMarkdown()`
  - `replaceSelection(text)`
  - `insertBlock(markdownText)`
  - `resetDocument(markdownText)`
- 处理编辑器内 paste/drop 文件事件，把文件数组交给父组件；上传仍由 `EventDetailPane.vue` 调 `api.uploadImage()`，避免 API 逻辑下沉到展示组件。

组件禁止：
- 禁止直接调用后端 API。
- 禁止知道事件 id、topic、附件列表语义。
- 禁止渲染保存、附件、关联等工具按钮。

### 3.2 新增 CM6 工具模块

新增 `ui/src/utils/cmMarkdownLivePreview.js`：

- `createMarkdownEditorExtensions(options)`：组合基础扩展、主题、keymap、事件处理。
- `buildInlinePreviewDecorations(view, options)`：只按 visible ranges 构建**不改变行高**的行内 decorations。
- `buildBlockWidgetStateField(options)`：用直接 `StateField` / `RangeSet` 提供会改变布局高度的 block widgets（首期主要是图片）。
- `markdownImageTokenAt(...)` / `collectMarkdownImageTokens(...)`：识别图片语法，生成 widget 输入。
- `activeLineRanges(state)`：当前光标所在行集合。当前行显示 Markdown 源符号；非当前行做 Live Preview。

纯函数尽量放这里，便于 `node --test` 覆盖，不把所有逻辑塞进 Vue SFC。

### 3.3 `EventDetailPane.vue` 改造

实现阶段删除这些 contenteditable 专属函数：

- `inlineToMarkdown`
- `blockToMarkdown`
- `editableRootToMarkdown`
- `syncEditableBody`
- `handleBodyInput`
- `handleEditablePaste`
- `handleEditableDrop`
- `handleEditableDragOver`
- `handleEditableDragLeave`

保留并改造：
- `uploadFiles(files, { insertIntoBody })`：当 `insertIntoBody` 为真，优先调用 `bodyEditorRef.insertBlock(block)`；编辑器未就绪时降级追加到 `draft.bodyMarkdown` 末尾。
- `appendMarkdownBlock()`：改为通过编辑器插入，并返回最新 Markdown。
- `submit()`：保存前调用 `bodyEditorRef.getMarkdown()` 同步最后状态，再按现有 `CONTENT_LIMITS.bodyMarkdown` 截断和校验。
- `applyDraft()`：切换事件或创建态时刷新 `editorDocumentKey`，重建编辑器并清空 undo history，避免跨事件或跨创建会话复用历史。

## 4. Live Preview 细则

### 4.1 基础编辑体验

使用最小 CM6 配置，而不是 `basicSetup` 一把梭：
- `history()` + `historyKeymap`
- `defaultKeymap`
- `markdown()`
- 自定义 `EditorView.theme`
- 自定义 `EditorView.lineWrapping`
- 自定义 update listener
- 自定义 DOM event handlers

不启用：
- line numbers
- gutters
- fold gutter
- search panel
- autocomplete panel
- lint panel
- bracket matching UI（首期不需要）

### 4.2 装饰策略

CodeMirror 官方文档要求通过 decorations/widgets 改变编辑器内容展示；不得直接改 `.cm-content` 内部 DOM。实现按这个原则：

Decoration 分两层，禁止混用：
- **直接 decorations**：图片等会改变布局高度的 block widgets 必须来自 `StateField` / `RangeSet`，由 CM6 在垂直布局测量前感知。
- **viewport decorations**：粗体、斜体、code、链接弱化、标题标记弱化等不改变行高的行内样式可以按 visible ranges 计算。

- 当前光标所在行：显示 Markdown 源文，保证可编辑和可理解。
- 非当前行：
  - 标题：`#` 前缀弱化或隐藏，内容套 `.cm-md-heading-*`，视觉匹配 `.markdown-body h1/h2/h3`。
  - 粗体/斜体/行内 code：定界符弱化或隐藏，内容套对应 mark class。
  - 链接：文字部分按 `.timeline-markdown-link` 风格展示；URL 部分在非当前行弱化。
  - 引用：行级 decoration 加左边线和软底，匹配 `.markdown-body blockquote`。
  - 无序列表：marker 取强调色，行距匹配 `.markdown-body li`。
  - 图片：非当前行把完整 `![alt](src)` 替换成 widget，widget 内渲染真实 `<img class="timeline-markdown-image">`；当前行显示源文。

布局会变高的图片 widget 必须使用直接 decoration source，不能只在 viewport 计算后间接提供，避免 CM6 高度测量不稳定。若首期无法稳定实现直接图片 widget，则不得把 CM6 shell 切到生产主路径。

### 4.3 图片 widget

图片 widget 输出：

```html
<figure class="cm-md-image-widget">
  <img class="timeline-markdown-image" src="..." alt="..." loading="lazy">
  <figcaption>alt 或文件名</figcaption>
</figure>
```

行为：
- 点击图片 emit `open-image`，复用现有 `AttachmentModal`。
- `src` 只允许渲染 Markdown 中的 URL 字符串，并通过 DOM property 设置，不拼 HTML 字符串。
- 图片加载失败显示简洁占位，不引入新图标或装饰背景。
- 外观复用 `.markdown-body img` 的 token；新增样式只处理 CM6 容器和 widget 对齐。

### 4.4 中文 IME

实现要求：
- 不在 `compositionstart` 到 `compositionend` 期间强制外部 replace doc。
- `watch(modelValue)` 只有在外部值与 `view.state.doc.toString()` 不一致，且不是当前 editor 自己刚发出的更新时才 dispatch。
- 输入法组合期间不重建 EditorView。
- Visual QA 外加手动验证：在编辑态连续输入中文、删除、换行、保存，确认无字符丢失和光标跳转。

## 5. 样式要求

新增样式集中写入 `ui/src/styles/timeline-notes.css`，使用既有 token。

核心选择器：
- `.markdown-live-editor`
- `.markdown-live-editor .cm-editor`
- `.markdown-live-editor .cm-scroller`
- `.markdown-live-editor .cm-content`
- `.markdown-live-editor .cm-line`
- `.markdown-live-editor .cm-focused`
- `.cm-md-heading-1/2/3`
- `.cm-md-image-widget`

硬约束：
- `.cm-editor` 无 border、无 outline、无 box-shadow。
- `.cm-focused` 不显示默认黑框。
- 背景透明，继承 `--bg-detail`。
- 字体、字号、行高与 `.body.markdown-body` 一致。
- 不显示 CM gutter，不占左侧空列。
- 右栏滚动仍由 `.detail-scroll` 承担；如果 CM6 必须保留内部 scroller，滚动条必须隐藏，并在视觉 QA 中确认不会出现双滚动冲突。
- 不使用 `transform: scale()`。
- 不新增非 token 颜色；Markdown 预设 `clown` 的已有固定色继续只作用 `.markdown-body` 范围，CM6 live preview 需要同步作用于 `.markdown-live-editor` 或共享选择器。

## 6. 分阶段实现计划

### P6-F1：CM6 外壳替换 + 最小图片 widget

目标：移除 `contenteditable` 主路径，用 CM6 管理 Markdown 源文，并在首个生产切换点就满足“编辑器内图片内联可见”。基础语法高亮可保持克制，但最小图片 widget 是上线门槛。

改动：
- 安装允许的 CM6 依赖。
- 新增 `MarkdownLiveEditor.vue`。
- `EventDetailPane.vue` 正文编辑态改用新组件。
- 删除 DOM -> Markdown 反推逻辑。
- 保留 read mode `renderMarkdownToHtml()`。
- 实现 `![alt](src)` 的最小直接 block widget：非当前行显示内联图片，当前行显示源文。
- paste/drop 图片仍可上传并插入 Markdown。

验收：
- 编辑、保存、取消、切换事件未保存确认均正常。
- 中文输入不跳光标。
- 编辑器无边框、无工具栏。
- 编辑态 Markdown 图片内联可见，并可打开附件 modal。
- `agent:check / build / test:ui / pytest` 通过。
- 归档 `1920-edit-cm6-shell.png` 和 `1920-edit-cm6-image-widget.png`。

硬闸口：
- 如果最小图片 widget 或图片视觉 QA 未通过，CM6 shell 只能保留在非生产实验路径，不得替换当前右栏主编辑器。

### P6-F2：Live Preview 装饰

目标：在 P6-F1 的最小图片 widget 基础上，补齐 P6 约定的第一期 Live Preview：行内 marks、标题、列表、引用、链接和更完整的图片边界。

改动：
- 新增 `cmMarkdownLivePreview.js`。
- 基于 Markdown syntax tree 和 visible ranges 生成 decorations。
- 当前行显示源文，非当前行显示 live preview。
- 图片 widget 可点击打开附件 modal。
- 增加纯函数单测。

验收：
- 图片在编辑态内联可见。
- 光标进入图片/标题/链接所在行时源文可编辑，移出后恢复预览。
- 阅读/编辑整体尺寸无明显位移；用 Playwright 记录 title/meta/body 顶部坐标。
- 归档 `1920-edit-live-preview.png` 和至少一张图片内联状态截图。

### P6-F3：编辑器硬化

目标：补齐边界、性能、主题和回归。

改动：
- 长正文滚动、外观预设 `default/clown`、暗色令牌下的 CM6 样式对齐。
- 多选区/撤销重做/插入附件的边界测试。
- 修复视觉 QA 发现的布局误差。

验收：
- 浅色 + 暗色各过 1920x1080 编辑态截图。
- 中文输入、撤销、保存、放弃、切换事件、附件插入、图片点击均可用。
- 无可见滚动条、无横向溢出、无文本重叠。

### P6-F4：二期能力排期，不在首批实现

候选：
- 表格 live preview。
- 代码块语言高亮。
- 脚注。
- Markdown 快捷键命令（加粗/列表等），但仍不显示工具栏。

## 7. 测试矩阵

### 7.1 单元测试

新增 `ui/tests/cmMarkdownLivePreview.test.js`：
- 图片 token 识别：alt、src、中文文件名、空 alt。
- 链接 token 不误判图片。
- active line 不隐藏 Markdown 源符号。
- 非 active line 可产生 image widget decoration 输入。
- 插入块逻辑保持前后空行，复用或替换 `editorMarkdown.js` 现有测试。

更新 `ui/tests/editorMarkdown.test.js`：
- `buildAttachmentMarkdown()` 与 CM6 `insertBlock()` 组合后光标位置合理。

### 7.2 浏览器/视觉 QA

固定 URL：
- `http://127.0.0.1:8798/?topic=1&event=1&mode=view`
- `http://127.0.0.1:8798/?topic=1&event=1&mode=edit`

必测：
- 阅读态截图。
- 编辑态 CM6 shell 截图。
- 编辑态含 Markdown 图片预览截图。
- 输入中文后保存再回到阅读态。
- 未保存确认三按钮。
- 粘贴/拖拽图片插入正文。

归档目录建议：
- `docs/visual-qa/<YYYYMMDD>-p6f-cm6-editor/`

README 必须记录：
- URL、视口、截图、运行命令、是否手动验证中文 IME、已知偏差。

## 8. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| CM6 样式默认带编辑器 chrome | 违反无感编辑 | 第一阶段先写最小主题，截图验证 `.cm-editor` 无边框/outline/gutter |
| Live Preview decoration 影响布局高度 | 阅读/编辑位移 | 先实现文字 marks，再上图片 widget；图片 widget 单独视觉 QA |
| 外部 v-model 同步打断 IME | 中文输入丢字/跳光标 | composition 期间不外部 replace，切事件用 `document-key` 重建 |
| 组件承担 API 逻辑 | 分层污染 | 上传、保存、toast 仍留在 `EventDetailPane.vue` |
| 依赖面扩大 | 违反 AGENTS/P6 | 不用 Vue wrapper，不用 remark/markdown-it/highlight.js |
| CM6 内部 scroller 与右栏 scroller 冲突 | 滚动体验差 | 先按无独立视觉滚动实现，QA 中实测长文；必要时保留内部 scroller 但禁显滚动条并记录取舍 |

## 9. Review Gate

P6-F 触发强制 review：
- 新依赖。
- 核心编辑路径行为改动。
- 前端视觉基准和右栏零位移风险。
- 单次有效代码 churn 预期超过阈值。

实现阶段每个提交在 commit 前必须：
1. 运行相关验证。
2. `git status --short` + `git ls-files --others --exclude-standard`。
3. 把完整 diff、验证结果和已知风险交给独立 subagent review。
4. P0/P1/P2 阻断问题修复后再 commit。

## 10. 参考资料

- CodeMirror Reference Manual: https://codemirror.net/docs/ref/
- CodeMirror Decorations Example: https://codemirror.net/examples/decoration/
- `@codemirror/lang-markdown` package docs: https://github.com/codemirror/lang-markdown
