import { describe, expect, it } from "vitest";

import { EventHub } from "../src/events.js";

describe("EventHub", () => {
  it("fans one core lifecycle event out to every browser subscriber", () => {
    const hub = new EventHub();
    const first: string[] = [];
    const second: string[] = [];
    const stopFirst = hub.subscribe((event) => first.push(event));
    hub.subscribe((event) => second.push(event));

    hub.publish("{\"type\":\"memory_ready\"}");
    stopFirst();
    hub.publish("{\"type\":\"capture_started\"}");

    expect(first).toEqual(["{\"type\":\"memory_ready\"}"]);
    expect(second).toEqual([
      "{\"type\":\"memory_ready\"}",
      "{\"type\":\"capture_started\"}",
    ]);
  });
});
