// Simple verification script - checks code structure without browser
import fs from 'fs';

console.log('=== Verifying Bug Fixes (Code Structure Check) ===\n');

// Check 1: HistoryPage code structure
console.log('Check 1: HistoryPage - Independent message loading + Continue chat button');
const historyPage = fs.readFileSync('./frontend/src/pages/HistoryPage.tsx', 'utf-8');

const hasLocalViewMessages = historyPage.includes('viewMessages') &&
  historyPage.includes('useState<Message[]>');
const hasContinueChatButton = historyPage.includes('继续对话') &&
  historyPage.includes('handleContinueChat');
const setActiveSessionCalls = historyPage.split('\n').filter(line => line.includes('setActiveSession('));
const onlyInContinueChat = setActiveSessionCalls.length === 1 &&
  setActiveSessionCalls[0].includes('viewingSessionId');
const hasDividerImport = historyPage.includes('Divider');
const hasMessageIcon = historyPage.includes('MessageOutlined');

console.log(`  ✅ Has local viewMessages state: ${hasLocalViewMessages}`);
console.log(`  ✅ Has 继续对话 button: ${hasContinueChatButton}`);
console.log(`  ✅ setActiveSession only in handleContinueChat: ${onlyInContinueChat}`);
console.log(`  ✅ Imports Divider: ${hasDividerImport}`);
console.log(`  ✅ Imports MessageOutlined: ${hasMessageIcon}`);

// Check 2: ChatPage route-based reset
console.log('\nCheck 2: ChatPage - Route-based message reset');
const chatPage = fs.readFileSync('./frontend/src/pages/ChatPage.tsx', 'utf-8');

const hasLocationImport = chatPage.includes('useLocation');
const hasRouteReset = chatPage.includes('loadedSessionRef.current = null') &&
  chatPage.includes('location.pathname');
const hasFixedPosition = chatPage.includes("position: 'fixed'") &&
  chatPage.includes('bottom: 32') &&
  chatPage.includes('justifyContent: \'center\'');

console.log(`  ✅ Imports useLocation: ${hasLocationImport}`);
console.log(`  ✅ Resets loadedSessionRef on route change: ${hasRouteReset}`);
console.log(`  ✅ Input uses position: fixed: ${hasFixedPosition}`);

// Check 3: Summary
console.log('\n=== Summary ===');
const allChecks = [
  hasLocalViewMessages,
  hasContinueChatButton,
  onlyInContinueChat,
  hasDividerImport,
  hasMessageIcon,
  hasLocationImport,
  hasRouteReset,
  hasFixedPosition
];
const passed = allChecks.filter(Boolean).length;
console.log(`${passed}/${allChecks.length} checks passed`);

if (passed === allChecks.length) {
  console.log('✅ All code structure checks passed!');
  console.log('\nNext steps: Please manually verify in browser:');
  console.log('1. 历史页 → 点击对话 → 在历史页内查看消息');
  console.log('2. 点击底部「继续对话」按钮 → 跳转到对话页并可继续发消息');
  console.log('3. 对话页输入框 → 浮动在底部中央（DeepSeek 风格）');
} else {
  console.log('❌ Some checks failed. Please review the code.');
}
