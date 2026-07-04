"use client";

import { useState } from "react";
import { LayoutDashboard, TerminalSquare, Cpu } from "lucide-react";
import { useSimulatedStream } from "@/hooks/useSimulatedStream";
import { Header } from "@/components/dashboard/Header";
import { TabNav, type TabDef } from "@/components/dashboard/TabNav";
import { StatsRow } from "@/components/dashboard/StatCard";
import { HeartbeatMonitor } from "@/components/dashboard/HeartbeatMonitor";
import { ThreatChart } from "@/components/dashboard/ThreatChart";
import { AgentTerminal } from "@/components/dashboard/AgentTerminal";
import { IncidentMemo } from "@/components/dashboard/IncidentMemo";
import { HumanOverride } from "@/components/dashboard/HumanOverride";
import { DeviceTable } from "@/components/dashboard/DeviceTable";

const TABS: TabDef[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "agent", label: "Live Agent", icon: TerminalSquare },
  { id: "fleet", label: "Devices", icon: Cpu },
];

export default function CommandCenter() {
  const {
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
  } = useSimulatedStream();

  const [tab, setTab] = useState("overview");

  return (
    <main className="mx-auto flex min-h-screen max-w-[1400px] flex-col gap-5 p-4 sm:p-6">
      <Header autonomous={autonomous} running={running} dataMode={dataMode} />

      <TabNav tabs={TABS} active={tab} onChange={setTab} />

      {tab === "overview" && (
        <div className="flex flex-col gap-5">
          <StatsRow stats={stats} />
          <section className="grid gap-5 lg:grid-cols-2">
            <HeartbeatMonitor devices={devices} />
            <ThreatChart data={threats} />
          </section>
        </div>
      )}

      {tab === "agent" && (
        <section className="grid h-[calc(100vh-15rem)] min-h-[460px] gap-5 lg:grid-cols-[1.35fr_1fr]">
          <AgentTerminal logs={logs} running={running} onRun={runAgent} />
          <IncidentMemo memos={memos} />
        </section>
      )}

      {tab === "fleet" && (
        <div className="flex flex-col gap-5">
          <HumanOverride autonomous={autonomous} onToggle={setAutonomous} />
          <DeviceTable devices={devices} onOverride={overrideDevice} />
        </div>
      )}

      <footer className="mt-auto pt-2 text-center text-[11px] text-white/25">
        Panacea v2 · Command Center · live agent reasoning &amp; incident memos
        when the backend is connected; device vitals are simulated
      </footer>
    </main>
  );
}
