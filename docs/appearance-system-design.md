# 编年 Chronicle · 外观/主题系统 + 全屏设置 — 实现设计

> 本文是「主题色/背景/文字自定义 + 预设风格(含暗色) + Markdown 样式 + 全屏设置壳」的实现基准，对应整改 Req7 + Req10 + Req8(统计)。
> 视觉参考：Codex「外观」设置面板（全屏 modal、左导航 + 右内容、预设卡 + 主题编辑表）。Markdown 风格参考用户 Typora 主题 `clown.css`。
> 落地阶段 = 整改 **P5**。涉及视觉基准 + 解禁暗色，**触发 review gate**，并需同步改 `obsidian-minimal-implementation-spec.md` §1/§9/§12 与 `AGENTS.md §9`。

## 0. 决策基线（用户已拍板）

1. 主题范围 = **预设(系统/浅色/暗色) + 三色自定义(强调/背景/前景) + 对比度 + 字体 + Markdown 样式**。
2. **正式解禁暗色**（覆盖旧基准「本期不做深色」）。
3. 设置改为**全屏 modal**（左导航 + 右内容），参考 Codex；替换现有简陋小弹层。
4. Markdown 样式内置「编年默认 / clown(用户 Typora 风)」+ 支持导入自定义。
5. 令牌纪律不破：主题系统**只覆盖既有 `:root` 令牌**，不散落魔法值、不新造离散色。

## 1. 设置壳（全屏 modal）

替换 `TimelinePage.vue` 现有 `.timeline-settings-card` 小弹层。结构：左导航 + 右内容（Obsidian/Codex 风）。
```
┌─────────────────────────────────────────────┐
│ ← 返回                                    ✕  │
│ 🔍 搜索设置…  │  外观                         │
│ ───────────   │  ┌────┐ ┌────┐ ┌────┐        │
│ 常规          │  │系统│ │浅色│ │深色│  预设卡  │
│ 外观       ←  │  └────┘ └────┘ └────┘        │
│ 属性          │  ── 主题编辑 ──  导入  复制   │
│ 数据          │  强调色  ● #7b68d9            │
│ 关于          │  背景    ○ #faf9f8            │
│               │  前景    ● #2b2824            │
│               │  对比度  ───────●──  85       │
│               │  界面字体 [Noto Sans SC ▾]    │
│               │  正文字体 [Noto Sans SC ▾]    │
│               │  Markdown [编年默认 / clown ▾] 导入│
└─────────────────────────────────────────────┘
```
导航分区：
- **常规**：品牌名、默认笔记本、显示预览默认等。
- **外观**：主题(本文 §2–§5)。
- **属性**：内嵌/跳转左栏属性管理器（与 property-system 同源，一处管理多处入口）。
- **数据**：导入/导出当前笔记本（迁移现有「导出」入口）。
- **关于**：版本、帮助/快捷键（承载 Req10 的 `?`）。

新增组件建议：`SettingsModal.vue`（壳 + 路由式分区）、`AppearanceSettings.vue`、`ColorField.vue`（色板+取色器+hex 输入）。弹层/输入遵 spec §2.1。

## 2. 主题模型（少量旋钮 → 派生全套令牌）

不直接让用户编辑十几个令牌；只暴露 Codex 那几个旋钮，由 `deriveTokens()` 计算出全套 `:root` 变量（变量名不变，值被覆盖）。

主题配置对象（持久化单元）：
```jsonc
{
  "mode": "system",          // system | light | dark
  "accent": "#7b68d9",
  "background": "#faf9f8",   // 亮色基底; 暗色预设另存
  "foreground": "#2b2824",
  "contrast": 85,            // 0–100, 调 text/border 与底色的拉开度
  "uiFont": "Noto Sans SC",
  "bodyFont": "Noto Sans SC",
  "markdown": "default"      // default | clown | custom
}
```
派生规则（`deriveTokens(config)`）：
- `accent` → `--accent`；`--accent-hover`(微调暗)、`--accent-contrast`(按对比择黑/白)、`--accent-soft/-soft-2/-line`(accent + 透明度 .10/.16/.34)。
- `background` → `--bg-app`；`--bg-sidebar/-timeline/-detail/-surface/-surface-2`(对 background 做轻微提亮/压暗梯度)、`--bg-hover`(前景叠 .045 透明)。
- `foreground` → `--text`；`--text-strong/-muted/-faint`(按 contrast 拉开明度梯度)。
- `contrast` → 调 `--border/-soft/-strong`、`--rail`、muted 梯度强弱。
- `--scrim/--shadow-pop` 由 background 明暗自适应。
- 标签/选项色 `--t-*` 保留为调色板基色（属性选项配色取自这里，见 property-system §4）。

## 3. 预设

| 预设 | mode | 说明 |
|---|---|---|
| 系统 | system | 跟随 `prefers-color-scheme`，在浅/深间自动切 |
| 浅色 | light | spec §1 现有亮色值（accent `#7b68d9`，bg `#faf9f8`，text `#2b2824`） |
| 深色 | dark | 新增暗色令牌组（见 §3.1） |

选中预设即载入其旋钮值；用户在编辑表里改任意旋钮 → 变为「自定义」（基于该预设派生）。「复制主题」= 以当前为模板另存；「导入」= 粘贴主题 JSON。

### 3.1 暗色令牌组（新增到 spec §1）
暗色不是亮色反相，需独立调校，建议基线（落地时按 1920×1080 实测微调）：
```
--bg-app:#1a1917 --bg-sidebar:#1e1d1b --bg-timeline:#201f1d --bg-detail:#242220
--bg-surface:#242220 --bg-surface-2:#2b2926 --bg-hover:rgba(255,252,245,.05)
--border:#332f2a --border-soft:#2a2723 --border-strong:#403b34
--text:#e8e4dc --text-strong:#f5f1e9 --text-muted:#a59f94 --text-faint:#736d63
--accent:#8c7ae6 --accent-contrast:#fff (accent 软底用 accent + 透明度)
--rail:#3a352e --scrim:rgba(0,0,0,.5) --shadow-pop:0 10px 34px rgba(0,0,0,.4)
```
不变量：暗色同样**无 scale 布局、全局禁滚动条、右栏无边框编辑**——暗色只换令牌值，不改结构。禁装饰渐变/glow/玻璃态（AGENTS.md §9 仍生效）。

## 4. Markdown 样式

渲染产物根选择器 = `.markdown-body`（`renderMarkdownToHtml` 输出）。样式按预设切换 `:root[data-md=default|clown|custom]` 或注入 `<style>`。

- **编年默认**：现有极简风（沿用 `timeline-notes.css` 既有 `.markdown-body` 规则）。
- **clown（移植用户 Typora 主题）**：把 `clown.css` 的 `#write` 规则映射到 `.markdown-body`：
  - 标题分色 + 下划线：h1 `#470024`/2px、h2 `#6e0c2f`/2px、h3 `#ac1349`/1px、h4 `#005199`/1px、h5 `#4d80e6`/1px、h6 `#19dcdd`/1px。
  - 行内 `code`：底 `#F9F2F4`、字 `#E6005C`、圆角 3px。
  - `blockquote`：左边 2px `#1fe36e`、底 `#f8f8ff`、字 `#4d4d4d`。
  - 列表 marker：`ol` 粗体 `#255fa9`、`ul` `#de3163`；嵌套 ol = upper-roman / lower-roman。
  - 表格：GitHub 风（`#dfe2e5` 边、隔行 `#f8f8f8`）；`hr` 2px `#e7e7e7`。
  - 链接 `#4183C4`；正文行高 1.6。
  - 字体：原 Open Sans **不外链 Google Fonts**（离线优先），回退现有自托管 Noto + 系统栈；若要 Open Sans 后续自托管 woff2 子集再加。
  - **作用域**：仅 `.markdown-body` 内，不污染应用外壳。
- **导入自定义**：本地版接受用户 CSS（针对 `.markdown-body` 或 Typora `#write`，导入时做选择器前缀化注入）；托管版后续加 CSS 消毒/沙箱。

## 5. 持久化与应用（重写 `useTheme.js`）

- 现状废弃：旧 `/theme/{dark,light}.css` link 切换 + `/api/themes/{name}/vars` 是上一版遗留，与现 `:root` 令牌脱节 → **改为令牌覆盖方案**。
- `applyTheme(config)`：`deriveTokens(config)` → 写 `document.documentElement.style.setProperty('--x', v)`；设 `data-theme`/`data-md`；注入 markdown `<style>`。
- 持久化：`localStorage`（即时）+ 可选 `PUT /api/config`（跨设备，单用户）。`system` 模式监听 `matchMedia('(prefers-color-scheme: dark)')`。
- 启动 `initTheme()` 读取并应用，避免首屏闪烁（FOUC）。

## 6. Req8 · 左栏统计 Tab 优化（随 P5）
- 维持极简（不恢复 spec 已删的「标签分布/年代活动」大图表）。
- 改进：3 数字卡排版层级 + 一条轻量「近 N 周新增」趋势 sparkline（纯 CSS/SVG，无新依赖）；可加「最近活跃笔记本」。

## 7. 对 spec / AGENTS 影响（落地时同步）
- spec **§1**：新增暗色令牌组（§3.1）。
- spec **§9 / AGENTS.md §9**：删除「本期不做深色」「禁新增暗色模式」；改为「暗色经主题系统统一令牌实现，禁装饰渐变/glow/玻璃态仍生效」。
- spec **§12 差异表**：暗色行由「不做」改「主题系统支持」。
- 设置入口：spec §5.4 底栏 settings 打开本全屏 modal（非小弹层）。

## 8. 文件改动映射
前端：`composables/useTheme.js`(重写为令牌覆盖)、新增 `components/SettingsModal.vue` / `AppearanceSettings.vue` / `ColorField.vue`、`pages/TimelinePage.vue`(挂全屏 modal、去旧小弹层)、`styles/timeline-notes.css`(暗色令牌组 + `.markdown-body` clown 预设)、`TopicSidebar.vue`(底栏精致化、设置入口)、`constants/`(主题预设/调色板)。
后端：`api/config.py`(主题配置读写,若走后端持久化)；评估 `api/themes.py` 旧接口去留（倾向随 P2/P5 清理遗留）。

## 9. 提交前自检（P5 专项，叠加 spec §14.2）
- [ ] 主题只覆盖既有 `:root` 令牌名，无散落魔法值、无新造离散色（选项色取调色板）。
- [ ] 浅/暗/系统三态切换无 FOUC；`system` 跟随系统并实时响应。
- [ ] 暗色下：无 scale 布局、全局禁滚动条、右栏阅读↔编辑零位移无边框；无渐变/glow/玻璃态。
- [ ] Markdown 自定义仅作用 `.markdown-body`，不污染外壳；clown 预设离线可用（不外链字体）。
- [ ] 全屏设置 modal 遵 §2.1；Esc/✕ 关闭，不触发原生 dialog。
- [ ] spec §1/§9/§12 + AGENTS.md §9 已同步；`agent:check/build/test:ui/pytest` 全过；浅+暗各归档一组 1920×1080 视觉 QA。
