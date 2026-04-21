import type { FixMethod } from "../../types/aircraft";

interface MethodBadgeProps {
  method: FixMethod;
}

const METHOD_CLASSES: Record<FixMethod, string> = {
  CPR: "bg-lime-900 text-lime-300 border border-lime-700",
  MLAT: "bg-cyan-900 text-cyan-300 border border-cyan-700",
  PREDICTED: "bg-gray-800 text-gray-400 border border-gray-600",
};

export function MethodBadge({ method }: MethodBadgeProps) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs uppercase ${METHOD_CLASSES[method]}`}
    >
      {method}
    </span>
  );
}
