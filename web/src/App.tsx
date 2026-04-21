import { useMemo } from "react";

import { Globe } from "./components/globe/Globe";
import { Sidebar } from "./components/sidebar/Sidebar";
import { useAircraftStore } from "./hooks/useAircraftStore";
import { useWebSocket } from "./hooks/useWebSocket";

function App() {
  const { aircraft, dispatchWsMessage } = useAircraftStore();
  const wsUrl = useMemo(() => {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    return `${protocol}://${window.location.host}/ws/tracks`;
  }, []);
  const { status } = useWebSocket(wsUrl, dispatchWsMessage);

  return (
    <div className="flex h-screen w-screen bg-gray-950 text-white overflow-hidden">
      <Sidebar aircraft={aircraft} wsStatus={status} />
      <main className="flex-1">
        <Globe aircraft={aircraft} />
      </main>
    </div>
  );
}

export default App;
