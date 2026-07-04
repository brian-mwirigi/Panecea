"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { config, endpoints } from "@/lib/config";
import type {
  AgentLogLine,
  DashboardStats,
  Device,
  IncidentMemo,
  ThreatPoint,
  ContractB,
} from "@/lib/types";

const MAX_LOG_LINES = 120;
const MAX_MEMOS = 8;
const DEMO_MANUAL = `Philips IntelliVue patient monitor, firmware B.01.
Network requirements: TCP port 3200 is required for HL7 patient data.
All undocumented remote administration services, including SSH port 22 and Telnet port 23, are prohibited.`;

function authHeaders(): HeadersInit {
  const token = typeof window === "undefined" ? null : sessionStorage.getItem("panacea_access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export interface CommandCenterState {
  devices: Device[];
  logs: AgentLogLine[];
  memos: IncidentMemo[];
  threats: ThreatPoint[];
  stats: DashboardStats;
  autonomous: boolean;
  running: boolean;
  setAutonomous: (v: boolean) => void;
  runAgent: () => void;
  overrideDevice: (deviceId: string) => void;
}

/**
 * Central live-data source for the Command Center.
 *
 * In mock mode it drives the simulator. In live mode it consumes the Vultr
 * backend WebSocket and REST control-plane endpoints.
 */
export function useSimulatedStream(): CommandCenterState {
  const [devices, setDevices] = useState<Device[]>([]);
  const [logs, setLogs] = useState<AgentLogLine[]>([]);
  const [memos, setMemos] = useState<IncidentMemo[]>([]);
  const [threats, setThreats] = useState<ThreatPoint[]>([]);
  const [autonomous, setAutonomous] = useState(true);
  const [running, setRunning] = useState(false);
  const runTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pushLogs = useCallback((incoming: AgentLogLine[]) => {
    setLogs((prev) => [...prev, ...incoming].slice(-MAX_LOG_LINES));
  }, []);

  // Seed initial state once on mount (client-side to avoid hydration drift).
  useEffect(() => {
    const initial = setTimeout(() => {
      const seededDevices = seedDevices(6);
      setDevices(seededDevices);
      setMemos(config.useMock ? seedMemos(seededDevices, 3) : []);
      setThreats(seedThreatSeries(24));
      setLogs([
        {
          id: "boot",
          ts: Date.now(),
          level: "system",
          text: config.useMock
            ? "Command Center online :: monitoring hospital network immune system."
            : "Command Center online :: connected to Vultr-native control plane.",
        },
      ]);
    }, 0);
    return () => clearTimeout(initial);
  }, []);

  useEffect(() => {
    if (config.useMock) return;
    const socket = new WebSocket(endpoints.agentStream);
    const keepalive = setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) socket.send("ping");
    }, 15000);
    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as { type?: string; text?: string };
        const text = message.text ?? event.data;
        const level: AgentLogLine["level"] = text.includes("ERROR")
          ? "threat"
          : text.includes("WARN") || text.includes("OVERRIDE")
            ? "warn"
            : text.includes("DONE") || text.includes("SEALED")
              ? "success"
              : message.type === "reasoning"
                ? "info"
                : "system";
        pushLogs([{ id: `live_${Date.now()}_${Math.random()}`, ts: Date.now(), level, text }]);
      } catch {
        pushLogs([{ id: `live_${Date.now()}`, ts: Date.now(), level: "info", text: event.data }]);
      }
    };
    socket.onerror = () => {
      pushLogs([{ id: `ws_error_${Date.now()}`, ts: Date.now(), level: "warn", text: "Vultr backend WebSocket disconnected." }]);
    };
    return () => {
      clearInterval(keepalive);
      socket.close();
    };
  }, [pushLogs]);

  // Stream an ordered agent run trace, one line at a time, then emit a memo.
  const runAgent = useCallback(() => {
    if (running) return;
    if (!config.useMock) {
      setRunning(true);
      const vpcId = config.vpcId;
      void fetch(endpoints.agentRun, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ raw_pdf_text: DEMO_MANUAL, vpc_id: vpcId }),
      })
        .then(async (response) => {
          if (!response.ok) throw new Error(await response.text());
          return response.json() as Promise<ContractB>;
        })
        .then((policy) => {
          setMemos((current) => [{
            ...policy,
            id: `memo_${Date.now()}`,
            device_model: devices[0]?.model ?? "Philips_IntelliVue",
            created_at: Date.now(),
          }, ...current].slice(0, MAX_MEMOS));
          setThreats((current) => [...current.slice(1), nextThreatPoint()]);
        })
        .catch((error: Error) => {
          pushLogs([{ id: `run_error_${Date.now()}`, ts: Date.now(), level: "threat", text: `Agent run failed: ${error.message}` }]);
        })
        .finally(() => setRunning(false));
      return;
    }
    setRunning(true);
    const trace = agentRunTrace();
    trace.forEach((line, i) => {
      setTimeout(() => pushLogs([line]), i * 550);
    });
    runTimer.current = setTimeout(
      () => {
        setDevices((prev) => {
          const target = prev.find((d) => d.status !== "override");
          setMemos((m) => [makeIncidentMemo(target), ...m].slice(0, MAX_MEMOS));
          return prev;
        });
        setThreats((prev) => [...prev.slice(1), nextThreatPoint()]);
        setRunning(false);
      },
      trace.length * 550 + 400,
    );
  }, [devices, pushLogs, running]);

  // Ambient telemetry ticks: device vitals, idle log lines, threat series.
  useEffect(() => {
    if (!config.useMock) return;
    const vitals = setInterval(() => {
      setDevices((prev) => prev.map(tickDevice));
    }, 2500);

    const ambient = setInterval(() => {
      pushLogs([ambientLine()]);
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

  // In autonomous mode, kick off agent runs periodically.
  useEffect(() => {
    if (!config.useMock || !autonomous) return;
    const id = setInterval(() => runAgent(), 16000);
    return () => clearInterval(id);
  }, [autonomous, runAgent]);

  useEffect(() => () => {
    if (runTimer.current) clearTimeout(runTimer.current);
  }, []);

  // Human Override: retract active policy for a device (maps to DELETE /policy/:id).
  const overrideDevice = useCallback(
    (deviceId: string) => {
      const device = devices.find((d) => d.id === deviceId);
      if (!config.useMock && device) {
        void fetch(endpoints.policy(device.vpc_id), {
          method: "DELETE",
          headers: authHeaders(),
        }).then(async (response) => {
          if (!response.ok) throw new Error(await response.text());
        }).catch((error: Error) => {
          pushLogs([{ id: `override_error_${Date.now()}`, ts: Date.now(), level: "threat", text: `Override failed: ${error.message}` }]);
        });
      }
      setDevices((prev) =>
        prev.map((d) =>
          d.id === deviceId
            ? { ...d, status: d.status === "override" ? "secure" : "override" }
            : d,
        ),
      );
      pushLogs([
        {
          id: `override_${deviceId}_${Date.now()}`,
          ts: Date.now(),
          level: "warn",
          text: `Human Override :: operator toggled policy control for ${device?.model ?? deviceId}.`,
        },
      ]);
    },
    [devices, pushLogs],
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
    setAutonomous,
    runAgent,
    overrideDevice,
  };
}
