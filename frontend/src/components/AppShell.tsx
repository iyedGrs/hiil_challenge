import { Outlet } from "react-router-dom";
import { dataMode } from "../api";
import { AppHeader } from "./AppHeader";
import { FixtureBanner } from "./FixtureBanner";

export function AppShell() {
  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      {dataMode === "fixture" && <FixtureBanner />}
      <AppHeader />
      <main className="flex-1">
        <Outlet />
      </main>
    </div>
  );
}
