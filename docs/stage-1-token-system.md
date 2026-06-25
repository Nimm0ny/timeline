# 阶段 1 · Token 与核心组件

## 1. 设计立场

- 参考锚点：Obsidian
- 唯一主元素：中栏年份数字
- 其余全部次级，不允许第二焦点
- 默认做减法，优先文字信息，不做装饰性“精致”

## 2. Token

### 颜色

- 背景：`--tn-bg`
- 软背景：`--tn-bg-soft`
- 主卡片：`--tn-surface`
- 次级输入底：`--tn-surface-muted`
- 透明值：`--tn-transparent`
- 主文字：`--tn-ink`
- 次级文字：`--tn-text-muted`
- 弱提示：`--tn-text-faint`
- 边框：`--tn-line`
- 强边框：`--tn-line-strong`
- 唯一强调色：`--tn-accent`
- 强调色深阶：`--tn-accent-deep`
- 强调色前景文字：`--tn-on-accent`
- 强调色边框弱阶：`--tn-accent-border-soft`
- 强调色边框强阶：`--tn-accent-border-strong`
- 节点外环宽度：`--tn-dot-ring`

### 字号

- `--tn-step-1 = 12px`
- `--tn-step-2 = 14px`
- `--tn-step-3 = 16px`
- `--tn-step-4 = 20px`
- `--tn-step-5 = 32px`

### 字重

- 正文：`400`
- 标题 / 重点：`600`
- `--tn-weight-regular = 400`
- `--tn-weight-strong = 600`

### 圆角

- 原型来源：
  [product prototype reference](C:/Users/clown/AppData/Local/Temp/codex-clipboard-99b66e2a-feed-4cca-9802-de9840bad871.png)
- 本节只负责把原型里的圆角关系 token 化，不代表这张图只用于圆角参考。
- 大面板：`--tn-radius-xl = 18px`
- 卡片：`--tn-radius-lg = 16px`
- 控件：`--tn-radius-md = 12px`
- 胶囊 / pill：`--tn-radius-pill = 999px`

### 间距阶

- `--tn-space-0 = 0px`
- `--tn-space-1 = 4px`
- `--tn-space-2 = 6px`
- `--tn-space-3 = 8px`
- `--tn-space-4 = 10px`
- `--tn-space-5 = 12px`
- `--tn-space-6 = 14px`
- `--tn-space-7 = 16px`
- `--tn-space-8 = 18px`
- `--tn-space-9 = 20px`
- `--tn-space-10 = 22px`
- `--tn-space-11 = 24px`
- `--tn-space-12 = 28px`
- `--tn-space-13 = 30px`
- `--tn-space-14 = 32px`
- `--tn-shell-padding-x = clamp(18px, 2vw, 32px)`

### 尺寸

- `--tn-control-height = 40px`
- `--tn-input-height = 42px`
- `--tn-chip-height = 28px`
- `--tn-card-min-height = 132px`
- `--tn-line-width = 1px`
- `--tn-stage-width = 1920px`
- `--tn-stage-height = 1080px`
- 不使用 `--tn-stage-scale` 或外层 `transform: scale()` 承载布局；运行时通过栏宽、卡宽、rail、年份列和 composer 等响应式变量重算布局
- `--tn-font = "TimelinePrototypeFont"`，由 `ui/src/assets/fonts/timeline-prototype-regular.ttc` 与 `ui/src/assets/fonts/timeline-prototype-bold.ttc` 提供，不使用系统字体栈回退
- `--tn-serif = "TimelinePrototypeFont"`，保持与原型实际落到的 Microsoft YaHei 一致，不切换到宋体/衬线字体
- `--tn-icon-button-size = 28px / 32px / 36px / 40px`，按原型场景使用
- `--tn-icon-size = 16px ~ 18px`
- `--tn-icon-stroke = 1.65px`
- `--tn-actionbar-icon-size = 18px`
- `--tn-card-icon-size = 17px`
- 运行时 SVG 图标源：`@lucide/vue`
- 图标渲染组件：`ui/src/components/timeline-notes/TimelineLucideIcon.vue`
- 新版原型 HTML 仅包含整体 PNG，不包含可直接导入的 iconfont/SVG 源；当前阶段不使用 PNG 反推 SVG token，图标按 Lucide 体系落地，并通过 CSS token 校准尺寸、线宽、颜色和按钮热区。
- `--tn-year-dot-size = 8px`
- `--tn-rail-offset = 13px`
- `--tn-dot-offset = 7px`
- `scrollbar-width = none`，所有滚动容器隐藏滚动条但保留滚动能力
- `--tn-search-width = clamp(360px, 34vw, 560px)`
- `--tn-segment-min-width = 70px`
- `--tn-segment-height = 34px`
- `--tn-year-label-width = 92px`
- `--tn-year-rail-width = 28px`
- `--tn-year-label-width-mobile = 70px`
- `--tn-year-rail-width-mobile = 24px`
- `--tn-chip-max-width = 160px`
- `--tn-image-min-height = 180px`
- `--tn-image-max-height = 240px`

### 阴影

- 只允许中性阴影：
  - `--tn-panel-shadow`
  - `--tn-card-shadow`

### 视口

- `--tn-viewport-desktop = 1440px`
- `--tn-viewport-laptop = 1280px`
- `--tn-sidebar-width = clamp(240px, 17vw, 320px)`
- `--tn-detail-width = clamp(300px, 20vw, 360px)`
- `--tn-feed-measure = clamp(720px, 54vw, 860px)`
- `--tn-sidebar-width-compact = 240px`
- `--tn-detail-width-compact = 340px`
- `--tn-sidebar-width-tablet = 228px`
- 中栏主流宽度：不设固定 `max-width`，占据剩余空间
- 断点：
  - `1280px`
  - `1100px`
  - `820px`

## 3. 深浅色

- 浅色先落地，深色通过同名 token 覆盖。
- 深色不改结构，只改背景、文字、边框和阴影。
- 深浅色共用同一个强调色 `#bb2d24`。

## 4. 核心组件：事件卡

文件：
- [TimelineEventCard.vue](/C:/py_pj/cursor/clown/timeline/ui/src/components/timeline-notes/TimelineEventCard.vue:1)

内容元素上限 `N = 3`：
- 标题
- 一行摘要
- 标签行

日期信息由左侧年份/月轨道承担，不进入事件卡内容行。

当前允许加入的操作按钮不计入内容元素上限：
- 星标图标按钮
- 更多操作按钮

当前不允许加入：
- 收藏数 / 评论数 / 阅读数
- 多行 meta 区
- 次级操作行

## 5. 字符预算

- 事件卡标题：`48` 英文字符 / `24` 汉字
- 事件卡摘要：`140` 英文字符 / `72` 汉字
- 标签：`16` 英文字符 / `8` 汉字

实现位置：
- [contentLimits.js](/C:/py_pj/cursor/clown/timeline/ui/src/constants/contentLimits.js:1)
- [timelineNotes.js](/C:/py_pj/cursor/clown/timeline/ui/src/utils/timelineNotes.js:1)

## 6. 状态

事件卡当前定义：
- 默认态
- 选中态
- 长字符串截断态

页面级状态当前定义：
- 加载态
- 空态
- 错误态

这些状态由页面壳层承载，不往事件卡里塞额外提示元素。

## 7. 右栏设计补充

右栏阅读 / 编辑是同一块面板的两种视图：

- 阅读视图：
  - 标题
  - 时间 / 年代
  - Markdown 渲染正文
  - 分割线后的次级区域：标签 / 附件 / 关联笔记

- 编辑视图：
  - 结构化日期
  - 标题
  - 年代
  - Markdown 编辑输入
  - 与正文同步的实时渲染
  - 分割线后的次级区域：标签 / 附件 / 关联笔记

限制：
- 只允许单栏同位，不允许常驻双栏预览
- 实时渲染只服务正文，不把右栏做回文档编辑器
- 不做完整富文本工具栏
- 不做多层嵌套卡片
- 分组靠分割线，不靠卡片套卡片
- 标签 / 附件 / 关联笔记默认常显
- 每组默认最多展示 `5` 条
- 不做缩略图网格
- 不做常驻内嵌选择器
- 编辑态直接提供 `插入图片` / `上传附件` / `关联笔记` / `标签输入`
