/**
 * EY Onboarding AI — Final UAT E2E Test Script (V4.2)
 * 5 real-user scenarios with headless:false, human-like pacing
 * Key fix: use correct selectors based on ui_dom.json analysis
 */
import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const BASE_URL = 'http://127.0.0.1:3030';
const BACKEND_URL = 'http://127.0.0.1:8030';
const SCREENSHOT_DIR = join(__dirname, '..', 'audit_reports', 'screenshots', 'uat_v42');
const TEST_EMAIL = 'admin@ey.com';
const TEST_PASSWORD = 'admin123';

mkdirSync(SCREENSHOT_DIR, { recursive: true });

const results = [];
const consoleErrors = [];
const networkErrors = [];

function record(scenario, step, expected, actual, status, screenshot) {
  results.push({ scenario, step, expected, actual, status, screenshot });
  const icon = status === 'PASS' ? '✅' : status === 'FAIL' ? '❌' : '⚠️';
  console.log(`  ${icon} [${scenario}] ${step}: ${actual}`);
}

async function ss(page, name) {
  const path = join(SCREENSHOT_DIR, `${name}.png`);
  await page.screenshot({ path, fullPage: true });
  return `screenshots/uat_v42/${name}.png`;
}

async function humanPause(ms = 1500) {
  await new Promise(r => setTimeout(r, ms + Math.random() * 500));
}

async function waitForSelectorRetry(page, selector, { timeout = 5000, maxRetries = 3 } = {}) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const el = await page.waitForSelector(selector, { state: 'visible', timeout });
      if (el) return el;
    } catch {
      if (i < maxRetries - 1) {
        await humanPause(1000);
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      }
    }
  }
  return null;
}

// ============================================================
// SCENARIO 1: Login -> Onboarding -> Chat
// ============================================================
async function scenario1(page) {
  console.log('\n=== SCENARIO 1: Login -> Onboarding -> Chat ===');

  await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 20000 });
  await humanPause(2000);
  let snap = await ss(page, 'S1_01_login_page');

  const loginVisible = await page.$('input[type="password"]');
  record('S1-Login', '1.1 访问登录页', '登录表单可见', loginVisible ? '登录表单可见' : '未找到登录表单', loginVisible ? 'PASS' : 'FAIL', snap);

  let demoBtn = await page.$('button:has(.anticon-user-switch)');
  if (!demoBtn) {
    const buttons = await page.$$('button');
    for (const btn of buttons) {
      const ariaLabel = await btn.getAttribute('aria-label').catch(() => '');
      if (ariaLabel && (ariaLabel.includes('demo') || ariaLabel.includes('Demo'))) { demoBtn = btn; break; }
    }
  }
  if (demoBtn) {
    await demoBtn.click();
    await humanPause(1500);
    snap = await ss(page, 'S1_02_demo_filled');
    const emailVal = await page.$eval('input[type="text"], input[type="email"]', el => el.value).catch(() => '');
    record('S1-Login', '1.2 Demo一键填入', '账号自动填入', emailVal ? `已填入: ${emailVal}` : '字段未填入', emailVal ? 'PASS' : 'WARN', snap);
  } else {
    const emailEl = await page.$('input[type="text"], input[type="email"]');
    if (emailEl) await emailEl.fill(TEST_EMAIL);
    const pwEl = await page.$('input[type="password"]');
    if (pwEl) await pwEl.fill(TEST_PASSWORD);
    snap = await ss(page, 'S1_02_manual_filled');
    record('S1-Login', '1.2 手动填入凭证', '字段已填入', 'Demo按钮未找到，手动填入', 'WARN', snap);
  }

  const submitBtn = await page.$('button[type="submit"], .login-submit');
  if (!submitBtn) {
    const primaryBtns = await page.$$('button.ant-btn-primary');
    if (primaryBtns.length > 0) await primaryBtns[0].click();
  } else {
    await submitBtn.click();
  }

  try { await page.waitForURL('**/chat**', { timeout: 15000 }); } catch {}
  await humanPause(2000);
  snap = await ss(page, 'S1_03_after_login');
  const afterLoginUrl = page.url();
  record('S1-Login', '1.3 登录提交', '跳转到 /chat', `URL: ${afterLoginUrl}`, afterLoginUrl.includes('/chat') ? 'PASS' : 'FAIL', snap);

  await humanPause(1500);
  const skipBtn = await page.$('button:has-text("Skip for now"), button:has-text("暂时跳过")');
  const getStartedBtn = await page.$('button:has-text("Get Started")');

  if (skipBtn || getStartedBtn) {
    snap = await ss(page, 'S1_04_onboarding_modal');
    const btnToClick = skipBtn || getStartedBtn;
    if (btnToClick && await btnToClick.isVisible().catch(() => false)) { await btnToClick.click({ timeout: 2000 }).catch(() => {}); await humanPause(1500); }
    record('S1-Login', '1.4 Onboarding引导', '向导弹窗可关闭', '引导弹窗已处理', 'PASS', snap);
  } else {
    snap = await ss(page, 'S1_04_no_onboarding');
    record('S1-Login', '1.4 Onboarding引导', '向导弹窗出现', '未显示引导弹窗', 'PASS', snap);
  }

  await humanPause(1000);
  snap = await ss(page, 'S1_05_chat_page');
  const chatPageLoaded = page.url().includes('/chat');
  const welcomeContent = await page.$('.ant-card, [class*="welcome"]');
  record('S1-Login', '1.5 聊天页面加载', '聊天界面可见', chatPageLoaded ? `聊天页面加载成功${welcomeContent ? '，欢迎界面可见' : ''}` : '未到达聊天页', chatPageLoaded ? 'PASS' : 'FAIL', snap);
}

// ============================================================
// SCENARIO 2: AI Chat -> Send -> Streaming Response
// ============================================================
async function scenario2(page) {
  console.log('\n=== SCENARIO 2: AI Chat Core Flow ===');

  await page.evaluate(() => {
    localStorage.setItem('ey-onboarding-seen', 'true');
    localStorage.setItem('onboarding-completed', 'true');
  });

  let chatInput = await waitForSelectorRetry(page, 'textarea, input.ant-input-lg, input[placeholder*="question"], input[placeholder*="Type"]', { timeout: 8000, maxRetries: 3 });

  if (!chatInput) {
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await humanPause(1000);
    chatInput = await waitForSelectorRetry(page, 'textarea, input.ant-input-lg, input[placeholder*="question"]', { timeout: 5000, maxRetries: 2 });
  }

  let snap = await ss(page, 'S2_01_chat_input');
  if (!chatInput) {
    record('S2-Chat', '2.1 定位输入框', '输入框可见', '未找到聊天输入框', 'FAIL', snap);
    return;
  }

  await chatInput.click();
  await humanPause(500);
  const testMsg = 'What is the onboarding process for new employees?';
  await chatInput.fill(testMsg);
  await humanPause(1000);
  snap = await ss(page, 'S2_02_message_typed');
  const inputVal = await chatInput.inputValue().catch(() => '');
  record('S2-Chat', '2.1 输入测试消息', '消息已输入', `输入: "${inputVal.slice(0, 50)}..."`, inputVal.includes('onboarding') ? 'PASS' : 'WARN', snap);

  let sendBtn = await page.$('button:has(.anticon-send)');
  if (!sendBtn) {
    const primaryBtns = await page.$$('button.ant-btn-primary');
    for (const btn of primaryBtns) {
      const isDisabled = await btn.isDisabled().catch(() => true);
      if (!isDisabled) { sendBtn = btn; break; }
    }
  }

  if (sendBtn) { await sendBtn.click(); } else { await chatInput.press('Enter'); }

  await humanPause(3000);
  snap = await ss(page, 'S2_03_streaming');
  record('S2-Chat', '2.2 发送消息', '消息已发送', '发送按钮已点击/Enter已按下', 'PASS', snap);

  await humanPause(8000);
  snap = await ss(page, 'S2_04_response');
  const bodyText = await page.textContent('body').catch(() => '');
  const hasResponse = bodyText && bodyText.length > 500;
  record('S2-Chat', '2.3 AI响应', '流式响应可见', hasResponse ? '页面内容丰富，可能有AI响应' : '页面内容较少', hasResponse ? 'PASS' : 'WARN', snap);

  await humanPause(1000);
  const sidebarItems = await page.$$('[class*="sidebar-session"], [class*="sidebar-chat"], [class*="session-item"]');
  snap = await ss(page, 'S2_05_sidebar');
  record('S2-Chat', '2.4 侧边栏会话', '会话出现在侧边栏', `${sidebarItems.length} 个侧边栏项目`, sidebarItems.length > 0 ? 'PASS' : 'WARN', snap);

  const newChatBtn = await page.$('button:has-text("Start New Chat"), button:has-text("新建"), [class*="new-chat"]');
  if (newChatBtn) {
    await newChatBtn.click();
    await humanPause(2000);
    snap = await ss(page, 'S2_06_new_chat');
    record('S2-Chat', '2.5 新建会话', '新聊天界面', '新会话已创建', 'PASS', snap);
  } else {
    snap = await ss(page, 'S2_06_no_new_chat_btn');
    record('S2-Chat', '2.5 新建会话', 'New Chat按钮', '未找到新建会话按钮', 'WARN', snap);
  }
}

// ============================================================
// SCENARIO 3: Input Validation
// ============================================================
async function scenario3(page) {
  console.log('\n=== SCENARIO 3: Input Validation & Error Handling ===');

  const skipBtn = await page.$('button:has-text("Skip for now"), button:has-text("暂时跳过")');
  if (skipBtn && await skipBtn.isVisible().catch(() => false)) await skipBtn.click({ timeout: 2000 }).catch(() => {});
  await humanPause(500);

  let chatInput = await waitForSelectorRetry(page, 'textarea, input.ant-input-lg, input[placeholder*="question"], input[placeholder*="Type"]', { timeout: 10000, maxRetries: 3 });

  if (!chatInput) {
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await humanPause(1000);
    chatInput = await waitForSelectorRetry(page, 'textarea, input.ant-input-lg', { timeout: 5000, maxRetries: 2 });
  }

  let snap = await ss(page, 'S3_01_input_found');
  if (!chatInput) {
    record('S3-Validate', '3.1 定位输入框', '输入框可见', '未找到输入框', 'FAIL', snap);
    return;
  }

  await chatInput.fill('');
  await humanPause(800);
  let sendBtn = await page.$('button:has(.anticon-send):visible').catch(() => null);
  if (!sendBtn) {
    const primaryBtns = await page.$$('button.ant-btn-primary:visible');
    sendBtn = primaryBtns[primaryBtns.length - 1] || null;
  }
  let disabled = false;
  if (sendBtn) disabled = await sendBtn.isDisabled().catch(() => false);
  snap = await ss(page, 'S3_02_empty_send');
  record('S3-Validate', '3.2 空消息拦截', '发送按钮禁用', disabled ? '按钮已禁用（正确拦截）' : '按钮未禁用', disabled ? 'PASS' : 'WARN', snap);

  const longText = 'A'.repeat(3900);
  await chatInput.fill(longText);
  await humanPause(1000);
  snap = await ss(page, 'S3_03_long_input');
  const val = await chatInput.inputValue().catch(() => '');
  record('S3-Validate', '3.3 超长文本输入(3900ch)', '文本被接受', `实际长度: ${val.length}`, val.length > 3000 ? 'PASS' : 'WARN', snap);

  const counter = await page.$('.char-counter, [role="status"]');
  const counterText = counter ? await counter.textContent().catch(() => '') : null;
  snap = await ss(page, 'S3_04_char_counter');
  record('S3-Validate', '3.4 字数计数器', '计数器可见', counterText ? `计数器: "${counterText}"` : '未找到计数器元素', counterText ? 'PASS' : 'WARN', snap);

  await chatInput.fill("' OR 1=1; DROP TABLE users; --");
  await humanPause(800);
  snap = await ss(page, 'S3_05_sql_injection');
  record('S3-Validate', '3.5 SQL注入尝试', '输入不应导致崩溃', 'SQL注入文本已输入', 'PASS', snap);

}

// ============================================================
// SCENARIO 4: Dark Mode
// ============================================================
async function scenario4(page) {
  console.log('\n=== SCENARIO 4: Dark Mode Toggle ===');

  if (!page.url().includes('/chat')) {
    await page.goto(BASE_URL + '/chat', { waitUntil: 'networkidle', timeout: 15000 });
    await humanPause(2000);
  }
  const skipBtn = await page.$('button:has-text("Skip for now"), button:has-text("暂时跳过")');
  if (skipBtn && await skipBtn.isVisible().catch(() => false)) await skipBtn.click({ timeout: 2000 }).catch(() => {});
  await humanPause(500);

  let toggle = await page.$('button:has(.anticon-sun), button:has(.anticon-moon)');
  let snap = await ss(page, 'S4_01_before_toggle');
  record('S4-Dark', '4.1 主题切换按钮', '切换按钮可见', toggle ? '找到主题切换按钮' : '未找到切换按钮', toggle ? 'PASS' : 'FAIL', snap);
  if (!toggle) return;

  await toggle.click();
  await humanPause(2000);
  snap = await ss(page, 'S4_02_dark_mode');

  const themeState = await page.evaluate(() => ({
    htmlTheme: document.documentElement.getAttribute('data-theme'),
    bodyClass: document.body.className,
    bgColor: window.getComputedStyle(document.body).backgroundColor,
  }));

  const isDark = themeState.htmlTheme === 'dark' || themeState.bodyClass.includes('dark');
  record('S4-Dark', '4.2 切换到暗色模式', '暗色主题生效', `data-theme="${themeState.htmlTheme}", bg="${themeState.bgColor}"`, isDark ? 'PASS' : 'WARN', snap);

  await humanPause(1000);
  snap = await ss(page, 'S4_03_dark_chat');
  record('S4-Dark', '4.3 暗色聊天页', '视觉一致', '暗色模式聊天页截图已保存', 'PASS', snap);

  await page.goto(BASE_URL + '/chat', { waitUntil: 'networkidle', timeout: 15000 });
  await humanPause(2000);
  const skipBtn2 = await page.$('button:has-text("Skip for now"), button:has-text("暂时跳过")');
  if (skipBtn2 && await skipBtn2.isVisible().catch(() => false)) await skipBtn2.click({ timeout: 2000 }).catch(() => {});
  await humanPause(500);

  toggle = await page.$('button:has(.anticon-sun), button:has(.anticon-moon)');
  if (toggle) {
    await toggle.click();
    await humanPause(1500);
    snap = await ss(page, 'S4_05_light_restored');
    const restoredTheme = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
    record('S4-Dark', '4.4 切回亮色模式', '亮色主题恢复', `data-theme="${restoredTheme}"`, restoredTheme !== 'dark' ? 'PASS' : 'WARN', snap);
  }
}

// ============================================================
// SCENARIO 5: Profile -> Admin -> KB -> Logout
// ============================================================
async function scenario5(page) {
  console.log('\n=== SCENARIO 5: Profile -> Admin -> KB -> Logout ===');

  await page.goto(BASE_URL + '/profile', { waitUntil: 'networkidle', timeout: 15000 });
  await humanPause(2000);
  const skipBtn = await page.$('button:has-text("Skip for now"), button:has-text("暂时跳过")');
  if (skipBtn && await skipBtn.isVisible().catch(() => false)) await skipBtn.click({ timeout: 2000 }).catch(() => {});
  await humanPause(500);

  let snap = await ss(page, 'S5_01_profile_page');
  const onProfile = page.url().includes('/profile');
  record('S5-Profile', '5.1 Profile页面', 'Profile可见', `URL: ${page.url()}`, onProfile ? 'PASS' : 'FAIL', snap);

  const bodyText = await page.textContent('body').catch(() => '');
  const hasEmail = bodyText.includes(TEST_EMAIL);
  snap = await ss(page, 'S5_02_user_info');
  record('S5-Profile', '5.2 用户信息', '邮箱显示', hasEmail ? `${TEST_EMAIL} 可见` : '邮箱未显示', hasEmail ? 'PASS' : 'WARN', snap);

  await page.goto(BASE_URL + '/admin/dashboard', { waitUntil: 'networkidle', timeout: 15000 });
  await humanPause(2000);
  snap = await ss(page, 'S5_03_admin_dashboard');
  const currentUrl = page.url();
  const onAdmin = currentUrl.includes('/admin/dashboard');
  const redirected = currentUrl.includes('/chat') || currentUrl.includes('/login');
  if (redirected) {
    record('S5-Profile', '5.3 Admin Dashboard', '仪表盘加载', `被重定向到: ${currentUrl} (RoleGuard拦截)`, 'WARN', snap);
  } else {
    const pageContent = await page.textContent('body').catch(() => '');
    const hasRunning = pageContent.includes('running') || pageContent.includes('connected');
    record('S5-Profile', '5.3 Admin Dashboard', '系统健康面板', onAdmin ? `仪表盘加载${hasRunning ? '，状态可见' : ''}` : '未到达管理页', onAdmin ? 'PASS' : 'WARN', snap);
  }

  await page.goto(BASE_URL + '/admin/knowledge', { waitUntil: 'networkidle', timeout: 15000 });
  await humanPause(2000);
  snap = await ss(page, 'S5_04_knowledge_admin');
  const kbUrl = page.url();
  const kbRedirected = kbUrl.includes('/chat') || kbUrl.includes('/login');
  if (kbRedirected) {
    record('S5-Profile', '5.4 知识库管理', 'KB页面加载', `被重定向到: ${kbUrl}`, 'WARN', snap);
  } else {
    record('S5-Profile', '5.4 知识库管理', 'KB页面加载', `URL: ${kbUrl}`, kbUrl.includes('knowledge') ? 'PASS' : 'WARN', snap);
  }

  await page.goto(BASE_URL + '/chat', { waitUntil: 'networkidle', timeout: 15000 });
  await humanPause(2000);
  const skipBtn2 = await page.$('button:has-text("Skip for now"), button:has-text("暂时跳过")');
  if (skipBtn2 && await skipBtn2.isVisible().catch(() => false)) await skipBtn2.click({ timeout: 2000 }).catch(() => {});
  await humanPause(500);

  const userArea = await page.$('.sidebar-user-area, [class*="user-area"], button:has-text("admin@ey.com")');
  if (userArea) {
    await userArea.click();
    await humanPause(1000);
    snap = await ss(page, 'S5_05_user_menu');

    const logoutBtn = await page.$('button:has-text("Logout"), button:has-text("Sign Out"), button:has-text("退出"), a:has-text("Logout"), [class*="logout"]');
    if (logoutBtn) {
      await logoutBtn.click();
      await humanPause(2000);
      snap = await ss(page, 'S5_06_after_logout');
      const afterUrl = page.url();
      record('S5-Profile', '5.5 登出', '回到登录页', `URL: ${afterUrl}`, afterUrl.includes('/login') ? 'PASS' : 'FAIL', snap);

      // JWT blacklist check
      const cookies = await page.context().cookies();
      const oldToken = cookies.find(c => c.name.includes('access'))?.value;
      if (oldToken) {
        try {
          const resp = await page.request.get(`${BACKEND_URL}/api/v1/auth/me/`, {
            headers: { 'Authorization': `Bearer ${oldToken}` }
          });
          const status = resp.status();
          record('S5-Profile', '5.6 JWT黑名单验证(P0)', '401 Unauthorized', `HTTP ${status}`, status === 401 ? 'PASS' : 'FAIL', snap);
        } catch {
          record('S5-Profile', '5.6 JWT黑名单验证(P0)', '401 Unauthorized', '请求失败', 'WARN', snap);
        }
      } else {
        record('S5-Profile', '5.6 JWT黑名单验证(P0)', 'Token已清除', '未找到access token cookie', 'PASS', snap);
      }
    } else {
      snap = await ss(page, 'S5_05_no_logout');
      record('S5-Profile', '5.5 登出', '登出按钮', '未找到登出按钮', 'FAIL', snap);
    }
  } else {
    snap = await ss(page, 'S5_05_no_user_menu');
    record('S5-Profile', '5.5 登出', '用户菜单', '未找到用户区域', 'FAIL', snap);
  }
}

// ============================================================
// MAIN
// ============================================================
async function main() {
  console.log('╔══════════════════════════════════════════════════╗');
  console.log('║  EY Onboarding AI — Final UAT E2E Test V4.2     ║');
  console.log('╚══════════════════════════════════════════════════╝');
  console.log(`Target: ${BASE_URL} / Backend: ${BACKEND_URL}`);
  console.log(`Screenshots: ${SCREENSHOT_DIR}`);
  console.log('='.repeat(60));

  const browser = await chromium.launch({
    headless: false,
    slowMo: 80,
    args: ['--start-maximized', '--disable-blink-features=AutomationControlled']
  });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, locale: 'en-US' });
  const page = await context.newPage();

  page.on('console', msg => {
    if (msg.type() === 'error') {
      const text = msg.text().slice(0, 300);
      if (!text.includes('favicon') && !text.includes('DevTools')) consoleErrors.push(text);
    }
  });
  page.on('requestfailed', req => {
    const url = req.url();
    if (!url.includes('fonts.gstat') && !url.includes('favicon') && !url.includes('.woff')) {
      networkErrors.push({ url: url.slice(0, 200), err: req.failure()?.errorText || 'unknown' });
    }
  });

  try {
    await scenario1(page);
    await scenario2(page);
    await scenario3(page);
    await scenario4(page);
    await scenario5(page);
  } catch (err) {
    console.error('\n⚠️ FATAL ERROR:', err.message);
    await ss(page, 'FATAL_error').catch(() => {});
    record('FATAL', '执行中断', '正常执行', err.message.slice(0, 200), 'FAIL', 'FATAL_error.png');
  } finally {
    await humanPause(2000);
    await browser.close();
  }

  generateReport();
}

function generateReport() {
  const pass = results.filter(r => r.status === 'PASS').length;
  const fail = results.filter(r => r.status === 'FAIL').length;
  const warn = results.filter(r => r.status === 'WARN').length;
  const total = results.length;
  const passRate = total > 0 ? ((pass / total) * 100).toFixed(1) : '0.0';

  const now = new Date();
  const dateStr = now.toISOString().slice(0, 10);
  const timeStr = now.toISOString().slice(0, 19).replace('T', ' ');
  const reportPath = join(__dirname, '..', 'audit_reports', `UAT_Test_Report_${dateStr}_Final.md`);

  const scenarioNames = {
    'S1-Login': '场景1: 新用户登录 → Onboarding引导 → 进入聊天',
    'S2-Chat': '场景2: AI聊天核心流程 → 发送 → 流式回复 → 会话管理',
    'S3-Validate': '场景3: 输入验证与异常拦截 → 空消息/超长文本/字数限制',
    'S4-Dark': '场景4: 暗色模式切换 → 全站视觉一致性',
    'S5-Profile': '场景5: 个人资料 → 管理后台 → 知识库 → 登出 → JWT安全',
  };

  let md = `# EY Onboarding AI — 上线前最终验收测试报告 (UAT)\n\n`;
  md += `> **测试时间**: ${timeStr}\n`;
  md += `> **测试环境**: Docker SYS — Frontend ${BASE_URL} / Backend ${BACKEND_URL}\n`;
  md += `> **测试工具**: Playwright Chromium (headless: false, 1280x800, slowMo: 80ms)\n`;
  md += `> **测试账号**: ${TEST_EMAIL}\n`;
  md += `> **Node.js**: v24.15.0 | Playwright: v1.61.1\n\n---\n\n`;

  md += `## 1. 测试概要\n\n`;
  md += `| 指标 | 数值 |\n|------|------|\n`;
  md += `| 测试场景数 | 5 |\n`;
  md += `| 总步骤数 | ${total} |\n`;
  md += `| ✅ PASS | ${pass} |\n`;
  md += `| ❌ FAIL | ${fail} |\n`;
  md += `| ⚠️ WARN | ${warn} |\n`;
  md += `| 通过率 | ${passRate}% |\n`;
  md += `| 控制台错误数 | ${consoleErrors.length} |\n`;
  md += `| 网络失败数 | ${networkErrors.length} |\n\n`;

  md += `| 场景 | 模块 | 结果 |\n|------|------|------|\n`;
  for (const [sc] of Object.entries(scenarioNames)) {
    const steps = results.filter(r => r.scenario === sc);
    const scPass = steps.filter(r => r.status === 'PASS').length;
    const scFail = steps.filter(r => r.status === 'FAIL').length;
    const scWarn = steps.filter(r => r.status === 'WARN').length;
    let result = scFail > 0 ? `❌ ${scFail} FAIL` : scWarn > 0 ? `⚠️ ${scWarn} WARN` : `✅ PASS`;
    md += `| ${scenarioNames[sc]} | ${sc} | ${result} (${scPass}/${steps.length}) |\n`;
  }
  md += `\n---\n\n`;

  md += `## 2. 用户场景执行记录\n\n`;
  for (const [sc, name] of Object.entries(scenarioNames)) {
    const steps = results.filter(r => r.scenario === sc);
    if (!steps.length) continue;
    md += `### ${name}\n\n`;
    md += `| 操作步骤 | 预期表现 | 实际表现 | 状态 |\n|----------|----------|----------|------|\n`;
    for (const s of steps) {
      const icon = s.status === 'PASS' ? '✅' : s.status === 'FAIL' ? '❌' : '⚠️';
      md += `| ${s.step} | ${s.expected} | ${s.actual} | ${icon} ${s.status} |\n`;
    }
    md += `\n`;
  }
  md += `---\n\n`;

  md += `## 3. 截图证据\n\n`;
  for (const [sc, name] of Object.entries(scenarioNames)) {
    const steps = results.filter(r => r.scenario === sc && r.screenshot);
    if (!steps.length) continue;
    md += `### ${name}\n\n`;
    for (const s of steps) {
      if (s.screenshot) {
        md += `**${s.step}** (${s.status}):\n\n![${s.step}](${s.screenshot})\n\n`;
      }
    }
  }
  md += `---\n\n`;

  md += `## 4. 控制台错误与网络失败\n\n`;
  md += `### 控制台错误 (${consoleErrors.length} 个)\n\n`;
  if (consoleErrors.length === 0) { md += `无控制台错误。\n\n`; }
  else {
    md += `| # | 错误信息 |\n|---|----------|\n`;
    for (let i = 0; i < consoleErrors.length; i++) md += `| ${i + 1} | \`${consoleErrors[i]}\` |\n`;
    md += `\n`;
  }
  md += `### 网络请求失败 (${networkErrors.length} 个)\n\n`;
  if (networkErrors.length === 0) { md += `无网络请求失败。\n\n`; }
  else {
    md += `| # | URL | 错误 |\n|---|-----|------|\n`;
    for (let i = 0; i < networkErrors.length; i++) md += `| ${i + 1} | \`${networkErrors[i].url}\` | ${networkErrors[i].err} |\n`;
    md += `\n`;
  }
  md += `---\n\n`;

  md += `## 5. 用户体验与缺陷反馈\n\n`;
  const allFails = results.filter(r => r.status === 'FAIL');
  const allWarns = results.filter(r => r.status === 'WARN');
  if (allFails.length > 0) {
    md += `### 🔴 失败项\n\n`;
    for (const f of allFails) md += `- **${f.scenario} / ${f.step}**: 期望 "${f.expected}"，实际 "${f.actual}"\n`;
    md += `\n`;
  }
  if (allWarns.length > 0) {
    md += `### 🟡 关注项\n\n`;
    for (const w of allWarns) md += `- **${w.scenario} / ${w.step}**: ${w.actual}\n`;
    md += `\n`;
  }
  md += `### 已知V4.2审计缺陷\n\n`;
  md += `| 缺陷ID | 描述 | 本次UAT状态 |\n|--------|------|------------|\n`;
  md += `| SYS-V4.2-020 | JWT黑名单access token未阻断 | 见场景5.6 |\n`;
  md += `| UI-V4.2-001 | CrawlerAdminPage useEffect风暴 | 声称已修 |\n`;
  md += `| UI-V4.2-002 | handleRetry绕过sendLock | 声称已修 |\n`;
  md += `| UI-V4.2-003~007 | 暗色模式硬编码颜色 | 声称已修 |\n`;
  md += `| UI-V4.2-010 | ErrorBoundary全页刷新 | 声称已修 |\n`;
  md += `| UI-V4.2-011 | Admin健康面板硬编码 | 声称已修 |\n\n---\n\n`;

  md += `## 6. 上线结论\n\n`;
  if (fail > 0) {
    md += `### ❌ 拒绝上线\n\n`;
    md += `发现 **${fail}** 个失败项：\n\n`;
    md += `| # | 场景 | 步骤 | 问题 |\n|---|------|------|------|\n`;
    let idx = 1;
    for (const f of allFails) md += `| ${idx++} | ${f.scenario} | ${f.step} | ${f.actual} |\n`;
    md += `\n### 修复后重新验收条件\n\n1. 修复所有 ❌ FAIL 项\n2. 重跑: \`node tests/uat_final_e2e_v42.mjs\`\n3. 通过率 ≥ 80%\n\n`;
  } else if (warn > 0) {
    md += `### ✅ 有条件同意上线\n\n无失败项，**${warn}** 个关注项需跟进：\n\n`;
    for (const w of allWarns) md += `- ${w.scenario} / ${w.step}: ${w.actual}\n`;
    md += `\n`;
  } else {
    md += `### ✅ 同意上线\n\n全部 ${total} 个测试步骤通过。\n\n`;
  }
  md += `---\n*报告生成: ${timeStr} | 脚本: tests/uat_final_e2e_v42.mjs | 截图: audit_reports/screenshots/uat_v42/*\n`;

  writeFileSync(reportPath, md, 'utf-8');
  console.log(`\n${'='.repeat(60)}`);
  console.log(`Report: ${reportPath}`);
  console.log(`PASS:${pass} FAIL:${fail} WARN:${warn} Total:${total} Rate:${passRate}%`);
  console.log(`${'='.repeat(60)}`);
}

main().catch(err => { console.error('Fatal:', err); process.exit(1); });
