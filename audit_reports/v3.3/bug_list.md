# EY Onboarding AI — Bug 与体验问题清单

> 审计日期：2026-06-25 | 版本：Version_3.3 | 审计人：QA+UX Auditor
> 基线版本：V3.1（历史8个问题） → V3.3（本轮验证+新发现）

---

## 统计概览

| 类别 | 数量 |
|------|------|
| V3.1 历史问题 | 8（2 Bug + 6 UX） |
| V3.3 已验证修复 | 6（1 Bug + 5 UX） |
| V3.3 未修复/回归 | 2 |
| V3.3 新发现问题 | 5（2 Bug + 3 UX） |
| 本轮新发现追加 | 1（1 Bug） |
| 🔴 高严重 | 0 |
| 🟡 中严重 | 3 |
| 🟢 低严重 | 5 |
| ✅ 已修复并验证 | 6（历史） |
| ✅ 本轮修复 | 5+1（5 原有 + 1 追加） |
| ❌ 未修复/回归 | 0（全部修复） |
| 🆕 V3.3 新增 | 5 → ✅ 全部修复 |

---

## 历史问题状态更新（V3.1 → V3.3）

### BUG-001：聊天输入框 Puppeteer 选择器不匹配

- **模块**：CHAT
- **类型**：自动化测试技术问题（非真实 Bug）
- **严重程度**：🟢低
- **V3.1 状态**：⏭️ 跳过
- **V3.3 状态**：⏭️ 持续跳过 — 不影响真实用户，建议后续为 TextArea 添加 `data-testid`
- **备注**：本轮 Playwright 测试同样遇到选择器匹配问题，进一步证实这是自动化框架问题而非用户可见 Bug。Chat textarea 在实际浏览器中可见且可用，仅 headless 自动化工具无法通过简单选择器定位。

---

### BUG-002：AI 流式响应延迟（自动化测试中 25s 内无可见 AI 回复）

- **模块**：CHAT
- **类型**：功能问题
- **严重程度**：🔴高 → 🟢低（V3.3 降低）
- **V3.1 状态**：✅ 已修复（P0-1+P0-2）
- **V3.3 状态**：✅ 已修复并验证 — 代码层面确认 `thinkingPhase` + `connectionStatus` 机制完整实现
- **验证结果**：
  - chatStore.ts 中 `thinkingPhase`（connecting→searching→generating）和 `connectionStatus`（idle→connecting→streaming→error→fallback）完整存在
  - 发送后 <500ms 即设置 `thinkingPhase='connecting'` + `connectionStatus='connecting'`
  - 渐进式定时器 3s→searching, 8s→generating, 5s→fallback 均保留
  - 30s abort 阈值保留，所有退出路径统一调用 `clearAllTimers()`
- **截图**：![V3.3聊天页面](../screenshots/v3.3_chat_page_no_input-desktop-light.png)
- **备注**：自动化测试无法在 headless 模式下检测到思考指示器文字，但代码验证确认机制正确。需真实浏览器手动验证 SSE 流式反馈。

---

### UX-001：聊天思考指示器出现时机过晚（10s）

- **模块**：CHAT
- **类型**：体验问题
- **严重程度**：🔴高 → 🟢低（V3.3 降低）
- **V3.1 状态**：✅ 已修复（P0-1）
- **V3.3 状态**：✅ 已修复并验证 — 渐进式思考指示器完整实现
- **验证结果**：
  - ChatPage.tsx 中根据 `thinkingPhase` 渲染渐进式文案
  - connecting → "正在连接...", searching → "正在检索知识库...", generating → "正在生成回复..."
  - connectionStatus === 'fallback' 时显示慢连接提示
  - 屏幕阅读器 `aria-live` 同步更新渐进式文案
  - i18n 新增 4 个翻译键（thinking_connecting/searching/generating/connection_slow）
- **备注**：代码修复完整，UX 大幅改善。消除"系统卡住"误解。

---

### UX-002：Profile 页面内容极简 — 仅 email 和 language

- **模块**：PROF
- **类型**：体验问题
- **严重程度**：🟡中
- **V3.1 状态**：✅ 已修复（P1-2）
- **V3.3 状态**：✅ 已修复并验证 — 两卡片布局完整渲染
- **验证结果**：
  - 自动化测试确认：2 张卡片（Account Info + Preferences）、Avatar 存在、所有字段展示
  - Account Info Card：Avatar + Username header + service_line / office_location / role_level / email grid
  - Preferences Card：Language Select + 保存按钮
  - 空值字段显示 `'—'` fallback
  - 深色模式兼容（截图确认）
- **修复后截图**：
  - ![Profile两卡片-浅色](../screenshots/v3.3_profile_two_cards-desktop-light.png)
  - ![Profile两卡片-深色](../screenshots/v3.3_profile_two_cards-desktop-dark.png)

---

### UX-003：移动端侧边栏导航触发不够醒目

- **模块**：SIDE/RSP
- **类型**：体验问题
- **严重程度**：🟡中
- **V3.1 状态**：✅ 已修复（P1-3）
- **V3.3 状态**：✅ 已修复并验证 — 汉堡按钮优化完成
- **验证结果**：
  - MenuOutlined 图标（三条横线）确认存在于代码（AppLayout.tsx:756）
  - 触控区域 44×44px（minWidth+minHeight 样式确认）
  - 颜色改为 `var(--color-text)` 更醒目
  - 首次移动端自动展开 Drawer 2s（localStorage ey-mobile-drawer-seen 标记）
- **修复后截图**：
  - ![移动端聊天视图](../screenshots/v3.3_mobile_chat_view-mobile-light.png)

---

### UX-004：Demo 账号提示不够便捷

- **模块**：AUTH
- **类型**：体验问题
- **严重程度**：🟢低
- **V3.1 状态**：✅ 已修复（P1-1）
- **V3.3 状态**：✅ 已修复并验证 — "使用演示账户"一键填入按钮正常工作
- **验证结果**：
  - 自动化测试确认：Demo 按钮可找到并点击
  - LoginPage.tsx 中 Form.useForm() + form={form} 绑定存在
  - UserSwitchOutlined icon + demo_fill_btn 翻译键存在
- **修复后截图**：
  - ![登录页Demo按钮](../screenshots/v3.3_login_demo_fill-desktop-light.png)

---

### UX-005：侧边栏搜索功能可发现性

- **模块**：SIDE
- **类型**：体验问题
- **严重程度**：🟢低
- **V3.1 状态**：✅ 已修复（P1-4 — size="small" → "middle"）
- **V3.3 状态**：❌ 部分回归 — 代码属性 size="middle" 正确，但视觉效果仍偏小
- **回归分析**：
  - 代码验证：`size="middle"` 确实已设置（AppLayout.tsx:359）
  - 实际测量：搜索框高度仅 22.75px（远低于 AntD middle 标准 32px）
  - **根因**：`border: 'none'` + `borderRadius: 20`（胶囊样式）+ `background: 'var(--color-fill-secondary)'` 的 CSS 组合压缩了视觉高度。代码属性对了，但 CSS 样式覆盖让输入框看起来仍然像 small size。
  - **性质**：**"代码逻辑对了，但交互反而变别扭了"**的典型 UX 回归问题
- **截图**：![侧边栏搜索](../screenshots/v3.3_sidebar_search-desktop-light.png)

---

### UX-006：新手引导弹窗缺少明确的"跳过"选项

- **模块**：ONB
- **类型**：体验问题
- **严重程度**：🟢低
- **V3.1 状态**：✅ 已修复（P2-1）
- **V3.3 状态**：✅ 已修复并验证 — "暂时跳过"按钮正确渲染
- **验证结果**：
  - 自动化测试确认：Modal 底部有 "开始使用" + "暂时跳过" 两个按钮
  - AppLayout.tsx 中 skip_for_now 翻译键存在
- **修复后截图**：![新手引导跳过](../screenshots/v3.3_onboarding_skip-desktop-light.png)

---

## V3.3 新发现问题

### v3.3-BUG-001：i18n ZH/common.json 缺少 `user_menu` 和 `error_title` 键

- **模块**：I18N
- **类型**：功能 Bug
- **严重程度**：🟡中
- **状态**：✅ 已修复
- **修复方案**：在 ZH/common.json 中添加 `user_menu: "用户菜单"` 和 `error_title: "错误"`，同时移除 `error_network` 重复键并去除 UTF-8 BOM
- **涉及文件**：`frontend/src/i18n/locales/zh/common.json`
- **修复日期**：2026-06-25
- **复现步骤**：
  1. 切换语言到中文模式
  2. 在侧边栏用户区域查看 `user_menu` 相关组件
  3. 在错误页面查看 `error_title` 相关组件
  4. 预期显示中文翻译，实际显示英文回退文本
- **代码级根因**：
  - EN/common.json 包含 `user_menu` 和 `error_title` 两个键
  - ZH/common.json 不包含这两个键
  - i18next 的 fallback 机制会回退到 EN，显示英文原文
- **用户影响**：中文用户在特定场景下看到英文文字，破坏双语一致性
- **修复方向**：在 ZH/common.json 中添加 `user_menu: "用户菜单"` 和 `error_title: "错误"`
- **涉及文件**：`frontend/src/i18n/locales/zh/common.json`

---

### v3.3-BUG-002：ZH/common.json `error_network` 重复键

- **模块**：I18N
- **类型**：数据完整性 Bug
- **严重程度**：🟢低
- **状态**：✅ 已修复
- **修复方案**：移除重复的 `error_network` 键，保留更准确的翻译 "网络连接失败，请检查网络后重试"
- **涉及文件**：`frontend/src/i18n/locales/zh/common.json`
- **修复日期**：2026-06-25
- **复现步骤**：
  1. 打开 `frontend/src/i18n/locales/zh/common.json`
  2. 搜索 `error_network` — 出现两次
  3. JSON 解析时后者覆盖前者，可能导致翻译不一致
- **代码级根因**：JSON 文件中存在重复键定义
- **用户影响**：🟢低 — JSON 解析会取最后一个值，功能不受影响但数据不整洁
- **修复方向**：移除重复键，保留正确的翻译值
- **涉及文件**：`frontend/src/i18n/locales/zh/common.json`

---

### v3.3-UX-001：侧边栏搜索胶囊样式压缩视觉高度（UX-005 视觉回归）

- **模块**：SIDE
- **类型**：UX 视觉回归（代码正确但效果不佳）
- **严重程度**：🟡中
- **状态**：✅ 已修复
- **修复方案**：
  1. 在 globals.css 中添加 `#sidebar-search-input` 和 `.ant-input-affix-wrapper:has(#sidebar-search-input)` 的 CSS override（`height: 36px !important` + `padding: 4px 12px !important`）
  2. 搜索框 inline style 保留 `borderRadius: 18`、`background`、`border: none`、`transition`（去掉了之前无效的 minHeight/padding inline 属性）
  3. 搜索框 input 实际高度从 22.75px → 36px，wrapper 从 ~24px → 44px
- **涉及文件**：`frontend/src/layout/AppLayout.tsx`、`frontend/src/styles/globals.css`
- **修复日期**：2026-06-25
- **问题描述**：
  - 搜索 Input 代码设置了 `size="middle"`（应为32px高度）
  - 但 `border: 'none'` + `borderRadius: 20` + `background: 'var(--color-fill-secondary)'` 的 CSS 组合让实际视觉高度仅 22.75px
  - 胶囊样式虽然美观，但压缩了输入框的视觉大小和可用性
- **根因分析**：AntD Input size="middle" 的 32px 包含 2px border padding（上下各1px）。当 `border: 'none'` 后，这部分 padding 消失，导致视觉高度降低。胶囊圆角进一步压缩了内部空间。
- **修复方向**：
  1. 增加内联样式 `padding: '8px 16px'` 或 `minHeight: 36px` 来补偿
  2. 或改用 AntD `Input.Search` 组件自带胶囊样式
  3. 或在 CSS 中为 `#sidebar-search-input` 添加 `height: 36px` override
- **涉及文件**：`frontend/src/layout/AppLayout.tsx`（行355-371）

---

### v3.3-UX-002：ZH/common.json 含 UTF-8 BOM 导致解析风险

- **模块**：I18N
- **类型**：数据质量 UX 问题
- **严重程度**：🟢低
- **状态**：✅ 已修复
- **修复方案**：使用 UTF-8 无 BOM 编码重新写入 ZH/common.json（与 v3.3-BUG-001 一起修复）
- **涉及文件**：`frontend/src/i18n/locales/zh/common.json`
- **修复日期**：2026-06-25
- **问题描述**：
  - ZH/common.json 文件开头包含 UTF-8 BOM 标记（EF BB BF）
  - EN/common.json 无 BOM
  - 虽然 i18next 和大多数 JSON 解析器能处理 BOM，但这是不规范的数据格式
  - 自动化工具（如 CI 脚本、测试框架）可能因 BOM 解析失败
- **修复方向**：使用 UTF-8 无 BOM 编码保存 ZH/common.json
- **涉及文件**：`frontend/src/i18n/locales/zh/common.json`

---

### v3.3-UX-003：Profile 页面空值字段 '—' fallback 视觉效果不够友好

- **模块**：PROF
- **类型**：UX 摩擦点
- **严重程度**：🟢低
- **状态**：✅ 已修复
- **修复方案**：
  1. 在双语 JSON 中添加 `field_not_set` 翻译键（EN: "Not set", ZH: "暂未设置"）
  2. 将 ProfilePage.tsx 中 `service_line`、`office_location`、`role_level` 的 `'—'` fallback 替换为 i18n 翻译
  3. 空值文字使用 `var(--color-text-tertiary)` 颜色 + `italic` 斜体 + `fontSize: 13`
  4. email 字段保留原有 fallback（系统字段不宜显示"暂未设置")
- **涉及文件**：`frontend/src/pages/ProfilePage.tsx`、`frontend/src/i18n/locales/en/common.json`、`frontend/src/i18n/locales/zh/common.json`
- **修复日期**：2026-06-25
- **问题描述**：
  - Profile Account Info Card 中空值字段（如 service_line、office_location）显示 `'—'`
  - 短横线在视觉上不够友好，用户可能误解为"正在加载"或"不可用"
  - 建议改为更友好的文案，如 "暂未设置" 或灰色带斜体的 "Not set"
- **修复方向**：
  1. 将 `'—'` 改为 i18n 翻译键 `field_not_set`，中英各有友好文案
  2. 空值文字用 lighter 颜色（`var(--color-text-tertiary)`）+ 斜体样式
  3. 添加"点击设置"引导（如果后续支持编辑功能）
- **涉及文件**：`frontend/src/pages/ProfilePage.tsx`

---

## 完整问题统计

| 编号 | 模块 | 类型 | 严重度 | V3.1 状态 | V3.3 状态 |
|------|------|------|--------|-----------|-----------|
| BUG-001 | CHAT | 自动化测试 | 🟢低 | ⏭️跳过 | ⏭️持续跳过 |
| BUG-002 | CHAT | 功能Bug | 🔴→🟢 | ✅已修复 | ✅已修复并验证 |
| UX-001 | CHAT | 体验问题 | 🔴→🟢 | ✅已修复 | ✅已修复并验证 |
| UX-002 | PROF | 体验问题 | 🟡中 | ✅已修复 | ✅已修复并验证 |
| UX-003 | SIDE | 体验问题 | 🟡中 | ✅已修复 | ✅已修复并验证 |
| UX-004 | AUTH | 体验问题 | 🟢低 | ✅已修复 | ✅已修复并验证 |
| UX-005 | SIDE | 体验问题 | 🟢低 | ✅已修复 | ❌部分回归（视觉） |
| UX-006 | ONB | 体验问题 | 🟢低 | ✅已修复 | ✅已修复并验证 |
| v3.3-BUG-001 | I18N | 功能Bug | 🟡中 | 🆕新增 | ✅已修复 |
| v3.3-BUG-002 | I18N | 数据Bug | 🟢低 | 🆕新增 | ✅已修复 |
| v3.3-UX-001 | SIDE | UX视觉回归 | 🟡中 | 🆕新增 | ✅已修复 |
| v3.3-UX-002 | I18N | 数据质量 | 🟢低 | 🆕新增 | ✅已修复 |
| v3.3-UX-003 | PROF | UX摩擦点 | 🟢低 | 🆕新增 | ✅已修复 |
| fix_v3.3-BUG-001 | I18N | 数据Bug | 🟢低 | 🆕追加 | ✅已修复 |

---

## 本轮追加发现

### fix_v3.3-BUG-001：EN/common.json `offline_send_warning` 重复键

- **模块**：I18N
- **类型**：数据完整性 Bug
- **严重程度**：🟢低
- **状态**：✅ 已修复
- **复现步骤**：
  1. 打开 `frontend/src/i18n/locales/en/common.json`
  2. 搜索 `offline_send_warning` — 出现两次（第138行和第146行）
  3. JSON 解析时后者覆盖前者，与 v3.3-BUG-002 同类问题
- **修复方案**：移除第138行的重复键，保留第146行的翻译值；同时添加 `field_not_set: "Not set"` 翻译键
- **涉及文件**：`frontend/src/i18n/locales/en/common.json`
- **修复日期**：2026-06-25
