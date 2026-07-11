import request from "supertest";
import { describe, expect, it } from "vitest";

import { createApp } from "../src/app.js";
import { CoreTimeoutError, type CoreClient } from "../src/core-client.js";

function fakeCore(overrides: Partial<CoreClient> = {}): CoreClient {
  return {
    health: async () => ({ status: "ok" }),
    recommend: async () => ({ results: [] }),
    getAsset: async (id) => ({ id }),
    explain: async () => ({ explanation: "", cited_versions: [], cited_constraints: [] }),
    useAsset: async () => ({ recorded: true, content: "prompt" }),
    ...overrides,
  };
}

describe("API gateway", () => {
  it("reports healthy core", async () => {
    const response = await request(createApp(fakeCore())).get("/api/health");

    expect(response.status).toBe(200);
    expect(response.body).toEqual({
      status: "healthy",
      dependencies: { core: "healthy" },
    });
  });

  it("keeps the shell available when core health is degraded", async () => {
    const response = await request(
      createApp(fakeCore({ health: async () => { throw new Error("secret"); } })),
    ).get("/api/health");

    expect(response.status).toBe(200);
    expect(response.body).toEqual({
      status: "degraded",
      dependencies: { core: "unavailable" },
    });
  });

  it("maps a core timeout to a safe 503 response", async () => {
    const app = createApp(
      fakeCore({ recommend: async () => { throw new CoreTimeoutError(); } }),
    );

    const response = await request(app)
      .post("/api/recommend")
      .send({ task_description: "Build lead routing for inbound sales" });

    expect(response.status).toBe(503);
    expect(response.body).toEqual({ error: { code: "CORE_UNAVAILABLE" } });
  });

  it("rejects invalid recommendation input before calling core", async () => {
    const response = await request(createApp(fakeCore()))
      .post("/api/recommend")
      .send({ task_description: "  " });

    expect(response.status).toBe(400);
    expect(response.body).toEqual({ error: { code: "INVALID_REQUEST" } });
  });

  it("rejects an out-of-range recommendation count", async () => {
    const response = await request(createApp(fakeCore()))
      .post("/api/recommend")
      .send({
        task_description: "Build lead routing for inbound sales",
        top_k: 21,
      });

    expect(response.status).toBe(400);
    expect(response.body).toEqual({ error: { code: "INVALID_REQUEST" } });
  });

  it("proxies asset review, explanation, and explicit use", async () => {
    const core = fakeCore({
      getAsset: async (id) => ({ id, title: "Lead prompt" }),
      explain: async (id, question) => ({ id, question }),
      useAsset: async (id, body) => ({ id, ...body, recorded: true }),
    });
    const app = createApp(core);

    expect((await request(app).get("/api/assets/a1")).body.title).toBe("Lead prompt");
    expect(
      (await request(app).post("/api/assets/a1/explain").send({ question: "Why?" })).body,
    ).toMatchObject({ id: "a1", question: "Why?" });
    expect(
      (
        await request(app)
          .post("/api/assets/a1/use")
          .send({ task_description: "Qualify inbound leads" })
      ).body.recorded,
    ).toBe(true);
  });
});
