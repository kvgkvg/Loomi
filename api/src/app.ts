import express from "express";

export const app = express();

app.get("/api/health", (_request, response) => {
  response.json({ status: "healthy" });
});
