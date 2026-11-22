import path from "node:path";
import { defineConfig } from "@playwright/test";

const api = "http://127.0.0.1:5101";
const frontend = "http://127.0.0.1:3100";

export default defineConfig({
  testDir: "./tests",
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  use: {
    baseURL: frontend,
    launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE },
  },
  webServer: [
    {
      name: "Flask",
      command: "python -m flask --app backend.app run --host 127.0.0.1 --port 5101",
      cwd: path.resolve(".."),
      url: `${api}/api/bots`,
      env: { AUCTION_CORS_ORIGINS: frontend },
    },
    {
      name: "Next.js",
      command: "npx --no-install next dev --hostname 127.0.0.1 -p 3100",
      url: frontend,
      env: { NEXT_PUBLIC_API_BASE_URL: api, NEXT_TELEMETRY_DISABLED: "1" },
    },
  ],
});
