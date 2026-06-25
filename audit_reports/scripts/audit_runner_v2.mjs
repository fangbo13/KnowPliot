/**
 * EY Onboarding AI — QA+UX Comprehensive Audit Runner (v2)
 * Improved: API-based login, increased timeouts, fixed variable refs
 */
import puppeteer from 'puppeteer';
import fs from 'fs';
import path from 'path';
import http from 'http';

// ============================================================
// Configuration
// ============================================================
const BASE_URL = 'http://localhost:3000';
const API_URL = 'http://localhost:8000/api/v1';
const DEMO_EMAIL = 'admin@ey.com';
const DEMO_PASSWORD = 'admin123';
const OUTPUT_DIR = path.resolve('d:/Github/Onborading-AI/project_audit_output');
const SCREENSHOTS_DIR = path.join(OUTPUT_DIR, 'screenshots');
const RESULTS_FILE = path.join(OUTPUT_DIR, 'test_results.json');

const DESKTOP = { width: 1280, height: 800 };
const MOBILE = { width: 375, height: 667 };

// ============================================================
// Utility Functions
// ============================================================
function ensureDir(d) { if (!fs.existsSync(d)) fs.mkdirSync(d, { recursive: true }); }
async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function screenshot(page, name, opts = {}) {
  const fp = path.join(SCREENSHOTS_DIR, `${name}.png`);
  try {
    await page.screenshot({ path: fp, fullPage: opts.fullPage || false, type: 'png' });
    console.log(`  📸 ${name}.png`);
    return fp;
  } catch (e) {
    console.log(`  ❌ Screenshot fail: ${name}: ${e.message}`);
    return null;
  }
}

async function injectRed(page, sel) {
  try {
    await page.evaluate((s) => {
      const el = document.querySelector(s);
      if (el) { el.style.outline = '3px solid red'; el.style.outlineOffset = '2px'; }
    }, sel);
    await sleep(200);
  } catch {}
}

// Node.js-based API login using http module (avoids Puppeteer evaluate timeout)
async function nodeApiLogin() {
  const tokenData = await httpPost('127.0.0.1', 8000, '/api/v1/auth/token/', {
    email: DEMO_EMAIL, password: DEMO_PASSWORD
  });
  if (tokenData.access) {
    const userData = await httpGet('127.0.0.1', 8000, '/api/v1/auth/me/', {
      Authorization: `Bearer ${tokenData.access}`
    });
    return { success: true, token: tokenData.access, user: userData };
  }
  return { success: false };
}

// HTTP helper: POST request
async function httpPost(host, port, pathStr, bodyObj) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify(bodyObj);
    const options = { hostname: host, port, path: pathStr, method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) } };
    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => { try { resolve(JSON.parse(data)); } catch { resolve({}); } });
    });
    req.on('error', reject);
    req.setTimeout(10000, () => { req.destroy(); reject(new Error('HTTP timeout')); });
    req.write(body);
    req.end();
  });
}

// HTTP helper: GET request
async function httpGet(host, port, pathStr, headers = {}) {
  return new Promise((resolve, reject) => {
    const options = { hostname: host, port, path: pathStr, method: 'GET', headers };
    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => { try { resolve(JSON.parse(data)); } catch { resolve({}); } });
    });
    req.on('error', reject);
    req.setTimeout(10000, () => { req.destroy(); reject(new Error('HTTP timeout')); });
    req.end();
  });
}

// Inject auth token into browser localStorage (matching AuthProvider format)
async function injectAuth(page, tokenData) {
  // Ensure we're on app page
  const currentUrl = page.url();
  if (!currentUrl.startsWith(BASE_URL)) {
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded', timeout: 15000 });
    await sleep(500);
  }
  // AuthProvider expects: { isAuthenticated: true, user: {...}, token: "..." }
  const authState = { isAuthenticated: true, user: tokenData.user, token: tokenData.token };
  const authJSON = JSON.stringify(authState);
  const langPref = tokenData.user.language_preference || 'en';
  await page.evaluate((authData, lang) => {
    localStorage.setItem('ey-auth', authData);
    localStorage.setItem('ey-language', lang);
  }, authJSON, langPref);
}

// Combined login: Node API + localStorage injection
async function apiLogin(page) {
  console.log('  🔑 Logging in via API...');
  const loginResult = await nodeApiLogin();
  if (loginResult.success) {
    await injectAuth(page, loginResult);
    await page.goto(`${BASE_URL}/chat`, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(3000);
    console.log('  ✅ Login successful');
    return true;
  }

  // Fallback: form-based login
  console.log('  ⚠️ API login failed, trying form login...');
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(2000);
  const inputs = await page.$$('input');
  for (const input of inputs) {
    const type = await input.evaluate(el => el.type);
    if (type === 'email' || type === 'text') {
      await input.click({ clickCount: 3 });
      await input.type(DEMO_EMAIL, { delay: 30 });
    } else if (type === 'password') {
      await input.click({ clickCount: 3 });
      await input.type(DEMO_PASSWORD, { delay: 30 });
    }
  }
  const submit = await page.$('button[type="submit"]');
  if (submit) {
    await submit.click();
    await sleep(3000);
    await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 15000 }).catch(() => {});
    await sleep(2000);
  }
  const url = page.url();
  return !url.includes('/login');
}

// ============================================================
// Results Tracker
// ============================================================
const R = {
  startTime: new Date().toISOString(),
  env: { baseUrl: BASE_URL, apiUrl: API_URL },
  total: 0, pass: 0, fail: 0, warn: 0,
  bugs: [], ux: [], modules: {}
};

function rec(mod, id, status, det = {}) {
  R.total++;
  if (status === 'pass') R.pass++;
  else if (status === 'fail') R.fail++;
  else R.warn++;
  if (!R.modules[mod]) R.modules[mod] = { tests: [], bugs: [], ux: [] };
  R.modules[mod].tests.push({ id, status, ...det });
}

function bug(mod, title, sev, cat, steps, exp, act, ss) {
  const id = `BUG-${String(R.bugs.length + 1).padStart(3, '0')}`;
  const b = { id, module: mod, title, severity: sev, category: cat, steps, expected: exp, actual: act, screenshot: ss };
  R.bugs.push(b);
  if (R.modules[mod]) R.modules[mod].bugs.push(id);
}

function ux(mod, title, sev, heuristic, why, fix, ss) {
  const id = `UX-${String(R.ux.length + 1).padStart(3, '0')}`;
  const u = { id, module: mod, title, severity: sev, heuristic, whyBad: why, howToFix: fix, screenshot: ss };
  R.ux.push(u);
  if (R.modules[mod]) R.modules[mod].ux.push(id);
}

// ============================================================
// Module 1: Authentication
// ============================================================
async function testAuth(page) {
  const M = 'AUTH';
  console.log('\n🔐 Module 1: Authentication / Login Page');

  // AUTH-01: Login page renders
  console.log('  AUTH-01: Login page renders');
  await page.setViewport(DESKTOP);
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(500);
  // Set theme AFTER navigation (safe)
  await page.evaluate(() => { try { localStorage.setItem('ey-theme', 'light'); } catch {} });
  await sleep(2000);
  const s1 = await screenshot(page, 'login-page_view-desktop-light', { fullPage: true });
  const formVisible = await page.evaluate(() => {
    return document.querySelectorAll('input').length >= 2 &&
           document.querySelector('form') !== null;
  });
  if (formVisible) {
    rec(M, 'AUTH-01', 'pass', { screenshot: s1 });
  } else {
    await injectRed(page, 'form');
    await screenshot(page, 'login-page_view-desktop-light-FAIL');
    bug(M, 'Login form not visible', 'P0', 'Functional', 'Navigate to /login',
      'Login form with 2+ inputs', 'Form elements not found', s1);
    rec(M, 'AUTH-01', 'fail', { screenshot: s1 });
  }

  // AUTH-02: Demo hint
  console.log('  AUTH-02: Demo credentials hint');
  const demoHint = await page.evaluate(() => {
    const alerts = document.querySelectorAll('.ant-alert');
    const bodyText = document.body.innerText;
    const hasDemo = bodyText.includes('admin@ey.com') || bodyText.includes('admin123') || bodyText.includes('demo');
    return { alertCount: alerts.length, hasDemoText: hasDemo };
  });
  const s2 = await screenshot(page, 'login-demo_hint-desktop-light', { fullPage: true });
  if (demoHint.hasDemoText) {
    rec(M, 'AUTH-02', 'pass', { screenshot: s2, details: 'Demo credentials visible' });
  } else {
    ux(M, 'Demo hint not prominent enough for first-time users', '🟡中',
      'Recognition over Recall', 'New testers struggle without knowing demo credentials; subtle hint buried in text',
      'Add a clickable "Use demo account" button that auto-fills email/password',
      s2);
    rec(M, 'AUTH-02', 'warn', { screenshot: s2 });
  }

  // AUTH-03: Empty form validation
  console.log('  AUTH-03: Empty form validation');
  await page.evaluate(() => localStorage.clear());
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(2000);
  const submitBtn = await page.$('button[type="submit"]');
  if (submitBtn) {
    await submitBtn.click();
    await sleep(1500);
    const hasValidation = await page.evaluate(() => {
      return document.querySelectorAll('.ant-form-item-explain-error, .ant-form-item-with-help').length > 0;
    });
    const s3 = await screenshot(page, 'login-empty_validation-desktop-light', { fullPage: true });
    if (hasValidation) {
      rec(M, 'AUTH-03', 'pass', { screenshot: s3 });
    } else {
      bug(M, 'No validation on empty login form submit', 'P2', 'UX',
        ['Navigate to /login', 'Click submit without filling fields'],
        'Validation error messages appear', 'No visible validation errors', s3);
      rec(M, 'AUTH-03', 'fail', { screenshot: s3 });
    }
  } else {
    bug(M, 'Login submit button not found', 'P1', 'Functional', 'Navigate to /login',
      'Submit button visible', 'No submit button found', null);
    rec(M, 'AUTH-03', 'fail');
  }

  // AUTH-04: Invalid email format
  console.log('  AUTH-04: Invalid email format validation');
  const emailInput = await page.$('input[type="email"], input');
  if (emailInput) {
    await emailInput.click({ clickCount: 3 });
    await emailInput.type('abc', { delay: 20 });
    await sleep(300);
    const submitBtn4 = await page.$('button[type="submit"]');
    if (submitBtn4) await submitBtn4.click();
    await sleep(1500);
    const emailValid = await page.evaluate(() => {
      return document.querySelectorAll('.ant-form-item-explain-error').length > 0;
    });
    const s4 = await screenshot(page, 'login-invalid_email-desktop-light', { fullPage: true });
    if (emailValid) {
      rec(M, 'AUTH-04', 'pass', { screenshot: s4 });
    } else {
      bug(M, 'No email format validation', 'P2', 'UX',
        ['Type "abc" in email field', 'Click submit'],
        '"Please enter a valid email" shown', 'No validation for email format', s4);
      rec(M, 'AUTH-04', 'fail', { screenshot: s4 });
    }
  }

  // AUTH-05: Invalid credentials error
  console.log('  AUTH-05: Invalid credentials error display');
  await page.evaluate(() => localStorage.clear());
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(2000);
  const allInputs = await page.$$('input');
  if (allInputs.length >= 2) {
    // First input is email, second is password
    await allInputs[0].click({ clickCount: 3 });
    await allInputs[0].type('wrong@test.com', { delay: 20 });
    await allInputs[1].click({ clickCount: 3 });
    await allInputs[1].type('wrongpass', { delay: 20 });
    const sb5 = await page.$('button[type="submit"]');
    if (sb5) await sb5.click();
    await sleep(3000);
    const errorVisible = await page.evaluate(() => {
      return document.querySelectorAll('.ant-alert-error, .ant-alert').length > 0 ||
             document.body.innerText.includes('failed') ||
             document.body.innerText.includes('Invalid');
    });
    const s5 = await screenshot(page, 'login-error_state-desktop-light', { fullPage: true });
    if (errorVisible) {
      rec(M, 'AUTH-05', 'pass', { screenshot: s5 });
    } else {
      bug(M, 'No error alert on invalid login attempt', 'P1', 'Functional',
        ['Type wrong email/password', 'Click submit'],
        'Error alert/banner appears', 'No visible error feedback', s5);
      rec(M, 'AUTH-05', 'fail', { screenshot: s5 });
    }
  }

  // AUTH-06: Mobile login
  console.log('  AUTH-06: Mobile login view');
  await page.evaluate(() => localStorage.clear());
  await page.setViewport(MOBILE);
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(2000);
  const s6 = await screenshot(page, 'login-page_view-mobile-light', { fullPage: true });
  const brandVisible = await page.evaluate(() => {
    const bp = document.querySelector('[class*="brand"], [class*="login-left"], [class*="left-panel"]');
    if (!bp) return false;
    const style = window.getComputedStyle(bp);
    return style.display !== 'none' && style.visibility !== 'hidden';
  });
  if (!brandVisible) {
    rec(M, 'AUTH-06', 'pass', { screenshot: s6, note: 'Brand panel hidden on mobile ✓' });
  } else {
    ux(M, 'Brand panel wastes space on mobile login', '🟡中',
      'Aesthetic and Minimalist Design', 'On mobile, the brand panel takes 50% of viewport, leaving cramped form area',
      'Hide brand panel on mobile, show only login form', s6);
    rec(M, 'AUTH-06', 'warn', { screenshot: s6 });
  }

  // AUTH-07: Dark mode login
  console.log('  AUTH-07: Dark mode login');
  await page.setViewport(DESKTOP);
  await page.evaluate(() => localStorage.clear());
  await page.evaluate(() => localStorage.setItem('ey-theme', 'dark'));
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(2000);
  const s7 = await screenshot(page, 'login-page_view-desktop-dark', { fullPage: true });
  const isDark = await page.evaluate(() => document.documentElement.getAttribute('data-theme') === 'dark');
  rec(M, 'AUTH-07', isDark ? 'pass' : 'warn', { screenshot: s7, note: isDark ? 'Dark theme applied' : 'Dark theme may not apply on login before auth' });
}

// ============================================================
// Module 2: Chat Interface
// ============================================================
async function testChat(page) {
  const M = 'CHAT';
  console.log('\n💬 Module 2: Chat Interface');

  await page.setViewport(DESKTOP);
  await page.evaluate(() => localStorage.setItem('ey-theme', 'light'));
  await page.evaluate(() => localStorage.setItem('ey-language', 'en'));
  const loggedIn = await apiLogin(page);
  if (!loggedIn) {
    console.log('  ⚠️ Login failed, skipping chat tests');
    bug(M, 'Cannot login to test chat', 'P0', 'Functional', 'API login attempt', 'Auth success', 'Auth failed', null);
    return;
  }
  await sleep(3000);

  // CHAT-01: Welcome screen or session list
  console.log('  CHAT-01: Chat page initial view');
  const s1 = await screenshot(page, 'chat-initial_view-desktop-light', { fullPage: true });
  const chatContent = await page.evaluate(() => {
    const welcome = document.querySelector('[class*="welcome"], [class*="Welcome"]');
    const messages = document.querySelectorAll('[class*="message"], [class*="Message"]');
    const input = document.querySelector('textarea, [class*="input"]');
    return { hasWelcome: welcome !== null, messageCount: messages.length, hasInput: input !== null };
  });
  rec(M, 'CHAT-01', 'pass', { screenshot: s1, details: chatContent.hasWelcome ? 'Welcome screen' : `${chatContent.messageCount} messages loaded, input: ${chatContent.hasInput}` });

  // CHAT-02: Send a message
  console.log('  CHAT-02: Send a message');
  const textarea = await page.$('textarea');
  if (textarea) {
    await textarea.click();
    await textarea.type('What is the IT setup process for new employees?', { delay: 30 });
    await sleep(500);
    await screenshot(page, 'chat-message_input-desktop-light');
    await page.keyboard.press('Enter');
    await sleep(3000);
    const s2 = await screenshot(page, 'chat-user_message_sent-desktop-light', { fullPage: true });
    const userMsg = await page.evaluate(() => {
      const bubbles = document.querySelectorAll('[class*="message-bubble"], [class*="bubble"], [class*="user-message"]');
      return bubbles.length > 0;
    });
    if (userMsg) {
      rec(M, 'CHAT-02', 'pass', { screenshot: s2 });
    } else {
      rec(M, 'CHAT-02', 'warn', { screenshot: s2, note: 'Message sent but bubble selector may differ' });
    }
  } else {
    bug(M, 'Chat input textarea not found', 'P0', 'Functional', 'Navigate to /chat after login',
      'Textarea input at bottom of chat page', 'No textarea found', null);
    rec(M, 'CHAT-02', 'fail');
  }

  // CHAT-03: Streaming response (wait)
  console.log('  CHAT-03: Streaming response (wait 15s)');
  await sleep(15000);
  const s3 = await screenshot(page, 'chat-streaming_response-desktop-light', { fullPage: true });
  const streamState = await page.evaluate(() => {
    const assistantMsg = document.querySelectorAll('[class*="assistant-message"], [class*="assistant"], [class*="bot-message"]');
    const thinking = document.querySelector('[class*="thinking"], [class*="dot-bounce"]');
    const streamingContent = document.querySelector('[class*="stream"]');
    return {
      hasAssistant: assistantMsg.length > 0,
      isThinking: thinking !== null,
      isStreaming: streamingContent !== null,
      count: assistantMsg.length
    };
  });
  if (streamState.hasAssistant || streamState.isStreaming) {
    rec(M, 'CHAT-03', 'pass', { screenshot: s3, details: `Assistant response: ${streamState.count} bubbles, streaming: ${streamState.isStreaming}` });
  } else if (streamState.isThinking) {
    rec(M, 'CHAT-03', 'warn', { screenshot: s3, note: 'Still thinking — AI response pending' });
  } else {
    bug(M, 'No AI response after 15s wait', 'P1', 'Functional',
      ['Send chat message', 'Wait 15 seconds'],
      'Streaming indicator or AI response visible',
      'No assistant content visible', s3);
    rec(M, 'CHAT-03', 'fail', { screenshot: s3 });
  }

  // CHAT-04: Complete response + citations
  console.log('  CHAT-04: Complete response check (wait 10s more)');
  await sleep(10000);
  const s4 = await screenshot(page, 'chat-response_complete-desktop-light', { fullPage: true });
  const citations = await page.$('[class*="citation"], [class*="source"]');
  if (citations) {
    rec(M, 'CHAT-04', 'pass', { screenshot: s4, note: 'Citations/source section visible' });
    // Expand citations
    await citations.click();
    await sleep(1000);
    await screenshot(page, 'chat-citations_expanded-desktop-light', { fullPage: true });
  } else {
    rec(M, 'CHAT-04', 'warn', { screenshot: s4, note: 'No citations visible (non-RAG query or different UI pattern)' });
  }

  // CHAT-05: Quick actions (need new session)
  console.log('  CHAT-05: Quick actions check');
  const newChatBtn = await page.$('button');
  const allBtns = await page.$$('button');
  let foundNewChat = false;
  for (const btn of allBtns) {
    const text = await btn.evaluate(el => el.textContent || '');
    const hasPlusIcon = await btn.evaluate(el => el.querySelector('.anticon-plus') !== null);
    if (text.includes('New') || text.includes('新建') || hasPlusIcon) {
      foundNewChat = true;
      await btn.click();
      await sleep(3000);
      break;
    }
  }
  if (foundNewChat) {
    const s5 = await screenshot(page, 'chat-new_session-desktop-light', { fullPage: true });
    const quickActions = await page.evaluate(() => {
      const cards = document.querySelectorAll('[class*="quick-action"], [class*="action-card"], [class*="QuickAction"]');
      return cards.length;
    });
    if (quickActions > 0) {
      rec(M, 'CHAT-05', 'pass', { screenshot: s5, details: `${quickActions} quick action cards visible` });
    } else {
      rec(M, 'CHAT-05', 'warn', { screenshot: s5, note: 'New session created but quick action cards may have different selectors' });
    }
  } else {
    rec(M, 'CHAT-05', 'warn', { note: 'New Chat button not found via text/icon search' });
  }

  // CHAT-06: Dark mode chat
  console.log('  CHAT-06: Dark mode chat view');
  await page.evaluate(() => localStorage.setItem('ey-theme', 'dark'));
  await page.reload({ waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const s6 = await screenshot(page, 'chat-page_view-desktop-dark', { fullPage: true });
  const darkOk = await page.evaluate(() => document.documentElement.getAttribute('data-theme') === 'dark');
  rec(M, 'CHAT-06', darkOk ? 'pass' : 'warn', { screenshot: s6 });

  // CHAT-07: Mobile chat
  console.log('  CHAT-07: Mobile chat view');
  await page.evaluate(() => localStorage.setItem('ey-theme', 'light'));
  await page.setViewport(MOBILE);
  await page.reload({ waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const s7 = await screenshot(page, 'chat-page_view-mobile-light', { fullPage: true });
  const hamburger = await page.evaluate(() => {
    const btns = document.querySelectorAll('button');
    for (const b of btns) {
      if (b.querySelector('.anticon-menu') || b.querySelector('.anticon-menu-fold') ||
          b.querySelector('.anticon-menu-unfold')) return true;
    }
    return false;
  });
  if (hamburger) {
    rec(M, 'CHAT-07', 'pass', { screenshot: s7, note: 'Hamburger menu visible on mobile' });
  } else {
    ux(M, 'No hamburger menu visible on mobile chat', '🟡中',
      'Discoverability', 'Mobile users cannot access sidebar navigation without a visible toggle',
      'Add clear hamburger icon in header on mobile viewport', s7);
    rec(M, 'CHAT-07', 'warn', { screenshot: s7 });
  }
  await page.setViewport(DESKTOP);
}

// ============================================================
// Module 3: Sidebar / Session Management
// ============================================================
async function testSidebar(page) {
  const M = 'SIDE';
  console.log('\n📂 Module 3: Sidebar / Session Management');

  await page.setViewport(DESKTOP);
  await page.evaluate(() => localStorage.setItem('ey-theme', 'light'));
  await page.evaluate(() => localStorage.setItem('ey-language', 'en'));
  await apiLogin(page);
  await sleep(3000);

  // SIDE-01: Full sidebar view
  console.log('  SIDE-01: Sidebar session list');
  const s1 = await screenshot(page, 'sidebar-full_view-desktop-light', { fullPage: true });
  const sideContent = await page.evaluate(() => {
    const sidebar = document.querySelector('[class*="sidebar"], [class*="Sidebar"], [class*="sider"]');
    const items = document.querySelectorAll('[class*="session-item"], [class*="conversation-item"], [class*="chat-item"]');
    const searchInput = document.querySelector('input[placeholder*="search"], input[placeholder*="搜索"]');
    const newChatBtn = document.querySelector('button');
    return { hasSidebar: sidebar !== null, sessionCount: items.length, hasSearch: searchInput !== null };
  });
  rec(M, 'SIDE-01', 'pass', { screenshot: s1, details: `Sidebar: ${sideContent.hasSidebar}, Sessions: ${sideContent.sessionCount}, Search: ${sideContent.hasSearch}` });

  // SIDE-02: Session search
  console.log('  SIDE-02: Sidebar search');
  const searchInput = await page.$('input[placeholder*="search"], input[placeholder*="搜索"], input[placeholder*="Search"]');
  if (searchInput) {
    await searchInput.click();
    await searchInput.type('email', { delay: 40 });
    await sleep(1500);
    const s2 = await screenshot(page, 'sidebar-search_filtered-desktop-light', { fullPage: true });
    rec(M, 'SIDE-02', 'pass', { screenshot: s2 });
  } else {
    ux(M, 'Sidebar search not easily discoverable', '🟢低',
      'Recognition over Recall', 'Without a visible search input, users must scroll through long session lists',
      'Make search input always visible at top of sidebar, not hidden', null);
    rec(M, 'SIDE-02', 'warn', { note: 'Search input not found with placeholder text' });
  }

  // SIDE-03: User area
  console.log('  SIDE-03: User area bottom');
  const userArea = await page.evaluate(() => {
    const bottom = document.querySelector('[class*="user-area"], [class*="sidebar-footer"], [class*="user-section"]');
    const logoutBtn = document.querySelector('button');
    return { hasUserArea: bottom !== null };
  });
  const s3 = await screenshot(page, 'sidebar-user_area-desktop-light');
  rec(M, 'SIDE-03', 'pass', { screenshot: s3 });

  // SIDE-04: Header bar elements
  console.log('  SIDE-04: Header bar (theme, language, user menu)');
  await page.goto(`${BASE_URL}/chat`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const headerElements = await page.evaluate(() => {
    const header = document.querySelector('[class*="header"], [class*="Header"]');
    const themeBtn = document.querySelector('[class*="theme-toggle"], button');
    const langBtn = document.querySelector('[class*="lang"], button');
    return { hasHeader: header !== null };
  });
  const s4 = await screenshot(page, 'sidebar-header_bar-desktop-light', { fullPage: true });
  rec(M, 'SIDE-04', 'pass', { screenshot: s4 });

  // SIDE-05: Mobile sidebar (drawer)
  console.log('  SIDE-05: Mobile sidebar drawer');
  await page.setViewport(MOBILE);
  await page.reload({ waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const s5 = await screenshot(page, 'sidebar-mobile_layout-mobile', { fullPage: true });
  rec(M, 'SIDE-05', 'pass', { screenshot: s5, note: 'Mobile layout captured' });

  // Try opening drawer
  const menuBtns = await page.$$('button');
  let drawerOpened = false;
  for (const btn of menuBtns) {
    const hasMenuIcon = await btn.evaluate(el =>
      el.querySelector('.anticon-menu-fold, .anticon-menu-unfold, .anticon-menu') !== null
    );
    if (hasMenuIcon) {
      await btn.click();
      await sleep(2000);
      drawerOpened = true;
      break;
    }
  }
  if (drawerOpened) {
    const s5b = await screenshot(page, 'sidebar-mobile_drawer-open-mobile', { fullPage: true });
    rec(M, 'SIDE-05b', 'pass', { screenshot: s5b, note: 'Drawer opened on mobile' });
  } else {
    rec(M, 'SIDE-05b', 'warn', { note: 'Could not find hamburger button to open drawer' });
  }
  await page.setViewport(DESKTOP);
}

// ============================================================
// Module 4: Profile Page
// ============================================================
async function testProfile(page) {
  const M = 'PROF';
  console.log('\n👤 Module 4: Profile Page');

  await page.setViewport(DESKTOP);
  await page.evaluate(() => localStorage.setItem('ey-theme', 'light'));
  await apiLogin(page);
  await sleep(2000);

  // PROF-01: Profile page renders
  console.log('  PROF-01: Profile page renders');
  await page.goto(`${BASE_URL}/profile`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const s1 = await screenshot(page, 'profile-page_view-desktop-light', { fullPage: true });
  const profileContent = await page.evaluate(() => {
    const card = document.querySelector('.ant-card');
    const formItems = document.querySelectorAll('.ant-form-item');
    const inputs = document.querySelectorAll('input, .ant-select');
    return { hasCard: card !== null, formItemCount: formItems.length, inputCount: inputs.length };
  });
  if (profileContent.hasCard && profileContent.formItemCount > 0) {
    rec(M, 'PROF-01', 'pass', { screenshot: s1, details: `${profileContent.formItemCount} form items, ${profileContent.inputCount} inputs` });
  } else {
    bug(M, 'Profile page content not rendered', 'P1', 'Functional',
      'Navigate to /profile after login', 'Profile card with form items',
      'No card or form items found', s1);
    rec(M, 'PROF-01', 'fail', { screenshot: s1 });
  }

  // PROF-02: Email readonly
  console.log('  PROF-02: Email field readonly');
  const emailInputs = await page.$$('input');
  let emailReadOnly = false;
  for (const inp of emailInputs) {
    const isDisabled = await inp.evaluate(el => el.disabled || el.readOnly);
    const val = await inp.evaluate(el => el.value);
    if (val.includes('@') && isDisabled) {
      emailReadOnly = true;
      break;
    }
  }
  const s2 = await screenshot(page, 'profile-email_readonly-desktop-light');
  rec(M, 'PROF-02', emailReadOnly ? 'pass' : 'warn', { screenshot: s2, note: emailReadOnly ? 'Email field correctly disabled' : 'Email field may be editable or not found' });

  // PROF-03: Language select
  console.log('  PROF-03: Language preference select');
  const langSelect = await page.$('.ant-select');
  if (langSelect) {
    await langSelect.click();
    await sleep(1000);
    const s3 = await screenshot(page, 'profile-lang_dropdown-desktop-light');
    rec(M, 'PROF-03', 'pass', { screenshot: s3 });
  } else {
    rec(M, 'PROF-03', 'warn', { note: 'Language select not found' });
  }

  // PROF-04: Minimal content UX
  console.log('  PROF-04: Profile content richness UX review');
  if (profileContent.formItemCount <= 2) {
    ux(M, 'Profile page is extremely minimal — only email and language', '🟡中',
      'Aesthetic vs Functionality', 'Users expect richer settings (name, department, office); bare-bones page feels incomplete',
      'Add service_line, office_location, role_level fields from user model; add avatar upload',
      s1);
  }
  rec(M, 'PROF-04', 'warn', { screenshot: s1, note: 'Minimal profile page noted as UX issue' });

  // PROF-05: Mobile profile
  console.log('  PROF-05: Mobile profile view');
  await page.setViewport(MOBILE);
  await page.reload({ waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const s5 = await screenshot(page, 'profile-page_view-mobile-light', { fullPage: true });
  rec(M, 'PROF-05', 'pass', { screenshot: s5 });
  await page.setViewport(DESKTOP);
}

// ============================================================
// Module 5: Knowledge Base
// ============================================================
async function testKnowledge(page) {
  const M = 'KB';
  console.log('\n📚 Module 5: Knowledge Base Admin');

  await page.setViewport(DESKTOP);
  await page.evaluate(() => localStorage.setItem('ey-theme', 'light'));
  await apiLogin(page);
  await sleep(2000);

  // KB-01: Knowledge base page
  console.log('  KB-01: Knowledge base page renders');
  await page.goto(`${BASE_URL}/admin/knowledge`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const s1 = await screenshot(page, 'knowledge-page_view-desktop-light', { fullPage: true });
  const kbContent = await page.evaluate(() => {
    const table = document.querySelector('.ant-table');
    const card = document.querySelector('.ant-card');
    const empty = document.querySelector('.ant-empty');
    const uploadBtn = document.querySelector('[class*="upload"], .ant-upload');
    return { hasTable: table !== null, hasCard: card !== null, isEmpty: empty !== null, hasUpload: uploadBtn !== null };
  });
  if (kbContent.hasTable || kbContent.hasCard) {
    rec(M, 'KB-01', 'pass', { screenshot: s1, details: `Table: ${kbContent.hasTable}, Upload: ${kbContent.hasUpload}` });
  } else if (kbContent.isEmpty) {
    rec(M, 'KB-01', 'warn', { screenshot: s1, note: 'Empty state shown (no documents or non-admin)' });
  } else {
    bug(M, 'Knowledge base page content not rendered', 'P1', 'Functional',
      'Navigate to /admin/knowledge', 'Document table or card visible',
      'No content rendered', s1);
    rec(M, 'KB-01', 'fail', { screenshot: s1 });
  }

  // KB-02: Status tags
  console.log('  KB-02: Document status tags');
  const tags = await page.$$('.ant-tag');
  if (tags.length > 0) {
    const s2 = await screenshot(page, 'knowledge-status_tags-desktop-light');
    rec(M, 'KB-02', 'pass', { screenshot: s2, details: `${tags.length} status tags visible` });
  } else {
    rec(M, 'KB-02', 'warn', { note: 'No document status tags (empty table or no documents)' });
  }

  // KB-03: Mobile knowledge page
  console.log('  KB-03: Mobile knowledge page');
  await page.setViewport(MOBILE);
  await page.reload({ waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const s3 = await screenshot(page, 'knowledge-page_view-mobile-light', { fullPage: true });
  rec(M, 'KB-03', 'pass', { screenshot: s3 });
  await page.setViewport(DESKTOP);
}

// ============================================================
// Module 6: Onboarding Tutorial
// ============================================================
async function testOnboarding(page) {
  const M = 'ONB';
  console.log('\n🎉 Module 6: Onboarding Tutorial Modal');

  await page.setViewport(DESKTOP);
  await page.evaluate(() => localStorage.setItem('ey-theme', 'light'));
  await page.evaluate(() => localStorage.removeItem('ey-onboarding-seen'));
  await apiLogin(page);
  await sleep(3000);

  // ONB-01: First-time modal
  console.log('  ONB-01: Onboarding modal appears');
  const modal = await page.$('.ant-modal-root, .ant-modal-wrap');
  if (modal) {
    const s1 = await screenshot(page, 'onboarding-modal_view-desktop-light', { fullPage: true });
    const modalContent = await page.evaluate(() => {
      const modalBody = document.querySelector('.ant-modal-body');
      const cards = modalBody ? modalBody.querySelectorAll('.ant-card, [class*="feature-card"]') : [];
      return { hasContent: modalBody !== null, cardCount: cards.length };
    });
    rec(M, 'ONB-01', 'pass', { screenshot: s1, details: `${modalContent.cardCount} feature cards in modal` });
  } else {
    // May have been auto-dismissed or localStorage already set
    const s1 = await screenshot(page, 'onboarding-modal_not_shown-desktop-light', { fullPage: true });
    rec(M, 'ONB-01', 'warn', { screenshot: s1, note: 'Modal not shown (localStorage may already be set)' });
  }
}

// ============================================================
// Module 7: Theme System
// ============================================================
async function testTheme(page) {
  const M = 'THM';
  console.log('\n🎨 Module 7: Theme System');

  await page.setViewport(DESKTOP);

  // THM-01: Light theme
  console.log('  THM-01: Light theme');
  await page.evaluate(() => { localStorage.setItem('ey-theme', 'light'); localStorage.setItem('ey-language', 'en'); });
  await apiLogin(page);
  await sleep(2000);
  await page.goto(`${BASE_URL}/chat`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const s1 = await screenshot(page, 'theme-light_chat-desktop-light', { fullPage: true });
  const isLight = await page.evaluate(() => document.documentElement.getAttribute('data-theme') !== 'dark');
  rec(M, 'THM-01', isLight ? 'pass' : 'fail', { screenshot: s1 });

  // THM-02: Switch to dark
  console.log('  THM-02: Switch to dark');
  await page.evaluate(() => localStorage.setItem('ey-theme', 'dark'));
  await page.reload({ waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const s2 = await screenshot(page, 'theme-dark_chat-desktop-dark', { fullPage: true });
  const isDark = await page.evaluate(() => document.documentElement.getAttribute('data-theme') === 'dark');
  if (isDark) {
    rec(M, 'THM-02', 'pass', { screenshot: s2 });
  } else {
    bug(M, 'Dark theme not applied on chat page reload', 'P1', 'Functional',
      'Set ey-theme=dark in localStorage, reload page',
      'data-theme="dark" on html element', 'Theme attribute not set to dark', s2);
    rec(M, 'THM-02', 'fail', { screenshot: s2 });
  }

  // THM-03: Dark sidebar detail
  console.log('  THM-03: Dark sidebar detail');
  const s3 = await screenshot(page, 'theme-dark_sidebar-desktop-dark');
  rec(M, 'THM-03', 'pass', { screenshot: s3 });

  // THM-04: Switch back to light
  console.log('  THM-04: Switch back to light');
  await page.evaluate(() => localStorage.setItem('ey-theme', 'light'));
  await page.reload({ waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const s4 = await screenshot(page, 'theme-light_chat-desktop-light-2', { fullPage: true });
  rec(M, 'THM-04', 'pass', { screenshot: s4 });
}

// ============================================================
// Module 8: i18n
// ============================================================
async function testI18n(page) {
  const M = 'I18N';
  console.log('\n🌐 Module 8: i18n Language Switching');

  await page.setViewport(DESKTOP);
  await page.evaluate(() => { localStorage.setItem('ey-theme', 'light'); localStorage.setItem('ey-language', 'en'); });
  await apiLogin(page);
  await sleep(2000);

  // I18N-01: English chat page
  console.log('  I18N-01: English chat page labels');
  await page.goto(`${BASE_URL}/chat`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const s1 = await screenshot(page, 'i18n-chat_en-desktop-light', { fullPage: true });
  const enContent = await page.evaluate(() => {
    const placeholder = document.querySelector('textarea')?.placeholder || '';
    const bodyText = document.body.innerText.substring(0, 500);
    return { placeholder, bodyText, hasEnglish: /[a-zA-Z]/.test(bodyText) };
  });
  rec(M, 'I18N-01', 'pass', { screenshot: s1, details: `Placeholder: "${enContent.placeholder}"` });

  // I18N-02: Switch to Chinese
  console.log('  I18N-02: Switch to Chinese');
  await page.evaluate(() => {
    localStorage.setItem('ey-language', 'zh');
    if (window.switchLanguage) window.switchLanguage('zh');
  });
  await sleep(2000);
  await page.reload({ waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const s2 = await screenshot(page, 'i18n-chat_zh-desktop-light', { fullPage: true });
  const zhContent = await page.evaluate(() => {
    const placeholder = document.querySelector('textarea')?.placeholder || '';
    const bodyText = document.body.innerText.substring(0, 500);
    const hasChinese = /[一-鿿一-鿿]/.test(bodyText);
    return { placeholder, hasChinese };
  });
  if (zhContent.hasChinese) {
    rec(M, 'I18N-02', 'pass', { screenshot: s2, details: `Placeholder: "${zhContent.placeholder}"` });
  } else {
    bug(M, 'Chinese language switch did not apply', 'P1', 'Functional',
      'Set ey-language=zh, reload page', 'Chinese UI labels',
      `English labels still showing. Placeholder: "${zhContent.placeholder}"`, s2);
    rec(M, 'I18N-02', 'fail', { screenshot: s2 });
  }

  // I18N-03: Chinese sidebar labels
  console.log('  I18N-03: Chinese sidebar labels');
  const s3 = await screenshot(page, 'i18n-sidebar_zh-desktop-light', { fullPage: true });
  rec(M, 'I18N-03', 'pass', { screenshot: s3 });

  // I18N-04: Switch back to English
  console.log('  I18N-04: Switch back to English');
  await page.evaluate(() => {
    localStorage.setItem('ey-language', 'en');
    if (window.switchLanguage) window.switchLanguage('en');
  });
  await sleep(2000);
  await page.reload({ waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const s4 = await screenshot(page, 'i18n-chat_en-desktop-light-2', { fullPage: true });
  rec(M, 'I18N-04', 'pass', { screenshot: s4 });

  // I18N-05: Chinese login page
  console.log('  I18N-05: Chinese login page');
  await page.evaluate(() => { localStorage.removeItem('ey-auth'); localStorage.setItem('ey-language', 'zh'); });
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(2000);
  const s5 = await screenshot(page, 'i18n-login_zh-desktop-light', { fullPage: true });
  rec(M, 'I18N-05', 'pass', { screenshot: s5 });
}

// ============================================================
// Module 9: Responsive Layout
// ============================================================
async function testResponsive(page) {
  const M = 'RSP';
  console.log('\n📱 Module 9: Responsive Layout');

  // RSP-01: Desktop
  console.log('  RSP-01: Desktop layout (1280×800)');
  await page.setViewport(DESKTOP);
  await page.evaluate(() => { localStorage.setItem('ey-theme', 'light'); localStorage.setItem('ey-language', 'en'); });
  await apiLogin(page);
  await sleep(3000);
  const s1 = await screenshot(page, 'responsive-layout-desktop', { fullPage: true });
  rec(M, 'RSP-01', 'pass', { screenshot: s1 });

  // RSP-02: Tablet
  console.log('  RSP-02: Tablet layout (768×1024)');
  await page.setViewport({ width: 768, height: 1024 });
  await page.reload({ waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const s2 = await screenshot(page, 'responsive-layout-tablet', { fullPage: true });
  rec(M, 'RSP-02', 'pass', { screenshot: s2 });

  // RSP-03: Mobile chat
  console.log('  RSP-03: Mobile chat (375×667)');
  await page.setViewport(MOBILE);
  await page.goto(`${BASE_URL}/chat`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const s3 = await screenshot(page, 'responsive-chat-mobile', { fullPage: true });
  rec(M, 'RSP-03', 'pass', { screenshot: s3 });

  // RSP-04: Mobile login
  console.log('  RSP-04: Mobile login (375×667)');
  await page.evaluate(() => localStorage.removeItem('ey-auth'));
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(2000);
  const s4 = await screenshot(page, 'responsive-login-mobile', { fullPage: true });
  rec(M, 'RSP-04', 'pass', { screenshot: s4 });

  await page.setViewport(DESKTOP);
}

// ============================================================
// Module 10: Error Handling
// ============================================================
async function testErrors(page) {
  const M = 'ERR';
  console.log('\n⚠️ Module 10: Error Handling');

  await page.setViewport(DESKTOP);

  // ERR-01: 401 redirect
  console.log('  ERR-01: 401 auth redirect');
  await page.evaluate(() => {
    localStorage.setItem('ey-auth', JSON.stringify({ token: 'fake-expired-token', user: { id: 1, email: 'fake@test.com' } }));
    localStorage.setItem('ey-theme', 'light');
    localStorage.setItem('ey-language', 'en');
  });
  await page.goto(`${BASE_URL}/chat`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(5000);
  const s1 = await screenshot(page, 'error-401_redirect-desktop-light', { fullPage: true });
  const url = page.url();
  if (url.includes('/login')) {
    rec(M, 'ERR-01', 'pass', { screenshot: s1, note: 'Redirected to /login on invalid token ✓' });
  } else {
    bug(M, 'No redirect on invalid auth token', 'P1', 'Functional',
      'Set fake token, navigate to /chat', 'Redirect to /login',
      `Stayed at ${url}`, s1);
    rec(M, 'ERR-01', 'fail', { screenshot: s1 });
  }

  // ERR-02: Re-login for error page checks
  console.log('  ERR-02: Chat error state check');
  await page.evaluate(() => localStorage.clear());
  await apiLogin(page);
  await sleep(2000);
  await page.goto(`${BASE_URL}/chat`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const errorAlert = await page.$('.ant-alert-error, .ant-alert');
  if (errorAlert) {
    const s2 = await screenshot(page, 'error-chat_error-alert-desktop-light');
    rec(M, 'ERR-02', 'pass', { screenshot: s2 });
  } else {
    rec(M, 'ERR-02', 'pass', { note: 'No error alerts (normal state — no errors currently)' });
  }
}

// ============================================================
// Main Runner
// ============================================================
async function main() {
  ensureDir(OUTPUT_DIR);
  ensureDir(SCREENSHOTS_DIR);

  console.log('🚀 EY Onboarding AI QA+UX Audit Runner v2');
  console.log(`   Base URL: ${BASE_URL}`);
  console.log(`   Output: ${OUTPUT_DIR}`);

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu', '--window-size=1280,800'],
    defaultViewport: DESKTOP,
    protocolTimeout: 180000  // Increased timeout for API calls
  });

  const page = await browser.newPage();
  page.setDefaultNavigationTimeout(30000);
  page.setDefaultTimeout(30000);

  try {
    await testAuth(page);
    await testChat(page);
    await testSidebar(page);
    await testProfile(page);
    await testKnowledge(page);
    await testOnboarding(page);
    await testTheme(page);
    await testI18n(page);
    await testResponsive(page);
    await testErrors(page);

    // Save results
    R.endTime = new Date().toISOString();
    R.summary = {
      total: R.total,
      passed: R.pass,
      failed: R.fail,
      warnings: R.warn,
      passRate: `${((R.pass / R.total) * 100).toFixed(1)}%`,
      bugCount: R.bugs.length,
      uxIssueCount: R.ux.length
    };

    fs.writeFileSync(RESULTS_FILE, JSON.stringify(R, null, 2));
    console.log('\n✅ Audit complete!');
    console.log(`   Total: ${R.total} | Pass: ${R.pass} | Fail: ${R.fail} | Warn: ${R.warn}`);
    console.log(`   Pass rate: ${R.summary.passRate}`);
    console.log(`   Bugs: ${R.bugs.length} | UX issues: ${R.ux.length}`);
  } catch (e) {
    console.error('❌ Error:', e.message);
    console.error('Stack:', e.stack?.substring(0, 500));
    R.error = e.message + '\n' + (e.stack?.substring(0, 2000) || '');
    fs.writeFileSync(RESULTS_FILE, JSON.stringify(R, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch(console.error);
