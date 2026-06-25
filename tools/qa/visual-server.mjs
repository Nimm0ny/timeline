import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { URL } from "node:url";

const root = process.cwd();
const port = Number.parseInt(process.env.TIMELINE_VISUAL_PORT || process.env.PORT || "8798", 10);
const backendOrigin = process.env.TIMELINE_BACKEND_URL || "http://127.0.0.1:8000";
const visualTopicId = process.env.TIMELINE_VISUAL_TOPIC_ID || "1";
const visualEventId = process.env.TIMELINE_VISUAL_EVENT_ID || "1";
const frontendDir = path.join(root, "frontend");

const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".svg": "image/svg+xml",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".ttc": "font/collection",
};

function send(res, status, body, headers = {}) {
  res.writeHead(status, headers);
  res.end(body);
}

function safeFrontendPath(requestPath) {
  const cleanPath = requestPath === "/" ? "/index.html" : requestPath;
  const decoded = decodeURIComponent(cleanPath.split("?")[0]);
  const candidate = path.resolve(frontendDir, `.${decoded}`);
  const frontendRoot = path.resolve(frontendDir);
  if (candidate !== frontendRoot && !candidate.startsWith(`${frontendRoot}${path.sep}`)) {
    return null;
  }
  return candidate;
}

function isNavigationRequest(req, requestUrl) {
  if (path.extname(requestUrl.pathname)) return false;
  const accept = req.headers.accept || "";
  return req.method === "GET" && (requestUrl.pathname === "/" || accept.includes("text/html") || accept.includes("*/*"));
}

function serveFrontend(req, res) {
  if (!fs.existsSync(frontendDir)) {
    send(
      res,
      503,
      "frontend/ does not exist. Run `cmd /c npm run build` before visual QA.\n",
      { "content-type": "text/plain; charset=utf-8" },
    );
    return;
  }

  const requestUrl = new URL(req.url, `http://127.0.0.1:${port}`);
  let filePath = safeFrontendPath(requestUrl.pathname);
  if (!filePath) {
    send(res, 404, "Not found\n", { "content-type": "text/plain; charset=utf-8" });
    return;
  }

  const exists = fs.existsSync(filePath);
  const isDirectory = exists && fs.statSync(filePath).isDirectory();
  if (!exists || isDirectory) {
    if (!isNavigationRequest(req, requestUrl)) {
      send(res, 404, "Not found\n", { "content-type": "text/plain; charset=utf-8" });
      return;
    }
    filePath = path.join(frontendDir, "index.html");
  }

  if (!fs.existsSync(filePath)) {
    send(
      res,
      503,
      "frontend/index.html does not exist. Run `cmd /c npm run build` before visual QA.\n",
      { "content-type": "text/plain; charset=utf-8" },
    );
    return;
  }

  const extension = path.extname(filePath).toLowerCase();
  res.writeHead(200, { "content-type": contentTypes[extension] || "application/octet-stream" });
  fs.createReadStream(filePath).pipe(res);
}

function proxyToBackend(req, res) {
  const target = new URL(req.url, backendOrigin);
  const proxyReq = http.request(
    target,
    {
      method: req.method,
      headers: {
        ...req.headers,
        host: target.host,
      },
    },
    (proxyRes) => {
      res.writeHead(proxyRes.statusCode || 502, proxyRes.headers);
      proxyRes.pipe(res);
    },
  );

  proxyReq.on("error", (error) => {
    send(
      res,
      502,
      `Could not proxy to backend at ${backendOrigin}. Start it with \`python backend/server.py\`.\n${error.message}\n`,
      { "content-type": "text/plain; charset=utf-8" },
    );
  });

  req.pipe(proxyReq);
}

const server = http.createServer((req, res) => {
  const requestUrl = new URL(req.url, `http://127.0.0.1:${port}`);
  if (requestUrl.pathname.startsWith("/api/") || requestUrl.pathname.startsWith("/images/") || requestUrl.pathname.startsWith("/theme/")) {
    proxyToBackend(req, res);
    return;
  }
  serveFrontend(req, res);
});

server.listen(port, "127.0.0.1", () => {
  console.log(`Visual QA server: http://127.0.0.1:${port}/?topic=${visualTopicId}&event=${visualEventId}&mode=edit`);
  console.log(`Backend proxy target: ${backendOrigin}`);
});
