import { expect, test, type Page } from "@playwright/test";

test.use({ timezoneId: "America/Los_Angeles" });
test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-10-04T12:00:00-07:00"));
  await page.goto("/?member=1");
});
async function openSheet(page: Page, name = "Morning walk") {
  await page.getByRole("button", { name: "Add habit", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Add habit", exact: true });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Habit name", { exact: true }).fill(name);
  // Dismiss through a real focus transition, like tapping another form control.
  await dialog.getByRole("button", { name: "Daily", exact: true }).click();
  return dialog;
}

test("compact right-aligned launcher opens a daily sheet; save survives reload", async ({ page }) => {
  const trigger = page.getByRole("button", { name: "Add habit", exact: true });
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
  expect(await trigger.locator("svg").count()).toBe(1);
  const layout = await trigger.evaluate((button) => {
    const row = button.parentElement!.getBoundingClientRect(), box = button.getBoundingClientRect();
    return { width: box.width, parent: row.width, right: Math.abs(box.right - row.right) };
  });
  expect(layout.width).toBeLessThan(layout.parent / 2);
  expect(layout.right).toBeLessThan(2);
  const dialog = await openSheet(page);
  await expect(dialog.getByText("Every day", { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Add habit", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole("button", { name: "Morning walk", exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "Morning walk", exact: true })).toBeVisible();
});

test("weekly dates, custom interval, monthly rule and end date are editable", async ({ page }) => {
  const dialog = await openSheet(page, "Stretch");
  await dialog.getByRole("button", { name: "Weekly", exact: true }).click();
  await dialog.getByRole("button", { name: "Sunday", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "Add habit", exact: true })).toBeDisabled();
  await dialog.getByRole("button", { name: "Monday", exact: true }).click();
  await dialog.getByRole("button", { name: "Wednesday", exact: true }).click();
  await expect(dialog.getByText("Every Mon, Wed", { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Custom", exact: true }).click();
  await dialog.getByRole("button", { name: "Increase repeat interval" }).click();
  await expect(dialog.getByText("Every 2 weeks on Mon, Wed", { exact: true })).toBeVisible();
  await dialog.getByLabel("Repeat unit").selectOption("months");
  await expect(dialog.getByText("Every 2 months on day 4", { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Change end date" }).click();
  await dialog.getByRole("button", { name: "On a date", exact: true }).click();
  await dialog.getByRole("button", { name: "Oct 24, 2026", exact: true }).click();
  await dialog.getByRole("button", { name: "Add habit", exact: true }).click();
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem("vocal-biomarkers.habits.v1")!));
  expect(stored[0].schedule).toMatchObject({ frequency: "Custom", interval: 2, unit: "months", end: "2026-10-24", weekdays: [1, 3] });
});

test("custom dates support selection, deselection and month navigation", async ({ page }) => {
  const dialog = await openSheet(page, "Recovery session");
  await dialog.getByRole("button", { name: "Custom", exact: true }).click();
  await dialog.getByRole("button", { name: "Choose dates", exact: true }).click();
  const save = dialog.getByRole("button", { name: "Add habit", exact: true });
  await expect(save).toBeDisabled();
  await expect(dialog.getByRole("button", { name: "Oct 3, 2026", exact: true })).toBeDisabled();
  await dialog.getByRole("button", { name: "Oct 8, 2026", exact: true }).click();
  await dialog.getByRole("button", { name: "Oct 15, 2026", exact: true }).click();
  await dialog.getByRole("button", { name: "Oct 8, 2026", exact: true }).click();
  await dialog.getByRole("button", { name: "Next month", exact: true }).click();
  await dialog.getByRole("button", { name: "Nov 2, 2026", exact: true }).click();
  await save.click();
  await expect(page.getByRole("status")).toContainText("2 dates selected");
  await expect(page.getByRole("button", { name: "Recovery session", exact: true })).toHaveCount(0);
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem("vocal-biomarkers.habits.v1")!));
  expect(stored[0].schedule.dates).toEqual(["2026-10-15", "2026-11-02"]);
});

test("Once selects a single date without repeat controls and becomes due on that day", async ({ page }) => {
  const dialog = await openSheet(page, "Book dentist appointment");
  await dialog.getByRole("button", { name: "Once", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "Change end date" })).toHaveCount(0);
  await dialog.getByRole("button", { name: "Oct 8, 2026", exact: true }).click();
  await expect(dialog.getByText("Oct 8, 2026 · Does not repeat", { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Add habit", exact: true }).click();
  await expect(page.getByRole("button", { name: "Book dentist appointment", exact: true })).toHaveCount(0);
  await page.clock.setFixedTime(new Date("2026-10-08T12:00:00-07:00"));
  await page.reload();
  await expect(page.getByRole("button", { name: "Book dentist appointment", exact: true })).toBeVisible();
  await page.clock.setFixedTime(new Date("2026-10-09T12:00:00-07:00"));
  await page.reload();
  await expect(page.getByRole("button", { name: "Book dentist appointment", exact: true })).toHaveCount(0);
});

test("empty name, cancellation and keyboard dismissal leave no saved habit", async ({ page }) => {
  await page.getByRole("button", { name: "Add habit", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Add habit", exact: true });
  await dialog.getByLabel("Habit name", { exact: true }).fill("   ");
  await expect(dialog.getByRole("button", { name: "Add habit", exact: true })).toBeDisabled();
  await expect(page.getByTestId("keyboard-dock")).toHaveAttribute("data-visible", "true");
  await dialog.getByRole("button", { name: "Close Add habit" }).click();
  await expect(page.getByTestId("keyboard-dock")).toHaveAttribute("data-visible", "false");
  expect(await page.evaluate(() => localStorage.getItem("vocal-biomarkers.habits.v1"))).toBeNull();
  await page.getByRole("button", { name: "Add habit", exact: true }).click();
  await expect(dialog.getByLabel("Habit name", { exact: true })).toHaveValue("");
});

test("recurrence crosses DST, respects start/end, and skips nonexistent month days", async ({ page }) => {
  const results = await page.evaluate(async () => {
    // Test the same scheduling function used to populate Today, without provider calls.
    const { isHabitDue } = await import("/src/Prototype.tsx");
    const base = { frequency: "Custom", customMode: "rule", interval: 2, unit: "weeks", weekdays: [2, 4], start: "2026-10-06", end: null, dates: [], once: "2026-10-04" };
    return {
      weeks: ["2026-10-06", "2026-10-08", "2026-10-13", "2026-10-20", "2026-11-03"].map((date) => isHabitDue(base, date)),
      days: ["2026-10-31", "2026-11-01", "2026-11-02"].map((date) => isHabitDue({ ...base, unit: "days", start: "2026-10-31" }, date)),
      months: ["2026-01-31", "2026-02-28", "2026-03-31"].map((date) => isHabitDue({ ...base, interval: 1, unit: "months", start: "2026-01-31" }, date)),
      boundaries: ["2026-10-05", "2026-10-06", "2026-10-08", "2026-10-09"].map((date) => isHabitDue({ ...base, frequency: "Daily", end: "2026-10-08" }, date)),
    };
  });
  expect(results.weeks).toEqual([true, true, false, true, true]);
  expect(results.days).toEqual([true, false, true]);
  expect(results.months).toEqual([true, false, true]);
  expect(results.boundaries).toEqual([false, true, true, false]);
});
