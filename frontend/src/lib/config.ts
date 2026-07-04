// Runtime configuration for the Command Center.
//
// The dashboard supports a simulator for local UI work and a live Vultr mode.
// Production images set NEXT_PUBLIC_USE_MOCK=false at build time.

export const config = {
  /** When true, all data is generated locally by the simulator. */
  useMock: process.env.NEXT_PUBLIC_USE_MOCK !== "false",

  /** REST base for the FastAPI backend (agent run + policy override). */
  apiUrl: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",

  /** WebSocket endpoint that streams live agent reasoning tokens. */
  wsUrl: process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws/agent-stream",

  /** Real Vultr VPC targeted by the demo agent. */
  vpcId: process.env.NEXT_PUBLIC_VPC_ID ?? "vpc-medical-01",
} as const;

/** Backend routes, kept here so the swap-in later is a one-line change. */
export const endpoints = {
  agentRun: `${config.apiUrl}/api/v1/agent/run`,
  policy: (deviceId: string) => `${config.apiUrl}/api/v1/policy/${deviceId}`,
  agentStream: config.wsUrl,
} as const;
