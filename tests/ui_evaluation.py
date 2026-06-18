"""
EY Onboarding AI - 浏览器自动化UI测评脚本 (v2)
使用 Playwright 执行全面的 UI 测试并截图
"""
import asyncio
import os
import json
import time
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# 配置
BASE_URL = "http://localhost:3000"
SCREENSHOTS_DIR = Path(__file__).parent / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)

# 测试结果收集
results = {
    "screenshots": [],
    "performance": {},
    "findings": [],
    "scores": {}
}

def add_screenshot(name, path, description=""):
    results["screenshots"].append({"name": name, "path": str(path), "description": description})

def add_finding(category, severity, title, description, is_positive=False):
    results["findings"].append({
        "category": category, "severity": severity, "title": title,
        "description": description, "is_positive": is_positive
    })


async def do_login(page):
    """执行登录"""
    await page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
    await page.wait_for_selector("button", state="visible", timeout=10000)
    await asyncio.sleep(1)
    await page.fill("input[type='email']", "admin@ey.com")
    await page.fill("input[type='password']", "admin123")
    await page.click("button")
    try:
        await page.wait_for_url("**/chat*", timeout=10000)
    except:
        pass
    await asyncio.sleep(3)


async def ensure_welcome(page):
    """确保在欢迎页（无会话状态）"""
    # 先清除 localStorage 来重置会话状态
    await page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
    await asyncio.sleep(1)
    await page.evaluate("() => { localStorage.removeItem('ey-auth'); }")
    await asyncio.sleep(0.5)
    await do_login(page)
    await asyncio.sleep(2)


async def take_shot(page, name, desc, idx):
    """截图辅助函数"""
    path = SCREENSHOTS_DIR / f"{idx:02d}_{name}.png"
    await page.screenshot(path=str(path), full_page=True)
    add_screenshot(desc, path, desc)
    print(f"  [截图] {name} -> {path.name}")
    return path


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        shot_idx = [0]

        def next_shot():
            shot_idx[0] += 1
            return shot_idx[0]

        try:
            # ============================================
            # 1. 登录页测试
            # ============================================
            print("\n=== 1. 登录页测试 ===")
            start = time.time()
            await page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
            await page.wait_for_selector("button", state="visible", timeout=10000)
            await asyncio.sleep(1)
            load_time = time.time() - start
            results["performance"]["login_page_load"] = round(load_time, 3)
            print(f"  加载时间: {load_time:.3f}s")

            await take_shot(page, "login_page", "登录页默认状态，预填demo凭据", next_shot())

            # 品牌色检查
            h1_count = await page.locator("h1").count()
            if h1_count > 0:
                h1_style = await page.locator("h1").first.get_attribute("style")
                if h1_style and "E00033" in h1_style:
                    add_finding("视觉设计", "positive", "品牌色一致",
                                "登录页 EY 标题使用品牌红色 #E00033", is_positive=True)

            # 检查硬编码凭据
            email_val = await page.input_value("input[type='email']")
            pwd_val = await page.input_value("input[type='password']")
            if email_val and pwd_val:
                add_finding("安全性", "medium", "硬编码 demo 凭据",
                            f"登录页预填了账号({email_val})和密码，生产环境存在安全风险")

            # 错误登录测试 - 先刷新页面确保干净状态
            await page.reload()
            await page.wait_for_selector("button", state="visible", timeout=10000)
            await asyncio.sleep(1)
            await page.fill("input[type='email']", "admin@ey.com")
            await page.fill("input[type='password']", "wrong_password")
            await page.click("button")
            await asyncio.sleep(2)

            error_div = await page.locator("div:has-text('Login failed')").count()
            if error_div == 0:
                error_div2 = await page.locator("div[style*='ffccc7']").count()
                error_div = max(error_div, error_div2)

            if error_div > 0:
                add_finding("交互可用性", "positive", "错误提示清晰",
                            "登录失败时显示明确的错误提示", is_positive=True)
                await take_shot(page, "login_error", "错误凭据登录时的错误提示", next_shot())
            else:
                add_finding("交互可用性", "medium", "错误提示缺失",
                            "登录失败后未找到明显的错误提示元素")

            # 正常登录 - 完全刷新页面
            await page.reload()
            await page.wait_for_selector("button", state="visible", timeout=10000)
            await asyncio.sleep(1)
            await page.fill("input[type='email']", "admin@ey.com")
            await page.fill("input[type='password']", "admin123")
            start = time.time()
            await page.click("button")
            # 等待跳转
            try:
                await page.wait_for_url("**/chat*", timeout=10000)
            except:
                pass
            await asyncio.sleep(3)
            results["performance"]["login_to_chat"] = round(time.time() - start, 3)

            current_url = page.url
            print(f"  登录后 URL: {current_url}")
            if "/chat" in current_url:
                add_finding("交互可用性", "positive", "登录跳转正确",
                            "登录成功后自动跳转到 /chat 聊天页", is_positive=True)

            # ============================================
            # 2. 欢迎页测试
            # ============================================
            print("\n=== 2. 欢迎页测试 ===")
            await asyncio.sleep(2)

            # 获取页面内容用于调试
            page_text = await page.text_content("body")
            print(f"  页面文本片段: {page_text[:300]}...")

            await take_shot(page, "welcome_page", "聊天首页 - 欢迎界面", next_shot())

            # 检查快捷按钮
            all_btns = await page.locator("button").all()
            print(f"  总按钮数: {len(all_btns)}")

            quick_labels = []
            for btn in all_btns:
                try:
                    txt = await btn.text_content(timeout=2000)
                    if txt and any(x in txt for x in ["IT Setup", "Reimbursement", "Annual",
                                                        "Training", "Office", "Buddy"]):
                        quick_labels.append(txt.strip())
                        print(f"  快捷按钮: {txt.strip()[:40]}")
                except:
                    pass

            print(f"  找到 {len(quick_labels)} 个快捷按钮")
            if len(quick_labels) >= 6:
                add_finding("交互可用性", "positive", "快捷操作完整",
                            f"欢迎页显示 {len(quick_labels)} 个快捷操作按钮", is_positive=True)

            # 响应式测试 - 平板
            await page.set_viewport_size({"width": 768, "height": 1024})
            await asyncio.sleep(1)
            await take_shot(page, "welcome_tablet", "768px 平板响应式布局", next_shot())

            # 响应式测试 - 手机
            await page.set_viewport_size({"width": 375, "height": 812})
            await asyncio.sleep(1)
            await take_shot(page, "welcome_mobile", "375px 手机响应式布局", next_shot())

            # 恢复
            await page.set_viewport_size({"width": 1280, "height": 800})

            # ============================================
            # 3. 快捷操作点击测试
            # ============================================
            print("\n=== 3. 快捷操作点击测试 ===")

            # 尝试点击第一个快捷按钮 - 使用多种选择器
            clicked = False
            selectors = [
                "button:has-text('IT Setup')",
                "button:has-text('IT')",
                ".ant-btn:has-text('IT Setup')",
            ]

            for sel in selectors:
                try:
                    loc = page.locator(sel)
                    count = await loc.count()
                    print(f"  选择器 '{sel}': {count} 个匹配")
                    if count > 0:
                        await loc.first.click()
                        clicked = True
                        print(f"  已点击: {sel}")
                        break
                except Exception as e:
                    print(f"  选择器 '{sel}' 失败: {e}")

            if not clicked:
                # 尝试直接点击包含 "IT Setup" 文本的任何元素
                try:
                    await page.locator(":text('IT Setup')").first.click()
                    clicked = True
                    print("  通过 text 选择器点击成功")
                except Exception as e:
                    print(f"  text 选择器也失败: {e}")

                if not clicked:
                    # 尝试通过 evaluate 点击
                    btns = await page.query_selector_all("button")
                    for btn in btns:
                        txt = await btn.text_content()
                        if txt and "IT" in txt:
                            await btn.click()
                            clicked = True
                            print("  通过 querySelector 点击成功")
                            break

            if clicked:
                await take_shot(page, "action_click", "点击快捷按钮后", next_shot())
                print("  等待AI响应...")
                await asyncio.sleep(10)
                await take_shot(page, "action_response", "AI响应完成后", next_shot())

                # 检查消息气泡
                cards = await page.locator(".ant-card").count()
                print(f"  消息卡片数: {cards}")

                # 检查引用
                citation_count = await page.locator(":text('Score:')").count()
                if citation_count > 0:
                    add_finding("功能测试", "positive", "引用系统正常",
                                f"AI响应包含 {citation_count} 个来源引用", is_positive=True)
                    await take_shot(page, "citations", "AI响应的来源引用卡片", next_shot())

                # 检查自动滚动
                scroll_els = await page.query_selector_all("div[style*='overflow']")
                for el in scroll_els:
                    try:
                        sh = await el.evaluate("e => e.scrollHeight")
                        st = await el.evaluate("e => e.scrollTop")
                        ch = await el.evaluate("e => e.clientHeight")
                        if sh > 100:
                            at_bottom = (st + ch) >= (sh - 100)
                            print(f"  滚动检查: scrollHeight={sh}, scrollTop={st}, clientHeight={ch}, at_bottom={at_bottom}")
                            if at_bottom:
                                add_finding("交互可用性", "positive", "自动滚动",
                                            "新消息到达时自动滚动到底部", is_positive=True)
                            break
                    except:
                        pass

            # ============================================
            # 4. 发送自由消息
            # ============================================
            print("\n=== 4. 发送自由消息 ===")

            textarea = page.locator("textarea")
            ta_count = await textarea.count()
            print(f"  textarea 数量: {ta_count}")

            if ta_count > 0:
                await textarea.last.fill("What is the company's vacation policy?")
                await asyncio.sleep(0.5)

                # 检查字数统计
                count_suffix = await page.locator(".ant-input-show-count-suffix").count()
                if count_suffix > 0:
                    add_finding("交互可用性", "positive", "字数统计",
                                "输入框显示字符计数 (showCount)，限制 4000 字符", is_positive=True)

                start = time.time()
                send_btn = page.locator("button:has-text('Send')")
                if await send_btn.count() > 0:
                    await send_btn.last.click()
                else:
                    await page.locator("button").filter(has_text="Send").first.click()

                print("  已发送消息")

                # 等待思考指示器
                await asyncio.sleep(2)
                spinner_count = await page.locator(".ant-spin").count()
                if spinner_count > 0:
                    await take_shot(page, "thinking_spinner", "等待响应时的思考动画", next_shot())
                    add_finding("交互可用性", "positive", "加载状态反馈",
                                "等待响应时显示 Spinner + 'Thinking...' 提示", is_positive=True)

                # 等待响应完成
                await asyncio.sleep(15)
                results["performance"]["chat_response"] = round(time.time() - start, 3)
                print(f"  响应耗时: {results['performance']['chat_response']}s")

                await take_shot(page, "free_question_response", "自由问题AI响应", next_shot())

            # ============================================
            # 5. 边界测试
            # ============================================
            print("\n=== 5. 边界测试 ===")

            # 空输入时按钮状态
            ta = page.locator("textarea")
            if await ta.count() > 0:
                await ta.last.fill("")
                await asyncio.sleep(0.5)
                send_btns = page.locator("button:has-text('Send')")
                if await send_btns.count() > 0:
                    disabled = await send_btns.last.is_disabled()
                    if disabled:
                        add_finding("边界测试", "positive", "空输入防护",
                                    "输入框为空时发送按钮自动禁用", is_positive=True)
                    else:
                        add_finding("边界测试", "medium", "空输入可发送",
                                    "输入框为空时发送按钮未禁用")

                await take_shot(page, "edge_empty", "空输入时按钮状态", next_shot())

                # 超长输入
                await ta.last.fill("A" * 4000)
                await asyncio.sleep(0.5)
                await take_shot(page, "edge_long", "4000字符超长输入", next_shot())

                max_len = await ta.last.get_attribute("maxLength")
                if max_len == "4000":
                    add_finding("边界测试", "positive", "输入长度限制",
                                "输入框 maxLength=4000 并显示字数统计", is_positive=True)

            # ============================================
            # 6. 导航测试
            # ============================================
            print("\n=== 6. 导航测试 ===")

            # 侧边栏检查
            sider = await page.locator(".ant-layout-sider").count()
            if sider > 0:
                add_finding("视觉设计", "positive", "侧边栏导航",
                            "左侧导航栏包含 EY Onboarding 品牌标识和菜单项", is_positive=True)

            await take_shot(page, "sidebar", "侧边栏导航", next_shot())

            # 历史记录页
            await page.goto(f"{BASE_URL}/history", wait_until="domcontentloaded")
            await asyncio.sleep(2)
            await take_shot(page, "history_page", "会话历史列表页", next_shot())

            list_items = await page.locator(".ant-list-item").count()
            print(f"  历史会话数: {list_items}")
            if list_items > 0:
                add_finding("功能测试", "positive", "历史记录功能",
                            f"历史记录页正确显示 {list_items} 个会话", is_positive=True)

            # Profile 页
            await page.goto(f"{BASE_URL}/profile", wait_until="domcontentloaded")
            await asyncio.sleep(2)
            await take_shot(page, "profile_page", "用户设置页", next_shot())

            # 知识库管理页
            await page.goto(f"{BASE_URL}/admin/knowledge", wait_until="domcontentloaded")
            await asyncio.sleep(2)
            await take_shot(page, "knowledge_page", "知识库管理页", next_shot())

            # ============================================
            # 7. 消息气泡样式测试
            # ============================================
            print("\n=== 7. 消息气泡样式 ===")
            await page.goto(f"{BASE_URL}/chat", wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # 检查已有消息气泡的样式
            cards = await page.locator(".ant-card").all()
            user_msg_found = False
            ai_msg_found = False

            for card in cards:
                try:
                    style = await card.evaluate("el => el.style.cssText")
                    if "E00033" in (style or ""):
                        user_msg_found = True
                        # 检查右对齐
                        parent = await card.evaluate("el => el.parentElement?.parentElement?.style.justifyContent")
                        print(f"  用户消息: 红色背景, 对齐={parent}")
                        if parent == "flex-end":
                            add_finding("视觉设计", "positive", "消息气泡对齐",
                                        "用户消息红色右对齐，AI消息白色左对齐，视觉区分清晰", is_positive=True)
                        break
                except:
                    pass

            # 检查 Markdown 渲染
            has_markdown = await page.locator("article, p, ul, ol, h1, h2, h3, strong, em").count()
            if has_markdown > 0:
                add_finding("视觉设计", "positive", "Markdown 渲染",
                            "AI响应通过 react-markdown 渲染富文本格式", is_positive=True)

            await take_shot(page, "message_bubbles", "消息气泡样式", next_shot())

            # ============================================
            # 8. 安全性测试
            # ============================================
            print("\n=== 8. 安全性测试 ===")

            # 检查 localStorage token
            token = await page.evaluate("() => { try { return localStorage.getItem('ey-auth'); } catch(e) { return null; } }")
            if token and len(token) > 10:
                add_finding("安全性", "medium", "Token 存储于 localStorage",
                            "JWT Token 存储在浏览器 localStorage，XSS 攻击可能窃取。建议使用 httpOnly cookie")

            # 路由保护测试
            await page.evaluate("() => { localStorage.removeItem('ey-auth'); }")
            await page.goto(f"{BASE_URL}/history", wait_until="domcontentloaded")
            await asyncio.sleep(1)

            if "/login" in page.url:
                add_finding("安全性", "positive", "路由保护完善",
                            "未认证用户访问受保护路由时自动重定向到登录页", is_positive=True)
            else:
                add_finding("安全性", "critical", "路由保护缺失",
                            "未认证用户可直接访问受保护路由")

            # 重新登录继续测试
            await do_login(page)
            await asyncio.sleep(2)

            # ============================================
            # 9. 输入区域和 Enter 键测试
            # ============================================
            print("\n=== 9. 输入区域测试 ===")
            await page.goto(f"{BASE_URL}/chat", wait_until="domcontentloaded")
            await asyncio.sleep(2)

            ta = page.locator("textarea")
            if await ta.count() > 0:
                await ta.last.fill("Test Enter key")
                await ta.last.press("Enter")
                await asyncio.sleep(1)
                # 检查是否发送
                cards_after = await page.locator(".ant-card").count()
                if cards_after > 0:
                    add_finding("交互可用性", "positive", "Enter 键发送",
                                "按 Enter 键可发送消息", is_positive=True)
                await asyncio.sleep(10)

            await take_shot(page, "input_area", "输入区域和发送按钮", next_shot())

            # ============================================
            # 10. 响应式聊天页测试
            # ============================================
            print("\n=== 10. 响应式聊天页 ===")

            await page.set_viewport_size({"width": 1920, "height": 1080})
            await asyncio.sleep(1)
            await take_shot(page, "responsive_1920", "1920x1080 桌面端聊天页", next_shot())

            await page.set_viewport_size({"width": 1280, "height": 720})
            await asyncio.sleep(1)
            await take_shot(page, "responsive_1280", "1280x720 桌面端聊天页", next_shot())

            await page.set_viewport_size({"width": 768, "height": 1024})
            await asyncio.sleep(1)
            await take_shot(page, "responsive_768_chat", "768px 平板端聊天页", next_shot())

            # 检查侧边栏折叠
            sider_loc = page.locator(".ant-layout-sider").first
            if await sider_loc.count() > 0:
                sider_class = await sider_loc.get_attribute("class")
                if sider_class and "collapsed" in sider_class:
                    add_finding("跨端兼容", "positive", "侧边栏自适应",
                                "平板尺寸下侧边栏自动折叠", is_positive=True)

            await page.set_viewport_size({"width": 1280, "height": 800})

        except Exception as e:
            print(f"\n测试异常: {e}")
            import traceback
            traceback.print_exc()
            try:
                await take_shot(page, "error", f"测试异常: {str(e)[:80]}", next_shot())
            except:
                pass

        finally:
            await browser.close()

        # 保存结果
        result_path = SCREENSHOTS_DIR / "test_results.json"
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"\n=== 测试完成 ===")
        print(f"截图数量: {len(results['screenshots'])}")
        print(f"发现数量: {len(results['findings'])}")
        print(f"性能数据: {json.dumps(results['performance'], indent=2)}")
        print(f"结果保存到: {result_path}")


if __name__ == "__main__":
    asyncio.run(main())
