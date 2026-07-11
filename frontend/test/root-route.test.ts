import { access } from "node:fs/promises";
import { constants } from "node:fs";
import { describe, expect, it } from "vitest";

describe("frontend runtime", () => {
  it("has an App Router root route", async () => {
    await expect(access("app/page.tsx", constants.R_OK)).resolves.toBeUndefined();
  });
});
