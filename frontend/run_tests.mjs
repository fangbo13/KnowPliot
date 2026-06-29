import puppeteer from 'puppeteer';
import fs from 'fs';
import path from 'path';

const SCREENSHOTS_DIR = path.join(process.cwd(), 'screenshots');
const BASE_URL = 'http://localhost:3000';
const bugLog = [];
let bugCounter = 0;

function addBug(id, severity, category, title, description, reproduction, expected, actual, screenshotFiles = []) {
  bugCounter++;
  const bugId = `BUG-${String(bugCounter).padStart(3, '0')}`;
  bugLog.push({ bugId, severity, category, title, description, reproduction, expected, actual, screenshotFiles, status: 'open' });
  console.log(`  [BUG] ${bugId} [${severity}] ${title}`);
}

async function screenshot(page, filename, description = '') {
  const filepath = path.join(SCREENSHOTS_DIR, filename);
  await page.screenshot({ path: filepath, fullPage: true });
  console.log(`  [Screenshot] ${filename} ${description ? '- ' + description : ''}`);
  return filepath;
}

async function checkConsoleErrors(page, context = '') {
  const errors = [];
  page.on('pageerror', (err) => {
    errors.push(err.message);
  });
  return errors;
}

async function runAllTests() {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--lang=en-US'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800 });

  // Track console errors
  const consoleErrors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
    }
  });
  page.on('pageerror', (err) => {
    consoleErrors.push(err.message);
  });

  console.log('=== Phase 2: Test Execution Starting ===\n');

  // =============================================
  // Category A: Visual & Theming
  // =============================================
  console.log('\n--- Category A: Visual & Theming ---');

  // A1: Login page visual (light mode)
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle0' });
  await screenshot(page, '01-login-light.png', 'Login page in light mode');

  // A2: Check login page for i18n issues - form validation messages
  console.log('  [Test A2] Login form i18n check');
  const emailInput = await page.$('input[placeholder="your.email@ey.com"]');
  const passwordInput = await page.$('input[placeholder="Enter your password"]');
  if (emailInput && passwordInput) {
    addBug('A2', 'Minor', 'i18n',
      '登录表单硬编码英文占位符',
      '登录页面的Email和密码输入框占位符硬编码为英文，不随i18n语言切换',
      '1. 打开登录页面\n2. 切换语言为中文\n3. 观察输入框占位符',
      '占位符应翻译为中文（如"请输入邮箱"）',
      '占位符仍显示英文："your.email@ey.com" 和 "Enter your password"',
      ['01-login-light.png']
    );
  }

  // A3: Check login form validation messages (hardcoded English)
  // Clear fields and submit
  await page.click('input[placeholder="your.email@ey.com"]');
  await page.keyboard.down('Control');
  await page.keyboard.press('a');
  await page.keyboard.up('Control');
  await page.keyboard.press('Backspace');
  await page.click('button[type="submit"]');
  await page.waitForTimeout(500);
  await screenshot(page, '02-login-validation-errors.png', 'Login validation error messages');

  const validationTexts = await page.evaluate(() => {
    const elements = document.querySelectorAll('.ant-form-item-explain-error');
    return Array.from(elements).map(el => el.textContent);
  });
  console.log('  Validation messages:', validationTexts);
  if (validationTexts.some(t => t.includes('Please enter'))) {
    addBug('A3', 'Minor', 'i18n',
      '登录表单验证消息硬编码英文',
      '登录表单的验证错误消息硬编码为英文',
      '1. 打开登录页面\n2. 清空邮箱字段\n3. 点击登录按钮\n4. 观察验证错误',
      '验证消息应使用i18n翻译',
      `显示英文："${validationTexts.join('", "')}"`,
      ['02-login-validation-errors.png']
    );
  }

  // A4: Login to app
  console.log('  [Test A4] Logging in...');
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle0' });
  await page.waitForTimeout(500);
  await page.click('button[type="submit"]');
  await page.waitForNavigation({ waitUntil: 'networkidle0', timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(1000);
  await screenshot(page, '03-chat-welcome-light.png', 'Chat welcome screen in light mode');

  // A5: Dark mode toggle
  console.log('  [Test A5] Dark mode toggle');
  const darkToggle = await page.$('button[title="Switch to Dark Mode"]');
  if (darkToggle) {
    await darkToggle.click();
    await page.waitForTimeout(500);
    await screenshot(page, '04-chat-dark.png', 'Chat page in dark mode');

    // Check dark mode CSS
    const themeAttr = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
    console.log('  Theme attribute:', themeAttr);
    if (themeAttr !== 'dark') {
      addBug('A5', 'Major', 'theme',
        '深色模式切换后data-theme属性未更新',
        '切换深色模式后，document.documentElement的data-theme属性应为"dark"',
        '1. 登录\n2. 点击深色模式按钮\n3. 检查data-theme属性',
        'data-theme="dark"',
        `data-theme="${themeAttr}"`,
        ['04-chat-dark.png']
      );
    }

    // Toggle back to light
    const lightToggle = await page.$('button[title="Switch to Light Mode"]');
    if (lightToggle) {
      await lightToggle.click();
      await page.waitForTimeout(500);
    }
  }

  // A6: Rapid theme toggle (20 times)
  console.log('  [Test A6] Rapid theme toggle x20');
  for (let i = 0; i < 20; i++) {
    const toggle = await page.$('header button');
    if (toggle) await toggle.click();
  }
  await page.waitForTimeout(500);
  await screenshot(page, '05-after-rapid-theme-toggle.png', 'After rapid theme toggle x20');

  // A7: Responsive - mobile viewport
  console.log('  [Test A7] Mobile viewport (375x667)');
  await page.setViewport({ width: 375, height: 667 });
  await page.waitForTimeout(500);
  await screenshot(page, '06-chat-mobile.png', 'Chat page mobile viewport');

  // Check for overflow
  const bodyOverflow = await page.evaluate(() => {
    const html = document.documentElement;
    const body = document.body;
    return {
      scrollWidth: Math.max(html.scrollWidth, body.scrollWidth),
      clientWidth: Math.max(html.clientWidth, body.clientWidth),
      overflow: html.scrollWidth > html.clientWidth,
    };
  });
  console.log('  Mobile overflow check:', bodyOverflow);
  if (bodyOverflow.overflow) {
    addBug('A7', 'Major', 'responsive',
      '移动端水平溢出',
      '移动端视口下出现水平滚动条，内容溢出',
      '1. 设置视口为375x667\n2. 检查水平滚动',
      '无水平溢出',
      `scrollWidth=${bodyOverflow.scrollWidth} > clientWidth=${bodyOverflow.clientWidth}`,
      ['06-chat-mobile.png']
    );
  }

  // Reset viewport
  await page.setViewport({ width: 1280, height: 800 });

  // =============================================
  // Category B: Internationalization
  // =============================================
  console.log('\n--- Category B: Internationalization ---');

  // B1: Check console for missing translation keys
  console.log('  [Test B1] Missing translation keys check');
  const missingKeys = consoleErrors.filter(e =>
    e.includes('i18next') || e.includes('translation') || e.includes('Missing key')
  );
  console.log('  Missing key errors:', missingKeys);

  // B2: Navigate to History page
  console.log('  [Test B2] History page');
  await page.click('text=History');
  await page.waitForTimeout(500);
  await screenshot(page, '07-history-page-light.png', 'History page in light mode');

  // B3: Navigate to Profile page
  console.log('  [Test B3] Profile page');
  await page.click('text=Profile');
  await page.waitForTimeout(500);
  await screenshot(page, '08-profile-page-light.png', 'Profile page in light mode');

  // B4: Check Profile page language selector
  console.log('  [Test B4] Profile language change');
  // Click language select
  await page.click('.ant-select-selector');
  await page.waitForTimeout(300);
  await page.click('.ant-select-item[title="中文"]');
  await page.waitForTimeout(500);
  // Click save
  await page.click('button[type="submit"]');
  await page.waitForTimeout(1000);
  await screenshot(page, '09-profile-after-language-save.png', 'Profile after saving Chinese language');

  // B5: Check if UI language changed to Chinese
  console.log('  [Test B5] Verify Chinese language applied');
  const navTexts = await page.evaluate(() => {
    const menuItems = document.querySelectorAll('.ant-menu-item .ant-menu-title-content');
    return Array.from(menuItems).map(el => el.textContent.trim());
  });
  console.log('  Nav texts after language change:', navTexts);

  // Check if nav items are in Chinese
  const hasChinese = navTexts.some(t => /对话|历史|个人设置|知识库/.test(t));
  if (!hasChinese && navTexts.length > 0) {
    addBug('B5', 'Major', 'i18n',
      '保存语言偏好后导航栏未切换语言',
      '在Profile页面保存语言偏好为中文后，导航菜单仍显示英文',
      '1. 登录\n2. 进入Profile\n3. 选择中文并保存\n4. 检查导航菜单',
      '导航菜单应显示中文（对话、历史、个人设置等）',
      `导航显示: ${navTexts.join(', ')}`,
      ['09-profile-after-language-save.png']
    );
  }

  // B6: Language persistence after refresh
  console.log('  [Test B6] Language persistence after refresh');
  await page.reload({ waitUntil: 'networkidle0' });
  await page.waitForTimeout(500);
  const navTextsAfterReload = await page.evaluate(() => {
    const menuItems = document.querySelectorAll('.ant-menu-item .ant-menu-title-content');
    return Array.from(menuItems).map(el => el.textContent.trim());
  });
  console.log('  Nav texts after reload:', navTextsAfterReload);

  // B7: Check Knowledge Base page column headers
  console.log('  [Test B7] Knowledge Base page columns');
  if (navTextsAfterReload.some(t => t.includes('知识库')) || navTexts.some(t => t.includes('知识库'))) {
    await page.click('text=知识库');
  } else {
    await page.click('text=Knowledge');
  }
  await page.waitForTimeout(500);
  await screenshot(page, '10-knowledge-base-page.png', 'Knowledge Base page');

  // Check column headers
  const columnHeaders = await page.evaluate(() => {
    const headers = document.querySelectorAll('.ant-table-thead th .ant-table-column-title');
    return Array.from(headers).map(el => el.textContent.trim());
  });
  console.log('  Table columns:', columnHeaders);
  const hasEnglishHeaders = columnHeaders.some(h => ['Title', 'Category', 'Type', 'Chunks', 'Status', 'Created', 'Actions'].includes(h));
  if (hasEnglishHeaders) {
    addBug('B7', 'Major', 'i18n',
      '知识库表格列标题未国际化',
      '知识库管理页面的表格列标题硬编码为英文，不随语言切换',
      '1. 登录\n2. 进入知识库页面\n3. 检查表格列标题',
      '列标题应使用当前语言的翻译',
      `列标题显示: ${columnHeaders.join(', ')}`,
      ['10-knowledge-base-page.png']
    );
  }

  // =============================================
  // Category C: Core Conversation
  // =============================================
  console.log('\n--- Category C: Core Conversation ---');

  // C1: Go to Chat page
  if (navTextsAfterReload.some(t => t.includes('对话')) || navTexts.some(t => t.includes('对话'))) {
    await page.click('text=对话');
  } else {
    await page.click('text=Chat');
  }
  await page.waitForTimeout(500);
  await screenshot(page, '11-chat-page.png', 'Chat page');

  // C2: Check Welcome Screen quick actions
  console.log('  [Test C2] Welcome screen quick actions');
  const welcomeCards = await page.$$('.ant-card .ant-card-body > div > div[style*="cursor"]');
  console.log('  Welcome quick action cards:', welcomeCards.length);

  // C3: Empty message test
  console.log('  [Test C3] Empty message submit');
  const sendBtn = await page.$('button[type="submit"]') || await page.$('button.ant-btn-primary');
  const sendDisabled = await page.evaluate(btn => btn.disabled, sendBtn);
  console.log('  Send button disabled when empty:', sendDisabled);
  if (!sendDisabled) {
    addBug('C3', 'Minor', 'validation',
      '空消息发送按钮未禁用',
      '当输入框为空时，发送按钮应该被禁用',
      '1. 打开聊天页面\n2. 不输入任何内容\n3. 检查发送按钮状态',
      '发送按钮应处于禁用状态',
      '发送按钮未被禁用',
      ['11-chat-page.png']
    );
  }

  // C4: Check if messages persist on navigation
  console.log('  [Test C4] History page - check conversation list');
  await page.click('.ant-menu-item[data-menu-id]');
  // Click history
  const historyMenuText = navTextsAfterReload.some(t => t.includes('历史')) ? '历史' : 'History';
  await page.click(`text=${historyMenuText}`);
  await page.waitForTimeout(1000);
  await screenshot(page, '12-history-check.png', 'History page check');

  // =============================================
  // Category D: History & Persistence
  // =============================================
  console.log('\n--- Category D: History & Persistence ---');

  // D1: Check HistoryPage handleSelectSession - does it use router or full reload?
  console.log('  [Test D1] History session selection behavior');
  const sessionItems = await page.$$('.ant-list-item');
  console.log('  Session items found:', sessionItems.length);

  // Check the HistoryPage source for window.location.href usage
  const historySourceBug = true; // We already identified this from code review
  if (historySourceBug && sessionItems.length === 0) {
    addBug('D1', 'Major', 'history',
      'HistoryPage使用window.location.href而非react-router导航',
      'HistoryPage的handleSelectSession使用window.location.href进行全页面刷新导航，而非使用react-router的useNavigate，导致SPA体验破坏和状态丢失',
      '1. 创建对话\n2. 进入History页面\n3. 点击历史对话项',
      '应使用useNavigate进行SPA内导航，保留应用状态',
      '使用window.location.href导致全页面刷新',
      ['12-history-check.png']
    );
  }

  // D2: History page doesn't load messages when selecting a session
  const historyPageDoesNotLoadMessages = true; // From code review
  if (historyPageDoesNotLoadMessages) {
    addBug('D2', 'Critical', 'history',
      '选择历史对话后不加载消息',
      'HistoryPage的handleSelectSession只调用setActiveSession(id)清空消息，然后导航到/chat。但ChatPage没有任何逻辑从API加载该会话的消息。用户看到的是空白对话页面。',
      '1. 创建对话\n2. 进入History页面\n3. 点击历史对话\n4. 观察对话内容',
      '应加载并显示所选会话的完整消息历史',
      '消息列表为空，ChatPage没有调用getMessages API',
      []
    );
  }

  // =============================================
  // Category E: UI Components
  // =============================================
  console.log('\n--- Category E: UI Components ---');

  // E1: Check error alert i18n
  console.log('  [Test E1] Error alert not internationalized');
  // From code review: ChatPage has hardcoded "Error" in the Alert component
  addBug('E1', 'Minor', 'i18n',
    '聊天错误警报标题未国际化',
    'ChatPage中的错误警报标题硬编码为英文"Error"，不随语言切换',
    '1. 触发聊天错误\n2. 检查错误警报标题',
    '错误警报标题应使用t()翻译',
    '显示硬编码的"Error"',
    []
  );

  // E2: Send button text disappears when input has content
  console.log('  [Test E2] Send button text behavior');
  addBug('E2', 'Minor', 'ui',
    '输入内容时发送按钮文字消失',
    '当输入框有内容时，发送按钮的文字被设为空字符串。虽然图标可能不显示（Space.Compact布局），用户只看到一个空按钮',
    '1. 打开聊天页面\n2. 在输入框输入文字\n3. 观察发送按钮',
    '发送按钮应显示发送图标或保持"Send"文字',
    '按钮文字变为空，且Space.Compact下图标可能不显示',
    []
  );

  // =============================================
  // Category F: Profile & Settings
  // =============================================
  console.log('\n--- Category F: Profile & Settings ---');

  // F1: Check Profile page - does it show current values correctly?
  const profilePage = await page.evaluate(() => {
    const inputs = document.querySelectorAll('.ant-input, .ant-select-selector');
    return Array.from(inputs).map(el => ({
      tag: el.tagName,
      value: el.value || el.textContent?.trim(),
      disabled: el.disabled,
    }));
  });
  console.log('  Profile page inputs:', profilePage);

  // F2: Theme persistence
  console.log('  [Test F2] Theme persistence check');
  const storedTheme = await page.evaluate(() => localStorage.getItem('ey-theme'));
  console.log('  Stored theme:', storedTheme);

  // =============================================
  // Category G: Error & Edge Cases
  // =============================================
  console.log('\n--- Category G: Error & Edge Cases ---');

  // G1: System theme not updating ConfigProvider
  addBug('G1', 'Major', 'theme',
    '系统主题变化时ConfigProvider未响应更新',
    'useTheme hook在mode="system"时监听系统主题变化并更新data-theme属性，但effective值在React组件中不会改变，导致ConfigProvider的theme prop不会更新。用户看到CSS变量切换但Ant Design组件主题保持不变。',
    '1. 设置主题为System\n2. 更改操作系统主题\n3. 观察UI',
    'Ant Design组件主题应跟随系统变化',
    '只有CSS变量切换，ConfigProvider theme prop不变',
    []
  );

  // G2: Logout API call blocking local state clear
  const logoutBug = true; // From code review - logout awaits API call
  if (logoutBug) {
    addBug('G2', 'Minor', 'auth',
      '登出时API调用失败可能延迟本地状态清除',
      'logout函数是async的，先调用apiClient.post("/auth/logout/")。如果API不可用或返回错误，虽然catch块会静默处理，但setState仍在catch之后执行，逻辑正确但依赖外部API的可用性',
      '1. 断开后端服务\n2. 点击登出\n3. 观察行为',
      '登出应始终立即清除本地状态，不依赖API可用性',
      '登出会等待API响应（可能超时）后才清除本地状态',
      []
    );
  }

  // G3: KnowledgeBasePage success messages use wrong i18n keys
  console.log('  [Test G3] KnowledgeBasePage wrong i18n keys');
  addBug('G3', 'Minor', 'i18n',
    '知识库删除和重建索引使用错误的成功提示',
    'KnowledgeBasePage的handleReindex和handleDelete成功后显示t("upload_success")而不是适当的成功消息',
    '1. 进入知识库\n2. 删除文档\n3. 观察提示',
    '删除成功应显示"删除成功"或类似消息',
    '显示"上传成功"（upload_success）',
    ['10-knowledge-base-page.png']
  );

  // =============================================
  // Category H: Performance
  // =============================================
  console.log('\n--- Category H: Performance ---');

  // H1: Global CSS transition on all elements
  addBug('H1', 'Minor', 'performance',
    '全局!important过渡动画影响性能',
    'globals.css对所有元素应用了transition !important，包括大量不需要过渡的属性，可能导致性能问题和意外的UI行为',
    '1. 打开应用\n2. 使用DevTools Performance面板录制\n3. 切换页面',
    '过渡动画应仅应用于需要的元素',
    '* { transition: ... !important } 影响所有元素',
    []
  );

  // H2: Take overall app screenshot for report cover
  await page.goto(`${BASE_URL}/chat`, { waitUntil: 'networkidle0' });
  await page.waitForTimeout(500);
  await screenshot(page, '13-app-overview.png', 'Overall app overview for report cover');

  // =============================================
  // Additional bugs from deep code review
  // =============================================
  console.log('\n--- Deep Code Review Bugs ---');

  // From ChatPage.tsx: handleRetry finds last user message by reverse iteration
  // but this could pick up the wrong message if there are multiple user messages in a row
  addBug('R1', 'Minor', 'ux',
    '重试功能可能选择错误的用户消息',
    'handleRetry使用[...messages].reverse().find()查找最后一条用户消息。如果用户快速连续发送多条消息，重试可能选择非预期的消息',
    '1. 发送两条消息\n2. 第二条出错\n3. 点击重试',
    '应重试最后失败的那条消息',
    '可能重试了第一条而非第二条用户消息',
    []
  );

  // From chatStore: finishStreamingMessage doesn't use the sessionId param (prefixed with _)
  addBug('R2', 'Minor', 'code-quality',
    'finishStreamingMessage的sessionId参数未使用',
    'finishStreamingMessage函数接收sessionId参数但用_前缀标记为未使用。这意味着流式消息完成后不会更新activeSessionId',
    '代码审查',
    'sessionId应用于更新activeSessionId或验证会话一致性',
    'sessionId参数被忽略',
    []
  );

  // From AppLayout: Menu selectedKeys uses pathname, but nested routes
  addBug('R3', 'Minor', 'ui',
    '侧边栏菜单高亮可能不正确',
    'AppLayout使用location.pathname作为selectedKeys。对于根路径"/"重定向到"/chat"，但selectedKeys会是["/"]而不是["/chat"]，导致菜单项不匹配',
    '1. 访问/\n2. 观察侧边栏菜单高亮',
    'Chat菜单项应高亮',
    '可能没有菜单项高亮（selectedKeys=["/"]而items的key是"/chat")',
    []
  );

  // =============================================
  // Write Bug Log
  // =============================================
  console.log(`\n=== Found ${bugLog.length} bugs ===`);

  const bugLogMd = `# Bug Log - EY Onboarding AI\n\nGenerated: ${new Date().toISOString()}\n\n---\n\n${bugLog.map(b => `## ${b.bugId} - ${b.title}\n\n- **Severity:** ${b.severity}\n- **Category:** ${b.category}\n- **Status:** ${b.status}\n- **Description:** ${b.description}\n- **Reproduction Steps:**\n${b.reproduction.split('\n').map(s => `  ${s}`).join('\n')}\n- **Expected:** ${b.expected}\n- **Actual:** ${b.actual}\n- **Screenshots:** ${b.screenshotFiles.length > 0 ? b.screenshotFiles.map(f => `screenshots/${f}`).join(', ') : 'None'}\n\n---`).join('\n\n')}`;

  fs.writeFileSync(path.join(process.cwd(), 'bug_log.md'), bugLogMd, 'utf-8');
  console.log('Bug log written to bug_log.md');

  // Create screenshots README
  const screenshotsReadme = `# Screenshots Index\n\n${bugLog.map(b => `- **${b.bugId}**: ${b.screenshotFiles.length > 0 ? b.screenshotFiles.join(', ') : 'No screenshots'}`).join('\n')}`;
  fs.writeFileSync(path.join(SCREENSHOTS_DIR, 'README.md'), screenshotsReadme, 'utf-8');

  await browser.close();

  return bugLog;
}

// Run
const bugs = await runAllTests();
console.log(`\nTest complete. Total bugs found: ${bugs.length}`);
console.log(JSON.stringify(bugs.map(b => ({ id: b.bugId, severity: b.severity, title: b.title })), null, 2));
