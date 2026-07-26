import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { fileURLToPath } from 'node:url';

const host = '127.0.0.1';
const forwardedArgs = process.argv.slice(2);
const playwrightCli = fileURLToPath(new URL('../node_modules/@playwright/test/cli.js', import.meta.url));
const viteCli = fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url));

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

async function waitForServer(baseUrl, timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(baseUrl);
      if (response.ok) return;
    } catch {
      // Vite has not bound the port yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`Vite did not start at ${baseUrl} within ${timeoutMs / 1000} seconds.`);
}

const port = process.env.PLAYWRIGHT_PORT || await findAvailablePort();
const baseUrl = `http://${host}:${port}`;
const isListingTests = forwardedArgs.includes('--list');
let vite;

if (!isListingTests) {
  vite = spawn(process.execPath, [viteCli, '--host', host, '--port', port, '--strictPort'], {
    stdio: 'inherit',
  });
  vite.once('error', () => process.exit(1));
  try {
    await waitForServer(baseUrl);
  } catch (error) {
    vite.kill();
    throw error;
  }
}

const test = spawn(process.execPath, [playwrightCli, 'test', ...forwardedArgs], {
  stdio: 'inherit',
  env: {
    ...process.env,
    PLAYWRIGHT_PORT: port,
    PLAYWRIGHT_BASE_URL: baseUrl,
    PLAYWRIGHT_REUSE_EXISTING_SERVER: isListingTests ? '0' : '1',
  },
});

test.on('exit', (code) => {
  vite?.kill();
  process.exit(code ?? 1);
});
test.on('error', () => {
  vite?.kill();
  process.exit(1);
});
