import express, { type NextFunction, type Request, type Response } from "express";

import {
  CoreResponseError,
  CoreTimeoutError,
  HttpCoreClient,
  type CoreClient,
} from "./core-client.js";
import { EventHub, events } from "./events.js";

const invalid = (response: Response) =>
  response.status(400).json({ error: { code: "INVALID_REQUEST" } });

const text = (value: unknown) =>
  typeof value === "string" && value.trim() ? value.trim() : null;

export function createApp(
  core: CoreClient = new HttpCoreClient(process.env.CORE_URL ?? "http://core:8000"),
  hub: EventHub = events,
) {
  const app = express();
  app.use(express.json({ limit: "32kb" }));

  app.get("/api/health", async (_request, response) => {
    try {
      await core.health();
      response.json({ status: "healthy", dependencies: { core: "healthy" } });
    } catch {
      response.json({ status: "degraded", dependencies: { core: "unavailable" } });
    }
  });

  app.get("/api/events/stream", (_request, response) => {
    response.set({
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "Content-Type": "text/event-stream",
    });
    response.flushHeaders();
    const unsubscribe = hub.subscribe((event) => response.write(`data: ${event}\n\n`));
    response.on("close", unsubscribe);
  });

  app.post("/api/recommend", async (request, response) => {
    const taskDescription = text(request.body?.task_description);
    const topK = request.body?.top_k;
    if (
      !taskDescription ||
      (topK != null && (!Number.isInteger(topK) || topK < 1 || topK > 20))
    ) {
      return invalid(response);
    }
    response.json(await core.recommend(taskDescription, topK));
  });

  app.get("/api/assets/:assetId", async (request, response) => {
    response.json(await core.getAsset(request.params.assetId));
  });

  app.post("/api/assets/:assetId/explain", async (request, response) => {
    const question = request.body?.question;
    if (question != null && !text(question)) return invalid(response);
    response.json(await core.explain(request.params.assetId, question?.trim()));
  });

  app.post("/api/assets/:assetId/use", async (request, response) => {
    const taskDescription = text(request.body?.task_description);
    if (!taskDescription) return invalid(response);
    response.status(201).json(
      await core.useAsset(request.params.assetId, {
        task_description: taskDescription,
        user_id: text(request.body?.user_id),
      }),
    );
  });

  app.use(
    (error: unknown, _request: Request, response: Response, _next: NextFunction) => {
      if (error instanceof CoreResponseError && error.status === 404) {
        return response.status(404).json({ error: { code: "NOT_FOUND" } });
      }
      if (error instanceof CoreTimeoutError || error instanceof CoreResponseError) {
        return response.status(503).json({ error: { code: "CORE_UNAVAILABLE" } });
      }
      return response.status(500).json({ error: { code: "INTERNAL_ERROR" } });
    },
  );

  return app;
}

export const app = createApp();
