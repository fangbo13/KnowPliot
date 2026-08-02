const fs = require('fs');
const srcDir = 'e:/KnowPliot/backend/test_results';
const dstDir = 'e:/KnowPliot/audit_reports/file_upload_tests';

// Ensure dst exists
fs.mkdirSync(dstDir, { recursive: true });

// Copy report files
const files = ['File_Upload_Test_Report.md', 'file_upload_test_results.json'];
for (const f of files) {
  const src = `${srcDir}/${f}`;
  const dst = `${dstDir}/${f}`;
  try {
    fs.copyFileSync(src, dst);
    console.log(`Copied: ${f}`);
  } catch (e) {
    console.error(`Failed to copy ${f}: ${e.message}`);
  }
}
console.log('Done.');
