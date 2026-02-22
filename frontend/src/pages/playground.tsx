import { useRef, useState } from "react";
import {
  AssistantRuntimeProvider,
  useLocalRuntime,
  ThreadPrimitive,
  ComposerPrimitive,
  MessagePrimitive,
} from "@assistant-ui/react";
import { MarkdownTextPrimitive } from "@assistant-ui/react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ChevronDown,
  ChevronRight,
  Wrench,
  Loader2,
  CheckCircle2,
  Bot,
  User,
  ArrowDown,
  Send,
} from "lucide-react";
import { ExecutionResultDisplay } from "@/components/chat/execution-result-display";
import type { ExecutionResult } from "@/types/skill";
import {
  createPlaygroundAdapter,
  type PlaygroundConfig,
} from "@/lib/playground-runtime";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MODELS: Record<string, string> = {
  "claude-opus-4-6": "Claude Opus 4.6",
  "claude-opus-4-5": "Claude Opus 4.5",
  "claude-sonnet-4-5": "Claude Sonnet 4.5",
  "claude-haiku-4-5": "Claude Haiku 4.5",
};

// ---------------------------------------------------------------------------
// Tool-call UI (registered globally inside the provider)
// ---------------------------------------------------------------------------

interface ToolResult {
  text?: string;
  execution?: ExecutionResult;
  files?: Array<{ filename: string; download_url: string }>;
  duration_ms?: number;
}

function McpToolUI({
  toolName,
  args,
  result,
}: {
  toolName: string;
  args: Record<string, unknown>;
  result?: ToolResult;
  addResult: (r: unknown) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const isRunning = result === undefined;

  // Build execution result with files attached
  let executionResult: ExecutionResult | undefined;
  if (result?.execution) {
    executionResult = { ...result.execution };
    if (result.files && result.files.length > 0) {
      executionResult.output_files = result.files;
    }
  }

  return (
    <div className="space-y-2 my-2">
      <div className="bg-muted/50 rounded-lg overflow-hidden">
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center gap-2 p-2 hover:bg-muted/80 transition-colors text-left"
        >
          {expanded ? (
            <ChevronDown className="w-3 h-3 text-muted-foreground" />
          ) : (
            <ChevronRight className="w-3 h-3 text-muted-foreground" />
          )}
          {isRunning ? (
            <Loader2 className="w-3 h-3 animate-spin text-blue-500" />
          ) : (
            <CheckCircle2 className="w-3 h-3 text-green-500" />
          )}
          <Wrench className="w-3 h-3 text-muted-foreground" />
          <span className="font-mono text-sm flex-1 truncate">{toolName}</span>
          {result?.duration_ms != null && (
            <span className="text-xs text-muted-foreground">
              {result.duration_ms}ms
            </span>
          )}
          <Badge
            variant={isRunning ? "secondary" : "default"}
            className="text-xs"
          >
            {isRunning ? "running" : "success"}
          </Badge>
        </button>

        {expanded && (
          <div className="px-3 pb-3 space-y-2">
            {/* Input */}
            <div>
              <div className="text-xs font-medium text-muted-foreground mb-1">
                Input
              </div>
              <pre className="text-xs bg-background p-2 rounded overflow-x-auto">
                {JSON.stringify(args, null, 2)}
              </pre>
            </div>

            {/* Result text */}
            {result?.text && (
              <div>
                <div className="text-xs font-medium text-muted-foreground mb-1">
                  Result
                </div>
                <pre className="text-xs bg-background p-2 rounded overflow-x-auto max-h-40">
                  {typeof result.text === "string" && result.text.length > 500
                    ? result.text.substring(0, 500) + "..."
                    : result.text}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Execution result (code interpreter) */}
      {executionResult && <ExecutionResultDisplay result={executionResult} />}
    </div>
  );
}

/** Fallback tool-call renderer for MessagePrimitive.Content */
function ToolCallFallback(props: {
  toolName: string;
  args: Record<string, unknown>;
  result?: unknown;
  addResult: (r: unknown) => void;
}) {
  return (
    <McpToolUI
      toolName={props.toolName}
      args={props.args}
      result={props.result as ToolResult | undefined}
      addResult={props.addResult}
    />
  );
}

// ---------------------------------------------------------------------------
// Message components
// ---------------------------------------------------------------------------

function UserMessage() {
  return (
    <div className="flex justify-center py-2">
      <div className="w-full max-w-3xl px-4">
        <div className="flex items-start gap-3 mb-4">
          <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center flex-shrink-0">
            <User className="w-4 h-4 text-primary-foreground" />
          </div>
          <div className="flex-1">
            <div className="font-semibold text-sm mb-1">You</div>
            <div className="text-sm whitespace-pre-wrap">
              <MessagePrimitive.Content />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function AssistantMessage() {
  return (
    <div className="flex justify-center py-2">
      <div className="w-full max-w-3xl px-4">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
            <Bot className="w-4 h-4 text-primary" />
          </div>
          <div className="flex-1 prose prose-xs dark:prose-invert max-w-none text-sm">
            <div className="font-semibold text-sm mb-1 not-prose">
              Assistant
            </div>
            <MessagePrimitive.Content
              components={{
                Text: MarkdownText,
                tools: { Fallback: ToolCallFallback },
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function MarkdownText() {
  return (
    <MarkdownTextPrimitive
      className="aui-markdown"
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeKatex]}
    />
  );
}

// ---------------------------------------------------------------------------
// Thread (chat area + composer)
// ---------------------------------------------------------------------------

function PlaygroundThread() {
  return (
    <ThreadPrimitive.Root className="flex-1 flex flex-col overflow-hidden">
      <ThreadPrimitive.Viewport className="flex-1 overflow-y-auto p-4 bg-muted/30 rounded-lg">
        <ThreadPrimitive.Empty>
          <div className="flex items-center justify-center h-full text-muted-foreground">
            Start a conversation to test MCP Skills
          </div>
        </ThreadPrimitive.Empty>

        <ThreadPrimitive.Messages
          components={{
            UserMessage,
            AssistantMessage,
          }}
        />

        <ThreadPrimitive.ViewportFooter>
          <ThreadPrimitive.ScrollToBottom asChild>
            <button className="mx-auto flex h-8 w-8 items-center justify-center rounded-full border bg-background shadow-sm transition-opacity hover:bg-accent">
              <ArrowDown className="h-4 w-4" />
            </button>
          </ThreadPrimitive.ScrollToBottom>
        </ThreadPrimitive.ViewportFooter>
      </ThreadPrimitive.Viewport>

      {/* Composer */}
      <div className="pt-3">
        <ComposerPrimitive.Root className="flex gap-2">
          <ComposerPrimitive.Input
            placeholder="Type a message to test Skills..."
            className="flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 min-h-[76px]"
            rows={3}
          />
          <ComposerPrimitive.Send className="inline-flex items-center justify-center rounded-md bg-primary text-primary-foreground hover:bg-primary/90 h-auto min-h-[76px] w-10 disabled:pointer-events-none disabled:opacity-50">
            <Send className="h-4 w-4" />
          </ComposerPrimitive.Send>
        </ComposerPrimitive.Root>
      </div>
    </ThreadPrimitive.Root>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function PlaygroundPage() {
  const [selectedModel, setSelectedModel] = useState("claude-opus-4-6");
  const [useMcpServer, setUseMcpServer] = useState(true);

  const configRef = useRef<PlaygroundConfig>({
    model: selectedModel,
    useMcpServer,
  });
  // Keep ref in sync
  configRef.current = { model: selectedModel, useMcpServer };

  const adapter = useRef(createPlaygroundAdapter(configRef)).current;
  const runtime = useLocalRuntime(adapter);

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div className="flex flex-col h-[calc(100vh-4rem)] p-6 gap-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Playground</h1>
            <p className="text-muted-foreground mt-1">
              Test MCP Skills with AI Model
            </p>
          </div>
          <Badge variant="outline">Beta</Badge>
        </div>

        <Card className="flex-1 flex flex-col overflow-hidden">
          <CardHeader className="pb-3">
            <CardTitle>Chat</CardTitle>
          </CardHeader>
          <CardContent className="flex-1 flex flex-col gap-4 overflow-hidden">
            <PlaygroundThread />

            {/* Controls */}
            <div className="flex items-center gap-4 p-3 bg-muted/50 rounded-lg">
              <div className="flex items-center gap-2 flex-1">
                <Label
                  htmlFor="model-select"
                  className="text-sm font-medium whitespace-nowrap"
                >
                  Model:
                </Label>
                <Select value={selectedModel} onValueChange={setSelectedModel}>
                  <SelectTrigger id="model-select" className="w-[200px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(MODELS).map(([value, label]) => (
                      <SelectItem key={value} value={value}>
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center gap-2">
                <Switch
                  id="mcp-toggle"
                  checked={useMcpServer}
                  onCheckedChange={setUseMcpServer}
                />
                <Label
                  htmlFor="mcp-toggle"
                  className="text-sm font-medium whitespace-nowrap cursor-pointer"
                >
                  Use MCP Server
                </Label>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </AssistantRuntimeProvider>
  );
}
