import { useCallback, useMemo, useState } from "react";

import { Globe } from "./components/globe/Globe";
import type { FocusRequest } from "./components/globe/Globe.types";
import { Sidebar } from "./components/sidebar/Sidebar";
import { useAircraftStore } from "./hooks/useAircraftStore";
import { useWebSocket } from "./hooks/useWebSocket";

function App() {
  const { aircraft, dispatchWsMessage } = useAircraftStore();
  const [focusRequest, setFocusRequest] = useState<FocusRequest | null>(null);
  const wsUrl = useMemo(() => {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    return `${protocol}://${window.location.host}/ws/tracks`;
  }, []);
  const { status } = useWebSocket(wsUrl, dispatchWsMessage);

  const handleFocusAircraft = useCallback((icao: string) => {
    setFocusRequest((prev) => ({
      icao: icao.toUpperCase(),
      requestId: (prev?.requestId ?? 0) + 1,
    }));
  }, []);

  return (
    <div className="flex h-screen w-screen bg-gray-950 text-white overflow-hidden">
      <Sidebar aircraft={aircraft} wsStatus={status} onFocusAircraft={handleFocusAircraft} />
      <main className="flex-1">
        <Globe aircraft={aircraft} focusRequest={focusRequest} />
      </main>
    </div>
  );
}

export default App;
