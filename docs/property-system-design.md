# 编年 Chronicle · 统一「属性(Property)」系统 — 实现设计

> 本文是「类型/标签/自定义列」统一为**属性**的实现基准，对应整改需求 Req3 + Req5(情境删除入口)。
> 优先级：在「属性 / 标签 / 自定义列」这一范围内，本文**取代** `obsidian-minimal-implementation-spec.md` §5.3.3、§6.4、§8.2 的旧裁决；其余仍以 spec 为准。
> 落地阶段 = 整改 **P3**。涉及数据契约 + 视觉基准 + 跨模块，**触发 review gate**。

## 0. 决策基线（用户已拍板，不再问）

1. **一切皆属性**：类型、标签、自定义列都是「属性」，地位完全平等，**皆可增删改**，无「系统属性/锁定」之分。
2. **属性类型**决定它是「自由值」还是「选项(标签)」。选项类属性的可复用值统称「标签/选项」。
3. **默认种子**：新建笔记本种入 `类型(单选)` + `标签(多选)` 两个默认属性，**可删**。
4. **选项归属**：选项集按**专题(topic)** 存储，跟 `columns_json` 同级。
5. **后端全量迁移、不留尾巴**：废弃 `tags_json` 与 `items[].tag` 这两条标签来源，所有属性值统一进 `extra_json`。
6. 左栏「标签」Tab **更名为「属性」Tab**，作为每个笔记本的属性/选项管理中心。

## 1. 概念与术语

| 术语 | 含义 |
|---|---|
| 属性 Property | 笔记本内的一个字段（定义存 `Topic.columns_json`） |
| 属性类型 | `text / number / date / select(单选) / multiselect(多选)` |
| 选项 Option | 单/多选属性的可复用值 = 「标签」；`{ id, label, color }` |
| 属性值 | 某事件在某属性上的取值（存 `event.extra_json`） |
| 自由值属性 | text/number/date——值是每事件独立的自由输入，**不进选项词表** |
| 选项类属性 | select/multiselect——值取自该属性的选项词表 |

## 2. 属性类型表

| 类型 | 性质 | 事件值存储 | 中栏单元格 | 右栏编辑控件 |
|---|---|---|---|---|
| text | 自由值 | `extra[key]` = 字符串 | 列表内只读 | 无边框输入 |
| number | 自由值 | `extra[key]` = 字符串(数字文本) | 列表内只读 | number 输入 |
| date | 自由值 | `extra[key]` = `YYYY-MM-DD` 字符串 | 列表内只读 | date 输入 |
| **checkbox** | 布尔 | `extra[key]` = `"true"`/`"false"` | 对勾 / 「—」(只读) | 复选框开关 |
| **url** | 自由值(链接) | `extra[key]` = 字符串 | 文本只读 | url 输入；读态可点 `<a>`(补 https) |
| **email** | 自由值(链接) | `extra[key]` = 字符串 | 文本只读 | email 输入；读态可点 `mailto:` |
| **phone** | 自由值(链接) | `extra[key]` = 字符串 | 文本只读 | tel 输入；读态可点 `tel:` |
| **select** | 选项 | `extra[key]` = 单个 option id | 点击弹 OptionPicker | OptionPicker(单值) |
| **multiselect** | 选项 | `extra[key]` = option id 数组 | 点击弹 OptionPicker | OptionPicker(多值 chips) |

> **【2026-06-28 类型扩充】** 在 text/number/date/select/multiselect 基础上参考 Obsidian/Notion 增 `checkbox`(布尔开关)、`url`/`email`/`phone`(可点击链接，读态 `<a>`、`propertyHref` 安全前缀)。checkbox 值规范为 `"true"`/`"false"` 字符串（`normalize_extra`/`normalizeEventExtra` 强制），故「已添加但未勾」也算有值会显示；从未添加 = 不在 extra = 空隐藏。link 类空值不显示（同 text）。属性行类型图标 `propertyIcon`：checkbox→checkSquare、url→link、email→mail、phone→phone。

- **类型** = 默认单选属性（`key:"type"`，一条笔记一个类型）。
- **标签** = 默认多选属性（`key:"tags"`）。
- 自由值单元格在中栏**只读**，避免密集行内输入与「点行开右栏」冲突；编辑在右栏。
- 选项类单元格点击 = 弹 OptionPicker（`stopPropagation`，不触发开右栏），hover 露淡 `+` 提示。

## 3. 数据契约（后端）

### 3.1 属性定义（`Topic.columns_json`）
`ColumnDef` 扩展：
```jsonc
{
  "key": "type",              // 唯一, ^[a-z][a-z0-9_]*$
  "label": "类型",
  "type": "select",           // text|number|date|select|multiselect
  "width": 96,
  "order": 0,
  "visible": true,
  "options": [                // 仅 select|multiselect 有意义
    { "id": "battle", "label": "战役", "color": "#c05a52" }
  ]
}
```
- `options[].id`：稳定标识，事件值引用它；改名只改 `label`，不破坏关联。
- `normalize_topic_columns` 校验：`key` 合法/唯一；`type` 在白名单；`options` 仅对 select/multiselect 保留，`id` 唯一、`color` 合法(回退令牌色)。

### 3.2 事件值（`TimelineEvent.extra_json`）
- 放开为 `dict[str, str | list[str]]`：自由值/单选 → 字符串；多选 → 数组。
- `normalize_extra(payload, topic)`：按该专题各属性的 `key` 白名单过滤；选项类再按该属性的 option `id` 白名单过滤未知值丢弃；多选去重保序。
- `merge_orphan_extra` 现有「删属性保孤儿值（软删）」逻辑保留。

### 3.3 Schema（`schemas/common.py`）
- 新增 `OptionDef(BaseModel){ id:str, label:str, color:str="" }`。
- `ColumnDef` 增 `options: list[OptionDef] = []`；`type` 文档注明含 `multiselect`。
- `TimelineEventIn.extra: dict[str, str | list[str]]`；**移除** `tags` 字段、`items` 字段（见 §4 迁移）。

## 4. 全量迁移（不留尾巴）

> ⚠️ 迁移前必须备份 `data/timeline.db`（复制为 `data/timeline.db.bak-<阶段>`）。一次性、加列+回填、可回滚。

1. **种默认属性**：对每个 topic，若 `columns_json` 缺 `type`/`tags`，种入 `类型(select)` + `标签(multiselect)`。
2. **迁标签选项**：扫描该 topic 全部事件的 `tags_json`（及历史 `items[].tag`）收集去重值 → 写入「标签」属性 `options`；`id = 原值`，`label = getTagLabel(原值)`，`color = getTagColor(原值)`（沿用 `constants/tags.js` 的默认色，未命中给调色板色）。
3. **迁事件值**：每事件 `extra["tags"] = deserialize(tags_json)`（过滤为已存在 option id）。
4. **类型值**：旧「类型」是「首个标签」的**派生视图**，从未真实存储 → 迁移后老事件 `extra["type"]` **留空**，中栏显示「—」，由用户补（**不臆造**）。
5. **清尾巴**：迁移完成后，`event_to_dict` 不再读 `tags_json`/`items[].tag`；`write_event_model` 不再写 `tags_json`；`TimelineEventIn` 去 `tags`/`items`。`tags_json` 列保留为 nullable 死列一个版本（仅作回滚保险），代码层完全不引用；下个清理点再 drop。
6. **同步**：`collectEventTags`/`matchesEventSearch`/全部标签筛选/导入导出 fixture/测试全部改读 `extra` 属性模型。

迁移落点：`services/legacy_migration.py`（或 db 初始化期），随启动幂等执行。

## 5. 前端组件

### 5.1 `OptionPicker.vue`（新增，弹层，遵 spec §2.1）
受控 props：`property`(含 options) / `value`(单值或数组) / `multiple`。emit `update`。
```
┌──────────────────────┐
│ 🔍 搜索或新建…        │  无边框输入(§2.1)
├──────────────────────┤
│ ● 战役           ✓   │  色点 + 名称 + 选中勾
│ ● 条约               │
│ ─────────────────── │
│ ＋ 新建「会议」       │  无精确匹配时出现, 建并配色
└──────────────────────┘
```
- 单选：选中即关闭并替换；多选：可多选、带勾、不自动关。
- 新建：写入该属性 options（带颜色）并选中；需回写 topic meta（防抖保存）。
- 复用处：中栏单元格、右栏属性区、列设置。

### 5.2 左栏「属性」Tab（`TopicSidebar.vue` 重写该面板 + `PropertyManager`）
Ribbon 图标由 `hash` 改注册「属性」图标（建议 Lucide `Tags` 或 `SlidersHorizontal`），tooltip「属性」。

**浏览态**（默认，承载筛选）：按属性分节，选项行点击 = 按 `属性=值` 筛选中栏。
```
属性 · 党史                        [⚙]
▾ 类型 · 单选                      ＋
   ● 战役            12
   ● 条约             5
▾ 标签 · 多选                      ＋
   ● 重要            20
▸ 来源 · 文本          自由值 · 无选项
＋ 新建属性
```
**管理态**（点 ⚙）：属性可改名/类型/显隐/排序/删除；选项可改名/改色/合并/删除（+计数）。新建属性时选类型（文本/数字/日期/单选/多选）。

### 5.3 中栏（`TimelineFeed.vue`）
- 列 = 可见属性；列头/行单元格按属性类型渲染（沿用 `--rowgrid` 重算）。
- 类型/标签成为普通属性列，去掉 `typeLabelFromEvent` 派生特例。
- 选项单元格就地编辑（OptionPicker）；自由值只读。

### 5.4 右栏（`EventDetailPane.vue`）
- 现「字段」区 + 独立「标签」小节 → 合并为统一「属性」区。
- 按属性类型渲染当前笔记**已设值的属性**；**空属性不显示（不再显「—」）**；编辑态显示有值属性 + 经「+属性」入口展开的未填项（选项类用 OptionPicker、自由值用无边框输入）。
- **【2026-06-28 升级·Obsidian 元数据区】** 「属性」区上移到标题正下方、正文下移到属性区之下（见 `obsidian-minimal-implementation-spec §7.2`）：日期、分组(专题·时代) 也并为属性行（每条必有→属性区恒显，不再「全空隐藏」；类型/标签/自定义为空仍不渲染该行）。「+属性」由旧的「编辑态底部虚线 chip」改为**属性区头 `+`**，点开 popover 列未填属性——区头 `+` 不增块高度，read↔edit 零位移更干净（旧「底部 chip 增量」放宽不再需要）。附件/关联同款区头 `+`（仅区可见时；空区隐藏、首加走 ⋮）。

### 5.5 列设置（`ColumnConfigPopover.vue`）
- 新建/编辑属性支持选 `multiselect`；选项类展开可就地增删选项（或跳左栏属性 Tab）。
- 去掉「内置类型/标签」与「自定义列」的二分，统一为「属性列表」。

## 6. 筛选泛化
- 现 `state.activeTag`（单一 tag）升级为 `activeFilters: { [propertyKey]: optionId }`（一期可先支持单条 `属性=值`）。
- `filterEvents` 由「按 tag」泛化为「按属性=值」。顺带修复「标签 Tab 点击后列表为空」——根因是旧 `tagRows` 依赖残留 `currentFilterEvents`，统一到属性模型后重写。

## 7. Req5 情境删除入口（随 P3）
- 在左栏 `pane-head`「新建笔记(squarePen)」**左侧**新增删除图标按钮。
- **仅当选中笔记本/笔记时显示**；删除当前选中笔记本（接 `api.deleteTopic`，现无 UI 入口）或当前选中笔记（软删入回收站）。
- 二次确认走应用内确认卡，不用浏览器 confirm。

## 8. 文件改动映射
前端：`components/timeline-notes/OptionPicker.vue`(新增)、`TopicSidebar.vue`、`TimelineFeed.vue`、`EventDetailPane.vue`、`ColumnConfigPopover.vue`、`TimelineLucideIcon.vue`(属性图标)、`utils/timelineNotes.js`、`constants/tags.js`(降级为种子)、`pages/TimelinePage.vue`(activeFilters/删除入口)。
后端：`schemas/common.py`、`services/timeline.py`、`services/legacy_migration.py`、`api/topics.py`(透传)。
测试：`tests/test_timeline_api.py`(options/多选/白名单/迁移)、`ui/tests/*`。

## 9. 提交前自检（P3 专项，叠加 spec §14.2）
- [ ] 迁移前已备份 `data/timeline.db`；迁移幂等、可回滚。
- [ ] `tags_json`/`items[].tag` 代码层零引用；所有标签来源统一 `extra`。
- [ ] 未知 option id / 未定义属性键被后端丢弃；**空属性不渲染（右栏不再显「—」、全空隐藏属性区，经编辑态「+属性」入口填写）**，无臆造。
- [ ] OptionPicker 遵 §2.1（无边框输入、单一弹层、Esc/外点关闭）。
- [ ] 选项 `id` 稳定，改名不破坏事件关联；删除/合并按孤儿软删纪律。
- [ ] 中栏选项单元格 `stopPropagation` 不误开右栏；自由值只读。
- [ ] 前后端字段名一致 + 契约测试同步；`agent:check/build/test:ui/pytest` 全过；视觉 QA 归档。
