// Runtime configuration for the Command Center.
//
// The dashboard runs in "mock" mode by default so it works with no backend
// (great for Vercel previews). When NEXT_PUBLIC_USE_MOCK is "false", the data
// hook talks to the real FastAPI backend:
//   - REST (agent run + policy override) is proxied through Next.js rewrites
//     (see next.config.ts) so an HTTPS Vercel page can reach an http:// backend
//     without mixed-content / CORS problems.
//   - The WebSocket connects directly to NEXT_PUBLIC_WS_URL (cannot be proxied
//     on Vercel), so for the deployed HTTPS site it must be a wss:// URL.

export const config = {
  /** When true, all data is generated locally by the simulator. */
  useMock: process.env.NEXT_PUBLIC_USE_MOCK !== "false",

  /** REST base for the FastAPI backend (used by the server-side rewrite). */
  apiUrl: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",

  /** WebSocket endpoint that streams live agent reasoning tokens. */
  wsUrl:
    process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws/agent-stream",
} as const;

/**
 * Backend routes.
 *
 * REST calls go through the same-origin `/backend/*` proxy (rewritten to
 * `config.apiUrl/*` server-side). The WebSocket is a direct connection.
 */
export const endpoints = {
  agentRun: "/backend/api/v1/agent/run",
  policy: (deviceId: string) => `/backend/api/v1/policy/${deviceId}`,
  agentStream: config.wsUrl,
} as const;

/**
 * Sample device-manual text sent as `raw_pdf_text` when triggering an agent
 * run from the UI (until a real uploaded PDF is wired in). Mirrors the Philips
 * IntelliVue example from the project README.
 */
export const SAMPLE_MANUAL_TEXT = [
  "Philips IntelliVue Patient Monitor — Network Configuration Guide (Firmware B.01).",
  "The monitor transmits HL7 patient data over TCP port 3200 to the central station.",
  "Port 2050 is used for device discovery. All remote administration (SSH, port 22)",
  "must remain disabled in clinical deployments to prevent lateral movement.",
].join(" ");
