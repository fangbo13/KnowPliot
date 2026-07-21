const IDENTIFIER = /^[A-Za-z_$][\w$]*$/;
const STATIC_IMPORT = /import\s*\{([^}]*)\}\s*from\s*(['"])(antd|@ant-design\/icons)\2\s*;?/g;
const DEFERRED_MESSAGE_IMPORT =
  /import\(\s*(['"])antd\1\s*\)\s*\.then\(\s*\(\{\s*message\s*:\s*([A-Za-z_$][\w$]*)\s*\}\)\s*=>/g;

function antDesignModulePath(exportedName) {
  return exportedName
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .toLowerCase();
}

function parseSpecifier(specifier) {
  const typeOnly = specifier.startsWith('type ');
  const value = typeOnly ? specifier.slice(5).trim() : specifier;
  const match = value.match(/^([A-Za-z_$][\w$]*)(?:\s+as\s+([A-Za-z_$][\w$]*))?$/);
  if (!match) return null;

  return {
    exported: match[1],
    local: match[2] ?? match[1],
    typeOnly,
  };
}

export function transformAntDesignImports(source, id) {
  const normalizedId = id.replaceAll('\\', '/').split('?')[0];
  if (
    normalizedId.includes('/node_modules/') ||
    !normalizedId.includes('/src/') ||
    !/\.[cm]?[jt]sx?$/.test(normalizedId)
  ) {
    return source;
  }

  const withStaticImports = source.replace(
    STATIC_IMPORT,
    (declaration, specifierList, _quote, packageName) => {
      const specifiers = specifierList
        .split(',')
        .map((specifier) => specifier.trim())
        .filter(Boolean)
        .map(parseSpecifier);

      if (specifiers.some((specifier) => specifier === null)) return declaration;

      const runtimeImports = specifiers
        .filter((specifier) => !specifier.typeOnly)
        .map(({ exported, local }) => {
          if (!IDENTIFIER.test(exported) || !IDENTIFIER.test(local)) return null;
          const modulePath = packageName === 'antd'
            ? `antd/es/${antDesignModulePath(exported)}`
            : `@ant-design/icons/es/icons/${exported}`;
          return `import ${local} from '${modulePath}';`;
        });

      if (runtimeImports.some((statement) => statement === null)) return declaration;

      const typeSpecifiers = specifiers
        .filter((specifier) => specifier.typeOnly)
        .map(({ exported, local }) => (exported === local ? exported : `${exported} as ${local}`));
      const typeImport = typeSpecifiers.length > 0
        ? `import type { ${typeSpecifiers.join(', ')} } from '${packageName}';`
        : null;

      return [...runtimeImports, typeImport].filter(Boolean).join('\n');
    },
  );

  return withStaticImports.replace(
    DEFERRED_MESSAGE_IMPORT,
    (_declaration, _quote, local) =>
      `import('antd/es/message').then(({ default: ${local} }) =>`,
  );
}

export function antDesignDirectImports() {
  return {
    name: 'knowpilot-antd-direct-imports',
    enforce: 'pre',
    apply: 'build',
    transform(source, id) {
      const code = transformAntDesignImports(source, id);
      return code === source ? null : { code, map: null };
    },
  };
}
