type Listener = (event: string) => void;

export class EventHub {
  private readonly listeners = new Set<Listener>();

  subscribe(listener: Listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  publish(event: string) {
    for (const listener of this.listeners) listener(event);
  }
}

export const events = new EventHub();

const delay = (milliseconds: number) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

export async function connectCoreEvents(
  coreUrl: string,
  hub: EventHub,
  signal: AbortSignal,
) {
  while (!signal.aborted) {
    try {
      const response = await fetch(`${coreUrl}/internal/events`, { signal });
      if (!response.ok || !response.body) throw new Error("event stream unavailable");
      const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
      let buffer = "";
      while (!signal.aborted) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += value;
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (line.startsWith("data: ")) hub.publish(line.slice(6));
        }
      }
    } catch (error) {
      if (signal.aborted) return;
    }
    await delay(1000);
  }
}
