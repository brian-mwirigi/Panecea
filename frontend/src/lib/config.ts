// Runtime configuration for the Command Center.
//
// The dashboard ships in "mock" mode so it can run standalone (and on Vercel
// previews) without a backend. When the real FastAPI service is ready, flip
// NEXT_PUBLIC_USE_MOCK to "false" and point the URLs at the backend — the data
// hooks are the only place that needs to branch on this.

export const config = {
  /** When true, all data is generated locally by the simulator. */
  useMock: process.env.NEXT_PUBLIC_USE_MOCK !== "false",

  /** REST base for the FastAPI backend (agent run + policy override). */
  apiUrl: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",

  /** WebSocket endpoint that streams live agent reasoning tokens. */
  wsUrl: process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws/agent-stream",
} as const;

/** Backend routes, kept here so the swap-in later is a one-line change. */
export const endpoints = {
  agentRun: `${config.apiUrl}/api/v1/agent/run`,
  policy: (deviceId: string) => `${config.apiUrl}/api/v1/policy/${deviceId}`,
  agentStream: config.wsUrl,
} as const;
