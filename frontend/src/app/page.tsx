"use client";

import { useSimulatedStream } from "@/hooks/useSimulatedStream";
import { Header } from "@/components/dashboard/Header";
import { StatsRow } from "@/components/dashboard/StatCard";
import { HeartbeatMonitor } from "@/components/dashboard/HeartbeatMonitor";
import { ThreatChart } from "@/components/dashboard/ThreatChart";
import { AgentTerminal } from "@/components/dashboard/AgentTerminal";
import { IncidentMemo } from "@/components/dashboard/IncidentMemo";
import { HumanOverride } from "@/components/dashboard/HumanOverride";
import { DeviceTable } from "@/components/dashboard/DeviceTable";

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

  return (
    <main className="mx-auto flex min-h-screen max-w-[1600px] flex-col gap-4 p-4 sm:p-6">
      <Header autonomous={autonomous} running={running} dataMode={dataMode} />

      <StatsRow stats={stats} />

      {/* Row 1 — vitals + live activity analytics */}
      <section className="grid gap-4 lg:grid-cols-2">
        <HeartbeatMonitor devices={devices} />
        <ThreatChart data={threats} />
      </section>

      {/* Row 2 — agent reasoning terminal + incident memos */}
      <section className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <div className="min-h-[24rem]">
          <AgentTerminal logs={logs} running={running} onRun={runAgent} />
        </div>
        <div className="min-h-[24rem]">
          <IncidentMemo memos={memos} />
        </div>
      </section>

      {/* Row 3 — operator control + fleet */}
      <section className="grid gap-4 lg:grid-cols-[1fr_1.8fr]">
        <HumanOverride autonomous={autonomous} onToggle={setAutonomous} />
        <DeviceTable devices={devices} onOverride={overrideDevice} />
      </section>

      <footer className="pb-2 pt-1 text-center text-[11px] text-white/25">
        Panacea v2 · Command Center · {dataMode === "live" ? "live Vultr control plane" : "device-twin simulation"}
      </footer>
    </main>
  );
}
