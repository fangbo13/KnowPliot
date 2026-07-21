// Kept outside Vitest's default *.test.* discovery; run through node --test.
import assert from 'node:assert/strict';
import test from 'node:test';

import { transformAntDesignImports } from './vite-direct-imports.mjs';

test('rewrites Ant Design runtime imports to statically analyzable module paths', () => {
  const source = `
import {
  ConfigProvider,
  InputNumber,
  message as antMessage,
  type ThemeConfig,
} from 'antd';
`;

  assert.equal(
    transformAntDesignImports(source, '/workspace/src/example.tsx'),
    `
import ConfigProvider from 'antd/es/config-provider';
import InputNumber from 'antd/es/input-number';
import antMessage from 'antd/es/message';
import type { ThemeConfig } from 'antd';
`,
  );
});

test('does not let an earlier named import swallow the Ant Design declaration', () => {
  const source =
    "import { useMemo } from 'react';\n" +
    "import { BrowserRouter } from 'react-router-dom';\n" +
    "import { ConfigProvider } from 'antd';\n";

  assert.equal(
    transformAntDesignImports(source, '/workspace/src/main.tsx'),
    "import { useMemo } from 'react';\n" +
      "import { BrowserRouter } from 'react-router-dom';\n" +
      "import ConfigProvider from 'antd/es/config-provider';\n",
  );
});

test('rewrites icon imports while preserving local aliases', () => {
  const source = "import { CheckOutlined, CloseOutlined as Close } from '@ant-design/icons';\n";

  assert.equal(
    transformAntDesignImports(source, '/workspace/src/example.tsx'),
    "import CheckOutlined from '@ant-design/icons/es/icons/CheckOutlined';\n" +
      "import Close from '@ant-design/icons/es/icons/CloseOutlined';\n",
  );
});

test('narrows the deferred Ant Design message import', () => {
  const source = "import('antd').then(({ message: antMessage }) => antMessage.info('ok'));\n";

  assert.equal(
    transformAntDesignImports(source, '/workspace/src/example.ts'),
    "import('antd/es/message').then(({ default: antMessage }) => antMessage.info('ok'));\n",
  );
});

test('does not transform dependencies or unsupported import shapes', () => {
  const dependency = "import { Button } from 'antd';\n";
  const defaultImport = "import antd from 'antd';\n";

  assert.equal(
    transformAntDesignImports(dependency, '/workspace/node_modules/pkg/index.js'),
    dependency,
  );
  assert.equal(
    transformAntDesignImports(defaultImport, '/workspace/src/example.ts'),
    defaultImport,
  );
});
