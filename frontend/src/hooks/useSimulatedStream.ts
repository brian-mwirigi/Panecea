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
import type {
  AgentLogLine,
  DashboardStats,
  Device,
  IncidentMemo,
  ThreatPoint,
} from "@/lib/types";

const MAX_LOG_LINES = 120;
const MAX_MEMOS = 8;

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
 * In mock mode it drives everything from the simulator on timers. To go live,
 * replace the effects below with a WebSocket subscription (config.wsUrl) for
 * logs/memos and a REST call (endpoints.agentRun) inside `runAgent`.
 */
export function useSimulatedStream(): CommandCenterState {
  const [devices, setDevices] = useState<Device[]>([]);
  const [logs, setLogs] = useState<AgentLogLine[]>([]);
  const [memos, setMemos] = useState<IncidentMemo[]>([]);
  const [threats, setThreats] = useState<ThreatPoint[]>([]);
  const [autonomous, setAutonomous] = useState(true);
  const [running, setRunning] = useState(false);
  const runTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Seed initial state once on mount (client-side to avoid hydration drift).
  useEffect(() => {
    const seededDevices = seedDevices(6);
    setDevices(seededDevices);
    setMemos(seedMemos(seededDevices, 3));
    setThreats(seedThreatSeries(24));
    setLogs([
      {
        id: "boot",
        ts: Date.now(),
        level: "system",
        text: "Command Center online :: monitoring hospital network immune system.",
      },
    ]);
  }, []);

  const pushLogs = useCallback((incoming: AgentLogLine[]) => {
    setLogs((prev) => [...prev, ...incoming].slice(-MAX_LOG_LINES));
  }, []);

  // Stream an ordered agent run trace, one line at a time, then emit a memo.
  const runAgent = useCallback(() => {
    if (running) return;
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
  }, [pushLogs, running]);

  // Ambient telemetry ticks: device vitals, idle log lines, threat series.
  useEffect(() => {
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
    if (!autonomous) return;
    const id = setInterval(() => runAgent(), 16000);
    return () => clearInterval(id);
  }, [autonomous, runAgent]);

  useEffect(() => () => {
    if (runTimer.current) clearTimeout(runTimer.current);
  }, []);

  // Human Override: retract active policy for a device (maps to DELETE /policy/:id).
  const overrideDevice = useCallback(
    (deviceId: string) => {
      setDevices((prev) =>
        prev.map((d) =>
          d.id === deviceId
            ? { ...d, status: d.status === "override" ? "secure" : "override" }
            : d,
        ),
      );
      const device = devices.find((d) => d.id === deviceId);
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
