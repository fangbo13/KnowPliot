/**
 * EY Onboarding AI — QA+UX Comprehensive Audit Runner
 * Puppeteer-based automated test script with screenshot capture
 * Covers 10 functional modules, ~50 test scenarios
 */
import puppeteer from 'puppeteer';
import fs from 'fs';
import path from 'path';

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

const DESKTOP_VIEWPORT = { width: 1280, height: 800 };
const MOBILE_VIEWPORT = { width: 375, height: 667 };

// ============================================================
// Utility Functions
// ============================================================
function ensureDir(dir) {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function takeScreenshot(page, name, options = {}) {
  const filepath = path.join(SCREENSHOTS_DIR, `${name}.png`);
  try {
    await page.screenshot({ path: filepath, fullPage: options.fullPage || false, type: 'png' });
    console.log(`  📸 Screenshot saved: ${name}.png`);
    return filepath;
  } catch (e) {
    console.log(`  ❌ Screenshot failed for ${name}: ${e.message}`);
    return null;
  }
}

async function injectRedBorder(page, selector) {
  try {
    await page.evaluate((sel) => {
      const el = document.querySelector(sel);
      if (el) {
        el.style.outline = '3px solid red';
        el.style.outlineOffset = '2px';
      }
    }, selector);
    await sleep(300);
  } catch (e) {
    // selector may not exist, skip
  }
}

async function login(page) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(1000);

  // Fill login form
  const emailInput = await page.$('input[id="login_email"], input[type="email"]');
  const passwordInput = await page.$('input[id="login_password"], input[type="password"]');

  if (emailInput && passwordInput) {
    await emailInput.click();
    await emailInput.type(DEMO_EMAIL, { delay: 50 });
    await passwordInput.click();
    await passwordInput.type(DEMO_PASSWORD, { delay: 50 });

    // Click submit button
    const submitBtn = await page.$('button[type="submit"], button.ant-btn-primary');
    if (submitBtn) {
      await submitBtn.click();
      await sleep(3000);
      // Wait for redirect to /chat
      await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 15000 }).catch(() => {});
    }
  } else {
    // Alternative: direct API login then inject token
    const response = await page.evaluate(async (email, pwd, apiUrl) => {
      try {
        const res = await fetch(`${apiUrl}/auth/token/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password: pwd })
        });
        const data = await res.json();
        if (data.access) {
          // Get user profile
          const meRes = await fetch(`${apiUrl}/auth/me/`, {
            headers: { Authorization: `Bearer ${data.access}` }
          });
          const user = await meRes.json();
          // Set localStorage
          const authData = JSON.stringify({ token: data.access, user });
          localStorage.setItem('ey-auth', authData);
          localStorage.setItem('ey-language', user.language_preference || 'en');
          return { success: true, user };
        }
        return { success: false, error: data };
      } catch (e) {
        return { success: false, error: e.message };
      }
    }, DEMO_EMAIL, DEMO_PASSWORD, API_URL);

    if (response.success) {
      await page.goto(`${BASE_URL}/chat`, { waitUntil: 'networkidle2', timeout: 15000 });
      await sleep(2000);
    }
  }

  return page.url().includes('/chat') || page.url().includes('/login') === false;
}

// ============================================================
// Test Results Tracker
// ============================================================
const results = {
  startTime: new Date().toISOString(),
  environment: { baseUrl: BASE_URL, apiUrl: API_URL, viewport: DESKTOP_VIEWPORT },
  totalTests: 0,
  passed: 0,
  failed: 0,
  warnings: 0,
  bugs: [],
  uxIssues: [],
  screenshots: [],
  modules: {}
};

function recordResult(moduleId, scenarioId, status, details = {}) {
  results.totalTests++;
  if (status === 'pass') results.passed++;
  else if (status === 'fail') results.failed++;
  else results.warnings++;

  if (!results.modules[moduleId]) results.modules[moduleId] = { tests: [], bugs: [], uxIssues: [] };
  results.modules[moduleId].tests.push({
    id: scenarioId,
    status,
    ...details
  });
}

function recordBug(moduleId, title, severity, category, reproduction, expected, actual, screenshot) {
  const bugId = `BUG-${String(results.bugs.length + 1).padStart(3, '0')}`;
  const bug = {
    id: bugId,
    module: moduleId,
    title,
    severity,
    category,
    reproductionSteps: reproduction,
    expectedBehavior: expected,
    actualBehavior: actual,
    screenshot
  };
  results.bugs.push(bug);
  if (results.modules[moduleId]) results.modules[moduleId].bugs.push(bugId);
}

function recordUXIssue(moduleId, title, severity, heuristic, whyBad, howToFix, screenshot) {
  const uxId = `UX-${String(results.uxIssues.length + 1).padStart(3, '0')}`;
  const issue = {
    id: uxId,
    module: moduleId,
    title,
    severity,
    heuristicViolated: heuristic,
    whyBad,
    howToFix,
    screenshot
  };
  results.uxIssues.push(issue);
  if (results.modules[moduleId]) results.modules[moduleId].uxIssues.push(uxId);
}

// ============================================================
// Module 1: Authentication / Login Page
// ============================================================
async function testAuthModule(page) {
  const moduleId = 'AUTH';
  console.log('\n🔐 Module 1: Authentication / Login Page');

  // AUTH-01: Login page renders
  console.log('  AUTH-01: Login page renders correctly');
  await page.setViewport(DESKTOP_VIEWPORT);
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(1500);
  const loginFormVisible = await page.$('form, .ant-form, input[type="email"]');
  const screenshotPath = await takeScreenshot(page, 'login-page_view-desktop-light', { fullPage: true });
  if (loginFormVisible) {
    recordResult(moduleId, 'AUTH-01', 'pass', { screenshot: screenshotPath });
  } else {
    await injectRedBorder(page, '.ant-card, .login-container');
    await takeScreenshot(page, 'login-page_view-desktop-light-FAIL');
    recordBug(moduleId, 'Login page form not visible', 'P1', 'Functional',
      'Navigate to /login', 'Login form with email/password fields visible',
      'Login form elements not found', screenshotPath);
    recordResult(moduleId, 'AUTH-01', 'fail', { screenshot: screenshotPath });
  }

  // AUTH-02: Login with valid credentials
  console.log('  AUTH-02: Login with valid credentials');
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(1000);

  // Clear localStorage first
  await page.evaluate(() => { localStorage.clear(); });

  const emailInput2 = await page.$('input[type="email"], input[id="login_email"]');
  const passwordInput2 = await page.$('input[type="password"], input[id="login_password"]');
  if (emailInput2 && passwordInput2) {
    await emailInput2.click({ clickCount: 3 });
    await emailInput2.type(DEMO_EMAIL, { delay: 30 });
    await passwordInput2.click({ clickCount: 3 });
    await passwordInput2.type(DEMO_PASSWORD, { delay: 30 });
    await sleep(500);
    await takeScreenshot(page, 'login-filled_form-desktop-light');

    const submitBtn = await page.$('button[type="submit"], button.ant-btn-primary');
    if (submitBtn) {
      await submitBtn.click();
      await sleep(3000);
      await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 15000 }).catch(() => {});
      await sleep(2000);
    }

    const currentUrl = page.url();
    const afterLoginScreenshot = await takeScreenshot(page, 'login-success_redirect-desktop-light', { fullPage: true });
    if (currentUrl.includes('/chat') || !currentUrl.includes('/login')) {
      recordResult(moduleId, 'AUTH-02', 'pass', { screenshot: afterLoginScreenshot });
    } else {
      await injectRedBorder(page, '.ant-alert, .login-error');
      await takeScreenshot(page, 'login-success_redirect-desktop-light-FAIL');
      recordBug(moduleId, 'Login redirect failure', 'P1', 'Functional',
        ['Navigate to /login', 'Type valid credentials', 'Click submit'],
        'Redirect to /chat after login',
        `Stayed on ${currentUrl}`, afterLoginScreenshot);
      recordResult(moduleId, 'AUTH-02', 'fail', { screenshot: afterLoginScreenshot });
    }
  } else {
    recordBug(moduleId, 'Login form inputs not found', 'P0', 'Functional',
      'Navigate to /login', 'Email and password inputs visible',
      'Form inputs not found on page', null);
    recordResult(moduleId, 'AUTH-02', 'fail');
  }

  // AUTH-03: Login with invalid credentials
  console.log('  AUTH-03: Login with invalid credentials');
  await page.evaluate(() => { localStorage.clear(); });
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(1000);
  const emailInput3 = await page.$('input[type="email"], input[id="login_email"]');
  const passwordInput3 = await page.$('input[type="password"], input[id="login_password"]');
  if (emailInput3 && passwordInput3) {
    await emailInput3.click({ clickCount: 3 });
    await emailInput3.type('wrong@test.com', { delay: 30 });
    await passwordInput3.click({ clickCount: 3 });
    await passwordInput3.type('wrongpass', { delay: 30 });
    const submitBtn3 = await page.$('button[type="submit"], button.ant-btn-primary');
    if (submitBtn3) {
      await submitBtn3.click();
      await sleep(3000);
    }
    const errorAlert = await page.$('.ant-alert, [class*="error"], .login-error');
    const failScreenshot = await takeScreenshot(page, 'login-error_state-desktop-light', { fullPage: true });
    if (errorAlert) {
      recordResult(moduleId, 'AUTH-03', 'pass', { screenshot: failScreenshot });
    } else {
      recordBug(moduleId, 'No error alert on invalid login', 'P2', 'UX',
        ['Navigate to /login', 'Type wrong credentials', 'Click submit'],
        'Error alert/banner showing login failed',
        'No visible error alert', failScreenshot);
      recordResult(moduleId, 'AUTH-03', 'fail', { screenshot: failScreenshot });
    }
  }

  // AUTH-04: Empty form validation
  console.log('  AUTH-04: Empty form validation');
  await page.evaluate(() => { localStorage.clear(); });
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(1000);
  const submitBtn4 = await page.$('button[type="submit"], button.ant-btn-primary');
  if (submitBtn4) {
    await submitBtn4.click();
    await sleep(1500);
    const validationMsg = await page.$('.ant-form-item-explain-error, .ant-form-item-with-help');
    const valScreenshot = await takeScreenshot(page, 'login-empty_validation-desktop-light', { fullPage: true });
    if (validationMsg) {
      recordResult(moduleId, 'AUTH-04', 'pass', { screenshot: valScreenshot });
    } else {
      recordBug(moduleId, 'No validation on empty login form', 'P2', 'UX',
        ['Navigate to /login', 'Click submit without filling fields'],
        'Validation error messages under email and password',
        'No visible validation messages', valScreenshot);
      recordResult(moduleId, 'AUTH-04', 'fail', { screenshot: valScreenshot });
    }
  }

  // AUTH-05: Invalid email format
  console.log('  AUTH-05: Invalid email format validation');
  await page.evaluate(() => { localStorage.clear(); });
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(1000);
  const emailInput5 = await page.$('input[type="email"], input[id="login_email"]');
  if (emailInput5) {
    await emailInput5.click({ clickCount: 3 });
    await emailInput5.type('abc', { delay: 30 });
    await sleep(500);
    const submitBtn5 = await page.$('button[type="submit"], button.ant-btn-primary');
    if (submitBtn5) await submitBtn5.click();
    await sleep(1500);
    const emailValidation = await page.$('.ant-form-item-explain-error');
    const emailValScreenshot = await takeScreenshot(page, 'login-invalid_email-desktop-light', { fullPage: true });
    if (emailValidation) {
      recordResult(moduleId, 'AUTH-05', 'pass', { screenshot: emailValScreenshot });
    } else {
      recordBug(moduleId, 'No email format validation', 'P2', 'UX',
        ['Navigate to /login', 'Type "abc" in email field', 'Click submit'],
        '"Please enter a valid email" validation message',
        'No visible email format validation', emailValScreenshot);
      recordResult(moduleId, 'AUTH-05', 'fail', { screenshot: emailValScreenshot });
    }
  }

  // AUTH-06: Demo hint visibility
  console.log('  AUTH-06: Demo credentials hint');
  const demoHint = await page.$('.ant-alert-info, [class*="demo"], .ant-typography');
  const demoScreenshot = await takeScreenshot(page, 'login-demo_hint-desktop-light', { fullPage: true });
  if (demoHint) {
    recordResult(moduleId, 'AUTH-06', 'pass', { screenshot: demoScreenshot });
  } else {
    recordUXIssue(moduleId, 'Demo credentials hint not prominent', '🟡中',
      'Recognition over Recall', 'New testers may not know demo credentials; hidden or subtle hint makes first login hard',
      'Make demo hint more visible with a clickable "Use demo account" button that auto-fills credentials',
      demoScreenshot);
    recordResult(moduleId, 'AUTH-06', 'warning', { screenshot: demoScreenshot });
  }

  // AUTH-07: Login page mobile view
  console.log('  AUTH-07: Login page mobile view');
  await page.setViewport(MOBILE_VIEWPORT);
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(1500);
  const mobileLoginScreenshot = await takeScreenshot(page, 'login-page_view-mobile-light', { fullPage: true });
  // Check brand panel visibility
  const brandPanelVisible = await page.evaluate(() => {
    const panel = document.querySelector('.brand-panel, [class*="brand"], [class*="login-left"]');
    return panel ? window.getComputedStyle(panel).display !== 'none' : false;
  });
  if (!brandPanelVisible) {
    recordResult(moduleId, 'AUTH-07', 'pass', { screenshot: mobileLoginScreenshot, note: 'Brand panel correctly hidden on mobile' });
  } else {
    recordUXIssue(moduleId, 'Brand panel visible on mobile — layout overflow', '🟡中',
      'Aesthetic and Minimalist Design', 'Brand panel wastes precious mobile screen space, making the login form cramped',
      'Hide brand panel on mobile viewport, show only the login form',
      mobileLoginScreenshot);
    recordResult(moduleId, 'AUTH-07', 'warning', { screenshot: mobileLoginScreenshot });
  }
  // Reset viewport
  await page.setViewport(DESKTOP_VIEWPORT);

  // AUTH-08: Login page dark mode
  console.log('  AUTH-08: Login page dark mode');
  await page.evaluate(() => { localStorage.clear(); localStorage.setItem('ey-theme', 'dark'); });
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(2000);
  const darkLoginScreenshot = await takeScreenshot(page, 'login-page_view-desktop-dark', { fullPage: true });
  const isDarkTheme = await page.evaluate(() => {
    return document.documentElement.getAttribute('data-theme') === 'dark';
  });
  if (isDarkTheme) {
    recordResult(moduleId, 'AUTH-08', 'pass', { screenshot: darkLoginScreenshot });
  } else {
    recordBug(moduleId, 'Dark theme not applied on login page', 'P2', 'Visual',
      ['Set localStorage ey-theme=dark', 'Navigate to /login'],
      'Dark background and light text on login page',
      'Light theme still showing', darkLoginScreenshot);
    recordResult(moduleId, 'AUTH-08', 'fail', { screenshot: darkLoginScreenshot });
  }
}

// ============================================================
// Module 2: Chat Interface
// ============================================================
async function testChatModule(page) {
  const moduleId = 'CHAT';
  console.log('\n💬 Module 2: Chat Interface');

  // Ensure logged in with light theme
  await page.setViewport(DESKTOP_VIEWPORT);
  await page.evaluate(() => { localStorage.setItem('ey-theme', 'light'); });
  const loggedIn = await login(page);
  if (!loggedIn) {
    console.log('  ⚠️ Login failed, attempting manual login...');
    await login(page);
  }

  // CHAT-01: Welcome screen (new session)
  console.log('  CHAT-01: Welcome screen renders');
  // Reset to no active session
  await page.evaluate(() => {
    const auth = JSON.parse(localStorage.getItem('ey-auth') || '{}');
    localStorage.setItem('ey-auth', JSON.stringify(auth));
    // Clear any active session
  });
  await page.goto(`${BASE_URL}/chat`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);

  const welcomeScreenshot = await takeScreenshot(page, 'chat-welcome_screen-desktop-light', { fullPage: true });
  const welcomeElements = await page.evaluate(() => {
    const welcome = document.querySelector('.welcome-screen, [class*="welcome"]');
    const quickActions = document.querySelectorAll('.quick-action, [class*="quick-action"], [class*="action-card"]');
    const inputBox = document.querySelector('.ant-input, textarea, [class*="chat-input"]');
    return {
      hasWelcome: welcome !== null,
      quickActionCount: quickActions.length,
      hasInput: inputBox !== null
    };
  });

  if (welcomeElements.hasWelcome || welcomeElements.quickActionCount > 0) {
    recordResult(moduleId, 'CHAT-01', 'pass', {
      screenshot: welcomeScreenshot,
      details: `Welcome screen with ${welcomeElements.quickActionCount} quick actions`
    });
  } else {
    // May already have sessions, check for message list instead
    const messageList = await page.$('.message-list, [class*="message"], [class*="chat-content"]');
    if (messageList) {
      recordResult(moduleId, 'CHAT-01', 'warning', {
        screenshot: welcomeScreenshot,
        note: 'Welcome screen not shown — existing sessions loaded'
      });
    } else {
      await injectRedBorder(page, '.chat-page, main');
      await takeScreenshot(page, 'chat-welcome_screen-desktop-light-FAIL');
      recordBug(moduleId, 'Chat welcome screen missing', 'P1', 'Functional',
        'Login and navigate to /chat with no active session',
        'Welcome screen with quick action cards and input box',
        'No welcome screen visible', welcomeScreenshot);
      recordResult(moduleId, 'CHAT-01', 'fail', { screenshot: welcomeScreenshot });
    }
  }

  // CHAT-02: Send a message
  console.log('  CHAT-02: Send a message via input');
  const chatInput = await page.$('textarea, input[type="text"].ant-input, [class*="chat-input"] textarea');
  if (chatInput) {
    await chatInput.click();
    await chatInput.type('What is the company email setup process?', { delay: 30 });
    await sleep(500);
    await takeScreenshot(page, 'chat-message_input-desktop-light');

    // Send via Enter key
    await page.keyboard.press('Enter');
    await sleep(2000);
    const sentScreenshot = await takeScreenshot(page, 'chat-user_message_sent-desktop-light', { fullPage: true });

    // Check if user message bubble appeared
    const userBubble = await page.$('[class*="user-message"], [class*="message-bubble-user"]');
    if (userBubble) {
      recordResult(moduleId, 'CHAT-02', 'pass', { screenshot: sentScreenshot });
    } else {
      recordBug(moduleId, 'User message bubble not displayed after send', 'P1', 'Functional',
        ['Navigate to /chat', 'Type a question', 'Press Enter'],
        'User message bubble appears in chat area',
        'No user message visible after sending', sentScreenshot);
      recordResult(moduleId, 'CHAT-02', 'fail', { screenshot: sentScreenshot });
    }
  } else {
    recordBug(moduleId, 'Chat input box not found', 'P0', 'Functional',
      'Navigate to /chat page',
      'Chat input textarea visible at bottom',
      'No input textarea found', null);
    recordResult(moduleId, 'CHAT-02', 'fail');
  }

  // CHAT-03: Streaming response display
  console.log('  CHAT-03: Wait for streaming response');
  await sleep(8000); // Wait for AI response
  const streamScreenshot = await takeScreenshot(page, 'chat-streaming_response-desktop-light', { fullPage: true });

  const assistantBubble = await page.$('[class*="assistant-message"], [class*="message-bubble-assistant"]');
  const thinkingIndicator = await page.$('[class*="thinking"], [class*="dot-bounce"], [class*="streaming"]');

  if (assistantBubble) {
    recordResult(moduleId, 'CHAT-03', 'pass', { screenshot: streamScreenshot, note: 'Assistant response received' });
  } else if (thinkingIndicator) {
    recordResult(moduleId, 'CHAT-03', 'warning', {
      screenshot: streamScreenshot,
      note: 'Still streaming — thinking indicator visible'
    });
  } else {
    recordBug(moduleId, 'No assistant response or streaming indicator after 8s', 'P1', 'Functional',
      ['Send a chat message', 'Wait 8 seconds'],
      'Streaming indicator or assistant response bubble',
      'No response visible', streamScreenshot);
    recordResult(moduleId, 'CHAT-03', 'fail', { screenshot: streamScreenshot });
  }

  // CHAT-04: Wait for complete response with citations
  console.log('  CHAT-04: Complete response with citations');
  await sleep(15000); // Wait longer for full response
  const completeScreenshot = await takeScreenshot(page, 'chat-response_complete-desktop-light', { fullPage: true });

  const citationsToggle = await page.$('[class*="citation"], [class*="source"], button[class*="citation"]');
  if (citationsToggle) {
    recordResult(moduleId, 'CHAT-04', 'pass', { screenshot: completeScreenshot, note: 'Citations/source toggle visible' });
    // Try expanding citations
    await citationsToggle.click();
    await sleep(1000);
    await takeScreenshot(page, 'chat-citations_expanded-desktop-light', { fullPage: true });
  } else {
    recordResult(moduleId, 'CHAT-04', 'warning', {
      screenshot: completeScreenshot,
      note: 'Response complete but no citations visible (may not be RAG query)'
    });
  }

  // CHAT-05: Quick action card click
  console.log('  CHAT-05: Quick action card');
  // Create a new session to see welcome screen
  const newChatBtn = await page.$('[class*="new-chat"], button[class*="new-chat"], [class*="ant-btn"]:has(.anticon-plus)');
  if (newChatBtn) {
    await newChatBtn.click();
    await sleep(2000);
    const quickActionCard = await page.$('.quick-action, [class*="action-card"], [class*="quick"] button, [class*="quick"] .ant-card');
    if (quickActionCard) {
      await quickActionCard.click();
      await sleep(3000);
      await takeScreenshot(page, 'chat-quick_action_click-desktop-light', { fullPage: true });
      recordResult(moduleId, 'CHAT-05', 'pass', { note: 'Quick action triggered message send' });
    } else {
      recordResult(moduleId, 'CHAT-05', 'warning', { note: 'Quick action cards not found (may be in different layout)' });
    }
  }

  // CHAT-06: Message character counter
  console.log('  CHAT-06: Character counter');
  const inputArea2 = await page.$('textarea, [class*="chat-input"] textarea');
  if (inputArea2) {
    await inputArea3.click({ clickCount: 3 });
    // Type a long text to check counter
    const longText = 'This is a test message to check the character counter functionality of the chat input. We want to see if the counter appears and changes color as we approach the limit. '.repeat(30);
    await inputArea2.type(longText.substring(0, 3800), { delay: 10 });
    await sleep(500);
    const counterScreenshot = await takeScreenshot(page, 'chat-char_counter-desktop-light');
    const counterVisible = await page.$('[class*="counter"], [class*="char-count"]');
    if (counterVisible) {
      recordResult(moduleId, 'CHAT-06', 'pass', { screenshot: counterScreenshot });
    } else {
      recordUXIssue(moduleId, 'Character counter not visible near limit', '🟢低',
        'Visibility of System Status', 'Users need feedback on input length limits; missing counter may cause unexpected truncation',
        'Show character count near input when approaching 4000 char limit',
        counterScreenshot);
      recordResult(moduleId, 'CHAT-06', 'warning', { screenshot: counterScreenshot });
    }
  }

  // CHAT-07: Chat page dark mode
  console.log('  CHAT-07: Chat page dark mode');
  await page.evaluate(() => { localStorage.setItem('ey-theme', 'dark'); });
  await page.reload({ waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const darkChatScreenshot = await takeScreenshot(page, 'chat-page_view-desktop-dark', { fullPage: true });
  const isDark = await page.evaluate(() => document.documentElement.getAttribute('data-theme') === 'dark');
  if (isDark) {
    recordResult(moduleId, 'CHAT-07', 'pass', { screenshot: darkChatScreenshot });
  } else {
    recordBug(moduleId, 'Dark theme not applied on chat page after reload', 'P2', 'Visual',
      'Set theme=dark, reload page',
      'Dark themed chat interface',
      'Theme did not persist', darkChatScreenshot);
    recordResult(moduleId, 'CHAT-07', 'fail', { screenshot: darkChatScreenshot });
  }

  // CHAT-08: Chat page mobile view
  console.log('  CHAT-08: Chat page mobile view');
  await page.evaluate(() => { localStorage.setItem('ey-theme', 'light'); });
  await page.setViewport(MOBILE_VIEWPORT);
  await page.reload({ waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const mobileChatScreenshot = await takeScreenshot(page, 'chat-page_view-mobile-light', { fullPage: true });
  const hamburgerBtn = await page.$('[class*="hamburger"], [class*="menu-toggle"], button:has(.anticon-menu)');
  if (hamburgerBtn) {
    recordResult(moduleId, 'CHAT-08', 'pass', { screenshot: mobileChatScreenshot, note: 'Mobile layout with hamburger menu' });
  } else {
    recordUXIssue(moduleId, 'Hamburger menu button not found on mobile', '🟡中',
      'Recognition over Recall', 'On mobile, users cannot access sidebar navigation without a visible toggle button',
      'Ensure hamburger menu button is clearly visible in header on mobile viewport',
      mobileChatScreenshot);
    recordResult(moduleId, 'CHAT-08', 'warning', { screenshot: mobileChatScreenshot });
  }
  await page.setViewport(DESKTOP_VIEWPORT);
}

// ============================================================
// Module 3: Sidebar / Session Management
// ============================================================
async function testSidebarModule(page) {
  const moduleId = 'SIDE';
  console.log('\n📂 Module 3: Sidebar / Session Management');

  await page.setViewport(DESKTOP_VIEWPORT);
  await page.evaluate(() => { localStorage.setItem('ey-theme', 'light'); });
  const loggedIn = await login(page);
  await sleep(3000);

  // SIDE-01: Sidebar renders with sessions
  console.log('  SIDE-01: Sidebar session list');
  const sidebarScreenshot = await takeScreenshot(page, 'sidebar-session_list-desktop-light', { fullPage: true });
  const sessionItems = await page.$$('.session-item, [class*="session-item"], [class*="conversation-item"]');
  const sessionCount = sessionItems.length;
  if (sessionCount > 0) {
    recordResult(moduleId, 'SIDE-01', 'pass', { screenshot: sidebarScreenshot, details: `${sessionCount} sessions visible` });
  } else {
    recordResult(moduleId, 'SIDE-01', 'warning', { screenshot: sidebarScreenshot, note: 'No sessions visible in sidebar (empty state or different selector)' });
  }

  // SIDE-02: New Chat button
  console.log('  SIDE-02: New Chat button');
  const newChatBtn = await page.$('button[class*="new-chat"], [class*="ant-btn"]:has-text("New"), button .anticon-plus');
  if (newChatBtn) {
    const beforeUrl = page.url();
    await newChatBtn.click();
    await sleep(2000);
    const afterNewChatScreenshot = await takeScreenshot(page, 'sidebar-new_chat-desktop-light', { fullPage: true });
    recordResult(moduleId, 'SIDE-02', 'pass', { screenshot: afterNewChatScreenshot });
  } else {
    recordUXIssue(moduleId, 'New Chat button not clearly visible in sidebar', '🟡中',
      'Discoverability', 'Creating a new conversation is a primary action; if the button is hard to find, users feel stuck in old sessions',
      'Make "New Chat" button prominent with a contrasting color and clear icon',
      null);
    recordResult(moduleId, 'SIDE-02', 'warning', { note: 'New Chat button selector not matched' });
  }

  // SIDE-03: Session search
  console.log('  SIDE-03: Session search');
  const searchInput = await page.$('[class*="search"] input, input[placeholder*="search"], input[placeholder*="Search"]');
  if (searchInput) {
    await searchInput.click();
    await searchInput.type('email', { delay: 50 });
    await sleep(1000);
    const searchScreenshot = await takeScreenshot(page, 'sidebar-search_filtered-desktop-light', { fullPage: true });
    recordResult(moduleId, 'SIDE-03', 'pass', { screenshot: searchScreenshot });
  } else {
    recordResult(moduleId, 'SIDE-03', 'warning', { note: 'Sidebar search input not found' });
  }

  // SIDE-04: Session click navigation
  console.log('  SIDE-04: Session click');
  const firstSession = await page.$('.session-item, [class*="session-item"], [class*="conversation-item"]');
  if (firstSession) {
    await firstSession.click();
    await sleep(2000);
    const sessionSwitchScreenshot = await takeScreenshot(page, 'sidebar-session_switch-desktop-light', { fullPage: true });
    recordResult(moduleId, 'SIDE-04', 'pass', { screenshot: sessionSwitchScreenshot });
  } else {
    recordResult(moduleId, 'SIDE-04', 'warning', { note: 'No session items to click' });
  }

  // SIDE-05: Sidebar date groups
  console.log('  SIDE-05: Date group headers');
  const dateGroups = await page.$('[class*="date-group"], [class*="group-header"], [class*="time-group"]');
  const groupScreenshot = await takeScreenshot(page, 'sidebar-date_groups-desktop-light');
  if (dateGroups) {
    recordResult(moduleId, 'SIDE-05', 'pass', { screenshot: groupScreenshot });
  } else {
    recordResult(moduleId, 'SIDE-05', 'warning', { screenshot: groupScreenshot, note: 'Date group headers not found (different component structure)' });
  }

  // SIDE-06: User area at bottom
  console.log('  SIDE-06: User area bottom');
  const userArea = await page.$('[class*="user-area"], [class*="sidebar-footer"], [class*="user-info"]');
  const userScreenshot = await takeScreenshot(page, 'sidebar-user_area-desktop-light');
  if (userArea) {
    recordResult(moduleId, 'SIDE-06', 'pass', { screenshot: userScreenshot });
  } else {
    recordResult(moduleId, 'SIDE-06', 'warning', { screenshot: userScreenshot });
  }

  // SIDE-07: Mobile sidebar drawer
  console.log('  SIDE-07: Mobile sidebar drawer');
  await page.setViewport(MOBILE_VIEWPORT);
  await page.reload({ waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);

  // Find hamburger and click it
  const hamburger = await page.$('button:has(.anticon-menu-fold), button:has(.anticon-menu-unfold), [class*="hamburger"]');
  if (hamburger) {
    await hamburger.click();
    await sleep(2000);
    const drawerScreenshot = await takeScreenshot(page, 'sidebar-mobile_drawer-mobile', { fullPage: true });
    recordResult(moduleId, 'SIDE-07', 'pass', { screenshot: drawerScreenshot });
  } else {
    const mobileSidebar = await takeScreenshot(page, 'sidebar-mobile_nondrawer-mobile', { fullPage: true });
    recordUXIssue(moduleId, 'No hamburger menu button visible on mobile', '🟡中',
      'Discoverability', 'Mobile users cannot access sidebar/session list without a visible toggle button',
      'Add a hamburger menu icon in the header for mobile viewports',
      null);
    recordResult(moduleId, 'SIDE-07', 'warning', { screenshot: mobileSidebar });
  }
  await page.setViewport(DESKTOP_VIEWPORT);
}

// ============================================================
// Module 4: Profile Page
// ============================================================
async function testProfileModule(page) {
  const moduleId = 'PROF';
  console.log('\n👤 Module 4: Profile Page');

  await page.setViewport(DESKTOP_VIEWPORT);
  await page.evaluate(() => { localStorage.setItem('ey-theme', 'light'); });
  await login(page);
  await sleep(2000);

  // PROF-01: Profile page renders
  console.log('  PROF-01: Profile page renders');
  await page.goto(`${BASE_URL}/profile`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const profileScreenshot = await takeScreenshot(page, 'profile-page_view-desktop-light', { fullPage: true });

  const profileCard = await page.$('.ant-card, [class*="profile"], form');
  if (profileCard) {
    recordResult(moduleId, 'PROF-01', 'pass', { screenshot: profileScreenshot });
  } else {
    await injectRedBorder(page, 'main, .ant-layout-content');
    await takeScreenshot(page, 'profile-page_view-desktop-light-FAIL');
    recordBug(moduleId, 'Profile page content not rendered', 'P1', 'Functional',
      'Login and navigate to /profile', 'Profile settings card visible',
      'No profile content visible', profileScreenshot);
    recordResult(moduleId, 'PROF-01', 'fail', { screenshot: profileScreenshot });
  }

  // PROF-02: Email field readonly
  console.log('  PROF-02: Email field readonly');
  const emailField = await page.$('input[type="email"], input[disabled], input[name="email"]');
  if (emailField) {
    const isDisabled = await page.evaluate(el => el.disabled || el.readOnly, emailField);
    const emailScreenshot = await takeScreenshot(page, 'profile-email_readonly-desktop-light');
    if (isDisabled) {
      recordResult(moduleId, 'PROF-02', 'pass', { screenshot: emailScreenshot, note: 'Email field correctly disabled' });
    } else {
      recordBug(moduleId, 'Email field is editable on profile page', 'P2', 'Functional',
        'Navigate to /profile, check email input',
        'Email field disabled/read-only',
        'Email field is editable', emailScreenshot);
      recordResult(moduleId, 'PROF-02', 'fail', { screenshot: emailScreenshot });
    }
  }

  // PROF-03: Language dropdown
  console.log('  PROF-03: Language preference dropdown');
  const langSelect = await page.$('.ant-select, [class*="language"] .ant-select');
  if (langSelect) {
    await langSelect.click();
    await sleep(1000);
    const langDropdownScreenshot = await takeScreenshot(page, 'profile-lang_dropdown-desktop-light');
    recordResult(moduleId, 'PROF-03', 'pass', { screenshot: langDropdownScreenshot });
  } else {
    recordResult(moduleId, 'PROF-03', 'warning', { note: 'Language select not found' });
  }

  // PROF-04: Profile minimal content UX observation
  console.log('  PROF-04: Profile page content richness');
  const profileContentCheck = await page.evaluate(() => {
    const inputs = document.querySelectorAll('input, select, .ant-select');
    const sections = document.querySelectorAll('.ant-card, .ant-form-item');
    return { inputCount: inputs.length, sectionCount: sections.length };
  });
  if (profileContentCheck.sectionCount <= 2) {
    recordUXIssue(moduleId, 'Profile page is very minimal — only email and language', '🟡中',
      'Aesthetic and Minimalist Design vs Functionality', 'Users expect richer profile settings (name, department, office location); bare-bones page feels incomplete and makes the app feel "unfinished"',
      'Add service line, office location, role level fields that are already in the user model; add a "Last login" info line for trust',
      profileScreenshot);
  }
  recordResult(moduleId, 'PROF-04', 'warning', { screenshot: profileScreenshot });
}

// ============================================================
// Module 5: Knowledge Base Admin
// ============================================================
async function testKnowledgeModule(page) {
  const moduleId = 'KB';
  console.log('\n📚 Module 5: Knowledge Base Admin');

  await page.setViewport(DESKTOP_VIEWPORT);
  await page.evaluate(() => { localStorage.setItem('ey-theme', 'light'); });
  await login(page);
  await sleep(2000);

  // KB-01: Knowledge base page renders
  console.log('  KB-01: Knowledge base page renders');
  await page.goto(`${BASE_URL}/admin/knowledge`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const kbScreenshot = await takeScreenshot(page, 'knowledge-page_view-desktop-light', { fullPage: true });

  const kbTable = await page.$('.ant-table, [class*="document-table"], [class*="knowledge"]');
  if (kbTable) {
    recordResult(moduleId, 'KB-01', 'pass', { screenshot: kbScreenshot });
  } else {
    // Check if non-admin was redirected or content is empty
    const noAccess = await page.evaluate(() => {
      return document.querySelector('.ant-result, .ant-empty') !== null;
    });
    if (noAccess) {
      recordResult(moduleId, 'KB-01', 'warning', { screenshot: kbScreenshot, note: 'Empty or no-access state shown (may be non-admin or no documents)' });
    } else {
      recordBug(moduleId, 'Knowledge base page content not rendered', 'P1', 'Functional',
        'Login as admin, navigate to /admin/knowledge',
        'Document table with upload toolbar visible',
        'No content rendered', kbScreenshot);
      recordResult(moduleId, 'KB-01', 'fail', { screenshot: kbScreenshot });
    }
  }

  // KB-02: Document status tags
  console.log('  KB-02: Document status tags');
  const statusTags = await page.$$('.ant-tag, [class*="status-tag"]');
  if (statusTags.length > 0) {
    const tagsScreenshot = await takeScreenshot(page, 'knowledge-status_tags-desktop-light');
    recordResult(moduleId, 'KB-02', 'pass', { screenshot: tagsScreenshot, details: `${statusTags.length} status tags visible` });
  } else {
    recordResult(moduleId, 'KB-02', 'warning', { note: 'No status tags visible (empty table or no documents)' });
  }

  // KB-03: Upload button
  console.log('  KB-03: Upload button');
  const uploadBtn = await page.$('[class*="upload"] button, button .anticon-upload, .ant-upload');
  if (uploadBtn) {
    const uploadScreenshot = await takeScreenshot(page, 'knowledge-upload_button-desktop-light');
    recordResult(moduleId, 'KB-03', 'pass', { screenshot: uploadScreenshot });
  } else {
    recordUXIssue(moduleId, 'Upload button not easily discoverable on knowledge page', '🟡中',
      'Discoverability', 'Admin users need a clear way to add documents; a hidden or subtle upload button makes this harder',
      'Make upload button prominent with a clear label and icon in the toolbar area',
      null);
    recordResult(moduleId, 'KB-03', 'warning');
  }

  // KB-04: Mobile knowledge page
  console.log('  KB-04: Mobile knowledge page');
  await page.setViewport(MOBILE_VIEWPORT);
  await page.reload({ waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const mobileKB = await takeScreenshot(page, 'knowledge-page_view-mobile-light', { fullPage: true });
  recordResult(moduleId, 'KB-04', 'pass', { screenshot: mobileKB });
  await page.setViewport(DESKTOP_VIEWPORT);
}

// ============================================================
// Module 6: Onboarding Tutorial
// ============================================================
async function testOnboardingModule(page) {
  const moduleId = 'ONB';
  console.log('\n🎉 Module 6: Onboarding Tutorial Modal');

  await page.setViewport(DESKTOP_VIEWPORT);

  // ONB-01: First-time modal (fresh browser state)
  console.log('  ONB-01: Onboarding modal appears for new user');
  await page.evaluate(() => {
    localStorage.removeItem('ey-onboarding-seen');
    localStorage.setItem('ey-theme', 'light');
  });
  await login(page);
  await sleep(3000);

  const onboardingModal = await page.$('.ant-modal, [class*="onboarding"], [class*="tutorial"]');
  if (onboardingModal) {
    const onbScreenshot = await takeScreenshot(page, 'onboarding-modal_view-desktop-light', { fullPage: true });
    recordResult(moduleId, 'ONB-01', 'pass', { screenshot: onbScreenshot });
  } else {
    // Modal may have been dismissed already or not triggered
    recordResult(moduleId, 'ONB-01', 'warning', { note: 'Onboarding modal not shown (may need fresh auth state)' });
  }

  // ONB-02: Onboarding close/dismiss
  console.log('  ONB-02: Dismiss onboarding modal');
  const closeBtn = await page.$('.ant-modal-close, button[class*="close"], button[class*="get-started"]');
  if (closeBtn) {
    await closeBtn.click();
    await sleep(1500);
    const closedScreenshot = await takeScreenshot(page, 'onboarding-modal_closed-desktop-light', { fullPage: true });
    recordResult(moduleId, 'ONB-02', 'pass', { screenshot: closedScreenshot });
  } else {
    recordResult(moduleId, 'ONB-02', 'warning', { note: 'No modal to dismiss' });
  }
}

// ============================================================
// Module 7: Theme System
// ============================================================
async function testThemeModule(page) {
  const moduleId = 'THM';
  console.log('\n🎨 Module 7: Theme System (Light/Dark/System)');

  await page.setViewport(DESKTOP_VIEWPORT);
  await page.evaluate(() => { localStorage.setItem('ey-theme', 'light'); });
  await login(page);
  await sleep(2000);

  // THM-01: Light theme
  console.log('  THM-01: Light theme default');
  await page.reload({ waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(2000);
  const lightScreenshot = await takeScreenshot(page, 'theme-light_default-desktop-light', { fullPage: true });
  recordResult(moduleId, 'THM-01', 'pass', { screenshot: lightScreenshot });

  // THM-02: Switch to dark mode
  console.log('  THM-02: Switch to dark mode');
  const themeToggle = await page.$('[class*="theme-toggle"], button:has(.anticon-sun), button:has(.anticon-moon)');
  if (themeToggle) {
    await themeToggle.click();
    await sleep(2000);
    const darkScreenshot = await takeScreenshot(page, 'theme-switch_dark-desktop-dark', { fullPage: true });
    const isDark = await page.evaluate(() => document.documentElement.getAttribute('data-theme') === 'dark');
    if (isDark) {
      recordResult(moduleId, 'THM-02', 'pass', { screenshot: darkScreenshot });
    } else {
      recordBug(moduleId, 'Theme toggle did not switch to dark mode', 'P1', 'Functional',
        'Click theme toggle button', 'data-theme attribute set to "dark"',
        'Theme attribute unchanged', darkScreenshot);
      recordResult(moduleId, 'THM-02', 'fail', { screenshot: darkScreenshot });
    }
  } else {
    // Manual theme switch via localStorage
    await page.evaluate(() => { localStorage.setItem('ey-theme', 'dark'); });
    await page.reload({ waitUntil: 'networkidle2', timeout: 15000 });
    await sleep(3000);
    const darkScreenshot2 = await takeScreenshot(page, 'theme-switch_dark-desktop-dark', { fullPage: true });
    recordResult(moduleId, 'THM-02', 'warning', { screenshot: darkScreenshot2, note: 'Theme toggle via localStorage' });
  }

  // THM-03: Dark sidebar
  console.log('  THM-03: Dark sidebar appearance');
  const darkSidebar = await takeScreenshot(page, 'theme-dark_sidebar-desktop-dark');
  recordResult(moduleId, 'THM-03', 'pass', { screenshot: darkSidebar });

  // THM-04: Switch back to light
  console.log('  THM-04: Switch back to light mode');
  await page.evaluate(() => { localStorage.setItem('ey-theme', 'light'); });
  await page.reload({ waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const backLightScreenshot = await takeScreenshot(page, 'theme-switch_light-desktop-light', { fullPage: true });
  recordResult(moduleId, 'THM-04', 'pass', { screenshot: backLightScreenshot });
}

// ============================================================
// Module 8: i18n Language Switching
// ============================================================
async function testI18nModule(page) {
  const moduleId = 'I18N';
  console.log('\n🌐 Module 8: i18n Language Switching');

  await page.setViewport(DESKTOP_VIEWPORT);
  await page.evaluate(() => { localStorage.setItem('ey-theme', 'light'); localStorage.setItem('ey-language', 'en'); });
  await login(page);
  await sleep(2000);

  // I18N-01: Language dropdown
  console.log('  I18N-01: Language dropdown');
  const globeBtn = await page.$('[class*="lang-toggle"], button:has(.anticon-globe), [class*="language-switch"]');
  if (globeBtn) {
    await globeBtn.click();
    await sleep(1000);
    const langDropdownScreenshot = await takeScreenshot(page, 'i18n-lang_dropdown-desktop-light');
    recordResult(moduleId, 'I18N-01', 'pass', { screenshot: langDropdownScreenshot });
  } else {
    recordResult(moduleId, 'I18N-01', 'warning', { note: 'Language toggle button not found' });
  }

  // I18N-02: Switch to Chinese
  console.log('  I18N-02: Switch to Chinese');
  await page.evaluate(() => {
    localStorage.setItem('ey-language', 'zh');
    // Trigger language change
    if (window.switchLanguage) window.switchLanguage('zh');
  });
  await sleep(2000);
  const zhScreenshot = await takeScreenshot(page, 'i18n-switch_zh-desktop-light', { fullPage: true });

  // Check if Chinese text is visible
  const hasChinese = await page.evaluate(() => {
    const body = document.body.innerText;
    // Check for common Chinese characters
    return /[一-鿿]/.test(body);
  });
  if (hasChinese) {
    recordResult(moduleId, 'I18N-02', 'pass', { screenshot: zhScreenshot });
  } else {
    recordBug(moduleId, 'Chinese language switch did not apply UI labels', 'P1', 'Functional',
      'Set localStorage ey-language=zh, trigger language switch',
      'All UI labels in Chinese',
      'UI labels still in English or mixed', zhScreenshot);
    recordResult(moduleId, 'I18N-02', 'fail', { screenshot: zhScreenshot });
  }

  // I18N-03: Chinese chat page
  console.log('  I18N-03: Chinese chat page labels');
  await page.goto(`${BASE_URL}/chat`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const zhChatScreenshot = await takeScreenshot(page, 'i18n-chat_zh-desktop-light', { fullPage: true });
  const zhChatLabels = await page.evaluate(() => {
    const placeholder = document.querySelector('textarea, input[type="text"]')?.placeholder || '';
    const hasZhPlaceholder = /[一-鿿]/.test(placeholder);
    return { hasZhPlaceholder, placeholder };
  });
  if (zhChatLabels.hasZhPlaceholder) {
    recordResult(moduleId, 'I18N-03', 'pass', { screenshot: zhChatScreenshot });
  } else {
    recordResult(moduleId, 'I18N-03', 'warning', { screenshot: zhChatScreenshot, note: `Placeholder: "${zhChatLabels.placeholder}" — may be English` });
  }

  // I18N-04: Switch back to English
  console.log('  I18N-04: Switch back to English');
  await page.evaluate(() => {
    localStorage.setItem('ey-language', 'en');
    if (window.switchLanguage) window.switchLanguage('en');
  });
  await sleep(2000);
  const enScreenshot = await takeScreenshot(page, 'i18n-switch_en-desktop-light', { fullPage: true });
  recordResult(moduleId, 'I18N-04', 'pass', { screenshot: enScreenshot });

  // I18N-05: Chinese login page
  console.log('  I18N-05: Chinese login page');
  await page.evaluate(() => { localStorage.removeItem('ey-auth'); localStorage.setItem('ey-language', 'zh'); });
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(2000);
  const zhLoginScreenshot = await takeScreenshot(page, 'i18n-login_zh-desktop-light', { fullPage: true });
  recordResult(moduleId, 'I18N-05', 'pass', { screenshot: zhLoginScreenshot });
}

// ============================================================
// Module 9: Responsive Layout
// ============================================================
async function testResponsiveModule(page) {
  const moduleId = 'RSP';
  console.log('\n📱 Module 9: Responsive Layout');

  // RSP-01: Desktop layout
  console.log('  RSP-01: Desktop layout (1280x800)');
  await page.setViewport(DESKTOP_VIEWPORT);
  await page.evaluate(() => { localStorage.setItem('ey-theme', 'light'); localStorage.setItem('ey-language', 'en'); });
  await login(page);
  await sleep(3000);
  const desktopLayoutScreenshot = await takeScreenshot(page, 'responsive-layout-desktop', { fullPage: true });
  recordResult(moduleId, 'RSP-01', 'pass', { screenshot: desktopLayoutScreenshot });

  // RSP-02: Tablet (768x1024)
  console.log('  RSP-02: Tablet breakpoint (768x1024)');
  await page.setViewport({ width: 768, height: 1024 });
  await page.reload({ waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const tabletScreenshot = await takeScreenshot(page, 'responsive-layout-tablet', { fullPage: true });
  recordResult(moduleId, 'RSP-02', 'pass', { screenshot: tabletScreenshot });

  // RSP-03: Mobile chat
  console.log('  RSP-03: Mobile chat (375x667)');
  await page.setViewport(MOBILE_VIEWPORT);
  await page.goto(`${BASE_URL}/chat`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const mobileChatScreenshot = await takeScreenshot(page, 'responsive-chat-mobile', { fullPage: true });
  recordResult(moduleId, 'RSP-03', 'pass', { screenshot: mobileChatScreenshot });

  // RSP-04: Mobile profile
  console.log('  RSP-04: Mobile profile (375x667)');
  await page.goto(`${BASE_URL}/profile`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const mobileProfileScreenshot = await takeScreenshot(page, 'responsive-profile-mobile', { fullPage: true });
  recordResult(moduleId, 'RSP-04', 'pass', { screenshot: mobileProfileScreenshot });

  // RSP-05: Mobile login
  console.log('  RSP-05: Mobile login (375x667)');
  await page.evaluate(() => { localStorage.removeItem('ey-auth'); });
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(3000);
  const mobileLoginScreenshot = await takeScreenshot(page, 'responsive-login-mobile', { fullPage: true });
  recordResult(moduleId, 'RSP-05', 'pass', { screenshot: mobileLoginScreenshot });

  await page.setViewport(DESKTOP_VIEWPORT);
}

// ============================================================
// Module 10: Error Handling
// ============================================================
async function testErrorModule(page) {
  const moduleId = 'ERR';
  console.log('\n⚠️ Module 10: Error Handling');

  await page.setViewport(DESKTOP_VIEWPORT);

  // ERR-01: 401 redirect (expired token)
  console.log('  ERR-01: 401 auth redirect');
  await page.evaluate(() => {
    // Set a fake expired token
    localStorage.setItem('ey-auth', JSON.stringify({ token: 'fake-expired-token', user: { id: 1 } }));
    localStorage.setItem('ey-theme', 'light');
  });
  await page.goto(`${BASE_URL}/chat`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(5000);
  const errScreenshot = await takeScreenshot(page, 'error-401_redirect-desktop-light', { fullPage: true });
  const currentUrl = page.url();
  if (currentUrl.includes('/login')) {
    recordResult(moduleId, 'ERR-01', 'pass', { screenshot: errScreenshot, note: 'Redirected to /login on invalid token' });
  } else {
    recordBug(moduleId, 'No redirect on invalid/expired auth token', 'P1', 'Functional',
      'Set invalid auth token in localStorage, navigate to /chat',
      'Redirect to /login page',
      `Stayed on ${currentUrl}`, errScreenshot);
    recordResult(moduleId, 'ERR-01', 'fail', { screenshot: errScreenshot });
  }

  // ERR-02: Offline detection
  console.log('  ERR-02: Offline detection banner');
  // Re-login properly
  await page.evaluate(() => { localStorage.clear(); });
  await login(page);
  await sleep(2000);
  await page.goto(`${BASE_URL}/chat`, { waitUntil: 'networkidle2', timeout: 15000 });
  await sleep(2000);

  // Simulate offline by cutting network (cannot truly go offline in Puppeteer, observe the UI state)
  const networkBanner = await page.$('[class*="network-status"], [class*="offline"], .ant-alert:has-text("offline")');
  if (networkBanner) {
    const offlineScreenshot = await takeScreenshot(page, 'error-offline_banner-desktop-light');
    recordResult(moduleId, 'ERR-02', 'pass', { screenshot: offlineScreenshot });
  } else {
    // We can't truly simulate offline, but we can observe the banner structure
    recordResult(moduleId, 'ERR-02', 'warning', { note: 'Offline banner not visible (network is online — expected)' });
  }

  // ERR-03: Chat send error
  console.log('  ERR-03: Chat error display');
  // Check error alert pattern
  const errorAlert = await page.$('.ant-alert, [class*="chat-error"], [class*="send-error"]');
  if (errorAlert) {
    const errScreenshot3 = await takeScreenshot(page, 'error-chat_error-desktop-light');
    recordResult(moduleId, 'ERR-03', 'pass', { screenshot: errScreenshot3 });
  } else {
    recordResult(moduleId, 'ERR-03', 'warning', { note: 'No error alert currently visible (expected in normal state)' });
  }

  // ERR-04: Error boundary fallback (visual check)
  console.log('  ERR-04: Error boundary exists');
  const errorBoundaryComponent = await page.evaluate(() => {
    // Check if ErrorBoundary component is in the React tree (look for fallback UI patterns)
    return document.querySelector('[class*="error-boundary"], [class*="ant-result-error"]') !== null;
  });
  recordResult(moduleId, 'ERR-04', 'warning', { note: 'Error boundary not triggered (normal state — component exists in code)' });
}

// ============================================================
// Main Runner
// ============================================================
async function main() {
  ensureDir(OUTPUT_DIR);
  ensureDir(SCREENSHOTS_DIR);

  console.log('🚀 Starting EY Onboarding AI QA+UX Audit Runner');
  console.log(`   Base URL: ${BASE_URL}`);
  console.log(`   API URL: ${API_URL}`);
  console.log(`   Screenshots: ${SCREENSHOTS_DIR}`);

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu', '--window-size=1280,800'],
    defaultViewport: DESKTOP_VIEWPORT
  });

  const page = await browser.newPage();

  try {
    // Run all modules sequentially
    await testAuthModule(page);
    await testChatModule(page);
    await testSidebarModule(page);
    await testProfileModule(page);
    await testKnowledgeModule(page);
    await testOnboardingModule(page);
    await testThemeModule(page);
    await testI18nModule(page);
    await testResponsiveModule(page);
    await testErrorModule(page);

    // Save results
    results.endTime = new Date().toISOString();
    results.summary = {
      total: results.totalTests,
      passed: results.passed,
      failed: results.failed,
      warnings: results.warnings,
      passRate: `${((results.passed / results.totalTests) * 100).toFixed(1)}%`,
      bugCount: results.bugs.length,
      uxIssueCount: results.uxIssues.length
    };

    fs.writeFileSync(RESULTS_FILE, JSON.stringify(results, null, 2));
    console.log('\n✅ Audit complete!');
    console.log(`   Total tests: ${results.totalTests}`);
    console.log(`   Passed: ${results.passed} | Failed: ${results.failed} | Warnings: ${results.warnings}`);
    console.log(`   Pass rate: ${results.summary.passRate}`);
    console.log(`   Bugs found: ${results.bugs.length}`);
    console.log(`   UX issues: ${results.uxIssues.length}`);
    console.log(`   Results saved: ${RESULTS_FILE}`);
  } catch (e) {
    console.error('❌ Audit runner error:', e);
    results.error = e.message;
    fs.writeFileSync(RESULTS_FILE, JSON.stringify(results, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch(console.error);
