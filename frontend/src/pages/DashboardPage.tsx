import {
  Activity,
  Brain,
  Cpu,
  Database,
  Blocks,
  Hexagon,
} from "lucide-react";
import { getStatus, getMemoryStats, getSkills } from "../lib/api";
import { useFetch } from "../lib/utils";

export default function DashboardPage() {
  const { data: status, loading: statusLoading } = useFetch(getStatus);
  const { data: memStats, loading: memLoading } = useFetch(getMemoryStats);
  const { data: skills, loading: skillsLoading } = useFetch(getSkills);

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-8 flex items-center gap-3">
        <Hexagon className="h-8 w-8 text-hive-400" strokeWidth={2} />
        <div>
          <h1 className="text-xl font-bold">Dashboard</h1>
          <p className="text-sm text-surface-400">
            HiveCore system overview
          </p>
        </div>
      </div>

      {/* Status Cards */}
      <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatusCard
          icon={<Activity className="h-5 w-5 text-emerald-400" />}
          label="Status"
          value={status?.status ?? "..."}
          loading={statusLoading}
          valueColor={
            status?.status === "running" ? "text-emerald-400" : "text-red-400"
          }
        />
        <StatusCard
          icon={<Cpu className="h-5 w-5 text-blue-400" />}
          label="LLM Provider"
          value={
            status
              ? `${status.provider} / ${status.model}`
              : "..."
          }
          loading={statusLoading}
        />
        <StatusCard
          icon={<Database className="h-5 w-5 text-purple-400" />}
          label="Memory Backend"
          value={status?.memory_backend ?? "..."}
          loading={statusLoading}
        />
        <StatusCard
          icon={<Blocks className="h-5 w-5 text-hive-400" />}
          label="Skills Loaded"
          value={skills ? `${skills.length}` : "..."}
          loading={skillsLoading}
        />
      </div>

      {/* Memory Overview */}
      <div className="mb-8">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-surface-400">
          Memory
        </h2>
        {memLoading ? (
          <div className="card animate-pulse h-32" />
        ) : memStats ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MemoryStatCard
              label="Short-term"
              count={memStats.short_term_count}
              icon={<Brain className="h-4 w-4 text-hive-300" />}
            />
            <MemoryStatCard
              label="Long-term"
              count={memStats.long_term_count}
              icon={<Database className="h-4 w-4 text-blue-300" />}
            />
            <MemoryStatCard
              label="File Memory"
              count={memStats.file_memory_count}
              icon={<Database className="h-4 w-4 text-purple-300" />}
            />
            <MemoryStatCard
              label="Vector Memory"
              count={memStats.vector_memory_count}
              icon={<Database className="h-4 w-4 text-emerald-300" />}
            />
          </div>
        ) : (
          <p className="text-sm text-surface-500">
            Unable to load memory stats.
          </p>
        )}
      </div>

      {/* Skills List */}
      <div>
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-surface-400">
          Loaded Skills
        </h2>
        {skillsLoading ? (
          <div className="card animate-pulse h-24" />
        ) : skills && skills.length > 0 ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {skills.map((skill) => (
              <div key={skill.name} className="card flex items-start gap-3">
                <Blocks className="mt-0.5 h-4 w-4 text-hive-400" />
                <div>
                  <p className="text-sm font-medium">{skill.name}</p>
                  <p className="text-xs text-surface-400">
                    {skill.description}
                  </p>
                  <span className="badge-hive mt-1">{skill.category}</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-surface-500">No skills loaded.</p>
        )}
      </div>
    </div>
  );
}

function StatusCard({
  icon,
  label,
  value,
  loading,
  valueColor,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  loading: boolean;
  valueColor?: string;
}) {
  return (
    <div className="card">
      <div className="mb-2 flex items-center gap-2 text-surface-400">
        {icon}
        <span className="text-xs font-medium uppercase tracking-wider">
          {label}
        </span>
      </div>
      {loading ? (
        <div className="h-6 w-32 animate-pulse rounded bg-surface-800" />
      ) : (
        <p className={`text-sm font-semibold ${valueColor ?? "text-surface-100"}`}>
          {value}
        </p>
      )}
    </div>
  );
}

function MemoryStatCard({
  label,
  count,
  icon,
}: {
  label: string;
  count: number;
  icon: React.ReactNode;
}) {
  return (
    <div className="card flex items-center gap-3">
      {icon}
      <div>
        <p className="text-lg font-bold">{count.toLocaleString()}</p>
        <p className="text-xs text-surface-400">{label}</p>
      </div>
    </div>
  );
}
