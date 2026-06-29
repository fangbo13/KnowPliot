# KnowPilot — 项目审计与功能文档

> 📅 最近更新：2026-06-28 | 🏷️ 当前版本：V6.0

KnowPilot 原名 **EY Onboarding AI / onboardingai**。V6.0 起，文档口径统一为“知识库应用 Agent”，历史审计报告中的旧项目名和 V3.x/V4.x 缺陷编号保留为版本证据链。

---

## 📂 目录结构

```
project_audit_output/
│
├── README.md               📖 本文件（目录说明+Agent指引）
│
├── v3.1/                   🤖 历史版本 — 早期 Agent 可读文档
│   ├── 项目功能模块.md          功能清单+路由+组件路径（持续更新）
│   ├── bug_list.md              Bug+UX问题详情+复现步骤（持续更新）
│   ├── 迭代功能规划.md           P0/P1/P2/P3迭代路线图（持续更新）
│   ├── test_results.json        自动化测试原始数据
│   └── reports/                 👤 给人看的汇报快照
│       ├── 综合审计报告.md           图文并茂完整审计报告
│       └── 优化建议报告.md           评分矩阵+核心问题+路线图
│
├── screenshots/             📸 按模块分类的真实截图
│   ├── auth/        (7张)  登录页面各状态
│   ├── chat/        (6张)  聊天界面各视图
│   ├── sidebar/     (6张)  侧边栏+搜索+移动端Drawer
│   ├── profile/     (4张)  Profile页面+语言下拉
│   ├── knowledge/   (3张)  知识库表格+状态标签
│   ├── onboarding/  (1张)  新手引导弹窗
│   ├── theme/       (4张)  亮色/暗色主题切换
│   ├── i18n/        (5张)  英文/中文界面对比
│   ├── responsive/  (4张)  桌面/平板/移动端布局
│   └── error/       (1张)  401重定向
│
└── scripts/                 🔧 自动化测试脚本
    ├── audit_runner.mjs         v1 测试脚本（旧版）
    └── audit_runner_v2.mjs      v2 测试脚本（修复版）
```

---

## 📖 给下一个 Agent 的指引

**当前应优先读取根目录的 `KnowPilot.md`、`README.md`，以及最新功能模块汇总文档。历史版本细节再按需回溯 `v3.1/`、`v3.8/`、`v4.x/`。**

```
请优先阅读：
1. KnowPilot.md — 了解 V6.0 产品定位、业务场景和知识库应用 Agent 叙事
2. README.md — 了解当前项目入口、技术栈和启动方式
3. audit_reports/v3.8/项目功能模块汇总_V3.8.md — 了解当前 V6.0 功能模块口径与历史来源

截图参考路径：project_audit_output/screenshots/{模块名}/
汇报文件（给人看的）：project_audit_output/v3.1/reports/
```

---

## 🔑 核心发现摘要

| 指标 | 数值 |
|------|------|
| 测试通过率 | 86.4% (38/44) |
| 体验评分 | 7.5 / 10 |
| Bug数量 | 2 |
| UX摩擦点 | 6 (1🔴 / 2🟡 / 3🟢) |
| 截图数量 | 40张 / 25种不同画面 |
| 最严重问题 | 🔴 聊天思考指示器10s才出现 |

---

## 🔄 版本管理规则

- **根目录 `KnowPilot.md` 与 `README.md` 是当前活文档** — 随 V6.0 及后续版本持续更新。
- **`audit_reports/v3.x`、`audit_reports/v4.x` 下报告是历史快照** — 对应特定版本，不随项目更新而改写历史结论。
- **新版本时**：优先更新当前活文档和最新功能模块汇总；如需要完整审计快照，再新增对应版本目录。
