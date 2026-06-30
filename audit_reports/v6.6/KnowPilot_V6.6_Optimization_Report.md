# KnowPilot V6.6 设计格调优化与全页面升级计划

> 📅 日期：2026-06-30 | 🏷️ 当前版本：V6.6 | 📂 分支：`Version_6.6`

---

## 🎨 第一部分：V6.6 已完成的重构与视觉升级

在本次更新中，我们启动了代号为 **“人文书卷意趣 (Tactile & Editorial Milano Paper v2)”** 的视觉重构。主要对项目的通用底座样式、物理阻尼、全局呼吸感与登录仪式感进行了升级。

### 1. 设计 Token 系统升级 (`tokens.css`)
*   **主色与字色**：主色升级为高阶、低饱和度且温暖的 **陶土褐 (Terracotta, `#B85B35`)**，文字色采用黑曜墨水色 **墨羽黑 (Ebony Black, `#231F1B`)**。
*   **纸张背景底色**：背景采用高级纤维艺术纸色 **米兰纸白 (Milano Paper White, `#F7F6F0`)** 与 **灰泥粘土 (Sunken Clay, `#F1EFE8`)**，暗色模式升级为 ** Obsidian 暖灰 (`#161513`)**。
*   **物理阴影**：引入了多层柔化阴影（如：`--shadow-md`, `--shadow-lg` 等），取消了强硬的物理边框，转而利用极浅的背景差和发散的环境光斑进行自然分级。
*   **阻尼曲线**：定义了物理弹性阻尼曲线 `--ease-spring` 与 `--ease-soft-spring`（基于超调弹簧公式 `cubic-bezier(0.34, 1.56, 0.64, 1)`），提供生动的按压回弹手感。

### 2. 全局样式与微动效 (`globals.css` / `chat.css`)
*   **软弹性淡入**：新增 `softFadeInUp` keyframe。所有页面在路由切换时，内容块将从底部 `8px` 平滑淡入并伴随轻微缩放。
*   **聚焦指示环**：重设聚焦环样式为 35% 不透明度的陶土色半透明光环，贴合圆角曲线。
*   **不规则消息圆角**：用户气泡调整为非对称的 `18px 18px 4px 18px`，更具现代对话的流式动感。
*   **流式打字脉冲 caret**：打字机 caret 动效改用渐变的 `pulseCaret` 呼吸脉冲（1.2s），降低视力疲劳。
*   **动作栏滑入微动效**：消息上方的复制、分享等动作栏在 hover 时加入 `translateY(4px -> 0)` 的微滑入淡显，交互极具亲和力。

### 3. 登录页极致升级 (`LoginPage.tsx`)
*   右侧表单面板 padding 由 `52px` 扩大为 `60px 48px`，输入框聚焦时引入陶土色柔和环境阴影扩展。
*   左侧暗色背景的 `ambientGlow` 环境光斑放慢至 `18s` 的超慢速呼吸流转，提供深沉且克制的品牌质感。

---

## 🛠️ 第二部分：其他未优化页面的全量升级计划 (Upgrade Plan)

为了实现 KnowPilot 全站设计格调、呼吸感、反馈亲和力和物理阻尼的连贯统一，接下来的升级工作将对**聊天页、历史记录页、个人设置页、空间管理页及侧边栏**等剩余界面进行全量优化。

### 1. 聊天页与输入框 (`ChatPage.tsx` / `ChatComposer.tsx`)

#### A. 视觉留白与呼吸感
*   **对话列宽与两侧留白**：保持聊天主视窗内容宽度 `--content-max: 640px`。当视窗处于 Empty State（WelcomeScreen）时，输入框和建议卡片应具备完全一致的宽度，两侧保留至少 `48px` 的空气流动区。
*   **对话间距优化**：将相邻两条消息气泡的纵向间距从 `10px` 调整为 `16px`，不同会话角色（User 与 Assistant）的分组间距增加至 `24px`，避免段落堆叠感。

#### B. 微动效与反馈亲和力
*   **输入框聚焦扩展 (Composer Glow)**：
    *   `.composer` 在聚焦时边框色过渡至 `--accent`，同时注入 `0 0 0 4px var(--accent-soft)` 的发散光晕，带来“粘性聚焦”的亲和力。
    *   当用户在文本框中键入首个字符时，发送按钮（`.composer-send`）从不可用的浅色态平滑过渡为激活态，建议伴随微小的弹簧缩放 `scale(1.05)` 淡入。
*   **引文卡片渐进淡入 (Citation Sequence)**：
    *   AI 消息的引用来源列表（`.citation-list`）在展开时，引文条目（`.citation-item`）应使用 staggered (错落) 延迟淡入，每个条目的延迟递增 `60ms`。
*   **Scroll-to-Bottom 悬浮球 (Scroll FAB)**：
    *   `.scroll-fab` 的出现与隐藏引入 `scale` 和 `translateY` 的双重阻尼淡入淡出（180ms，使用 `--ease-soft-spring`）。

---

### 2. 会话历史记录页 (`HistoryPage.tsx`)

#### A. Spacing & Rhythm
*   **卡片网格留白**：将会话历史卡片和分页区域内边距拉大，标题区域下边界留白（`margin-bottom`）提升至 `32px`。
*   **列表空气感**：会话行列表的每项高度与间距拉大，将会话列表行之间的间距设为 `8px`，背景默认使用微弱底色。

#### B. 悬停与物理阻尼
*   **列表悬停软弹手感**：
    *   会话列表项在 hover 时，背景颜色平滑过渡到 `var(--color-fill)`，且卡片整体向右微滑移 `4px`，增加指向感。
    *   点击列表项时，运用物理阻尼按压动效 `transform: scale(0.98)`。
*   **搜索与过滤条**：
    *   顶部搜索框（`Input.Search`）及时间维度分段控制器（`Segmented`）均增加 `transition: all var(--dur) var(--ease-out)`。
    *   点击分段选项卡时，选中背景滑块应平滑过渡移动，而非闪烁切换。

---

### 3. 个人设置页 (`ProfilePage.tsx`)

#### A. 视觉格调与分级
*   **信息展示卡片**：将个人头像、用户账号基础信息和首选项配置合并为大气的两级板式。两块 AntD `Card` 容器的圆角统一采用 `var(--radius-lg)` (16px)，内边距设为 `32px`。
*   **移除冗余线框**：只保留大版面之间的逻辑线，表单字段之间取消分割线，改用纵向 `20px` 留白。

#### B. Feedback Affinity
*   **保存按钮回弹反馈**：
    *   “保存修改”按钮（`.ant-btn-primary`）增加 `box-shadow` 在 hover 时的扩散和 translateY 微提升（-1.5px）。
    *   按钮在 `loading` 状态（保存中）到 `success` 状态（保存成功）过渡时，加入微小的震动反馈和轻微的弹性勾选动效。
*   **输入框聚焦微交互**：
    *   语言首选项下拉框在展开时，选项菜单（Dropdown Menu）平滑向下展开（`transform-origin: top; animation: slideDown var(--dur-fast) var(--ease-out)`）。

---

### 4. 空间管理页 (`SpaceManagementPage.tsx`)

#### A. 列表与表格的克制与连贯
*   **无缝表格**：空间成员列表表格（`Table`）取消表头深色底，采用与 Milano Paper 融合的透明渐变。行高拉大至 `48px`，提供充裕的行间呼吸。
*   **状态标牌 (Access Code Tags)**：
    *   激活、失效状态 Tag 一律使用温润、低饱和度的柔和配色（Success 配淡绿底深绿字，Revoked 配淡咖底深咖字）。
*   **模态弹窗 (Invite Code Modal)**：
    *   生成访问码弹窗在弹出时，背景遮罩使用 `backdrop-filter: blur(4px)` 缓缓蒙上。
    *   弹窗面板从屏幕中央以 `scale(0.97) -> scale(1)` 结合 `var(--ease-spring)` 弹簧效果快速缩放进入，突出“加载确定性”。

---

### 5. 侧边栏与空间切换器 (`AppLayout.tsx` / `SpaceSwitcher.tsx`)

#### A. 物理收折与连贯叙事
*   **侧边栏推拉感**：
    *   侧边栏在收缩/展开时，右侧主视窗内容区域应当平滑自适应，过渡时间使用阻尼适中的 `var(--dur-slow)`，配合 `--ease-out`。
    *   侧边栏内部会话组（如“今天”、“过去7天”）在折叠和展开时，折叠箭头 `.sidebar-group-caret` 的旋转执行平滑的 90 度旋转动画。
*   **空间切换器悬停反馈**：
    *   点击顶部空间选择器时，下拉列表项淡入，并以级联 (Cascade) 延迟淡出，带来流畅的叙事连续性。

---

## 📅 实施路线图 (Implementation Roadmap)

| 阶段 | 优化目标 | 关联文件 | 验证要点 |
|---|---|---|---|
| **Phase 1** | 聊天页呼吸留白与引文、Composer 微交互升级 | `ChatPage.tsx`, `ChatComposer.tsx`, `MessageBubble.tsx` | 输入聚焦阴影、AI打字脉冲光标、操作条滑入微动效。 |
| **Phase 2** | 会话历史与个人中心列表悬停阻尼手感优化 | `HistoryPage.tsx`, `ProfilePage.tsx` | 卡片内边距拉大、分段滑块平滑过渡、保存按钮点击缩放。 |
| **Phase 3** | 空间管理无缝表格及模态弹窗弹性动效升级 | `SpaceManagementPage.tsx` | 表格行间空气感、状态 Tag 软配色、模态弹窗弹簧缩放。 |
| **Phase 4** | 侧边栏推拉、空间切换器级联效果整体校对 | `AppLayout.tsx`, `SpaceSwitcher.tsx` | 侧边栏折叠平滑过渡、切换器展开阻尼。 |
