import { useState, useCallback, useEffect, useRef } from "react";
import {
  Settings,
  ChevronDown,
  ChevronRight,
  Save,
  Check,
  AlertCircle,
  Eye,
  EyeOff,
  RefreshCw,
  Power,
  Zap,
  Server,
  Brain,
  Bot,
} from "lucide-react";
import { getConfig, updateConfig, restartServer } from "../lib/api";

// ─── types ────────────────────────────────────────────────────────────────────

type SectionState = "idle" | "saving" | "saved" | "error";

const SENSITIVE_FIELDS = new Set(["api_key", "token"]);
const READONLY_FIELDS = new Set(["data_dir"]);
const ROOT_SCALAR_FIELDS = new Set(["data_dir", "log_level"]);
const NESTED_SECTIONS = new Set(["channels"]);

// ─── LLM provider definitions ─────────────────────────────────────────────────

type ProviderDef = {
  id: string;
  label: string;
  icon: string;
  color: string;
  description: string;
  needsApiKey: boolean;
  apiKeyLabel: string;
  apiKeyPlaceholder: string;
  models: { value: string; label: string }[];
  customModel: boolean;
};

const PROVIDERS: ProviderDef[] = [
  {
    id: "google",
    label: "Google Gemini",
    icon: "✦",
    color: "from-blue-500 to-cyan-400",
    description: "Google's Gemini models via Generative AI API",
    needsApiKey: true,
    apiKeyLabel: "Gemini API Key",
    apiKeyPlaceholder: "AIza…",
    customModel: true,
    models: [
      { value: "gemini/gemini-2.0-flash", label: "Gemini 2.0 Flash (recommended)" },
      { value: "gemini/gemini-2.0-flash-lite", label: "Gemini 2.0 Flash Lite" },
      { value: "gemini/gemini-1.5-pro", label: "Gemini 1.5 Pro" },
      { value: "gemini/gemini-1.5-flash", label: "Gemini 1.5 Flash" },
    ],
  },
  {
    id: "openai",
    label: "OpenAI",
    icon: "⬡",
    color: "from-emerald-500 to-teal-400",
    description: "GPT-4o and GPT-4 Turbo via OpenAI API",
    needsApiKey: true,
    apiKeyLabel: "OpenAI API Key",
    apiKeyPlaceholder: "sk-…",
    customModel: true,
    models: [
      { value: "gpt-4o", label: "GPT-4o (recommended)" },
      { value: "gpt-4o-mini", label: "GPT-4o Mini (fast & cheap)" },
      { value: "gpt-4-turbo", label: "GPT-4 Turbo" },
      { value: "gpt-3.5-turbo", label: "GPT-3.5 Turbo" },
    ],
  },
  {
    id: "anthropic",
    label: "Anthropic",
    icon: "◈",
    color: "from-orange-500 to-amber-400",
    description: "Claude 3.5 Sonnet and Claude 3 via Anthropic API",
    needsApiKey: true,
    apiKeyLabel: "Anthropic API Key",
    apiKeyPlaceholder: "sk-ant-…",
    customModel: true,
    models: [
      { value: "anthropic/claude-3-5-sonnet-20241022", label: "Claude 3.5 Sonnet (recommended)" },
      { value: "anthropic/claude-3-5-haiku-20241022", label: "Claude 3.5 Haiku (fast)" },
      { value: "anthropic/claude-3-opus-20240229", label: "Claude 3 Opus (powerful)" },
      { value: "anthropic/claude-3-haiku-20240307", label: "Claude 3 Haiku" },
    ],
  },
  {
    id: "ollama",
    label: "Ollama (Local)",
    icon: "◉",
    color: "from-purple-500 to-violet-400",
    description: "Locally hosted models via Ollama — no API key needed",
    needsApiKey: false,
    apiKeyLabel: "",
    apiKeyPlaceholder: "",
    customModel: true,
    models: [
      { value: "ollama/llama3", label: "Llama 3 (8B)" },
      { value: "ollama/llama3:70b", label: "Llama 3 (70B)" },
      { value: "ollama/mistral", label: "Mistral 7B" },
      { value: "ollama/codellama", label: "Code Llama" },
      { value: "ollama/phi3", label: "Phi-3 Mini" },
    ],
  },
];

function detectProvider(model: string, provider: string): string {
  if (provider === "google" || model.startsWith("gemini/")) return "google";
  if (provider === "anthropic" || model.startsWith("anthropic/")) return "anthropic";
  if (provider === "ollama" || model.startsWith("ollama/")) return "ollama";
  // openai / litellm / default
  return "openai";
}

// ─── RestartBanner ─────────────────────────────────────────────────────────

function RestartBanner({ onDismiss }: { onDismiss: () => void }) {
  const [dots, setDots] = useState(".");
  const [reconnecting, setReconnecting] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    // Animate the dots
    timerRef.current = setInterval(() => {
      setDots((d) => (d.length >= 3 ? "." : d + "."));
    }, 500);

    // After 3s, start polling /api/status
    const pollDelay = setTimeout(() => {
      setReconnecting(true);
      const poll = setInterval(async () => {
        try {
          const res = await fetch("/api/status");
          if (res.ok) {
            clearInterval(poll);
            if (timerRef.current) clearInterval(timerRef.current);
            window.location.reload();
          }
        } catch {
          // still down — keep polling
        }
      }, 1500);
    }, 3000);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      clearTimeout(pollDelay);
    };
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="card max-w-sm w-full mx-4 text-center space-y-4">
        <div className="flex items-center justify-center gap-3">
          <Power className="h-8 w-8 text-hive-400 animate-pulse" />
          <h2 className="text-lg font-bold">Server Restarting</h2>
        </div>
        <p className="text-sm text-surface-400">
          {reconnecting
            ? `Waiting for server to come back${dots}`
            : `Sending shutdown signal${dots}`}
        </p>
        <p className="text-xs text-surface-500">
          On Windows, run{" "}
          <code className="rounded bg-surface-800 px-1 py-0.5 text-hive-300">
            python -m hivecore start
          </code>{" "}
          in your terminal if the page doesn't reconnect.
        </p>
        <button
          type="button"
          onClick={onDismiss}
          className="btn-secondary text-xs w-full"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}

// ─── LLMConfigCard ────────────────────────────────────────────────────────────

function LLMConfigCard({
  fields,
  onSaveAndRestart,
}: {
  fields: Record<string, unknown>;
  onSaveAndRestart: (updates: Record<string, unknown>) => Promise<void>;
}) {
  const currentModel = (fields.model as string) ?? "gemini/gemini-2.0-flash";
  const currentProvider = (fields.provider as string) ?? "google";
  const currentApiKey = (fields.api_key as string) ?? "";

  const initProvider = detectProvider(currentModel, currentProvider);
  const [selectedProvider, setSelectedProvider] = useState(initProvider);
  const [selectedModel, setSelectedModel] = useState(currentModel);
  const [isCustomModel, setIsCustomModel] = useState(false);
  const [customModel, setCustomModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [temperature, setTemperature] = useState((fields.temperature as number) ?? 0.7);
  const [maxTokens, setMaxTokens] = useState((fields.max_tokens as number) ?? 4096);
  const [streaming, setStreaming] = useState((fields.streaming as boolean) ?? true);
  const [timeout, setTimeout_] = useState((fields.timeout as number) ?? 120);

  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState("");

  const providerDef = PROVIDERS.find((p) => p.id === selectedProvider)!;

  // When provider changes, reset model to first in list
  const handleProviderSelect = (id: string) => {
    setSelectedProvider(id);
    const def = PROVIDERS.find((p) => p.id === id)!;
    setSelectedModel(def.models[0].value);
    setIsCustomModel(false);
    setCustomModel("");
  };

  const finalModel = isCustomModel ? customModel : selectedModel;

  const hasChanges =
    finalModel !== currentModel ||
    selectedProvider !== initProvider ||
    apiKey !== "" ||
    temperature !== ((fields.temperature as number) ?? 0.7) ||
    maxTokens !== ((fields.max_tokens as number) ?? 4096) ||
    streaming !== ((fields.streaming as boolean) ?? true) ||
    timeout !== ((fields.timeout as number) ?? 120);

  const handleApply = async () => {
    if (!finalModel) return;
    setStatus("saving");
    setErrorMsg("");
    try {
      const updates: Record<string, unknown> = {
        model: finalModel,
        provider: selectedProvider,
        temperature,
        max_tokens: maxTokens,
        streaming,
        timeout,
      };
      if (apiKey) updates.api_key = apiKey;
      await onSaveAndRestart(updates);
      setStatus("saved");
    } catch (e) {
      setStatus("error");
      setErrorMsg(e instanceof Error ? e.message : "Save failed");
    }
  };

  return (
    <div className="card overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 mb-5">
        <Zap className="h-4 w-4 text-hive-400" />
        <h3 className="text-sm font-semibold">LLM Provider</h3>
        <span className="ml-auto text-xs text-surface-500">
          Active: <span className="text-hive-300 font-mono">{currentModel}</span>
        </span>
      </div>

      {/* Provider cards */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 mb-5">
        {PROVIDERS.map((p) => {
          const active = selectedProvider === p.id;
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => handleProviderSelect(p.id)}
              className={`relative flex flex-col items-center gap-2 rounded-xl border p-3 text-center transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-hive-500 ${active
                  ? "border-hive-500 bg-hive-500/10 shadow-md shadow-hive-500/20"
                  : "border-surface-700 bg-surface-900 hover:border-surface-500 hover:bg-surface-800"
                }`}
            >
              <div
                className={`h-9 w-9 rounded-full bg-gradient-to-br ${p.color} flex items-center justify-center text-lg font-bold text-white shadow`}
              >
                {p.icon}
              </div>
              <span className="text-xs font-semibold leading-tight">{p.label}</span>
              {active && (
                <span className="absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-hive-400" />
              )}
            </button>
          );
        })}
      </div>

      {/* Provider description */}
      <p className="mb-4 text-xs text-surface-400 bg-surface-900 rounded-lg px-3 py-2">
        {providerDef.description}
      </p>

      {/* Model selector */}
      <div className="space-y-3 mb-4">
        <div className="flex items-center justify-between gap-4 rounded-md bg-surface-950 px-3 py-2.5">
          <span className="shrink-0 text-xs font-medium text-surface-300">Model</span>
          <div className="flex items-center gap-2">
            {isCustomModel ? (
              <input
                type="text"
                value={customModel}
                onChange={(e) => setCustomModel(e.target.value)}
                placeholder="e.g. ollama/my-custom-model"
                className="w-64 rounded border border-hive-500 bg-surface-800 px-2 py-1 text-right text-xs text-hive-300 outline-none focus:ring-1 focus:ring-hive-500"
              />
            ) : (
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="w-64 rounded border border-surface-700 bg-surface-800 px-2 py-1 text-right text-xs text-hive-300 outline-none transition-colors focus:border-hive-500 focus:ring-1 focus:ring-hive-500 cursor-pointer"
              >
                {providerDef.models.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>
            )}
            {providerDef.customModel && (
              <button
                type="button"
                onClick={() => {
                  setIsCustomModel((c) => !c);
                  setCustomModel(isCustomModel ? "" : selectedModel);
                }}
                className="shrink-0 rounded px-1.5 py-1 text-[10px] text-surface-400 hover:text-hive-300 border border-surface-700 hover:border-hive-500 transition-colors"
              >
                {isCustomModel ? "Presets" : "Custom"}
              </button>
            )}
          </div>
        </div>

        {/* API Key */}
        {providerDef.needsApiKey && (
          <div className="flex items-center justify-between gap-4 rounded-md bg-surface-950 px-3 py-2">
            <span className="shrink-0 text-xs font-medium text-surface-300">
              {providerDef.apiKeyLabel}
            </span>
            <div className="flex items-center gap-1">
              <input
                type={showApiKey ? "text" : "password"}
                value={apiKey}
                placeholder={
                  currentApiKey && currentApiKey !== ""
                    ? "•••••••• (leave blank to keep current)"
                    : providerDef.apiKeyPlaceholder
                }
                onChange={(e) => setApiKey(e.target.value)}
                className="w-52 rounded border border-surface-700 bg-surface-800 px-2 py-1 text-xs text-hive-300 outline-none transition-colors focus:border-hive-500 focus:ring-1 focus:ring-hive-500 placeholder:italic placeholder:text-surface-600"
              />
              <button
                type="button"
                onClick={() => setShowApiKey((s) => !s)}
                className="text-surface-500 hover:text-surface-300"
              >
                {showApiKey ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
              </button>
            </div>
          </div>
        )}

        {/* Ollama hint */}
        {selectedProvider === "ollama" && (
          <p className="text-xs text-surface-500 px-1">
            Make sure Ollama is running locally on port 11434.{" "}
            <code className="text-hive-400">ollama run llama3</code>
          </p>
        )}
      </div>

      {/* Advanced settings */}
      <div className="mb-5">
        <button
          type="button"
          onClick={() => setShowAdvanced((s) => !s)}
          className="flex items-center gap-1 text-xs text-surface-500 hover:text-surface-300 transition-colors"
        >
          {showAdvanced ? (
            <ChevronDown className="h-3.5 w-3.5" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" />
          )}
          Advanced settings
        </button>

        {showAdvanced && (
          <div className="mt-3 space-y-1.5">
            {/* Temperature */}
            <div className="flex items-center justify-between gap-4 rounded-md bg-surface-950 px-3 py-2.5">
              <div>
                <span className="text-xs font-medium text-surface-300">Temperature</span>
                <p className="text-[10px] text-surface-600">0 = deterministic, 2 = creative</p>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="range"
                  min={0}
                  max={2}
                  step={0.1}
                  value={temperature}
                  onChange={(e) => setTemperature(parseFloat(e.target.value))}
                  className="w-24 accent-hive-500"
                />
                <span className="w-8 text-right text-xs text-hive-300 font-mono">
                  {temperature.toFixed(1)}
                </span>
              </div>
            </div>

            {/* Max tokens */}
            <div className="flex items-center justify-between gap-4 rounded-md bg-surface-950 px-3 py-2">
              <span className="shrink-0 text-xs font-medium text-surface-300">Max Tokens</span>
              <input
                type="number"
                value={maxTokens}
                onChange={(e) => setMaxTokens(Number(e.target.value))}
                className="w-28 rounded border border-surface-700 bg-surface-800 px-2 py-1 text-right text-xs text-hive-300 outline-none focus:border-hive-500 focus:ring-1 focus:ring-hive-500"
              />
            </div>

            {/* Timeout */}
            <div className="flex items-center justify-between gap-4 rounded-md bg-surface-950 px-3 py-2">
              <span className="shrink-0 text-xs font-medium text-surface-300">Timeout (s)</span>
              <input
                type="number"
                value={timeout}
                onChange={(e) => setTimeout_(Number(e.target.value))}
                className="w-28 rounded border border-surface-700 bg-surface-800 px-2 py-1 text-right text-xs text-hive-300 outline-none focus:border-hive-500 focus:ring-1 focus:ring-hive-500"
              />
            </div>

            {/* Streaming */}
            <div className="flex items-center justify-between gap-4 rounded-md bg-surface-950 px-3 py-2.5">
              <span className="text-xs font-medium text-surface-300">Streaming responses</span>
              <button
                type="button"
                role="switch"
                aria-checked={streaming}
                onClick={() => setStreaming((s) => !s)}
                className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-hive-500 ${streaming ? "bg-hive-500" : "bg-surface-700"
                  }`}
              >
                <span
                  className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${streaming ? "translate-x-4" : "translate-x-1"
                    }`}
                />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex-1 text-xs text-red-400">{status === "error" && errorMsg}</div>
        {status === "saved" && (
          <span className="flex items-center gap-1 text-xs text-emerald-400">
            <Check className="h-3 w-3" /> Saved — restarting…
          </span>
        )}
        <button
          type="button"
          onClick={handleApply}
          disabled={!hasChanges || status === "saving"}
          className="btn-primary flex items-center gap-2 disabled:opacity-40"
        >
          {status === "saving" ? (
            <RefreshCw className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Power className="h-3.5 w-3.5" />
          )}
          {status === "saving" ? "Applying…" : "Apply & Restart"}
        </button>
      </div>
    </div>
  );
}

// ─── helpers ──────────────────────────────────────────────────────────────────

function inferType(value: unknown): "boolean" | "number" | "string" | "array" | "object" {
  if (typeof value === "boolean") return "boolean";
  if (typeof value === "number") return "number";
  if (Array.isArray(value)) return "array";
  if (typeof value === "object" && value !== null) return "object";
  return "string";
}

// ─── FieldRow ──────────────────────────────────────────────────────────────────

function FieldRow({
  label,
  value,
  draft,
  onChange,
  readOnly = false,
}: {
  label: string;
  value: unknown;
  draft: unknown;
  onChange: (val: unknown) => void;
  readOnly?: boolean;
}) {
  const [showPassword, setShowPassword] = useState(false);
  const isSensitive = SENSITIVE_FIELDS.has(label);
  const isReadOnly = READONLY_FIELDS.has(label) || readOnly;
  const type = inferType(value);
  const isRedacted = typeof value === "string" && value.includes("***");

  if (type === "boolean") {
    const checked = draft as boolean;
    return (
      <div className="flex items-center justify-between gap-4 rounded-md bg-surface-950 px-3 py-2.5">
        <span className="text-xs font-medium text-surface-300">{label}</span>
        <button
          type="button"
          role="switch"
          aria-checked={checked}
          disabled={isReadOnly}
          onClick={() => !isReadOnly && onChange(!checked)}
          className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-hive-500 disabled:opacity-40 disabled:cursor-not-allowed ${checked ? "bg-hive-500" : "bg-surface-700"
            }`}
        >
          <span
            className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${checked ? "translate-x-4" : "translate-x-1"
              }`}
          />
        </button>
      </div>
    );
  }

  if (type === "number") {
    return (
      <div className="flex items-center justify-between gap-4 rounded-md bg-surface-950 px-3 py-2">
        <span className="shrink-0 text-xs font-medium text-surface-300">{label}</span>
        <input
          type="number"
          value={(draft as number) ?? ""}
          readOnly={isReadOnly}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-36 rounded border border-surface-700 bg-surface-800 px-2 py-1 text-right text-xs text-hive-300 outline-none transition-colors focus:border-hive-500 focus:ring-1 focus:ring-hive-500 read-only:opacity-60 read-only:cursor-default"
        />
      </div>
    );
  }

  if (type === "array") {
    const arr = draft as unknown[];
    return (
      <div className="flex items-start justify-between gap-4 rounded-md bg-surface-950 px-3 py-2">
        <span className="shrink-0 pt-0.5 text-xs font-medium text-surface-300">{label}</span>
        <textarea
          value={arr.join(", ")}
          readOnly={isReadOnly}
          rows={2}
          onChange={(e) =>
            onChange(
              e.target.value
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean)
            )
          }
          className="w-64 resize-none rounded border border-surface-700 bg-surface-800 px-2 py-1 text-right text-xs text-hive-300 outline-none transition-colors focus:border-hive-500 focus:ring-1 focus:ring-hive-500 read-only:opacity-60 read-only:cursor-default"
          placeholder="comma-separated"
        />
      </div>
    );
  }

  if (isSensitive) {
    const displayVal = isRedacted ? "" : ((draft as string) ?? "");
    return (
      <div className="flex items-center justify-between gap-4 rounded-md bg-surface-950 px-3 py-2">
        <span className="shrink-0 text-xs font-medium text-surface-300">{label}</span>
        <div className="flex items-center gap-1">
          <input
            type={showPassword ? "text" : "password"}
            value={displayVal}
            placeholder={isRedacted ? "••••••••  (unchanged)" : "enter value…"}
            onChange={(e) => onChange(e.target.value)}
            className="w-52 rounded border border-surface-700 bg-surface-800 px-2 py-1 text-xs text-hive-300 outline-none transition-colors focus:border-hive-500 focus:ring-1 focus:ring-hive-500 placeholder:italic placeholder:text-surface-600"
          />
          <button
            type="button"
            onClick={() => setShowPassword((p) => !p)}
            className="text-surface-500 hover:text-surface-300"
          >
            {showPassword ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-between gap-4 rounded-md bg-surface-950 px-3 py-2">
      <span className="shrink-0 text-xs font-medium text-surface-300">{label}</span>
      <input
        type="text"
        value={(draft as string) ?? ""}
        readOnly={isReadOnly}
        onChange={(e) => onChange(e.target.value)}
        className="w-64 rounded border border-surface-700 bg-surface-800 px-2 py-1 text-right text-xs text-hive-300 outline-none transition-colors focus:border-hive-500 focus:ring-1 focus:ring-hive-500 read-only:opacity-60 read-only:cursor-default"
      />
    </div>
  );
}

// ─── SectionCard ──────────────────────────────────────────────────────────────

const SECTION_ICONS: Record<string, JSX.Element> = {
  memory: <Brain className="h-4 w-4 text-hive-400" />,
  agent: <Bot className="h-4 w-4 text-hive-400" />,
  web: <Server className="h-4 w-4 text-hive-400" />,
};

function SectionCard({
  sectionKey,
  sectionLabel,
  fields,
  onSave,
  defaultOpen = true,
}: {
  sectionKey: string;
  sectionLabel: string;
  fields: Record<string, unknown>;
  onSave: (section: string, updates: Record<string, unknown>) => Promise<void>;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [draft, setDraft] = useState<Record<string, unknown>>({ ...fields });
  const [status, setStatus] = useState<SectionState>("idle");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    setDraft((prev) => ({ ...fields, ...prev }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(fields)]);

  const isDirty = JSON.stringify(draft) !== JSON.stringify(fields);

  const handleSave = async () => {
    setStatus("saving");
    setErrorMsg("");
    const changes: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(draft)) {
      if (SENSITIVE_FIELDS.has(k) && (v === "" || v === null || v === undefined)) continue;
      if (JSON.stringify(v) !== JSON.stringify(fields[k])) changes[k] = v;
    }
    if (Object.keys(changes).length === 0) { setStatus("idle"); return; }
    try {
      await onSave(sectionKey, changes);
      setStatus("saved");
      setTimeout(() => setStatus("idle"), 2500);
    } catch (e) {
      setStatus("error");
      setErrorMsg(e instanceof Error ? e.message : "Save failed");
    }
  };

  const handleReset = () => { setDraft({ ...fields }); setStatus("idle"); setErrorMsg(""); };

  return (
    <div className="card overflow-hidden">
      <button
        type="button"
        className="flex w-full items-center gap-2 text-left"
        onClick={() => setOpen((o) => !o)}
      >
        {open
          ? <ChevronDown className="h-4 w-4 text-hive-400" />
          : <ChevronRight className="h-4 w-4 text-hive-400" />}
        {SECTION_ICONS[sectionKey] ?? <Settings className="h-4 w-4 text-hive-400" />}
        <h3 className="text-sm font-semibold capitalize">{sectionLabel}</h3>
        {isDirty && (
          <span className="ml-2 rounded-full bg-hive-500/20 px-2 py-0.5 text-xs text-hive-400">unsaved</span>
        )}
        {status === "saved" && (
          <span className="ml-2 flex items-center gap-1 text-xs text-emerald-400">
            <Check className="h-3 w-3" /> saved
          </span>
        )}
        {status === "error" && (
          <span className="ml-2 flex items-center gap-1 text-xs text-red-400">
            <AlertCircle className="h-3 w-3" /> error
          </span>
        )}
      </button>

      {open && (
        <>
          <div className="mt-3 space-y-1.5">
            {Object.entries(fields).map(([key, origVal]) => (
              <FieldRow
                key={key}
                label={key}
                value={origVal}
                draft={draft[key] ?? origVal}
                onChange={(val) => setDraft((d) => ({ ...d, [key]: val }))}
                readOnly={READONLY_FIELDS.has(key)}
              />
            ))}
          </div>
          <div className="mt-4 flex items-center justify-between gap-3">
            <div className="flex-1 text-xs text-red-400">{status === "error" && errorMsg}</div>
            <div className="flex items-center gap-2">
              {isDirty && (
                <button type="button" onClick={handleReset} className="btn-secondary flex items-center gap-1.5 text-xs">
                  <RefreshCw className="h-3 w-3" /> Reset
                </button>
              )}
              <button
                type="button"
                onClick={handleSave}
                disabled={!isDirty || status === "saving"}
                className="btn-primary flex items-center gap-1.5 text-xs disabled:opacity-40"
              >
                {status === "saving" ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                {status === "saving" ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ─── NestedSectionCard (channels) ────────────────────────────────────────────

function NestedSectionCard({
  sectionKey,
  sectionLabel,
  value,
  onSave,
}: {
  sectionKey: string;
  sectionLabel: string;
  value: Record<string, Record<string, unknown>>;
  onSave: (section: string, updates: Record<string, unknown>) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, Record<string, unknown>>>(
    () => Object.fromEntries(Object.entries(value).map(([k, v]) => [k, { ...v }]))
  );
  const [status, setStatus] = useState<SectionState>("idle");
  const [errorMsg, setErrorMsg] = useState("");

  const isDirty = JSON.stringify(drafts) !== JSON.stringify(value);

  const handleSave = async () => {
    setStatus("saving");
    setErrorMsg("");
    const changes: Record<string, Record<string, unknown>> = {};
    for (const [ch, chDraft] of Object.entries(drafts)) {
      const orig = value[ch] ?? {};
      const chChanges: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(chDraft)) {
        if (SENSITIVE_FIELDS.has(k) && (v === "" || v === null)) continue;
        if (JSON.stringify(v) !== JSON.stringify(orig[k])) chChanges[k] = v;
      }
      if (Object.keys(chChanges).length) changes[ch] = chChanges;
    }
    if (!Object.keys(changes).length) { setStatus("idle"); return; }
    try {
      await onSave(sectionKey, changes);
      setStatus("saved");
      setTimeout(() => setStatus("idle"), 2500);
    } catch (e) {
      setStatus("error");
      setErrorMsg(e instanceof Error ? e.message : "Save failed");
    }
  };

  const handleReset = () => {
    setDrafts(Object.fromEntries(Object.entries(value).map(([k, v]) => [k, { ...v }])));
    setStatus("idle");
    setErrorMsg("");
  };

  return (
    <div className="card overflow-hidden">
      <button type="button" className="flex w-full items-center gap-2 text-left" onClick={() => setOpen((o) => !o)}>
        {open ? <ChevronDown className="h-4 w-4 text-hive-400" /> : <ChevronRight className="h-4 w-4 text-hive-400" />}
        <Settings className="h-4 w-4 text-hive-400" />
        <h3 className="text-sm font-semibold capitalize">{sectionLabel}</h3>
        {isDirty && <span className="ml-2 rounded-full bg-hive-500/20 px-2 py-0.5 text-xs text-hive-400">unsaved</span>}
        {status === "saved" && <span className="ml-2 flex items-center gap-1 text-xs text-emerald-400"><Check className="h-3 w-3" /> saved</span>}
      </button>

      {open && (
        <>
          {Object.entries(value).map(([chName, chFields]) => (
            <div key={chName} className="mt-4">
              <p className="mb-1.5 text-xs font-semibold capitalize text-surface-400">{chName}</p>
              <div className="space-y-1.5">
                {Object.entries(chFields).map(([key, origVal]) => (
                  <FieldRow
                    key={key}
                    label={key}
                    value={origVal}
                    draft={drafts[chName]?.[key] ?? origVal}
                    onChange={(val) =>
                      setDrafts((d) => ({ ...d, [chName]: { ...d[chName], [key]: val } }))
                    }
                  />
                ))}
              </div>
            </div>
          ))}
          <div className="mt-4 flex items-center justify-between gap-3">
            <div className="flex-1 text-xs text-red-400">{status === "error" && errorMsg}</div>
            <div className="flex items-center gap-2">
              {isDirty && (
                <button type="button" onClick={handleReset} className="btn-secondary flex items-center gap-1.5 text-xs">
                  <RefreshCw className="h-3 w-3" /> Reset
                </button>
              )}
              <button type="button" onClick={handleSave} disabled={!isDirty || status === "saving"} className="btn-primary flex items-center gap-1.5 text-xs disabled:opacity-40">
                {status === "saving" ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                {status === "saving" ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ─── ConfigPage ───────────────────────────────────────────────────────────────

export default function ConfigPage() {
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [showRestartBanner, setShowRestartBanner] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setFetchError(null);
    try {
      const data = await getConfig();
      setConfig(data as Record<string, unknown>);
    } catch (e) {
      setFetchError(e instanceof Error ? e.message : "Failed to load config");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSave = async (section: string, updates: Record<string, unknown>) => {
    const result = await updateConfig(section, updates);
    setConfig((prev) => {
      if (!prev) return prev;
      const updated = result.updated as Record<string, unknown>;
      if (section === "root") return { ...prev, ...updates };
      return { ...prev, [section]: updated };
    });
  };

  const handleLLMSaveAndRestart = async (updates: Record<string, unknown>) => {
    await updateConfig("llm", updates);
    setShowRestartBanner(true);
    try {
      await restartServer();
    } catch {
      // Server may close before response arrives — that's fine
    }
  };

  const sections: Array<{
    key: string;
    label: string;
    value: Record<string, unknown>;
    nested: boolean;
  }> = [];
  const rootScalars: Record<string, unknown> = {};

  if (config) {
    for (const [k, v] of Object.entries(config)) {
      if (k === "llm") continue; // handled by LLMConfigCard
      if (ROOT_SCALAR_FIELDS.has(k)) {
        rootScalars[k] = v;
      } else if (typeof v === "object" && v !== null && !Array.isArray(v)) {
        sections.push({
          key: k,
          label: k,
          value: v as Record<string, unknown>,
          nested: NESTED_SECTIONS.has(k),
        });
      } else {
        rootScalars[k] = v;
      }
    }
  }

  return (
    <div className="p-6">
      {showRestartBanner && <RestartBanner onDismiss={() => setShowRestartBanner(false)} />}

      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Settings className="h-8 w-8 text-hive-400" strokeWidth={2} />
          <div>
            <h1 className="text-xl font-bold">Configuration</h1>
            <p className="text-sm text-surface-400">
              Edit HiveCore settings — changes are saved to{" "}
              <code className="text-hive-400">~/.hivecore/config.toml</code>
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="btn-secondary flex items-center gap-1.5 text-xs"
          title="Reload config from disk"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Reload
        </button>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="card h-16 animate-pulse" />
          ))}
        </div>
      ) : fetchError ? (
        <div className="card text-center">
          <p className="text-sm text-red-400">Failed to load config: {fetchError}</p>
        </div>
      ) : config ? (
        <div className="space-y-4">
          {/* Smart LLM Card — always first */}
          <LLMConfigCard
            fields={(config.llm as Record<string, unknown>) ?? {}}
            onSaveAndRestart={handleLLMSaveAndRestart}
          />

          {/* Root scalars (data_dir, log_level) */}
          {Object.keys(rootScalars).length > 0 && (
            <SectionCard
              key="root"
              sectionKey="root"
              sectionLabel="General"
              fields={rootScalars}
              onSave={handleSave}
              defaultOpen={false}
            />
          )}

          {/* Sub-model sections */}
          {sections.map(({ key, label, value, nested }) =>
            nested ? (
              <NestedSectionCard
                key={key}
                sectionKey={key}
                sectionLabel={label}
                value={value as Record<string, Record<string, unknown>>}
                onSave={handleSave}
              />
            ) : (
              <SectionCard
                key={key}
                sectionKey={key}
                sectionLabel={label}
                fields={value}
                onSave={handleSave}
                defaultOpen={false}
              />
            )
          )}
        </div>
      ) : null}
    </div>
  );
}
