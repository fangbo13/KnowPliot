# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Quick DOM explorer for UI selectors"""
import asyncio, json, sys, os
os.environ['PYTHONIOENCODING'] = 'utf-8'
try: sys.stdout.reconfigure(encoding='utf-8')
except: pass
from playwright.async_api import async_playwright

async def explore():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1280, 'height': 800})

        # Login
        await page.goto('http://127.0.0.1:3030/login', wait_until='networkidle')
        await asyncio.sleep(2)
        await page.fill('#email', 'admin@ey.com')
        await page.fill('#password', 'admin123')
        await page.click('button[type=submit]')
        await asyncio.sleep(5)

        r = {'url': page.url}

        # Chat
        r['chat'] = await page.evaluate('''() => {
            const a = document.querySelectorAll('textarea,button,[class*=sidebar],[class*=session]');
            return Array.from(a).slice(0,20).map(e => ({t:e.tagName,c:e.className.slice(0,80),x:(e.textContent||'').slice(0,40),p:e.placeholder||''}));
        }''')

        # Dashboard
        await page.goto('http://127.0.0.1:3030/admin/dashboard', wait_until='networkidle')
        await asyncio.sleep(3)
        r['dash'] = await page.evaluate('''() => {
            const a = document.querySelectorAll('.ant-table,.ant-card,.ant-tag,.ant-statistic,[class*=health],[class*=badge]');
            return Array.from(a).slice(0,20).map(e => ({t:e.tagName,c:e.className.slice(0,80),x:(e.textContent||'').slice(0,50)}));
        }''')

        # KB
        await page.goto('http://127.0.0.1:3030/admin/knowledge', wait_until='networkidle')
        await asyncio.sleep(3)
        r['kb'] = await page.evaluate('''() => {
            const a = document.querySelectorAll('.ant-btn,button,.ant-table,input[type=file]');
            return Array.from(a).slice(0,15).map(e => ({t:e.tagName,tp:e.type||'',c:e.className.slice(0,80),x:(e.textContent||'').slice(0,50)}));
        }''')

        # Crawler
        await page.goto('http://127.0.0.1:3030/admin/crawler', wait_until='networkidle')
        await asyncio.sleep(3)
        r['crawl'] = await page.evaluate('''() => {
            const a = document.querySelectorAll('input,button,.ant-btn');
            return Array.from(a).slice(0,15).map(e => ({t:e.tagName,tp:e.type||'',c:e.className.slice(0,80),x:(e.textContent||'').slice(0,50),p:e.placeholder||''}));
        }''')

        # Profile/Theme
        await page.goto('http://127.0.0.1:3030/profile', wait_until='networkidle')
        await asyncio.sleep(3)
        r['theme'] = await page.evaluate('''() => {
            return {
                dt: document.documentElement.getAttribute('data-theme') || '',
                seg: document.querySelectorAll('.ant-segmented-item').length,
                segItems: Array.from(document.querySelectorAll('.ant-segmented-item')).slice(0,6).map(e => ({x:(e.textContent||'').slice(0,30),c:e.className.slice(0,60)}))
            };
        }''')

        with open('D:/Github/Onborading-AI/audit_reports/ui_dom.json', 'w', encoding='utf-8') as f:
            json.dump(r, f, ensure_ascii=False, indent=2)

        await browser.close()

asyncio.run(explore())
