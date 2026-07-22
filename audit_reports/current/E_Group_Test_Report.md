# E 组测试报告：CSS 变量缺失与硬编码颜色清理

**日期**：2026-07-23  
**分支**：主分支（backup/ui-ux-2026-07-23 已创建）  
**提交**：feat(ui-ux): E group CSS variable & hardcoded color cleanup (E1-E5)

---

## 修改文件清单

| 文件 | 修改项 |
|---|---|
| `frontend/src/design/tokens.ts` | E1（补定义 --accent-bg / --accent-border）、E3（新增 --color-overlay） |
| `frontend/src/styles/chat.css` | E2（app-header 暗色背景色温修复）、E3（cmdk-overlay 遮罩变量化） |
| `frontend/src/components/ErrorBoundary.tsx` | E4（color: '#fff' → var(--color-text-on-accent)） |
| `frontend/src/pages/WorkspaceCreationPage.css` | E5（box-shadow 硬编码 → var(--shadow-md)） |

---

## 逐项验证

### E1｜WorkspaceCreationPage.css 引用未定义 CSS 变量 【中】

**修改**：在 `tokens.ts` getCssVariables() 中补定义：
```typescript
'--accent-bg': `rgba(${color.accentRgb}, ${theme === 'dark' ? '0.14' : '0.07'})`,
'--accent-border': `rgba(${color.accentRgb}, ${theme === 'dark' ? '0.22' : '0.12'})`,
```

**浏览器验证**：
| 模式 | --accent-bg | --accent-border |
|---|---|---|
| 暗色 | `rgba(226, 123, 85, 0.14)` ✓ | `rgba(226, 123, 85, 0.22)` ✓ |
| 亮色 | `rgba(184, 91, 53, 0.07)` ✓ | `rgba(184, 91, 53, 0.12)` ✓ |

- WorkspaceCreationPage.css L61 `color-mix(in srgb, var(--color-bg-container) 94%, var(--accent-bg) 6%)` 成功解析 ✓
- L169 `border-color: var(--accent-border)` 成功解析 ✓
- L170 `background: var(--accent-bg)` 成功解析 ✓

**预期结果自检**：✅ 在 tokens.ts 补定义这两个变量（亮/暗两套），强调样式在两种主题下均生效

---

### E2｜chat.css app-header 暗色背景色温不一致 【低】

**修改**：`chat.css` L53 `rgba(17, 25, 40, 0.4)` → `rgba(var(--accent-rgb), 0.06)`

**浏览器验证**：
| 模式 | app-header 背景色 |
|---|---|
| 暗色 | `rgba(226, 123, 85, 0.06)` — 暖色调 ✓ |
| 亮色 | `rgba(255, 255, 255, 0.4)` — 亮色不变 ✓ |

- 暗色 app-header 背景从冷蓝 `rgba(17, 25, 40, 0.4)` 改为暖色调 `rgba(226, 123, 85, 0.06)`，与整体暖色暗主题色温统一

**预期结果自检**：✅ 改用暖色调 CSS 变量，app-header 与整体暗色主题色温统一

---

### E3｜cmdk-overlay 遮罩层硬编码 rgba 【低】

**修改**：
- `tokens.ts` 新增 `--color-overlay`: 暗色 `rgba(0, 0, 0, 0.60)` / 亮色 `rgba(0, 0, 0, 0.45)`
- `chat.css` L626 `rgba(0, 0, 0, 0.50)` → `var(--color-overlay)`

**浏览器验证**：
| 模式 | --color-overlay |
|---|---|
| 暗色 | `rgba(0, 0, 0, 0.60)` ✓ |
| 亮色 | `rgba(0, 0, 0, 0.45)` ✓ |

**预期结果自检**：✅ 新增 --color-overlay 变量并引用，遮罩透明度在主题层统一管理

---

### E4｜ErrorBoundary.tsx 硬编码 color: '#fff' 【中】

**修改**：`ErrorBoundary.tsx` L59 `color: '#fff'` → `color: 'var(--color-text-on-accent)'`

**浏览器验证**：
| 模式 | --color-text-on-accent |
|---|---|
| 暗色 | `#16100B` ✓ |
| 亮色 | `#FFFFFF` ✓ |

- 暗色模式下错误图标文字使用 `#16100B`（暗色 accent 背景上的浅色文字），对比度达标
- 亮色模式下使用 `#FFFFFF`（与原 `#fff` 相同），行为不变

**预期结果自检**：✅ 改为 var(--color-text-on-accent)，所有主题下错误界面文字对比度达标

---

### E5｜WorkspaceCreationPage.css 硬编码 box-shadow 【低】

**修改**：`WorkspaceCreationPage.css` L62 `box-shadow: 0 18px 55px rgba(55, 42, 30, .06)` → `box-shadow: var(--shadow-md)`

**浏览器验证**：
| 模式 | box-shadow 计算值 |
|---|---|
| 暗色 | `rgba(0, 0, 0, 0.42)` 系列 — 暗色阴影可见 ✓ |
| 亮色 | `rgba(35, 31, 27, 0.07)` 系列 — 亮色阴影可见 ✓ |

- 原硬编码 `rgba(55, 42, 30, .06)` 在暗色下不可见，现在使用 `var(--shadow-md)` 在两种模式下均正确呈现

**预期结果自检**：✅ 替换为 var(--shadow-md)，阴影在亮/暗模式均正确呈现

---

## 验证命令结果

| 检查项 | 结果 | 说明 |
|---|---|---|
| typecheck | ✅ 通过 | 修改的 4 文件无新增 TS 错误 |
| test | ✅ 通过 | tokens.test.ts 3 个全部通过 |
| check:i18n | 预存 6 缺失 | E 组无新增文案 |
| build | ✅ 通过 | Docker 构建成功 (built in 12.04s) |

---

## 浏览器截图

| 截图 | 说明 |
|---|---|
| `audit_reports/screenshots/e_group_dark_chat.png` | 暗色模式 Chat 页面（E2 app-header 暖色调） |
| `audit_reports/screenshots/e_group_light_chat.png` | 亮色模式 Chat 页面 |
| `audit_reports/screenshots/e_group_dark_workspace.png` | 暗色模式 WorkspaceCreation 页面（E1/E5） |
| `audit_reports/screenshots/e_group_light_workspace.png` | 亮色模式 WorkspaceCreation 页面（E1/E5） |

---

## 结论

E 组全部 5 项（E1-E5）已完成并通过验证：
- 所有缺失 CSS 变量在 tokens.ts 单点补定义
- 所有硬编码颜色替换为 CSS 变量引用
- 暗色/亮色双模式均验证通过
- 无新增 i18n 文案需求
