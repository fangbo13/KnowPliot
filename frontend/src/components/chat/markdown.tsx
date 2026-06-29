import { memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import CopyCodeButton from './CopyCodeButton';

/**
 * Shared Markdown rendering for assistant messages.
 *
 * XSS protection: a strict element whitelist + protocol validation on links and
 * images (carried over from the hardened V4.0 implementation). The component
 * styling is now fully CSS-variable driven (see globals.css `.markdown-content`),
 * so no per-node inline theme overrides are needed.
 */
export const ALLOWED_ELEMENTS = [
  'p', 'br', 'strong', 'em', 'u', 's', 'del', 'ins', 'sub', 'sup',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'ul', 'ol', 'li',
  'blockquote', 'code', 'pre', 'hr',
  'table', 'thead', 'tbody', 'tr', 'th', 'td',
  'a', 'img',
  'details', 'summary',
  'span',   // highlight.js syntax tokens
  'input',  // GFM task-list checkboxes
];

const SAFE_HREF_PROTOCOLS = ['http://', 'https://', 'mailto:'];
const SAFE_SRC_PROTOCOLS = ['http://', 'https://'];

const components = {
  pre: ({ children, node, ...props }: any) => {
    // Extract raw code + language from the AST for the copy button.
    let codeContent = '';
    let language = '';
    if (node?.children?.[0]) {
      const codeNode = node.children[0] as any;
      if (codeNode?.properties?.className) {
        const classes = Array.isArray(codeNode.properties.className)
          ? codeNode.properties.className
          : [codeNode.properties.className];
        const langClass = classes.find((c: string) => typeof c === 'string' && c.startsWith('language-'));
        if (langClass) language = langClass.replace('language-', '');
      }
      if (codeNode?.children) {
        codeContent = codeNode.children.map((c: any) => c.value || '').join('');
      }
    }
    return (
      <div style={{ position: 'relative' }}>
        <pre {...props}>{children}</pre>
        <CopyCodeButton code={codeContent} language={language} />
      </div>
    );
  },
  a: ({ href, children }: any) => {
    const isSafe = href && SAFE_HREF_PROTOCOLS.some((p) => String(href).toLowerCase().startsWith(p));
    if (!isSafe) return <span>{children}</span>;
    return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
  },
  img: ({ src, alt }: any) => {
    const isSafe = src && SAFE_SRC_PROTOCOLS.some((p) => String(src).toLowerCase().startsWith(p));
    if (!isSafe) return alt ? <span>[{alt}]</span> : null;
    return <img src={src} alt={alt || ''} loading="lazy" />;
  },
};

function MarkdownViewBase({ children }: { children: string }) {
  return (
    <ReactMarkdown
      allowedElements={ALLOWED_ELEMENTS}
      unwrapDisallowed
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeHighlight]}
      components={components}
    >
      {children}
    </ReactMarkdown>
  );
}

/** Memoized by source string — a stable block never re-parses. */
export const MarkdownView = memo(MarkdownViewBase, (p, n) => p.children === n.children);
