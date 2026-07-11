import request from "supertest";
import { describe, expect, it } from "vitest";

import { app } from "../src/app.js";

describe("API runtime", () => {
  it("returns an API health envelope", async () => {
    const response = await request(app).get("/api/health");

    expect(response.status).toBe(200);
    expect(response.body).toMatchObject({ status: "healthy" });
  });
});
