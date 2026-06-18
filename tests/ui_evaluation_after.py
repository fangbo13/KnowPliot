"""
EY Onboarding AI - 优化后截图脚本
专注于拍摄优化后的 UI 状态，用于与优化前对比
"""
import asyncio
import os
import json
import time
from pathlib import Path
from playwright.async_api import async_playwright

BASE_URL = "http://localhost:3000"
SCREENSHOTS_DIR = Path(__file__).parent / "screenshots_after"
SCREENSHOTS_DIR.mkdir(exist_ok=True)

results = {"screenshots": [], "performance": {}, "findings": []}

def add_screenshot(name, path, description=""):
    results["screenshots"].append({"name": name, "path": str(path), "description": description})


async def take_shot(page, name, desc, idx):
    path = SCREENSHOTS_DIR / f"{idx:02d}_{name}.png"
    await page.screenshot(path=str(path), full_page=True)
    add_screenshot(desc, path, desc)
    print(f"  [截图] {path.name}")
    return path


async def do_login(page):
    """使用 Ant Design Form 登录"""
    await page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
    await asyncio.sleep(2)

    # Ant Design Input with prefix icons - use the input inside the form
    inputs = await page.locator("input").all()
    print(f"  找到 {len(inputs)} 个 input")

    for inp in inputs:
        input_type = await inp.get_attribute("type")
        print(f"    input type={input_type}")

    # Find email and password inputs by type or placeholder
    email_inputs = page.locator("input[type='email'], input[placeholder*='email'], input[placeholder*='mail']")
    pwd_inputs = page.locator("input[type='password']")

    email_count = await email_inputs.count()
    pwd_count = await pwd_inputs.count()
    print(f"  email inputs: {email_count}, pwd inputs: {pwd_count}")

    if email_count > 0:
        await email_inputs.first.fill("admin@ey.com")
    if pwd_count > 0:
        await pwd_inputs.first.fill("admin123")

    # Click sign in button
    sign_in_btns = page.locator("button:has-text('Sign In')")
    if await sign_in_btns.count() > 0:
        await sign_in_btns.first.click()
    else:
        # Try any submit button
        await page.locator("button[type='submit']").first.click()

    try:
        await page.wait_for_url("**/chat*", timeout=15000)
    except:
        pass
    await asyncio.sleep(3)


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
            # 1. 登录页
            print("\n=== 1. 登录页 ===")
            start = time.time()
            await page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
            await asyncio.sleep(2)
            results["performance"]["login_page_load"] = round(time.time() - start, 3)
            await take_shot(page, "login_page", "优化后登录页 - EY Yellow 品牌配色", next_shot())

            # 2. 登录页错误测试
            inputs = page.locator("input")
            all_inputs = await inputs.all()
            pwd_inputs = page.locator("input[type='password']")
            email_inputs = page.locator("input[type='email'], input[placeholder*='email'], input[placeholder*='mail']")

            if await email_inputs.count() > 0:
                await email_inputs.first.fill("admin@ey.com")
            if await pwd_inputs.count() > 0:
                await pwd_inputs.first.fill("wrong_password")

            sign_in_btns = page.locator("button:has-text('Sign In')")
            if await sign_in_btns.count() > 0:
                await sign_in_btns.first.click()
            else:
                await page.locator("button[type='submit']").first.click()
            await asyncio.sleep(2)
            await take_shot(page, "login_error", "错误登录提示 - Ant Design Alert 组件", next_shot())

            # 3. 登录
            if await email_inputs.count() > 0:
                await email_inputs.first.fill("admin@ey.com")
            if await pwd_inputs.count() > 0:
                await pwd_inputs.first.fill("admin123")
            sign_in_btns = page.locator("button:has-text('Sign In')")
            if await sign_in_btns.count() > 0:
                await sign_in_btns.first.click()
            else:
                await page.locator("button[type='submit']").first.click()
            try:
                await page.wait_for_url("**/chat*", timeout=15000)
            except:
                pass
            await asyncio.sleep(3)
            await take_shot(page, "welcome_page", "优化后欢迎页 - EY Yellow Logo", next_shot())

            # 4. 点击快捷操作
            print("\n=== 快捷操作 ===")
            btn = page.locator("button:has-text('IT Setup')")
            if await btn.count() > 0:
                await btn.first.click()
                await asyncio.sleep(1)
                await take_shot(page, "action_click", "点击 IT Setup 快捷按钮", next_shot())
                await asyncio.sleep(10)
                await take_shot(page, "action_response", "AI 响应 - 新消息气泡样式", next_shot())

            # 5. 侧边栏
            print("\n=== 导航页 ===")
            await take_shot(page, "sidebar", "优化后侧边栏 - EY 黄色品牌标识", next_shot())

            # 6. 历史记录页
            await page.goto(f"{BASE_URL}/history", wait_until="domcontentloaded")
            await asyncio.sleep(2)
            await take_shot(page, "history_page", "历史记录页", next_shot())

            # 7. Profile 页 (含主题切换器)
            await page.goto(f"{BASE_URL}/profile", wait_until="domcontentloaded")
            await asyncio.sleep(2)
            await take_shot(page, "profile_page", "Profile 页 - 含主题切换器", next_shot())

            # 8. 知识库管理页
            await page.goto(f"{BASE_URL}/admin/knowledge", wait_until="domcontentloaded")
            await asyncio.sleep(2)
            await take_shot(page, "knowledge_page", "知识库管理页", next_shot())

            # 9. 回到聊天页截图消息气泡
            await page.goto(f"{BASE_URL}/chat", wait_until="domcontentloaded")
            await asyncio.sleep(2)
            await take_shot(page, "message_bubbles", "新消息气泡 - 深灰底+黄色装饰条", next_shot())

            # 10. 测试暗色模式 - 切换到暗色
            print("\n=== 暗色模式测试 ===")
            await page.goto(f"{BASE_URL}/profile", wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # Click "Dark" option in the Segmented theme switcher
            dark_btn = page.locator("div:has-text('Dark')")
            all_dark = await dark_btn.all()
            print(f"  Dark elements: {len(all_dark)}")
            for d in all_dark:
                text = await d.text_content()
                print(f"    text: {text.strip()[:30]}")

            # Try clicking the Dark segmented button
            try:
                segmented = page.locator(".ant-segmented-item:has-text('Dark')")
                if await segmented.count() > 0:
                    await segmented.first.click()
                    print("  已切换到暗色模式")
                else:
                    # Try direct text match
                    await page.locator("text=Dark").first.click()
                    print("  已切换到暗色模式 (text)")
            except Exception as e:
                print(f"  暗色模式切换失败: {e}")

            await asyncio.sleep(1)
            await take_shot(page, "profile_dark", "Profile 页 - 暗色模式", next_shot())

            # 11. 暗色模式下的聊天页
            await page.goto(f"{BASE_URL}/chat", wait_until="domcontentloaded")
            await asyncio.sleep(2)
            await take_shot(page, "chat_dark", "聊天页 - 暗色模式", next_shot())

            # 12. 暗色模式下的侧边栏
            await page.goto(f"{BASE_URL}/history", wait_until="domcontentloaded")
            await asyncio.sleep(2)
            await take_shot(page, "history_dark", "历史记录页 - 暗色模式", next_shot())

            # 13. 暗色模式下的知识库
            await page.goto(f"{BASE_URL}/admin/knowledge", wait_until="domcontentloaded")
            await asyncio.sleep(2)
            await take_shot(page, "knowledge_dark", "知识库管理页 - 暗色模式", next_shot())

            # 14. 切换回亮色模式
            await page.goto(f"{BASE_URL}/profile", wait_until="domcontentloaded")
            await asyncio.sleep(2)
            try:
                light_btn = page.locator(".ant-segmented-item:has-text('Light')")
                if await light_btn.count() > 0:
                    await light_btn.first.click()
            except:
                pass
            await asyncio.sleep(1)

            # 15. 响应式截图
            print("\n=== 响应式测试 ===")
            await page.goto(f"{BASE_URL}/chat", wait_until="domcontentloaded")
            await asyncio.sleep(2)

            await page.set_viewport_size({"width": 1920, "height": 1080})
            await asyncio.sleep(1)
            await take_shot(page, "responsive_1920", "1920px 桌面端", next_shot())

            await page.set_viewport_size({"width": 768, "height": 1024})
            await asyncio.sleep(1)
            await take_shot(page, "responsive_768", "768px 平板端", next_shot())

            await page.set_viewport_size({"width": 375, "height": 812})
            await asyncio.sleep(1)
            await take_shot(page, "responsive_375", "375px 手机端", next_shot())

        except Exception as e:
            print(f"\n测试异常: {e}")
            import traceback
            traceback.print_exc()
            try:
                await take_shot(page, "error", f"异常: {str(e)[:60]}", next_shot())
            except:
                pass

        finally:
            await browser.close()

        # Save results
        result_path = SCREENSHOTS_DIR / "test_results.json"
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"\n=== 测试完成 ===")
        print(f"截图: {len(results['screenshots'])} 张")
        print(f"结果: {result_path}")


if __name__ == "__main__":
    asyncio.run(main())
