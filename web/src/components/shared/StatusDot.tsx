interface StatusDotProps {
  status: "connecting" | "connected" | "disconnected";
}

const STATUS_STYLE: Record<StatusDotProps["status"], { dot: string; label: string }> = {
  connected: { dot: "bg-green-500", label: "Live" },
  connecting: { dot: "bg-amber-400 animate-pulse", label: "Connecting" },
  disconnected: { dot: "bg-red-500", label: "Offline" },
};

export function StatusDot({ status }: StatusDotProps) {
  const style = STATUS_STYLE[status];

  return (
    <div className="flex items-center gap-2">
      <span className={`h-2.5 w-2.5 rounded-full ${style.dot}`} />
      <span className="text-sm text-gray-200">{style.label}</span>
    </div>
  );
}
