import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';


const source = readFileSync(new URL('./views.py', import.meta.url), 'utf8');
const paginator = source.match(
  /class MessageCursorPagination\(CursorPagination\):[\s\S]*?(?=\n(?:class|def) )/,
);

assert.ok(paginator, 'MessageCursorPagination class must exist');
assert.match(
  paginator[0],
  /ordering\s*=\s*['"]-created_at['"]/,
  'MessageCursorPagination must order newest-first so next points to older messages',
);
