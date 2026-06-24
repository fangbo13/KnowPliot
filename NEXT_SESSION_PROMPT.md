# EY Onboarding AI — 迭代 9 开发任务（当前进度同步）

你好！你是 EY Onboarding AI 项目的 UX 优化工程师。以下是当前项目进度和待完成任务。

## 项目背景
- React 18 + TypeScript + Ant Design 5 + Vite 5 + Zustand + i18next
- 分支: Version_2.4 | Docker: frontend:3000 / backend:8000
- 登录: admin@ey.com / admin123

## 已完成工作（迭代 1-8 ✅）
详见 `HANDOFF.md`，包含 v1 审计 12/12、v2 审计 17/17、v3 审计 18/18 全部修复。

## 当前代码状态（迭代 9 — 80% 完成）

### ✅ 已完成部分
1. **侧边栏大幅重构** — 删除导航菜单，改为纯对话列表
2. **固定 260px 宽度** — 使用 div 替代 Sider，不再折叠
3. **顶部 Logo 区域** — EY 图标 + "Onboarding" 文字
4. **新建对话按钮** — 白底灰边圆角 "开启新对话"
5. **对话列表** — 日期分组（今天/昨天/7 天/30 天/更早），可折叠
6. **对话项样式** — 选中态浅蓝背景，hover 浅灰，右侧三点菜单
7. **右键菜单** — onContextMenu + Popconfirm 删除确认
8. **底部用户区** — 头像 + 用户名 + 三点菜单
9. **移动端 Drawer** — 同步桌面端结构
10. **Header 用户菜单** — 添加知识库入口（管理员可见）
11. **/history 路由已删除** — App.tsx 已更新
12. **i18n 已更新** — 20+ keys（zh/en 同步）
13. **Tour 已简化** — 移除交互式 Tour，保留 Onboarding Modal

### 待完成任务
1. **🔴 紧急 Bug 修复：聊天界面无法滚动**
   - 根元素：`<div style={{ height: '100vh', display: 'flex' }}>`
   - 问题：flex 链中某处 overflow 设置不当，导致聊天内容无法滚动
   - 需要修复的布局链：
     ```
     div (100vh, flex) →
       div (sidebar, 260px) +
       div (main, flex:1, flex-col) →
         div (header, height:56) +
         div (content, flex:1, overflow:hidden) →
           main (#main-content, flex:1) →
             div (page-enter, flex:1) →
               Outlet (ChatPage)
     ```
   - ChatPage 内部有 `div (scrollContainer, flex:1, overflowY:auto)` 但父级阻止了滚动
   - 请检查并确保滚动链畅通，使 ChatPage 的 `scrollContainerRef` 可以正常滚动

2. ⏳ **侧边栏顶栏右侧图标** — 添加 🔍搜索图标 + □布局图标
3. ⏳ **CSS 样式微调** — 滚动条隐藏、hover 效果完善
4. ⏳ **MessageBubble hover 增强** — 操作按钮平滑过渡
5.  **验证** — TypeScript 检查 + 浏览器测试 + 截图对比
6.  **文档更新** — 更新 HANDOFF.md 和 NEXT_SESSION_PROMPT.md

## 关键文件状态
| 文件 | 状态 | 说明 |
|------|------|------|
| `frontend/src/layout/AppLayout.tsx` | ✅ 已重构 80% | 核心变更，需修复滚动 bug |
| `frontend/src/App.tsx` | ✅ 已完成 | /history 路由已删除 |
| `frontend/src/pages/ChatPage.tsx` |  待检查 | 滚动容器设置正确，父级阻止 |
| `frontend/src/styles/globals.css` |  部分完成 | 需补充 DeepSeek 样式 |
| `frontend/src/i18n/locales/zh|en/common.json` | ✅ 已完成 | i18n keys 已更新 |
| `frontend/src/components/chat/MessageBubble.tsx` | ⏳ 待优化 | hover 过渡 |

## 参考代码
- DeepSeek Clone: `https://github.com/elyse502/deepseek-clone`
- Sidebar.jsx, ChatLabel.jsx, globals.css 已分析

## 注意事项
- 不要破坏现有功能（对话列表、搜索、右键菜单已正常工作）
- i18n 同步更新 zh/en
- 每次修改后运行 `npx tsc --noEmit`
- 完成后更新文档

## 如果遇到问题
- 查看 `HANDOFF.md` 了解完整上下文
- 使用 `docker compose logs --tail 20 frontend` 查看错误

祝你好运！
