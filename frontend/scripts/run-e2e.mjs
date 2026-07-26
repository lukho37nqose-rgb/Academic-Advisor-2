import { spawn, spawnSync } from 'node:child_process';
import { createServer } from 'node:net';
import { fileURLToPath } from 'node:url';

const isWindows = process.platform === 'win32';
const host = '127.0.0.1';
const forwardedArgs = process.argv.slice(2);
const viteCli = fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url));
const playwrightCli = fileURLToPath(new URL('../node_modules/@playwright/test/cli.js', import.meta.url));

async function findAvailablePort() {
  return new Promise((resolve, reject) => {
    const probe = createServer();
    probe.once('error', reject);
    probe.listen(0, host, () => {
      const address = probe.address();
      const port = typeof address === 'object' && address ? address.port : null;
      probe.close((error) => {
        if (error) {
          reject(error);
        } else if (port) {
          resolve(String(port));
        } else {
          reject(new Error('Could not allocate a local test port.'));
        }
      });
    });
  });
}

const port = process.env.PLAYWRIGHT_PORT || await findAvailablePort();
const baseUrl = `http://${host}:${port}`;

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForServer(timeoutMs = 30_000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(baseUrl);
      if (response.ok) {
        return;
      }
    } catch {}
    await delay(500);
  }
  throw new Error(`Vite did not become ready at ${baseUrl}`);
}

function spawnChild(command, args, options = {}) {
  return spawn(command, args, {
    windowsHide: isWindows,
    ...options,
  });
}

const server = spawnChild(process.execPath, [viteCli, '--host', host, '--port', port, '--strictPort'], {
  stdio: ['ignore', 'pipe', 'pipe'],
});

server.stdout.on('data', (chunk) => process.stdout.write(chunk));
server.stderr.on('data', (chunk) => process.stderr.write(chunk));

let shuttingDown = false;

function stopServer() {
  if (shuttingDown || server.killed) {
    return;
  }
  shuttingDown = true;
  if (isWindows && server.pid) {
    spawnSync('taskkill.exe', ['/pid', String(server.pid), '/T', '/F'], {
      stdio: 'ignore',
      windowsHide: true,
    });
    return;
  }
  server.kill('SIGTERM');
}

process.on('SIGINT', () => {
  stopServer();
  process.exit(130);
});

process.on('SIGTERM', () => {
  stopServer();
  process.exit(143);
});

try {
  await waitForServer();
  const test = spawnChild(process.execPath, [playwrightCli, 'test', ...forwardedArgs], {
    stdio: 'inherit',
    env: {
      ...process.env,
      PLAYWRIGHT_EXTERNAL_SERVER: '1',
      PLAYWRIGHT_BASE_URL: baseUrl,
    },
  });

  const exitCode = await new Promise((resolve) => {
    test.on('exit', (code) => resolve(code ?? 1));
    test.on('error', () => resolve(1));
  });
  stopServer();
  process.exit(exitCode);
} catch (error) {
  stopServer();
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
}
