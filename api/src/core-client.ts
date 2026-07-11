export class CoreTimeoutError extends Error {}

export class CoreResponseError extends Error {
  constructor(readonly status: number) {
    super("core request failed");
  }
}

export interface CoreClient {
  health(): Promise<unknown>;
  recommend(taskDescription: string, topK?: number): Promise<unknown>;
  getAsset(assetId: string): Promise<any>;
  explain(assetId: string, question?: string): Promise<any>;
  useAsset(assetId: string, body: Record<string, unknown>): Promise<any>;
}

export class HttpCoreClient implements CoreClient {
  constructor(
    readonly baseUrl: string,
    private readonly timeoutMs = 5000,
  ) {}

  private async request(path: string, init?: RequestInit) {
    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        ...init,
        headers: { "Content-Type": "application/json", ...init?.headers },
        signal: AbortSignal.timeout(this.timeoutMs),
      });
      if (!response.ok) throw new CoreResponseError(response.status);
      return await response.json();
    } catch (error) {
      if (error instanceof CoreResponseError) throw error;
      if (error instanceof Error && ["AbortError", "TimeoutError"].includes(error.name)) {
        throw new CoreTimeoutError();
      }
      throw new CoreResponseError(503);
    }
  }

  health() {
    return this.request("/health");
  }

  recommend(taskDescription: string, topK?: number) {
    return this.request("/recommend", {
      method: "POST",
      body: JSON.stringify({ task_description: taskDescription, top_k: topK }),
    });
  }

  getAsset(assetId: string) {
    return this.request(`/assets/${encodeURIComponent(assetId)}`);
  }

  explain(assetId: string, question?: string) {
    return this.request(`/assets/${encodeURIComponent(assetId)}/explain`, {
      method: "POST",
      body: JSON.stringify({ question }),
    });
  }

  useAsset(assetId: string, body: Record<string, unknown>) {
    return this.request(`/assets/${encodeURIComponent(assetId)}/use`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }
}
