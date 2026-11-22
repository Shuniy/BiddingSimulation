import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";

function gameStatus(page: Page) {
  return page.getByRole("region", { name: "Game controls" }).getByRole("status");
}

async function setUpCustomGame(page: Page, rounds = "12") {
  await page.goto("/");
  await expect(page.getByLabel("Player 1 strategy")).toBeEnabled();
  await page.getByRole("combobox", { name: "Rules", exact: true }).selectOption("custom");
  await page.getByLabel("Rounds", { exact: true }).fill(rounds);
  await page.getByLabel("Seed", { exact: true }).fill("4");
  await page.getByLabel("Player 1 name").fill('=Alice, "A"');
  await page.getByLabel("Player 1 budget").fill("900");
  await page.getByLabel("Player 1 strategy").selectOption("bots.flat_bot_15");
  await page.getByLabel("Player 2 strategy").selectOption("bots.flat_bot_10");
}

test("runs a real auction, inspects an early round, and exports all results", async ({ page }) => {
  await setUpCustomGame(page);
  await page.getByRole("button", { name: "Add player" }).click();
  await page.getByLabel("Player 3 strategy").selectOption("bots.flat_bot_10");
  await page.getByRole("button", { name: "Run game" }).click();
  await expect(gameStatus(page)).toHaveText("completed");
  await expect(page.getByRole("region", { name: "Game controls" })).toContainText("Seed 4");
  await expect(page.getByText('Winner · =Alice, "A"', { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Final rankings" }).getByRole("row")).toHaveCount(4);
  await page.getByRole("checkbox", { name: "Compare all players" }).check();
  await expect(page.getByRole("img", { name: "Remaining budget across 12 rounds" })).toBeVisible();

  await page.getByRole("button", { name: "Older" }).click();
  await page.getByRole("button", { name: "Round 1", exact: true }).click();
  await expect(page.getByText(/Round 1 of 12 ·/)).toBeVisible();
  await page.getByRole("button", { name: "Latest round" }).click();
  await expect(page.getByText(/Round 12 of 12 ·/)).toBeVisible();
  await page.getByRole("button", { name: "Play replay" }).click();
  await expect(page.getByRole("button", { name: "Pause replay" })).toBeVisible();
  await page.getByRole("button", { name: "Pause replay" }).click();

  for (const [name, extension] of [["Round CSV", ".csv"], ["Game JSON", ".json"], ["Summary JSON", "-summary.json"]]) {
    const downloaded = page.waitForEvent("download");
    await page.getByRole("button", { name }).click();
    const file = await downloaded;
    expect(file.suggestedFilename()).toMatch(new RegExp(extension.replace(".", "\\.") + "$"));
    const content = await readFile(await file.path(), "utf-8");
    if (name === "Round CSV") {
      expect(content.trimEnd().split("\r\n")).toHaveLength(37);
      expect(content).toContain('"\'=Alice, ""A"""');
    } else {
      const data = JSON.parse(content);
      expect(data.configuration.seed).toBe(4);
      if (name === "Game JSON") expect(data.events).toHaveLength(14);
      else expect(data.winners).toEqual(["Fixed Bid 15-1"]);
    }
  }
});

test("recovers a disconnected stream, cancels, and can replay the same game", async ({ page }) => {
  await setUpCustomGame(page, "100");
  await page.getByRole("button", { name: "Run game" }).click();
  await expect(page.getByText(/Round [1-9][0-9]* of 100 ·/)).toBeVisible();
  const saved = page.url();

  await page.route("**/events?after=0", (route) => route.abort("connectionreset"));
  await page.reload();
  await expect(page.getByRole("button", { name: "Reconnect", exact: true })).toBeVisible();
  await page.unroute("**/events?after=0");
  await page.getByRole("button", { name: "Reconnect", exact: true }).click();
  await expect(gameStatus(page)).toHaveText("running");
  await page.getByRole("button", { name: "Cancel game" }).click();
  await expect(gameStatus(page)).toHaveText("cancelled");
  await expect(page.getByRole("heading", { name: "Partial results" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Final results" })).toHaveCount(0);
  await page.goto(saved);
  await expect(gameStatus(page)).toHaveText("cancelled");
  await page.getByRole("button", { name: "Reset view" }).click();
  await expect(page).not.toHaveURL(/\?game=/);
});

test("reports an unavailable backend and loads strategies on retry", async ({ page }) => {
  await page.route("**/api/bots", (route) => route.abort());
  await page.goto("/");
  const alert = page.getByRole("region", { name: "Game setup" }).getByRole("alert");
  await expect(alert).toHaveText("Could not connect to the auction backend.");
  await expect(page.getByRole("button", { name: "Run game" })).toBeDisabled();
  await page.unroute("**/api/bots");
  await page.getByRole("button", { name: "Retry strategies" }).click();
  await expect(page.getByLabel("Player 1 strategy")).toBeEnabled();
  await expect(alert).toHaveCount(0);
});

test("does not show success when configuration is rejected", async ({ page }) => {
  await setUpCustomGame(page);
  await page.getByLabel("Seed", { exact: true }).fill("9007199254740992");
  await page.getByRole("button", { name: "Run game" }).click();
  await expect(page.getByRole("region", { name: "Game controls" }).getByRole("alert"))
    .toContainText("seed must be an integer");
  await expect(page.getByRole("heading", { name: "Final results" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Run game" })).toBeEnabled();
});

test("shows bot issues and a legitimate no-winner result", async ({ page }) => {
  await setUpCustomGame(page, "1");
  await page.getByLabel("Player 1 budget").fill("3");
  await page.getByLabel("Player 2 budget").fill("4");
  await page.getByRole("button", { name: "Run game" }).click();
  await expect(gameStatus(page)).toHaveText("completed");
  await expect(page.getByText("No winner. Every final score is zero.")).toBeVisible();
  await page.getByText("Bot issues (2)").click();
  await expect(page.getByText(/Over-budget bid changed to 0/)).toHaveCount(2);
});
