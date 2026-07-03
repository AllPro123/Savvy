import { createReadStream, existsSync, statSync } from 'node:fs';
import { createServer as createHttpServer } from 'node:http';
import { extname, join, normalize, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const publicDir = resolve(__dirname, '..', 'public');
const port = Number.parseInt(process.env.PORT || '3000', 10);
const host = process.env.HOST || '0.0.0.0';

const contentTypes = new Map([
  ['.css', 'text/css; charset=utf-8'],
  ['.html', 'text/html; charset=utf-8'],
  ['.ico', 'image/x-icon'],
  ['.js', 'text/javascript; charset=utf-8'],
  ['.json', 'application/json; charset=utf-8'],
  ['.svg', 'image/svg+xml; charset=utf-8']
]);

function sendJson(response, statusCode, payload) {
  const body = JSON.stringify(payload);
  response.writeHead(statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body),
    'Cache-Control': 'no-store'
  });
  response.end(body);
}

function sendNotFound(response) {
  sendJson(response, 404, {
    error: 'Not found',
    message: 'The requested resource does not exist.'
  });
}

function resolvePublicPath(pathname) {
  const cleanPath = pathname === '/' ? '/index.html' : pathname;
  const decodedPath = decodeURIComponent(cleanPath.split('?')[0]);
  const resolvedPath = normalize(join(publicDir, decodedPath));

  const relativePath = relative(publicDir, resolvedPath);

  if (relativePath.startsWith('..') || relativePath.includes(`..${sep}`)) {
    return null;
  }

  return resolvedPath;
}

export function createServer() {
  return createHttpServer((request, response) => {
    const requestUrl = new URL(request.url || '/', `http://${request.headers.host || 'localhost'}`);

    if (requestUrl.pathname === '/healthz') {
      sendJson(response, 200, {
        status: 'ok',
        service: 'savvy-deploy-app',
        uptime: Math.round(process.uptime())
      });
      return;
    }

    const filePath = resolvePublicPath(requestUrl.pathname);

    if (!filePath || !existsSync(filePath) || !statSync(filePath).isFile()) {
      sendNotFound(response);
      return;
    }

    response.writeHead(200, {
      'Content-Type': contentTypes.get(extname(filePath)) || 'application/octet-stream',
      'Cache-Control': filePath.endsWith('index.html') ? 'no-store' : 'public, max-age=3600'
    });
    createReadStream(filePath).pipe(response);
  });
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  createServer().listen(port, host, () => {
    console.log(`Savvy Deploy App is running at http://${host}:${port}`);
  });
}
