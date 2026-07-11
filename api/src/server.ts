import { app } from "./app.js";
import { connectCoreEvents, events } from "./events.js";

const port = Number(process.env.PORT ?? 3001);
const abort = new AbortController();

void connectCoreEvents(
  process.env.CORE_URL ?? "http://core:8000",
  events,
  abort.signal,
);

process.on("SIGTERM", () => abort.abort());

app.listen(port, () => {
  console.log(`Loomi API listening on ${port}`);
});
