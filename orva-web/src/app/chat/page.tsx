"use client";

import { useState, useEffect, useRef, useCallback, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import {
  sendChatMessage,
  getChatList,
  getChatHistory,
  deleteChat,
  type ChatMessage,
  type ChatListItem,
} from "@/lib/api";
import {
  Bot,
  Send,
  Plus,
  Clock,
  X,
  Trash2,
  Loader2,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const EXAMPLE_PROMPTS = [
  "Owners in Shoreline 9",
  "Expiring leases in Marina",
  "2-bed deals under AED 2M",
  "Compare Oceana vs Azure",
  "Rental yield for Ellington",
  "Who owns unit 607 in Shoreline 5?",
];

/** Make UAE phone numbers into clickable tel: links */
function linkifyPhones(text: string): string {
  // Match +971..., 05x..., 04x..., and spaced variants
  return text.replace(
    /(\+971[\s-]?\d[\s-]?\d{3}[\s-]?\d{4}|\b0[45]\d[\s-]?\d{3}[\s-]?\d{4})/g,
    (match) => {
      const clean = match.replace(/[\s-]/g, "");
      return `[${match}](tel:${clean})`;
    }
  );
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] md:max-w-[70%] rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-white text-sm">
          {msg.content}
        </div>
      </div>
    );
  }

  // Assistant: render markdown with phone links
  const processed = linkifyPhones(msg.content);

  return (
    <div className="flex justify-start">
      <div className="max-w-[95%] md:max-w-[80%] rounded-2xl rounded-bl-md border border-border bg-card px-4 py-3 text-sm text-foreground">
        <div className="prose-chat">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              table: ({ children }) => (
                <div className="table-scroll my-2">
                  <table className="w-full text-xs border-collapse">{children}</table>
                </div>
              ),
              th: ({ children }) => (
                <th className="border border-border bg-background px-2 py-1 text-left font-semibold text-muted text-[11px]">
                  {children}
                </th>
              ),
              td: ({ children }) => (
                <td className="border border-border px-2 py-1 text-[11px]">{children}</td>
              ),
              a: ({ href, children }) => {
                if (href?.startsWith("tel:")) {
                  return (
                    <a
                      href={href}
                      className="text-accent font-medium underline decoration-accent/40"
                    >
                      {children}
                    </a>
                  );
                }
                return (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent underline decoration-accent/40"
                  >
                    {children}
                  </a>
                );
              },
              p: ({ children }) => <p className="my-1.5 leading-relaxed">{children}</p>,
              ul: ({ children }) => <ul className="my-1 ml-4 list-disc">{children}</ul>,
              ol: ({ children }) => <ol className="my-1 ml-4 list-decimal">{children}</ol>,
              li: ({ children }) => <li className="my-0.5">{children}</li>,
              h1: ({ children }) => <h3 className="mt-3 mb-1 font-bold text-base">{children}</h3>,
              h2: ({ children }) => <h3 className="mt-3 mb-1 font-bold text-sm">{children}</h3>,
              h3: ({ children }) => <h4 className="mt-2 mb-1 font-semibold text-sm">{children}</h4>,
              strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
              code: ({ children }) => (
                <code className="rounded bg-background px-1 py-0.5 text-[11px] font-mono">{children}</code>
              ),
              hr: () => <hr className="my-2 border-border" />,
            }}
          >
            {processed}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

export default function ChatPage() {
  const { authenticated } = useAuth();
  const router = useRouter();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatId, setChatId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [statusText, setStatusText] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [chatList, setChatList] = useState<ChatListItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, statusText]);

  // Load chat list
  const refreshChatList = useCallback(async () => {
    try {
      const list = await getChatList();
      setChatList(list);
    } catch {
      /* ignore */
    }
  }, []);

  const handleSend = useCallback(
    (text?: string) => {
      const msg = (text || input).trim();
      if (!msg || isLoading) return;

      setInput("");
      setError(null);
      setIsLoading(true);
      setStatusText("Thinking...");

      // Optimistically add user message
      setMessages((prev) => [...prev, { role: "user", content: msg }]);

      abortRef.current = sendChatMessage(
        msg,
        chatId,
        (status) => setStatusText(status),
        (content, newChatId) => {
          setMessages((prev) => [...prev, { role: "assistant", content }]);
          setChatId(newChatId);
          setIsLoading(false);
          setStatusText(null);
          // Focus input for next message
          setTimeout(() => inputRef.current?.focus(), 100);
        },
        (errText) => {
          setError(errText);
          setIsLoading(false);
          setStatusText(null);
        }
      );
    },
    [input, chatId, isLoading]
  );

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    handleSend();
  };

  const handleNewChat = () => {
    abortRef.current?.abort();
    setMessages([]);
    setChatId(null);
    setError(null);
    setStatusText(null);
    setIsLoading(false);
    setShowHistory(false);
    setTimeout(() => inputRef.current?.focus(), 100);
  };

  const handleLoadChat = async (id: string) => {
    try {
      const data = await getChatHistory(id);
      setMessages(data.messages);
      setChatId(id);
      setShowHistory(false);
      setError(null);
    } catch {
      setError("Failed to load chat.");
    }
  };

  const handleDeleteChat = async (id: string) => {
    try {
      await deleteChat(id);
      setChatList((prev) => prev.filter((c) => c.id !== id));
      if (chatId === id) handleNewChat();
    } catch {
      /* ignore */
    }
  };

  if (!authenticated) { router.replace("/"); return null; }

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-1 flex-col" style={{ height: "calc(100dvh - 49px)" }}>
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-border bg-card px-4 py-2.5 shrink-0">
        <Bot size={18} className="text-accent" />
        <h1 className="text-sm font-semibold text-foreground">HLM Intelligence</h1>
        <div className="ml-auto flex items-center gap-1">
          <button
            onClick={handleNewChat}
            className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-muted hover:bg-card-hover hover:text-foreground"
          >
            <Plus size={14} />
            <span className="hidden md:inline">New</span>
          </button>
          <button
            onClick={() => {
              setShowHistory(!showHistory);
              if (!showHistory) refreshChatList();
            }}
            className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-muted hover:bg-card-hover hover:text-foreground"
          >
            <Clock size={14} />
            <span className="hidden md:inline">History</span>
          </button>
        </div>
      </div>

      {/* Chat history overlay */}
      {showHistory && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/50"
            onClick={() => setShowHistory(false)}
          />
          <div className="fixed right-0 top-0 z-50 h-full w-72 border-l border-border bg-card p-4 overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-foreground">Chat History</h2>
              <button
                onClick={() => setShowHistory(false)}
                className="rounded-lg p-1 text-muted hover:text-foreground"
              >
                <X size={18} />
              </button>
            </div>
            {chatList.length === 0 ? (
              <p className="text-xs text-muted">No previous chats.</p>
            ) : (
              <div className="flex flex-col gap-1">
                {chatList.map((c) => (
                  <div
                    key={c.id}
                    className={`flex items-center gap-2 rounded-lg px-3 py-2.5 text-sm cursor-pointer group ${
                      chatId === c.id
                        ? "bg-accent/15 text-accent"
                        : "text-muted hover:bg-card-hover hover:text-foreground"
                    }`}
                  >
                    <button
                      className="flex-1 text-left truncate"
                      onClick={() => handleLoadChat(c.id)}
                    >
                      <span className="block truncate text-xs font-medium">{c.name}</span>
                      <span className="block text-[10px] text-muted">
                        {c.message_count} messages
                      </span>
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteChat(c.id);
                      }}
                      className="opacity-0 group-hover:opacity-100 rounded p-1 text-muted hover:text-danger transition-opacity"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-3">
        {isEmpty && !isLoading && (
          <div className="flex flex-col items-center justify-center h-full gap-6">
            <div className="text-center">
              <Bot size={32} className="mx-auto mb-2 text-accent/40" />
              <h2 className="text-base font-semibold text-foreground">HLM Intelligence</h2>
              <p className="text-xs text-muted mt-1">Ask about any building, owner, or listing</p>
            </div>
            <div className="grid grid-cols-2 gap-2 max-w-sm w-full">
              {EXAMPLE_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => handleSend(prompt)}
                  className="rounded-lg border border-border bg-card px-3 py-2.5 text-left text-xs text-muted hover:bg-card-hover hover:text-foreground hover:border-accent/30 transition-colors"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <MessageBubble key={i} msg={msg} />
        ))}

        {/* Status indicator */}
        {statusText && (
          <div className="flex items-center gap-2 text-xs text-muted pl-2">
            <Loader2 size={14} className="animate-spin text-accent" />
            {statusText}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="rounded-lg border border-danger/30 bg-danger/5 px-4 py-2.5 text-xs text-danger">
            {error}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="shrink-0 border-t border-border bg-card px-3 py-2.5 pb-[calc(0.625rem+60px)] md:pb-2.5">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about any building..."
            enterKeyHint="send"
            disabled={isLoading}
            className="flex-1 rounded-xl border border-border bg-background px-4 py-2.5 text-sm text-foreground placeholder:text-muted/60 focus:border-accent focus:outline-none disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="flex items-center justify-center rounded-xl bg-accent px-3 py-2.5 text-white transition-colors hover:bg-accent-hover disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {isLoading ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
          </button>
        </form>
      </div>
    </div>
  );
}
