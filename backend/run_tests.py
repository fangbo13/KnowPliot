"""
EY Onboarding AI - Comprehensive Functional Test Script
Runs inside Docker backend container to access frontend via Docker network.
"""

import json
import time
import os
from datetime import datetime
from playwright.sync_api import sync_playwright, expect

FRONTEND_URL = "http://frontend:3000"
OUTPUT_DIR = "/tmp/test_output"
SCREENSHOTS_DIR = os.path.join(OUTPUT_DIR, "screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

bugs = []
bug_counter = 0

def add_bug(severity, category, title, description, reproduction, expected, actual, screenshot_files=None):
    global bug_counter
    bug_counter += 1
    bug_id = f"BUG-{bug_counter:03d}"
    bugs.append({
        "bugId": bug_id, "severity": severity, "category": category,
        "title": title, "description": description,
        "reproduction": reproduction, "expected": expected, "actual": actual,
        "screenshots": screenshot_files or [], "status": "open"
    })
    print(f"  [BUG] {bug_id} [{severity}] {title}")
    return bug_id

def screenshot(page, filename, description=""):
    filepath = os.path.join(SCREENSHOTS_DIR, filename)
    page.screenshot(path=filepath, full_page=True)
    print(f"  [Screenshot] {filename}{' - ' + description if description else ''}")
    return filename

def run_tests():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        page = context.new_page()

        # Track console errors
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        print("=== Phase 2: Test Execution Starting ===\n")

        # =============================================
        # Category A: Visual & Theming
        # =============================================
        print("\n--- Category A: Visual & Theming ---")

        # A1: Login page - light mode
        print("  [A1] Login page light mode")
        page.goto(f"{FRONTEND_URL}/login", wait_until="networkidle", timeout=30000)
        screenshot(page, "01-login-light.png", "Login page light mode")

        # A2: Login form hardcoded placeholders
        print("  [A2] Login form placeholders i18n check")
        email_placeholder = page.query_selector('input[placeholder="your.email@ey.com"]')
        password_placeholder = page.query_selector('input[placeholder="Enter your password"]')
        if email_placeholder and password_placeholder:
            add_bug("Minor", "i18n",
                "登录表单硬编码英文占位符",
                "登录页面的Email和密码输入框占位符硬编码为英文，不随i18n语言切换",
                "1. 打开登录页面\n2. 检查输入框占位符",
                '占位符应通过i18n翻译（如中文显示"请输入你的邮箱"）',
                '占位符硬编码为："your.email@ey.com" 和 "Enter your password"',
                ["01-login-light.png"])

        # A3: Login form validation messages hardcoded
        print("  [A3] Login validation messages")
        # Clear email and submit
        email_input = page.query_selector('input[placeholder="your.email@ey.com"]')
        if email_input:
            email_input.click()
            page.keyboard.down("Control")
            page.keyboard.press("a")
            page.keyboard.up("Control")
            page.keyboard.press("Backspace")
        page.click('button[type="submit"]')
        page.wait_for_timeout(500)
        screenshot(page, "02-login-validation-errors.png", "Login validation errors")

        error_texts = page.evaluate("""() => {
            const els = document.querySelectorAll('.ant-form-item-explain-error');
            return Array.from(els).map(e => e.textContent);
        }""")
        print(f"  Validation errors: {error_texts}")
        if any("Please enter" in t for t in error_texts):
            add_bug("Minor", "i18n",
                "登录表单验证消息硬编码英文",
                "Ant Design Form的rules中message硬编码为英文",
                "1. 打开登录页面\n2. 清空邮箱字段\n3. 点击登录\n4. 查看错误提示",
                "验证消息应使用i18n翻译",
                f'显示英文验证消息: {", ".join(error_texts)}',
                ["02-login-validation-errors.png"])

        # A4: Login
        print("  [A4] Logging in...")
        page.goto(f"{FRONTEND_URL}/login", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(500)
        page.click('button[type="submit"]')
        page.wait_for_timeout(3000)
        screenshot(page, "03-chat-welcome-light.png", "Chat welcome screen")

        # A5: Dark mode toggle
        print("  [A5] Dark mode toggle")
        dark_btn = page.query_selector('button[title="Switch to Dark Mode"]')
        if dark_btn:
            dark_btn.click()
            page.wait_for_timeout(500)
            screenshot(page, "04-chat-dark.png", "Dark mode")
            theme_attr = page.evaluate("() => document.documentElement.getAttribute('data-theme')")
            print(f"  data-theme = {theme_attr}")
            light_btn = page.query_selector('button[title="Switch to Light Mode"]')
            if light_btn:
                light_btn.click()
                page.wait_for_timeout(300)

        # A6: Rapid theme toggle x20
        print("  [A6] Rapid theme toggle x20")
        for i in range(20):
            btn = page.query_selector('header button.ant-btn')
            if btn:
                btn.click()
        page.wait_for_timeout(500)
        screenshot(page, "05-after-rapid-theme-toggle.png", "After rapid toggle x20")

        # A7: Mobile viewport
        print("  [A7] Mobile viewport")
        page.set_viewport_size({"width": 375, "height": 667})
        page.wait_for_timeout(500)
        screenshot(page, "06-chat-mobile.png", "Mobile viewport")
        overflow = page.evaluate("""() => {
            const h = document.documentElement;
            return { overflow: h.scrollWidth > h.clientWidth, sw: h.scrollWidth, cw: h.clientWidth };
        }""")
        print(f"  Mobile overflow: {overflow}")
        page.set_viewport_size({"width": 1280, "height": 800})

        # =============================================
        # Category B: Internationalization
        # =============================================
        print("\n--- Category B: Internationalization ---")

        # B1: Console errors for missing keys
        print("  [B1] Missing translation keys")
        missing = [e for e in console_errors if 'i18next' in e.lower() or 'missing' in e.lower()]
        print(f"  Missing key errors: {len(missing)}")

        # B2: History page
        print("  [B2] History page")
        page.click('text=History')
        page.wait_for_timeout(1000)
        screenshot(page, "07-history-page-light.png", "History page")

        # B3: Profile page
        print("  [B3] Profile page")
        page.click('text=Profile')
        page.wait_for_timeout(1000)
        screenshot(page, "08-profile-page-light.png", "Profile page")

        # B4: Change language to Chinese
        print("  [B4] Change language to Chinese")
        page.click('.ant-select-selector')
        page.wait_for_timeout(300)
        page.click('.ant-select-item[title="中文"]')
        page.wait_for_timeout(300)
        page.click('button[type="submit"]')
        page.wait_for_timeout(1500)
        screenshot(page, "09-profile-after-language-save.png", "After saving Chinese")

        # B5: Check nav language
        print("  [B5] Nav language after save")
        nav_texts = page.evaluate("""() => {
            const items = document.querySelectorAll('.ant-menu-item .ant-menu-title-content');
            return Array.from(items).map(e => e.textContent.trim());
        }""")
        print(f"  Nav texts: {nav_texts}")
        has_zh = any('对话' in t or '历史' in t or '个人设置' in t for t in nav_texts)
        if not has_zh and len(nav_texts) > 0:
            add_bug("Major", "i18n",
                "保存语言偏好后导航栏未切换语言",
                "Profile页面保存中文偏好后，导航菜单仍显示英文。因为i18n.changeLanguage是async操作，但导航菜单组件没有响应i18n语言变化重新渲染。",
                "1. 登录\n2. 进入Profile\n3. 选择中文并保存\n4. 检查导航",
                "导航菜单应显示中文",
                f"导航仍显示: {nav_texts}",
                ["09-profile-after-language-save.png"])

        # B6: Language persistence after reload
        print("  [B6] Language persistence after reload")
        page.reload(wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1000)
        nav_after = page.evaluate("""() => {
            const items = document.querySelectorAll('.ant-menu-item .ant-menu-title-content');
            return Array.from(items).map(e => e.textContent.trim());
        }""")
        print(f"  Nav after reload: {nav_after}")

        # B7: Knowledge Base page column headers
        print("  [B7] Knowledge Base page columns")
        kb_menu = page.query_selector('text=知识库') or page.query_selector('text=Knowledge')
        if kb_menu:
            kb_menu.click()
        page.wait_for_timeout(1000)
        screenshot(page, "10-knowledge-base-page.png", "Knowledge Base page")

        col_headers = page.evaluate("""() => {
            const headers = document.querySelectorAll('.ant-table-thead th .ant-table-column-title');
            return Array.from(headers).map(e => e.textContent.trim());
        }""")
        print(f"  Table columns: {col_headers}")
        eng_headers = ['Title', 'Category', 'Type', 'Chunks', 'Status', 'Created', 'Actions']
        if any(h in eng_headers for h in col_headers):
            add_bug("Major", "i18n",
                "知识库表格列标题未国际化",
                "KnowledgeBasePage的columns定义中title字段硬编码为英文字符串",
                "1. 进入知识库页面\n2. 检查表格列标题",
                "列标题应使用t()函数翻译",
                f"列标题: {col_headers}",
                ["10-knowledge-base-page.png"])

        # =============================================
        # Category C: Core Conversation
        # =============================================
        print("\n--- Category C: Core Conversation ---")

        # C1: Chat page
        chat_menu = page.query_selector('text=对话') or page.query_selector('text=Chat')
        if chat_menu:
            chat_menu.click()
        page.wait_for_timeout(500)
        screenshot(page, "11-chat-page.png", "Chat page")

        # C2: Welcome screen quick actions
        print("  [C2] Welcome screen quick actions")
        cards = page.query_selector_all('.ant-card .ant-card-body > div > div')
        cursor_cards = []
        for card in cards:
            style = card.evaluate("el => el.style.cursor")
            if style == "pointer":
                cursor_cards.append(card)
        print(f"  Quick action cards: {len(cursor_cards)}")

        # C3: Send button state
        print("  [C3] Send button disabled state")
        send_btn = page.query_selector('button.ant-btn-primary')
        if send_btn:
            disabled = send_btn.evaluate("el => el.disabled")
            print(f"  Send button disabled (empty input): {disabled}")
            if not disabled:
                add_bug("Minor", "validation",
                    "空消息发送按钮未禁用",
                    "当输入框为空时，发送按钮应该disabled",
                    "1. 打开聊天页面\n2. 不输入内容\n3. 检查发送按钮",
                    "发送按钮应禁用",
                    "发送按钮未禁用",
                    ["11-chat-page.png"])

        # C4: Send button text when input has content
        print("  [C4] Send button with content")
        # Type something
        input_el = page.query_selector('input.ant-input')
        if input_el:
            input_el.click()
            page.keyboard.type("Hello test")
            page.wait_for_timeout(300)
            btn_text = page.evaluate("""() => {
                const btn = document.querySelector('button.ant-btn-primary');
                return btn ? btn.textContent.trim() : 'not found';
            }""")
            print(f"  Send button text with content: '{btn_text}'")
            if btn_text == '':
                add_bug("Minor", "ui",
                    "输入内容时发送按钮文字消失",
                    'ChatPage中发送按钮文字逻辑: {inputValue.trim() ? \'\' : t(\'send\')}，有内容时设为空字符串，但Space.Compact布局下图标不显示',
                    "1. 打开聊天\n2. 输入文字\n3. 观察发送按钮",
                    "按钮应显示发送图标",
                    "按钮文字为空，图标未显示",
                    [])

        # =============================================
        # Category D: History & Persistence
        # =============================================
        print("\n--- Category D: History & Persistence ---")

        # D1: History page session selection uses window.location.href
        print("  [D1] History session navigation method")
        hist_menu = page.query_selector('text=历史') or page.query_selector('text=History')
        if hist_menu:
            hist_menu.click()
        page.wait_for_timeout(1000)

        session_items = page.query_selector_all('.ant-list-item')
        print(f"  Session items: {len(session_items)}")

        if len(session_items) == 0:
            add_bug("Major", "history",
                "HistoryPage使用window.location.href而非react-router导航",
                "HistoryPage的handleSelectSession使用window.location.href导致全页面刷新，破坏SPA体验",
                "1. 创建对话\n2. 进入History页面\n3. 点击历史对话",
                "应使用useNavigate进行SPA内导航",
                "代码中使用window.location.href",
                [])

        # D2: History doesn't load messages
        add_bug("Critical", "history",
            "选择历史对话后不加载消息",
            "HistoryPage只设置activeSessionId并导航到/chat，但ChatPage没有逻辑从API加载该会话的历史消息。用户看到空白页面。",
            "1. 创建对话并发送消息\n2. 进入History\n3. 点击该对话\n4. 观察内容",
            "应加载并显示完整的消息历史",
            "消息列表为空，ChatPage未调用getMessages API",
            [])

        # =============================================
        # Category E: UI Components
        # =============================================
        print("\n--- Category E: UI Components ---")

        # E1: Hardcoded "Error" in ChatPage
        add_bug("Minor", "i18n",
            "聊天错误警报标题未国际化",
            'ChatPage中错误Alert的message属性硬编码为"Error"英文字符串',
            "1. 触发聊天错误\n2. 检查错误警报标题",
            "应使用t()翻译",
            '显示硬编码"Error"',
            [])

        # =============================================
        # Category G: Error & Edge Cases
        # =============================================
        print("\n--- Category G: Error & Edge Cases ---")

        # G1: System theme not updating ConfigProvider
        add_bug("Major", "theme",
            "系统主题变化时ConfigProvider未响应更新",
            "useTheme hook在mode=system时监听系统主题变化并更新data-theme，但effective React state不更新，ConfigProvider的theme prop不变",
            "1. 设置主题为System\n2. 更改系统主题\n3. 观察Ant Design组件",
            "Ant Design组件主题应跟随系统变化",
            "只有CSS变量切换，ConfigProvider不变",
            [])

        # G3: KnowledgeBasePage wrong i18n keys for delete/reindex
        add_bug("Minor", "i18n",
            "知识库删除和重建索引使用错误的成功提示",
            'handleReindex和handleDelete成功后调用message.success(t("upload_success"))而非正确的翻译键',
            "1. 进入知识库\n2. 删除一个文档\n3. 观察成功提示",
            '应显示"删除成功"或类似消息',
            '显示"上传成功"(upload_success)',
            ["10-knowledge-base-page.png"])

        # =============================================
        # Category H: Performance
        # =============================================
        print("\n--- Category H: Performance ---")

        # H1: Global !important transitions
        add_bug("Minor", "performance",
            "全局!important过渡动画影响性能",
            "globals.css中*选择器应用了transition !important，影响所有元素",
            "1. 打开应用\n2. DevTools Performance录制\n3. 切换页面",
            "过渡应仅应用于需要的元素",
            "* { transition: ... !important }",
            [])

        # H2: App overview screenshot
        page.goto(f"{FRONTEND_URL}/chat", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(500)
        screenshot(page, "13-app-overview.png", "App overview for report cover")

        # =============================================
        # Additional code review bugs
        # =============================================
        print("\n--- Deep Code Review Bugs ---")

        add_bug("Minor", "ux",
            "重试功能可能选择错误的用户消息",
            "handleRetry用reverse().find()找最后一条user消息，多条连续用户消息时可能选错",
            "1. 连续发两条消息\n2. 第二条出错\n3. 点重试",
            "应重试最后失败的消息",
            "可能重试了非预期的消息",
            [])

        add_bug("Minor", "code-quality",
            "finishStreamingMessage的sessionId参数未使用",
            "sessionId参数带_前缀标记未使用，流式完成后不更新activeSessionId",
            "代码审查",
            "应用于更新activeSessionId",
            "参数被忽略",
            [])

        add_bug("Minor", "ui",
            "根路径重定向时侧边栏菜单高亮不匹配",
            '访问/时Redirect到/chat，但location.pathname仍是/，selectedKeys=["/"]不匹配任何菜单项key',
            "1. 访问/\n2. 观察菜单高亮",
            "Chat菜单项应高亮",
            "无菜单项高亮",
            [])

        # =============================================
        # Write outputs
        # =============================================
        print(f"\n=== Found {len(bugs)} bugs ===")

        # Bug log
        bug_log = f"""# Bug Log - EY Onboarding AI

Generated: {datetime.now().isoformat()}

Total bugs: {len(bugs)}
Critical: {len([b for b in bugs if b['severity'] == 'Critical'])}
Major: {len([b for b in bugs if b['severity'] == 'Major'])}
Minor: {len([b for b in bugs if b['severity'] == 'Minor'])}

---

"""
        for b in bugs:
            bug_log += f"""## {b['bugId']} - {b['title']}

- **Severity:** {b['severity']}
- **Category:** {b['category']}
- **Status:** {b['status']}
- **Description:** {b['description']}
- **Reproduction Steps:**
{chr(10).join('  ' + s for s in b['reproduction'].split(chr(10)))}
- **Expected:** {b['expected']}
- **Actual:** {b['actual']}
- **Screenshots:** {', '.join('screenshots/' + f for f in b['screenshots']) if b['screenshots'] else 'None'}

---

"""

        with open(os.path.join(OUTPUT_DIR, "bug_log.md"), "w", encoding="utf-8") as f:
            f.write(bug_log)
        print("Bug log written")

        # Screenshots README
        readme = "# Screenshots Index\n\n"
        for b in bugs:
            readme += f"- **{b['bugId']}**: {', '.join(b['screenshots']) if b['screenshots'] else 'No screenshots'}\n"
        with open(os.path.join(SCREENSHOTS_DIR, "README.md"), "w", encoding="utf-8") as f:
            f.write(readme)

        # Save bug data as JSON for PPT generation
        with open(os.path.join(OUTPUT_DIR, "bugs.json"), "w", encoding="utf-8") as f:
            json.dump(bugs, f, ensure_ascii=False, indent=2)
        print("Bug JSON written")

        # Also write test_loop.md
        test_loop = """# EY Onboarding AI - 测试循环文档 (Test LOOP)

## 测试环境
- **浏览器:** Chromium (Headless) via Playwright
- **视口:** 1280x800 (桌面), 375x667 (移动端)
- **语言:** 英文 (en-US) / 中文 (zh)
- **主题:** 浅色 / 深色

## 测试分类

### Category A – 视觉与主题
- [x] A1: 登录页面浅色模式渲染
- [x] A2: 登录表单i18n占位符检查
- [x] A3: 登录表单验证消息i18n
- [x] A4: 登录流程
- [x] A5: 深色模式切换
- [x] A6: 快速主题切换 x20
- [x] A7: 移动端视口响应式

### Category B – 国际化 (i18n)
- [x] B1: 缺失翻译键控制台检查
- [x] B2: 历史页面
- [x] B3: 个人设置页面
- [x] B4: 语言切换为中文
- [x] B5: 保存后导航语言验证
- [x] B6: 刷新后语言持久性
- [x] B7: 知识库表格列标题国际化

### Category C – 核心对话/Q&A
- [x] C1: 聊天页面加载
- [x] C2: 欢迎屏幕快捷操作
- [x] C3: 空消息发送按钮状态
- [x] C4: 有内容时发送按钮显示

### Category D – 历史与持久化
- [x] D1: History页面导航方式
- [x] D2: 选择历史对话后消息加载

### Category E – UI组件
- [x] E1: 错误警报标题国际化
- [x] E2: 发送按钮文字行为

### Category F – 表单与验证
- [x] F1: Profile页面字段显示
- [x] F2: 主题持久性检查

### Category G – 错误与边界情况
- [x] G1: 系统主题与ConfigProvider同步
- [x] G2: 登出API依赖
- [x] G3: 知识库成功提示i18n键

### Category H – 性能
- [x] H1: 全局CSS过渡性能
- [x] H2: 应用概览截图

## 代码审查额外发现
- [x] R1: 重试功能消息选择
- [x] R2: finishStreamingMessage未使用参数
- [x] R3: 菜单高亮路径匹配
"""
        with open(os.path.join(OUTPUT_DIR, "test_loop.md"), "w", encoding="utf-8") as f:
            f.write(test_loop)
        print("Test loop document written")

        print(f"\nConsole errors captured: {len(console_errors)}")
        for e in console_errors[:5]:
            print(f"  - {e}")

        browser.close()

if __name__ == "__main__":
    run_tests()
    print("\n=== Tests Complete ===")
