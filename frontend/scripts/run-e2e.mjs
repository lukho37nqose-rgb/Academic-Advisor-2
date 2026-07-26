import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { fileURLToPath } from 'node:url';

const host = '127.0.0.1';
const forwardedArgs = process.argv.slice(2);
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
const test = spawn(process.execPath, [playwrightCli, 'test', ...forwardedArgs], {
  stdio: 'inherit',
  env: {
    ...process.env,
    PLAYWRIGHT_PORT: port,
    PLAYWRIGHT_BASE_URL: baseUrl,
    PLAYWRIGHT_REUSE_EXISTING_SERVER: '0',
  },
});

test.on('exit', (code) => process.exit(code ?? 1));
test.on('error', () => process.exit(1));
