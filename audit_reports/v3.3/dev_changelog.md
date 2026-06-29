# EY Onboarding AI — 代码变更日志（V3.3 修复）

> 修复日期：2026-06-25
> 修复人：Senior Full-Stack Engineer
> 基线版本：Version_3.3

---

## 变更日期

2026-06-25

## 修改文件清单

| # | 文件路径 | 变更类型 |
|---|----------|----------|
| 1 | `frontend/src/i18n/locales/zh/common.json` | 数据修复 + 重写 |
| 2 | `frontend/src/i18n/locales/en/common.json` | 数据修复 + 重写 |
| 3 | `frontend/src/pages/ProfilePage.tsx` | UI 逻辑修改 |
| 4 | `frontend/src/layout/AppLayout.tsx` | 样式修改 |
| 5 | `frontend/src/styles/globals.css` | CSS 添加 |

---

## 详细变更说明

### [修复] v3.3-BUG-001：i18n ZH/common.json 缺少 `user_menu` 和 `error_title` 键

- **修复方案**：在 ZH/common.json 中新增 `"user_menu": "用户菜单"` 和 `"error_title": "错误"` 翻译键，确保中文模式下用户菜单区域和错误页面不再显示英文回退文本
- **关联修复**：同时处理了 v3.3-BUG-002（移除 `error_network` 重复键）和 v3.3-UX-002（去除 UTF-8 BOM），将三合一问题一次性修复
- **具体操作**：
  - 整份文件以 UTF-8 无 BOM 编码重新写入
  - 补全 `user_menu`、`error_title`、`field_not_set` 三个缺失键
  - 移除第54行的 `error_network` 重复键，保留第69行更准确的翻译值

### [修复] v3.3-BUG-002：ZH/common.json `error_network` 重复键

- **修复方案**：移除重复的 `error_network` 键定义（第54行），保留更准确的翻译 "网络连接失败，请检查网络后重试"
- **备注**：与 v3.3-BUG-001 三合一修复

### [修复] v3.3-UX-002：ZH/common.json 含 UTF-8 BOM

- **修复方案**：文件以 UTF-8 无 BOM 编码完整重写，消除解析风险
- **备注**：与 v3.3-BUG-001 三合一修复

### [修复] fix_v3.3-BUG-001：EN/common.json `offline_send_warning` 重复键（新发现）

- **修复方案**：移除第138行的 `offline_send_warning` 重复键，保留第146行；同时新增 `"field_not_set": "Not set"` 翻译键供 Profile 空值字段使用
- **新发现说明**：在修复 ZH 重复键时发现 EN 同样存在同类问题，追加编号 fix_v3.3-BUG-001

### [优化] v3.3-UX-003：Profile 空值字段 `'—'` fallback 视觉效果不够友好

- **优化方案**：将 `service_line`、`office_location`、`role_level` 三个空值字段的 `'—'` fallback 替换为 i18n 翻译键 `field_not_set`
- **具体修改**：
  - ProfilePage.tsx 第84行：`{user?.service_line || '—'}` → `{user?.service_line || (<span style={{...}}>{t('field_not_set')}</span>)}`
  - ProfilePage.tsx 第94行：`{user?.office_location || '—'}` → 同上替换
  - ProfilePage.tsx 第104行：`{user?.role_level || '—'}` → 同上替换
  - email 字段保留 `'—'` fallback（系统字段，不宜显示"暂未设置")
- **样式设定**：空值文字使用 `color: 'var(--color-text-tertiary)'`、`fontStyle: 'italic'`、`fontSize: 13`
- **双语翻译**：EN → "Not set"、ZH → "暂未设置"
- **暗色模式验证**：tertiary 颜色在暗色模式下为 `rgb(100,116,139)` (slate)，对比度良好

### [优化] v3.3-UX-001：侧边栏搜索胶囊样式压缩视觉高度（UX-005 视觉回归）

- **优化方案**：通过 globals.css 中添加 `#sidebar-search-input` 和 `.ant-input-affix-wrapper:has(#sidebar-search-input)` 的 CSS override，补偿 `border: 'none'` 导致的 AntD middle size 视觉高度损失
- **具体修改**：
  - globals.css：添加 `#sidebar-search-input { height: 36px !important; padding: 4px 12px !important; }` 和 `.ant-input-affix-wrapper:has(#sidebar-search-input) { min-height: 36px !important; padding: 4px 12px !important; }`
  - AppLayout.tsx：inline style 中移除之前无效的 `minHeight: 36` 和 `padding: '6px 12px'`，保留 `borderRadius: 18`、`background: 'var(--color-fill-secondary)'`、`border: 'none'`、`transition: 'all 0.2s ease'`
- **效果对比**：搜索框 input 高度 22.75px → 36px，wrapper 高度 ~24px → 44px，视觉可发现性和可操作性大幅提升
- **根因说明**：AntD Input 的 `id` 属性被放在内部 `<input>` 元素上而非外层 `.ant-input-affix-wrapper`，导致直接的 CSS class selector 无法生效。使用 `:has()` 选择器解决了 wrapper 定位问题
