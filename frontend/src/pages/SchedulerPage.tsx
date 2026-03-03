import { Clock, Play, Pause, AlertCircle } from "lucide-react";
import { getScheduledJobs } from "../lib/api";
import { useFetch, cn } from "../lib/utils";

export default function SchedulerPage() {
  const { data: jobs, loading, error, refetch } = useFetch(getScheduledJobs);

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Clock className="h-8 w-8 text-hive-400" strokeWidth={2} />
          <div>
            <h1 className="text-xl font-bold">Scheduler</h1>
            <p className="text-sm text-surface-400">
              Scheduled jobs and automation
            </p>
          </div>
        </div>
        <button onClick={refetch} className="btn-secondary text-xs">
          Refresh
        </button>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <div key={i} className="card h-20 animate-pulse" />
          ))}
        </div>
      ) : error ? (
        <div className="card text-center">
          <AlertCircle className="mx-auto mb-2 h-8 w-8 text-red-400" />
          <p className="text-sm text-red-400">
            Failed to load scheduler: {error}
          </p>
        </div>
      ) : jobs && jobs.length > 0 ? (
        <div className="space-y-3">
          {jobs.map((job) => (
            <div key={job.id} className="card">
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-3">
                  {job.enabled ? (
                    <Play className="mt-0.5 h-4 w-4 text-emerald-400" />
                  ) : (
                    <Pause className="mt-0.5 h-4 w-4 text-surface-500" />
                  )}
                  <div>
                    <p className="text-sm font-medium">{job.name}</p>
                    {job.description && (
                      <p className="mt-0.5 text-xs text-surface-400">
                        {job.description}
                      </p>
                    )}
                    <div className="mt-2 flex items-center gap-2">
                      <span className="badge-hive">{job.trigger}</span>
                      <span
                        className={cn(
                          "badge",
                          job.enabled ? "badge-green" : "badge-red"
                        )}
                      >
                        {job.enabled ? "Active" : "Paused"}
                      </span>
                    </div>
                  </div>
                </div>
                {job.next_run_time && (
                  <div className="text-right">
                    <p className="text-[10px] text-surface-500">Next run</p>
                    <p className="text-xs text-surface-300">
                      {new Date(job.next_run_time).toLocaleString()}
                    </p>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="card py-12 text-center">
          <Clock className="mx-auto mb-3 h-10 w-10 text-surface-700" />
          <p className="text-sm text-surface-400">No scheduled jobs.</p>
          <p className="mt-1 text-xs text-surface-600">
            Use the CLI or chat to create scheduled tasks.
          </p>
        </div>
      )}
    </div>
  );
}
