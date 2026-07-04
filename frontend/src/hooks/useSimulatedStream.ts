"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { config, endpoints, SAMPLE_MANUAL_TEXT } from "@/lib/config";
import {
  agentRunTrace,
  ambientLine,
  makeIncidentMemo,
  nextThreatPoint,
  seedDevices,
  seedMemos,
  seedThreatSeries,
  tickDevice,
} from "@/lib/simulator";
import type {
  AgentLogLine,
  ContractB,
  DashboardStats,
  Device,
  FirewallRule,
  IncidentMemo,
  LogLevel,
  ThreatPoint,
} from "@/lib/types";

const MAX_LOG_LINES = 120;
const MAX_MEMOS = 8;

/** How the terminal/memos are currently sourced. */
export type DataMode = "mock" | "live" | "fallback";

export interface CommandCenterState {
  devices: Device[];
  logs: AgentLogLine[];
  memos: IncidentMemo[];
  threats: ThreatPoint[];
  stats: DashboardStats;
  autonomous: boolean;
  running: boolean;
  dataMode: DataMode;
  setAutonomous: (v: boolean) => void;
  runAgent: () => void;
  overrideDevice: (deviceId: string) => void;
}

const lid = () => `log_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;

/** Infer a log severity/colour from the streamed reasoning text. */
function levelFromText(text: string, type?: string): LogLevel {
  const t = text.toLowerCase();
  if (/(deny|block|threat|attack|malicious|breach|lateral)/.test(t)) return "threat";
  if (/(allow|success|confirmed|complete|applied|approved)/.test(t)) return "success";
  if (/(warn|cve|risk|vulnerab|anomal)/.test(t)) return "warn";
  if (type && type !== "reasoning") return "system";
  return "info";
}

/** Map a backend Contract B payload to a UI incident memo. */
function memoFromContractB(data: ContractB, devices: Device[]): IncidentMemo {
  const match = devices.find((d) => d.vpc_id === data.target_vpc_id);
  return {
    ...data,
    id: `memo_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`,
    device_model: match?.model ?? "Philips_IntelliVue",
    created_at: Date.now(),
  };
}

/**
 * Reflect an enforced Contract B policy onto the matching device so the fleet
 * table visibly shows the lockdown (e.g. port 22 DENY / blocked, 3200 ALLOW).
 */
function applyEnforcement(
  devices: Device[],
  vpcId: string,
  rules: FirewallRule[],
): Device[] {
  return devices.map((d) =>
    d.vpc_id === vpcId
      ? { ...d, firewallRules: rules, status: d.status === "override" ? "override" : "secure" }
      : d,
  );
}

/**
 * Central data source for the Command Center.
 *
 * Device vitals, the heartbeat waveform and the threat chart are always
 * simulated (the backend does not provide them). The agent reasoning terminal
 * and incident memos come from the live backend when NEXT_PUBLIC_USE_MOCK is
 * "false", with an automatic fallback to the simulator if the backend is
 * unreachable so the demo never shows a dead screen.
 */
export function useSimulatedStream(): CommandCenterState {
  const [devices, setDevices] = useState<Device[]>([]);
  const [logs, setLogs] = useState<AgentLogLine[]>([]);
  const [memos, setMemos] = useState<IncidentMemo[]>([]);
  const [threats, setThreats] = useState<ThreatPoint[]>([]);
  const [autonomous, setAutonomous] = useState(true);
  const [running, setRunning] = useState(false);
  const [dataMode, setDataMode] = useState<DataMode>(config.useMock ? "mock" : "live");

  const runTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const devicesRef = useRef<Device[]>([]);
  const wsConnectedRef = useRef(false);

  useEffect(() => {
    devicesRef.current = devices;
  }, [devices]);

  // Seed the simulated visual layer once on mount (client-side).
  useEffect(() => {
    const seededDevices = seedDevices(6);
    setDevices(seededDevices);
    setThreats(seedThreatSeries(24));
    if (config.useMock) {
      setMemos(seedMemos(seededDevices, 3));
    }
    setLogs([
      {
        id: "boot",
        ts: Date.now(),
        level: "system",
        text: config.useMock
          ? "Command Center online :: monitoring hospital network immune system (simulated)."
          : "Command Center online :: connecting to live agent backend...",
      },
    ]);
  }, []);

  const pushLogs = useCallback((incoming: AgentLogLine[]) => {
    setLogs((prev) => [...prev, ...incoming].slice(-MAX_LOG_LINES));
  }, []);

  // ---- Mock agent run: stream a scripted trace, then emit a simulated memo.
  const runAgentMock = useCallback(() => {
    setRunning(true);
    const trace = agentRunTrace();
    trace.forEach((line, i) => setTimeout(() => pushLogs([line]), i * 550));
    runTimer.current = setTimeout(
      () => {
        const target = devicesRef.current.find((d) => d.status !== "override");
        const memo = makeIncidentMemo(target);
        setMemos((m) => [memo, ...m].slice(0, MAX_MEMOS));
        setDevices((prev) => applyEnforcement(prev, memo.target_vpc_id, memo.firewall_rules));
        setThreats((prev) => (prev.length ? [...prev.slice(1), nextThreatPoint()] : prev));
        setRunning(false);
      },
      trace.length * 550 + 400,
    );
  }, [pushLogs]);

  // ---- Live agent run: POST to the backend and render the returned Contract B.
  const runAgentLive = useCallback(async () => {
    setRunning(true);
    const vpc = devicesRef.current.find((d) => d.status !== "override")?.vpc_id ?? "vpc-medical-01";
    pushLogs([
      { id: lid(), ts: Date.now(), level: "system", text: `Agent run requested for ${vpc}...` },
    ]);
    try {
      const res = await fetch(endpoints.agentRun, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ raw_pdf_text: SAMPLE_MANUAL_TEXT, vpc_id: vpc }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as ContractB;
      const memo = memoFromContractB(data, devicesRef.current);
      setMemos((m) => [memo, ...m].slice(0, MAX_MEMOS));
      setDevices((prev) => applyEnforcement(prev, data.target_vpc_id, data.firewall_rules));
      pushLogs([
        {
          id: lid(),
          ts: Date.now(),
          level: "success",
          text: `Contract B received :: confidence ${data.confidence_score}% for ${data.target_vpc_id}.`,
        },
      ]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "unknown error";
      pushLogs([
        {
          id: lid(),
          ts: Date.now(),
          level: "warn",
          text: `Agent run failed (${msg}) :: showing simulated decision.`,
        },
      ]);
      const target = devicesRef.current.find((d) => d.status !== "override");
      const memo = makeIncidentMemo(target);
      setMemos((m) => [memo, ...m].slice(0, MAX_MEMOS));
      setDevices((prev) => applyEnforcement(prev, memo.target_vpc_id, memo.firewall_rules));
    } finally {
      setThreats((prev) => (prev.length ? [...prev.slice(1), nextThreatPoint()] : prev));
      setRunning(false);
    }
  }, [pushLogs]);

  const runAgent = useCallback(() => {
    if (running) return;
    if (config.useMock) runAgentMock();
    else runAgentLive();
  }, [running, runAgentMock, runAgentLive]);

  // ---- Live WebSocket: stream agent reasoning tokens into the terminal.
  useEffect(() => {
    if (config.useMock) return;

    let closed = false;
    let attempts = 0;
    let ws: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      try {
        ws = new WebSocket(endpoints.agentStream);
      } catch {
        setDataMode("fallback");
        return;
      }

      ws.onopen = () => {
        attempts = 0;
        wsConnectedRef.current = true;
        setDataMode("live");
        pushLogs([
          { id: lid(), ts: Date.now(), level: "system", text: "Live agent stream connected." },
        ]);
      };

      ws.onmessage = (ev) => {
        let text = "";
        let type: string | undefined;
        try {
          const msg = JSON.parse(ev.data);
          text = msg.text ?? msg.message ?? "";
          type = msg.type;
        } catch {
          text = typeof ev.data === "string" ? ev.data : "";
        }
        if (!text) return;
        // Backend emits {type:"reasoning"} for the model's thinking (rendered
        // dim) and {type:"content"} for its decisions/actions (bright, with
        // semantic colour from the text).
        const isReasoning = type === "reasoning";
        pushLogs([
          {
            id: lid(),
            ts: Date.now(),
            level: isReasoning ? "info" : levelFromText(text, type),
            dim: isReasoning,
            text,
          },
        ]);
      };

      ws.onerror = () => {
        wsConnectedRef.current = false;
      };

      ws.onclose = () => {
        wsConnectedRef.current = false;
        if (closed) return;
        if (attempts < 3) {
          attempts += 1;
          retry = setTimeout(connect, 2000 * attempts);
        } else {
          setDataMode("fallback");
          pushLogs([
            {
              id: lid(),
              ts: Date.now(),
              level: "warn",
              text: "Live stream unavailable :: falling back to simulated telemetry.",
            },
          ]);
        }
      };
    };

    connect();

    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      ws?.close();
    };
  }, [pushLogs]);

  // ---- Ambient telemetry: vitals + threat chart are always simulated. Idle
  // log lines run in mock mode, or in live mode while the stream is down.
  useEffect(() => {
    const vitals = setInterval(() => {
      setDevices((prev) => prev.map(tickDevice));
    }, 2500);

    const ambient = setInterval(() => {
      if (config.useMock || !wsConnectedRef.current) pushLogs([ambientLine()]);
    }, 3800);

    const series = setInterval(() => {
      setThreats((prev) => (prev.length ? [...prev.slice(1), nextThreatPoint()] : prev));
    }, 12000);

    return () => {
      clearInterval(vitals);
      clearInterval(ambient);
      clearInterval(series);
    };
  }, [pushLogs]);

  // In autonomous mode, kick off agent runs periodically (gentler when live).
  useEffect(() => {
    if (!autonomous) return;
    const id = setInterval(() => runAgent(), config.useMock ? 16000 : 30000);
    return () => clearInterval(id);
  }, [autonomous, runAgent]);

  useEffect(
    () => () => {
      if (runTimer.current) clearTimeout(runTimer.current);
    },
    [],
  );

  // Human Override: retract the active policy for a device
  // (maps to DELETE /api/v1/policy/{device_id}).
  const overrideDevice = useCallback(
    async (deviceId: string) => {
      const device = devicesRef.current.find((d) => d.id === deviceId);
      const willOverride = device?.status !== "override";

      // Optimistic UI: toggle status, clear enforced rules when releasing.
      setDevices((prev) =>
        prev.map((d) =>
          d.id === deviceId
            ? {
                ...d,
                status: willOverride ? "override" : "secure",
                firewallRules: willOverride ? d.firewallRules : undefined,
              }
            : d,
        ),
      );

      pushLogs([
        {
          id: lid(),
          ts: Date.now(),
          level: "warn",
          text: `Human Override :: operator ${willOverride ? "retracting policy for" : "restoring"} ${device?.model ?? deviceId}.`,
        },
      ]);

      // Only the "retract" direction hits the backend. On success the backend
      // broadcasts a [HUMAN OVERRIDE] content message over the WebSocket, which
      // shows up in the terminal automatically.
      if (config.useMock || !willOverride) return;

      try {
        const res = await fetch(endpoints.policy(deviceId), { method: "DELETE" });
        if (res.status === 404) {
          pushLogs([
            {
              id: lid(),
              ts: Date.now(),
              level: "warn",
              text: `Override :: backend reports no active policy for '${deviceId}'.`,
            },
          ]);
        } else if (!res.ok) {
          pushLogs([
            {
              id: lid(),
              ts: Date.now(),
              level: "warn",
              text: `Override :: backend returned HTTP ${res.status}.`,
            },
          ]);
        }
      } catch {
        pushLogs([
          {
            id: lid(),
            ts: Date.now(),
            level: "warn",
            text: "Override :: backend unreachable, applied locally only.",
          },
        ]);
      }
    },
    [pushLogs],
  );

  const stats = useMemo<DashboardStats>(() => {
    const activeRules = memos.reduce((sum, m) => sum + m.firewall_rules.length, 0);
    const threatsBlocked = threats.reduce((sum, p) => sum + p.blocked, 0);
    const avgConfidence = memos.length
      ? Math.round(memos.reduce((s, m) => s + m.confidence_score, 0) / memos.length)
      : 0;
    const portsMonitored = new Set(devices.flatMap((d) => d.ports)).size;
    return {
      devicesProtected: devices.filter((d) => d.status !== "quarantined").length,
      activeRules,
      threatsBlocked,
      avgConfidence,
      portsMonitored,
    };
  }, [devices, memos, threats]);

  return {
    devices,
    logs,
    memos,
    threats,
    stats,
    autonomous,
    running,
    dataMode,
    setAutonomous,
    runAgent,
    overrideDevice,
  };
}
