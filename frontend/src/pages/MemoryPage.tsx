import { useState } from "react";
import { Brain, Search, Database, Tag, Clock } from "lucide-react";
import { getMemoryStats, searchMemory } from "../lib/api";
import { useFetch, timeAgo } from "../lib/utils";
import type { MemoryEntry } from "../types";

export default function MemoryPage() {
  const { data: stats, loading: statsLoading } = useFetch(getMemoryStats);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<MemoryEntry[]>([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setSearching(true);
    try {
      const data = await searchMemory(query.trim());
      setResults(data.entries);
      setSearched(true);
    } catch (err) {
      console.error("Search failed:", err);
    } finally {
      setSearching(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSearch();
    }
  };

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-8 flex items-center gap-3">
        <Brain className="h-8 w-8 text-hive-400" strokeWidth={2} />
        <div>
          <h1 className="text-xl font-bold">Memory</h1>
          <p className="text-sm text-surface-400">
            Browse and search agent memory
          </p>
        </div>
      </div>

      {/* Stats */}
      <div className="mb-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard
          label="Short-term"
          value={stats?.short_term_count}
          loading={statsLoading}
        />
        <StatCard
          label="Long-term"
          value={stats?.long_term_count}
          loading={statsLoading}
        />
        <StatCard
          label="File Entries"
          value={stats?.file_memory_count}
          loading={statsLoading}
        />
        <StatCard
          label="Vector Entries"
          value={stats?.vector_memory_count}
          loading={statsLoading}
        />
      </div>

      {/* Memory Type Breakdown */}
      {stats?.memory_types && Object.keys(stats.memory_types).length > 0 && (
        <div className="mb-8">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-surface-400">
            By Type
          </h2>
          <div className="flex flex-wrap gap-2">
            {Object.entries(stats.memory_types).map(([type, count]) => (
              <span key={type} className="badge-hive">
                {type}: {count}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Search */}
      <div className="mb-6">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-surface-400">
          Search Memory
        </h2>
        <div className="flex gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-surface-500" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Search memories..."
              className="input pl-9"
            />
          </div>
          <button
            onClick={handleSearch}
            disabled={!query.trim() || searching}
            className="btn-primary"
          >
            {searching ? "Searching..." : "Search"}
          </button>
        </div>
      </div>

      {/* Results */}
      {searched && (
        <div>
          <p className="mb-3 text-sm text-surface-400">
            {results.length} result{results.length !== 1 ? "s" : ""} for
            &quot;{query}&quot;
          </p>
          {results.length > 0 ? (
            <div className="space-y-3">
              {results.map((entry) => (
                <MemoryCard key={entry.id} entry={entry} />
              ))}
            </div>
          ) : (
            <div className="card text-center">
              <Database className="mx-auto mb-2 h-8 w-8 text-surface-700" />
              <p className="text-sm text-surface-500">
                No memories found for this query.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  loading,
}: {
  label: string;
  value?: number;
  loading: boolean;
}) {
  return (
    <div className="card">
      {loading ? (
        <div className="h-10 animate-pulse rounded bg-surface-800" />
      ) : (
        <>
          <p className="text-2xl font-bold">{(value ?? 0).toLocaleString()}</p>
          <p className="text-xs text-surface-400">{label}</p>
        </>
      )}
    </div>
  );
}

function MemoryCard({ entry }: { entry: MemoryEntry }) {
  return (
    <div className="card">
      <div className="mb-2 flex items-start justify-between gap-4">
        <div className="flex items-center gap-2">
          <Tag className="h-3.5 w-3.5 text-surface-500" />
          <span className="badge-hive">{entry.memory_type}</span>
          {entry.score !== undefined && (
            <span className="badge-blue">
              {(entry.score * 100).toFixed(0)}% match
            </span>
          )}
        </div>
        <div className="flex items-center gap-1 text-[10px] text-surface-500">
          <Clock className="h-3 w-3" />
          {timeAgo(entry.created_at)}
        </div>
      </div>
      <p className="whitespace-pre-wrap text-sm text-surface-200">
        {entry.content}
      </p>
    </div>
  );
}
