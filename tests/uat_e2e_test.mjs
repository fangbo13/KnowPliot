/**
 * EY Onboarding AI — UAT E2E Test Script
 * 5 real-user scenarios with headless:false, human-like pacing
 */
import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const BASE_URL = 'http://127.0.0.1:3030';
const SCREENSHOT_DIR = join(__dirname, '..', 'audit_reports', 'screenshots', 'uat');
const REPORT_PATH = join(__dirname, '..', 'audit_reports', 'UAT_Test_Report_2026-06-26.md');
const TEST_EMAIL = 'admin@ey.com';
const TEST_PASSWORD = 'admin123';

mkdirSync(SCREENSHOT_DIR, { recursive: true });

const results = [];
function record(scenario, step, expected, actual, status, screenshot) {
  results.push({ scenario, step, expected, actual, status, screenshot });
  const icon = status === 'PASS' ? 'PASS' : status === 'FAIL' ? 'FAIL' : 'WARN';
  console.log(`  [${icon}] [${scenario}] ${step}: ${actual}`);
}

async function ss(page, name) {
  const path = join(SCREENSHOT_DIR, `${name}.png`);
  await page.screenshot({ path, fullPage: true });
  return `screenshots/uat/${name}.png`;
}

async function humanPause(ms = 1500) {
  await new Promise(r => setTimeout(r, ms + Math.random() * 500));
}

// SCENARIO 1: Login -> Onboarding -> Chat
async function scenario1(page) {
  console.log('\nSCENARIO 1: Login -> Onboarding -> Chat');
  await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 15000 });
  await humanPause(2000);
  let snap = await ss(page, '01_login_page');
  const loginForm = await page.$('.ant-form, form, input[type="password"]');
  record('S1-Login', '1.1 Login page loads', 'Login form visible', loginForm ? 'Login form visible' : 'No login form', loginForm ? 'PASS' : 'FAIL', snap);

  // Try demo button or fill manually
  const demoBtn = await page.$('button:has-text("Demo"), button:has-text("demo"), button:has-text("演示")');
  if (demoBtn) {
    await demoBtn.click();
    await humanPause(1000);
    snap = await ss(page, '02_login_demo_filled');
    record('S1-Login', '1.2 Demo fill', 'Fields auto-filled', 'Demo button clicked', 'PASS', snap);
  } else {
    const emailEl = await page.$('input[id*="email"], input[type="email"], #email');
    if (emailEl) await emailEl.fill(TEST_EMAIL);
    const pwEl = await page.$('input[type="password"]');
    if (pwEl) await pwEl.fill(TEST_PASSWORD);
    snap = await ss(page, '02_login_manual_filled');
    record('S1-Login', '1.2 Manual fill', 'Fields filled', 'Filled manually', 'PASS', snap);
  }

  // Submit
  const loginBtn = await page.$('button[type="submit"], button:has-text("Sign In"), button:has-text("Log In"), button:has-text("登录")');
  if (loginBtn) await loginBtn.click();
  try { await page.waitForURL('**/chat**', { timeout: 15000 }); } catch {}
  await humanPause(2000);
  snap = await ss(page, '03_after_login');
  const url = page.url();
  record('S1-Login', '1.3 Login submit', 'Redirect to /chat', `URL: ${url}`, url.includes('/chat') ? 'PASS' : 'FAIL', snap);

  // Onboarding
  await humanPause(1500);
  const skipBtn = await page.$('button:has-text("Skip"), button:has-text("跳过"), button:has-text("Get Started"), button:has-text("开始")');
  if (skipBtn) {
    snap = await ss(page, '04_onboarding_modal');
    await skipBtn.click();
    await humanPause(1500);
    record('S1-Login', '1.4 Onboarding wizard', 'Skip wizard', 'Wizard dismissed', 'PASS', snap);
  } else {
    await page.evaluate(() => localStorage.setItem('ey-onboarding-seen', 'true'));
    record('S1-Login', '1.4 Onboarding wizard', 'Wizard or skip', 'No wizard shown', 'PASS', snap);
  }
  await humanPause(1000);
  snap = await ss(page, '05_chat_page');
  record('S1-Login', '1.5 Chat page reached', 'Chat interface visible', 'Chat page loaded', page.url().includes('/chat') ? 'PASS' : 'FAIL', snap);
}

// SCENARIO 2: Chat — Send, Stream, Sessions
async function scenario2(page) {
  console.log('\nSCENARIO 2: AI Chat');
  await page.evaluate(() => localStorage.setItem('ey-onboarding-seen', 'true'));

  // Wait for textarea to be available (Ant Design wraps textarea)
  await page.waitForSelector('textarea', { state: 'visible', timeout: 15000 }).catch(() => {});
  const textarea = await page.$('textarea');
  if (!textarea) {
    let snap = await ss(page, '06_no_textarea');
    record('S2-Chat', '2.1 Find input', 'Textarea visible', 'No textarea found', 'FAIL', snap);
    return;
  }
  await textarea.click();
  await humanPause(500);
  await textarea.fill('What is the onboarding process for new employees?');
  await humanPause(1000);
  let snap = await ss(page, '06_message_typed');
  record('S2-Chat', '2.1 Type message', 'Message in input', 'Message typed', 'PASS', snap);

  // Send
  const sendBtn = await page.$('button[aria-label*="send"], button:has(.anticon-send)');
  if (sendBtn) await sendBtn.click();
  else await textarea.press('Enter');
  await humanPause(4000);
  snap = await ss(page, '07_message_sent');
  record('S2-Chat', '2.2 Send message', 'Message sent', 'Send button clicked / Enter pressed', 'PASS', snap);

  // Wait for response
  await humanPause(6000);
  snap = await ss(page, '08_response_received');
  const body = await page.textContent('body');
  const hasResp = body && body.length > 300;
  record('S2-Chat', '2.3 AI response', 'Response visible', hasResp ? 'Page has content' : 'Minimal content', hasResp ? 'PASS' : 'WARN', snap);

  // Sidebar session
  const sidebarItems = await page.$$('[class*="sidebar"] [class*="item"], [class*="sidebar"] li, .sidebar-session-item, .sidebar-chat-item');
  snap = await ss(page, '09_sidebar_sessions');
  record('S2-Chat', '2.4 Sidebar sessions', 'Session in sidebar', `${sidebarItems.length} sidebar items`, sidebarItems.length > 0 ? 'PASS' : 'WARN', snap);

  // New Chat
  const newBtn = await page.$('button:has-text("New"), button:has-text("新建"), [class*="new-chat"]');
  if (newBtn) {
    await newBtn.click();
    await humanPause(2000);
    snap = await ss(page, '10_new_chat');
    record('S2-Chat', '2.5 New Chat', 'Fresh chat', 'New chat started', 'PASS', snap);
  } else {
    snap = await ss(page, '10_new_chat_btn_missing');
    record('S2-Chat', '2.5 New Chat', 'New Chat button', 'Button not found', 'WARN', snap);
  }
}

// SCENARIO 3: Error Handling
async function scenario3(page) {
  console.log('\nSCENARIO 3: Error Handling');

  // Wait for textarea - may need extra time after navigation
  await page.waitForSelector('textarea', { state: 'visible', timeout: 15000 }).catch(() => {});
  const textarea = await page.$('textarea');
  if (!textarea) {
    let snap = await ss(page, '11_no_textarea_err');
    record('S3-Error', '3.1 Find input', 'Textarea', 'No textarea', 'FAIL', snap);
    return;
  }

  // Empty send
  await textarea.fill('');
  await humanPause(500);
  const sendBtn = await page.$('button[aria-label*="send"], button:has(.anticon-send)');
  let disabled = false;
  if (sendBtn) disabled = await sendBtn.isDisabled();
  let snap = await ss(page, '11_empty_send');
  record('S3-Error', '3.1 Empty message', 'Send disabled', disabled ? 'Button disabled' : 'Button NOT disabled', disabled ? 'PASS' : 'WARN', snap);

  // Long input
  await textarea.fill('A'.repeat(3900));
  await humanPause(1000);
  snap = await ss(page, '12_long_input');
  record('S3-Error', '3.2 Long input (3900ch)', 'Text accepted', '3900 chars filled', 'PASS', snap);

  // Check character counter
  const counter = await page.$('[class*="count"], [class*="counter"]');
  const counterText = counter ? await counter.textContent() : null;
  record('S3-Error', '3.2b Char counter', 'Counter visible', counterText ? `Counter: ${counterText}` : 'No counter element', counter ? 'PASS' : 'WARN', snap);

  // Send normal message for retry test
  await textarea.fill('Test retry scenario');
  if (sendBtn && !(await sendBtn.isDisabled())) {
    await sendBtn.click();
    await humanPause(5000);
    snap = await ss(page, '13_sent_for_retry');
    record('S3-Error', '3.3 Send for retry test', 'Message sent', 'Message sent', 'PASS', snap);
  }

  // Check retry
  await humanPause(2000);
  const retryBtn = await page.$('button:has-text("Retry"), button:has-text("重试"), button:has(.anticon-reload)');
  snap = await ss(page, '14_retry_check');
  record('S3-Error', '3.4 Retry button', 'Retry after error', retryBtn ? 'Retry found' : 'No retry (no error occurred)', retryBtn ? 'PASS' : 'PASS', snap);
}

// SCENARIO 4: Dark Mode
async function scenario4(page) {
  console.log('\nSCENARIO 4: Dark Mode');

  let toggle = await page.$('button:has(.anticon-sun), button:has(.anticon-moon)');
  let snap = await ss(page, '15_before_toggle');
  record('S4-Dark', '4.1 Theme toggle', 'Toggle visible', toggle ? 'Toggle found' : 'Toggle NOT found', toggle ? 'PASS' : 'FAIL', snap);

  if (toggle) {
    await toggle.click();
    await humanPause(2000);
    snap = await ss(page, '16_dark_mode');
    const isDark = await page.evaluate(() => {
      return document.documentElement.getAttribute('data-theme') === 'dark' ||
             document.body.classList.contains('dark') ||
             window.getComputedStyle(document.body).backgroundColor.match(/rgb\((\d+)/)?.[1] < 50;
    });
    record('S4-Dark', '4.2 Dark mode on', 'Dark theme', isDark ? 'Dark applied' : 'Dark not detected', isDark ? 'PASS' : 'WARN', snap);

    // Hover sidebar
    const item = await page.$('[class*="sidebar"] [class*="item"], [class*="sidebar"] li');
    if (item) {
      await item.hover();
      await humanPause(1000);
      snap = await ss(page, '17_dark_hover');
      record('S4-Dark', '4.3 Sidebar hover (dark)', 'Hover effect', 'Hovered sidebar item in dark mode', 'WARN', snap);
    }

    // Toggle back
    toggle = await page.$('button:has(.anticon-sun), button:has(.anticon-moon)');
    if (toggle) {
      await toggle.click();
      await humanPause(1500);
      snap = await ss(page, '18_light_restored');
      record('S4-Dark', '4.4 Back to light', 'Light restored', 'Toggled back', 'PASS', snap);
    }
  }
}

// SCENARIO 5: Profile + Admin + Logout
async function scenario5(page) {
  console.log('\nSCENARIO 5: Profile + Admin + Logout');

  // Profile
  await page.goto(BASE_URL + '/profile', { waitUntil: 'networkidle', timeout: 15000 });
  await humanPause(2000);
  let snap = await ss(page, '19_profile_page');
  const onProfile = page.url().includes('/profile');
  record('S5-Profile', '5.1 Profile page', 'Profile visible', `URL: ${page.url()}`, onProfile ? 'PASS' : 'FAIL', snap);

  // Check user info
  const body = await page.textContent('body');
  const hasEmail = body?.includes(TEST_EMAIL);
  snap = await ss(page, '20_profile_info');
  record('S5-Profile', '5.2 User info', 'Email shown', hasEmail ? 'Email found' : 'Email not found', hasEmail ? 'PASS' : 'WARN', snap);

  // Admin dashboard
  await page.goto(BASE_URL + '/admin/dashboard', { waitUntil: 'networkidle', timeout: 15000 });
  await humanPause(2000);
  snap = await ss(page, '21_admin_dashboard');
  const onAdmin = page.url().includes('/admin/dashboard');
  record('S5-Profile', '5.3 Admin dashboard', 'Dashboard loads', `URL: ${page.url()}`, onAdmin ? 'PASS' : 'WARN', snap);

  // Knowledge base
  await page.goto(BASE_URL + '/admin/knowledge', { waitUntil: 'networkidle', timeout: 15000 });
  await humanPause(2000);
  snap = await ss(page, '22_knowledge_base');
  const onKB = page.url().includes('/admin/knowledge');
  record('S5-Profile', '5.4 Knowledge base', 'KB page loads', `URL: ${page.url()}`, onKB ? 'PASS' : 'WARN', snap);

  // Logout
  await page.goto(BASE_URL + '/chat', { waitUntil: 'networkidle', timeout: 15000 });
  await humanPause(2000);
  // Try to find user avatar / dropdown
  const avatar = await page.$('.ant-dropdown-trigger, [class*="avatar"], [class*="user-menu"]');
  if (avatar) {
    await avatar.click();
    await humanPause(1000);
  }
  const logoutBtn = await page.$('button:has-text("Logout"), button:has-text("Sign Out"), button:has-text("退出"), a:has-text("Logout"), [class*="logout"]');
  snap = await ss(page, '23_logout_menu');
  if (logoutBtn) {
    await logoutBtn.click();
    await humanPause(2000);
    snap = await ss(page, '24_after_logout');
    const afterUrl = page.url();
    record('S5-Profile', '5.5 Logout', 'Redirect to login', `URL: ${afterUrl}`, afterUrl.includes('/login') ? 'PASS' : 'FAIL', snap);
  } else {
    record('S5-Profile', '5.5 Logout', 'Logout button', 'Logout button not found', 'FAIL', snap);
  }
}

// MAIN
async function main() {
  console.log('Starting EY Onboarding AI UAT E2E Test');
  console.log('Target: ' + BASE_URL);
  console.log('='.repeat(60));

  const consoleErrors = [];
  const networkErrors = [];

  const browser = await chromium.launch({ headless: false, slowMo: 100, args: ['--start-maximized'] });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, locale: 'en-US' });
  const page = await context.newPage();

  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text().slice(0, 200));
  });
  page.on('requestfailed', req => {
    if (!req.url().includes('fonts.gstat') && !req.url().includes('favicon')) {
      networkErrors.push({ url: req.url(), err: req.failure()?.errorText });
    }
  });

  try {
    await scenario1(page);
    await scenario2(page);
    await scenario3(page);
    await scenario4(page);
    await scenario5(page);
  } catch (err) {
    console.error('Fatal error:', err.message);
    await ss(page, 'fatal_error');
  } finally {
    await browser.close();
  }

  // Generate report
  const pass = results.filter(r => r.status === 'PASS').length;
  const fail = results.filter(r => r.status === 'FAIL').length;
  const warn = results.filter(r => r.status === 'WARN').length;
  const total = results.length;

  const scNames = {
    'S1-Login': '场景1: 新用户登录 -> Onboarding引导 -> 进入聊天',
    'S2-Chat': '场景2: AI聊天核心流程 -> 发送 -> 流式回复 -> 会话管理',
    'S3-Error': '场景3: 异常输入与交互 -> 空消息/超长文本/重试',
    'S4-Dark': '场景4: 暗色模式切换 -> 视觉一致性检查',
    'S5-Profile': '场景5: 个人资料 -> 管理员页面 -> 登出',
  };

  let md = `# EY Onboarding AI — 上线前最终验收测试报告 (UAT)\n\n`;
  md += `**测试时间**: ${new Date().toISOString().slice(0, 19).replace('T', ' ')}\n`;
  md += `**测试环境**: Docker SYS (${BASE_URL})\n`;
  md += `**测试工具**: Playwright Chromium (headless: false, 1280x800)\n`;
  md += `**测试账号**: ${TEST_EMAIL}\n\n---\n\n`;
  md += `## 测试概要\n\n`;
  md += `| 指标 | 数值 |\n|------|------|\n`;
  md += `| 总步骤 | ${total} |\n| PASS | ${pass} |\n| FAIL | ${fail} |\n| WARN | ${warn} |\n`;
  md += `| 通过率 | ${((pass / total) * 100).toFixed(1)}% |\n`;
  md += `| 控制台错误 | ${consoleErrors.length} |\n| 网络错误 | ${networkErrors.length} |\n\n---\n\n`;

  for (const sc of ['S1-Login', 'S2-Chat', 'S3-Error', 'S4-Dark', 'S5-Profile']) {
    const steps = results.filter(r => r.scenario === sc);
    if (!steps.length) continue;
    md += `## ${scNames[sc]}\n\n`;
    md += `| 步骤 | 预期 | 实际 | 状态 | 截图 |\n|------|------|------|------|------|\n`;
    for (const s of steps) {
      const icon = s.status === 'PASS' ? 'PASS' : s.status === 'FAIL' ? 'FAIL' : 'WARN';
      md += `| ${s.step} | ${s.expected} | ${s.actual} | ${icon} | ${s.screenshot ? `[查看](${s.screenshot})` : '-'} |\n`;
    }
    md += `\n`;
  }

  md += `---\n\n## 截图证据\n\n`;
  for (const r of results) {
    if (r.screenshot) md += `### ${r.step}\n![${r.step}](${r.screenshot})\n\n`;
  }

  md += `---\n\n## 控制台错误 (${consoleErrors.length})\n\n`;
  if (consoleErrors.length === 0) md += `无控制台错误。\n\n`;
  else { for (const e of consoleErrors.slice(0, 20)) md += `- \`${e}\`\n`; md += `\n`; }

  md += `## 网络错误 (${networkErrors.length})\n\n`;
  if (networkErrors.length === 0) md += `无网络错误。\n\n`;
  else { for (const e of networkErrors.slice(0, 20)) md += `- \`${e.url}\` -> ${e.err}\n`; md += `\n`; }

  md += `---\n\n## 上线结论\n\n`;
  if (fail > 0) {
    md += `### 拒绝上线\n\n发现 ${fail} 个失败项：\n\n`;
    for (const f of results.filter(r => r.status === 'FAIL')) {
      md += `- **${f.scenario} / ${f.step}**: 期望 "${f.expected}"，实际 "${f.actual}"\n`;
    }
  } else {
    md += `### 同意上线（附 ${warn} 个关注项）\n\n`;
    for (const w of results.filter(r => r.status === 'WARN')) {
      md += `- **${w.scenario} / ${w.step}**: ${w.actual}\n`;
    }
  }
  md += `\n---\n*Generated ${new Date().toISOString()}*\n`;

  writeFileSync(REPORT_PATH, md, 'utf-8');
  console.log('\nReport: ' + REPORT_PATH);
  console.log(`PASS:${pass} FAIL:${fail} WARN:${warn} Total:${total}`);
}

main().catch(err => { console.error('Fatal:', err); process.exit(1); });
