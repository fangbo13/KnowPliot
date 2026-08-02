import { mkdir, writeFile } from 'node:fs/promises';

await mkdir('dist/server', { recursive: true });

const worker = `const isHtmlRequest = (request) => {
  const accept = request.headers.get('accept') || '';
  return accept.includes('text/html');
};

const fallbackToIndex = (request) => {
  const url = new URL(request.url);
  url.pathname = '/index.html';
  return new Request(url, request);
};

export default {
  async fetch(request, env) {
    const response = await env.ASSETS.fetch(request);
    if (response.status === 404 && isHtmlRequest(request)) {
      return env.ASSETS.fetch(fallbackToIndex(request));
    }
    return response;
  },
};
`;

await writeFile('dist/server/index.js', worker, 'utf8');
