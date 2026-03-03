import { Settings, ChevronRight } from "lucide-react";
import { getConfig } from "../lib/api";
import { useFetch } from "../lib/utils";

export default function ConfigPage() {
  const { data: config, loading, error } = useFetch(getConfig);

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-8 flex items-center gap-3">
        <Settings className="h-8 w-8 text-hive-400" strokeWidth={2} />
        <div>
          <h1 className="text-xl font-bold">Configuration</h1>
          <p className="text-sm text-surface-400">
            Current HiveCore settings (read-only)
          </p>
        </div>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="card h-16 animate-pulse" />
          ))}
        </div>
      ) : error ? (
        <div className="card text-center">
          <p className="text-sm text-red-400">
            Failed to load config: {error}
          </p>
        </div>
      ) : config ? (
        <div className="space-y-4">
          {Object.entries(config).map(([section, value]) => (
            <ConfigSection key={section} name={section} value={value} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ConfigSection({
  name,
  value,
}: {
  name: string;
  value: unknown;
}) {
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    return (
      <div className="card">
        <div className="mb-3 flex items-center gap-2">
          <ChevronRight className="h-4 w-4 text-hive-400" />
          <h3 className="text-sm font-semibold capitalize">{name}</h3>
        </div>
        <div className="space-y-1.5">
          {Object.entries(value as Record<string, unknown>).map(
            ([key, val]) => (
              <ConfigRow key={key} label={key} value={val} />
            )
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <ConfigRow label={name} value={value} />
    </div>
  );
}

function ConfigRow({ label, value }: { label: string; value: unknown }) {
  const displayValue = (() => {
    if (value === null || value === undefined) return "null";
    if (typeof value === "boolean") return value ? "true" : "false";
    if (typeof value === "object") return JSON.stringify(value, null, 2);
    return String(value);
  })();

  const isRedacted =
    typeof value === "string" && value.includes("***");

  return (
    <div className="flex items-start justify-between gap-4 rounded-md bg-surface-950 px-3 py-2">
      <span className="text-xs font-medium text-surface-300">{label}</span>
      <code
        className={`text-right text-xs ${
          isRedacted ? "text-surface-600 italic" : "text-hive-300"
        }`}
      >
        {displayValue}
      </code>
    </div>
  );
}
