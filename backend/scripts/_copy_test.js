const fs = require('fs');
const src = 'e:/KnowPliot/tests/test_file_upload.py';
const dst = 'e:/KnowPliot/backend/scripts/run_upload_test.py';
fs.copyFileSync(src, dst);
console.log('Copied test script to backend/scripts/run_upload_test.py');
