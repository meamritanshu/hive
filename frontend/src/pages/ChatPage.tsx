import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Bot, User, Loader2, Wifi, WifiOff } from "lucide-react";
import { createChatSocket } from "../lib/api";
import { cn } from "../lib/utils";
import type { ChatMessage, WsMessage } from "../types";

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<{ send: (msg: string) => void; close: () => void } | null>(null);
  const streamBufferRef = useRef("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // Connect WebSocket
  const connect = useCallback(() => {
    const onMessage = (msg: WsMessage) => {
      if (msg.type === "chunk") {
        streamBufferRef.current += msg.content;
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "assistant" && last.id === "__streaming__") {
            return [
              ...prev.slice(0, -1),
              { ...last, content: streamBufferRef.current },
            ];
          }
          return [
            ...prev,
            {
              id: "__streaming__",
              role: "assistant",
              content: streamBufferRef.current,
              timestamp: new Date().toISOString(),
            },
          ];
        });
      } else if (msg.type === "done") {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === "__streaming__"
              ? { ...m, id: `msg-${Date.now()}` }
              : m
          )
        );
        streamBufferRef.current = "";
        setStreaming(false);
      } else if (msg.type === "error") {
        setMessages((prev) => [
          ...prev,
          {
            id: `err-${Date.now()}`,
            role: "system",
            content: `Error: ${msg.message}`,
            timestamp: new Date().toISOString(),
          },
        ]);
        setStreaming(false);
      }
    };

    const socket = createChatSocket(
      onMessage,
      () => setConnected(false),
      () => setConnected(false)
    );

    // Give it a moment to connect
    setTimeout(() => setConnected(true), 500);
    socketRef.current = socket;

    return socket;
  }, []);

  useEffect(() => {
    const socket = connect();
    return () => socket.close();
  }, [connect]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || streaming) return;

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setStreaming(true);
    streamBufferRef.current = "";

    if (socketRef.current) {
      socketRef.current.send(text);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-surface-800 px-6 py-3">
        <div>
          <h1 className="text-lg font-bold">Chat</h1>
          <p className="text-xs text-surface-500">
            Talk to your HiveCore
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          {connected ? (
            <Wifi className="h-3.5 w-3.5 text-emerald-400" />
          ) : (
            <WifiOff className="h-3.5 w-3.5 text-red-400" />
          )}
          <span
            className={cn(
              "text-xs",
              connected ? "text-emerald-400" : "text-red-400"
            )}
          >
            {connected ? "Connected" : "Disconnected"}
          </span>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {messages.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="space-y-4">
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-surface-800 px-6 py-4">
        <div className="flex items-end gap-3">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message..."
            rows={1}
            className="input min-h-[40px] max-h-32 resize-none"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || streaming}
            className="btn-primary flex h-10 w-10 items-center justify-center !p-0"
          >
            {streaming ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </button>
        </div>
        <p className="mt-1.5 text-[10px] text-surface-600">
          Press Enter to send, Shift+Enter for new line
        </p>
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const isSystem = message.role === "system";

  return (
    <div
      className={cn(
        "flex gap-3",
        isUser ? "flex-row-reverse" : "flex-row"
      )}
    >
      <div
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
          isUser
            ? "bg-hive-500/20"
            : isSystem
              ? "bg-red-500/20"
              : "bg-surface-800"
        )}
      >
        {isUser ? (
          <User className="h-3.5 w-3.5 text-hive-400" />
        ) : (
          <Bot className="h-3.5 w-3.5 text-surface-300" />
        )}
      </div>
      <div
        className={cn(
          "max-w-[75%] rounded-lg px-3.5 py-2.5",
          isUser
            ? "bg-hive-500/10 text-surface-100"
            : isSystem
              ? "bg-red-500/10 text-red-300"
              : "bg-surface-800 text-surface-200"
        )}
      >
        <div className="prose-chat whitespace-pre-wrap">{message.content}</div>
        <p className="mt-1 text-[10px] text-surface-600">
          {new Date(message.timestamp).toLocaleTimeString()}
        </p>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center text-center">
      <Bot className="mb-4 h-12 w-12 text-surface-700" />
      <h2 className="text-lg font-semibold text-surface-300">
        Start a conversation
      </h2>
      <p className="mt-1 max-w-sm text-sm text-surface-500">
        Type a message below to start chatting with your HiveCore. It can
        help with tasks, answer questions, and run skills.
      </p>
    </div>
  );
}
