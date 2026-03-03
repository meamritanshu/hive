import { Blocks, ChevronDown, ChevronRight } from "lucide-react";
import { getSkills } from "../lib/api";
import { useFetch, cn } from "../lib/utils";
import { useState } from "react";
import type { SkillInfo } from "../types";

export default function SkillsPage() {
  const { data: skills, loading, error } = useFetch(getSkills);

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-8 flex items-center gap-3">
        <Blocks className="h-8 w-8 text-hive-400" strokeWidth={2} />
        <div>
          <h1 className="text-xl font-bold">Skills</h1>
          <p className="text-sm text-surface-400">
            Installed and available skills
          </p>
        </div>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="card h-20 animate-pulse" />
          ))}
        </div>
      ) : error ? (
        <div className="card text-center">
          <p className="text-sm text-red-400">Failed to load skills: {error}</p>
        </div>
      ) : skills && skills.length > 0 ? (
        <div className="space-y-3">
          {skills.map((skill) => (
            <SkillCard key={skill.name} skill={skill} />
          ))}
        </div>
      ) : (
        <div className="card text-center py-12">
          <Blocks className="mx-auto mb-3 h-10 w-10 text-surface-700" />
          <p className="text-sm text-surface-400">No skills installed.</p>
          <p className="mt-1 text-xs text-surface-600">
            Add Python skill files to your .hivecore/skills/ directory.
          </p>
        </div>
      )}
    </div>
  );
}

function SkillCard({ skill }: { skill: SkillInfo }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="card">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-start justify-between text-left"
      >
        <div className="flex items-start gap-3">
          <Blocks className="mt-0.5 h-4 w-4 text-hive-400" />
          <div>
            <p className="text-sm font-medium">{skill.name}</p>
            <p className="mt-0.5 text-xs text-surface-400">
              {skill.description}
            </p>
            <div className="mt-2 flex items-center gap-2">
              <span className="badge-hive">{skill.category}</span>
              <span
                className={cn(
                  "badge",
                  skill.enabled ? "badge-green" : "badge-red"
                )}
              >
                {skill.enabled ? "Enabled" : "Disabled"}
              </span>
              {skill.parameters.length > 0 && (
                <span className="badge-blue">
                  {skill.parameters.length} param
                  {skill.parameters.length !== 1 ? "s" : ""}
                </span>
              )}
            </div>
          </div>
        </div>
        {skill.parameters.length > 0 &&
          (expanded ? (
            <ChevronDown className="h-4 w-4 text-surface-500" />
          ) : (
            <ChevronRight className="h-4 w-4 text-surface-500" />
          ))}
      </button>

      {expanded && skill.parameters.length > 0 && (
        <div className="mt-4 border-t border-surface-800 pt-3">
          <p className="mb-2 text-xs font-medium uppercase tracking-wider text-surface-500">
            Parameters
          </p>
          <div className="space-y-2">
            {skill.parameters.map((param) => (
              <div
                key={param.name}
                className="flex items-start justify-between rounded-md bg-surface-950 px-3 py-2"
              >
                <div>
                  <code className="text-xs text-hive-300">{param.name}</code>
                  <p className="mt-0.5 text-[11px] text-surface-400">
                    {param.description}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-surface-500">
                    {param.type}
                  </span>
                  {param.required && (
                    <span className="badge-red text-[10px]">required</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
