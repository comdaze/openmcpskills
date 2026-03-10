/**
 * Playground Runtime Adapter for @assistant-ui/react
 * Uses WebSocket to stream text + tool call progress from the backend.
 */

import type { ChatModelAdapter, ChatModelRunOptions, ChatModelRunResult } from "@assistant-ui/react";
import type { MutableRefObject } from "react";
import { API_BASE_URL } from "./api";

export interface PlaygroundConfig {
  model: string;
  useMcpServer: boolean;
}

// Build the WebSocket URL from the HTTP API base URL.
function wsUrl(): string {
  const base = API_BASE_URL || window.location.origin;
  return base.replace(/^http/, "ws") + "/playground/chat-ws";
}

/**
 * Helper: wait for a WebSocket message, respecting AbortSignal.
 * Resolves with the parsed JSON, or rejects on error / abort.
 */
function waitForMessage(ws: WebSocket, signal: AbortSignal): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const onMsg = (ev: MessageEvent) => { cleanup(); resolve(JSON.parse(ev.data)); };
    const onErr = () => { cleanup(); reject(new Error("WebSocket error")); };
    const onClose = () => { cleanup(); reject(new Error("WebSocket closed")); };
    const onAbort = () => { cleanup(); ws.close(); reject(new DOMException("Aborted", "AbortError")); };
    function cleanup() {
      ws.removeEventListener("message", onMsg);
      ws.removeEventListener("error", onErr);
      ws.removeEventListener("close", onClose);
      signal.removeEventListener("abort", onAbort);
    }
    ws.addEventListener("message", onMsg, { once: true });
    ws.addEventListener("error", onErr, { once: true });
    ws.addEventListener("close", onClose, { once: true });
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

export function createPlaygroundAdapter(
  configRef: MutableRefObject<PlaygroundConfig>
): ChatModelAdapter {
  return {
    async *run({ messages, abortSignal }: ChatModelRunOptions): AsyncGenerator<ChatModelRunResult> {
      const config = configRef.current;
      const mcpServerUrl = localStorage.getItem("mcp_server_url") || `${API_BASE_URL}/mcp`;

      // Open WebSocket
      const ws = new WebSocket(wsUrl());
      await new Promise<void>((resolve, reject) => {
        ws.onopen = () => resolve();
        ws.onerror = () => reject(new Error("WebSocket connection failed"));
        if (abortSignal.aborted) reject(new DOMException("Aborted", "AbortError"));
      });

      // Build messages in Anthropic Messages API format.
      // Sequential tool calls must be split into separate assistant/user pairs.
      // Bedrock requires: assistant(tool_use) → user(tool_result) for EACH tool call.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const apiMessages: any[] = [];
      for (const m of messages) {
        if (m.role === "assistant") {
          // Split assistant message: each tool call becomes its own
          // assistant(text + tool_use) → user(tool_result) pair.
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          let pendingText: any[] = [];

          for (const c of m.content) {
            if (c.type === "text") {
              pendingText.push({ type: "text", text: c.text });
            } else if (c.type === "tool-call") {
              // Emit assistant message with accumulated text + this tool_use
              const assistantContent = [
                ...pendingText,
                {
                  type: "tool_use",
                  id: c.toolCallId,
                  name: c.toolName,
                  input: c.args,
                },
              ];
              apiMessages.push({ role: "assistant", content: assistantContent });
              pendingText = [];

              // Emit matching user tool_result message
              const resultContent = c.result !== undefined
                ? (typeof c.result === "string" ? c.result : JSON.stringify(c.result))
                : "Tool call was interrupted and did not complete.";
              apiMessages.push({
                role: "user",
                content: [{
                  type: "tool_result",
                  tool_use_id: c.toolCallId,
                  content: resultContent,
                }],
              });
            } else {
              pendingText.push(c);
            }
          }

          // Any remaining text after the last tool call → standalone assistant message
          if (pendingText.length > 0) {
            apiMessages.push({ role: "assistant", content: pendingText });
          }
        } else {
          // User message — convert text parts
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const content: any[] = [];
          for (const c of m.content) {
            if (c.type === "text") {
              content.push({ type: "text", text: c.text });
            } else {
              content.push(c);
            }
          }
          apiMessages.push({ role: m.role, content });
        }
      }

      ws.send(JSON.stringify({
        messages: apiMessages,
        model: config.model,
        useMcpServer: config.useMcpServer,
        mcpServerUrl,
      }));

      // Accumulate content parts to yield progressively
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const parts: any[] = [];
      let currentText = "";
      // Map toolCallId -> index in parts, so we can update result later
      const toolPartIndex: Record<string, number> = {};
      let done = false;

      while (!done) {
        const evt = await waitForMessage(ws, abortSignal);
        const type = evt.type as string;

        switch (type) {
          case "text_delta": {
            currentText += evt.text as string;
            // Find or create a text part
            const lastPart = parts[parts.length - 1];
            if (lastPart && lastPart.type === "text") {
              lastPart.text = currentText;
            } else {
              parts.push({ type: "text" as const, text: currentText });
            }
            yield { content: [...parts] };
            break;
          }

          case "tool_call_start": {
            // Early notification: tool invocation starting, input still streaming.
            currentText = "";
            const earlyId = (evt.id as string) || `tool_${Date.now()}`;
            const earlyIdx = parts.length;
            toolPartIndex[evt.name as string] = earlyIdx;
            parts.push({
              type: "tool-call" as const,
              toolCallId: earlyId,
              toolName: evt.name as string,
              args: {},
              argsText: "Generating input…",
            });
            yield { content: [...parts] };
            break;
          }

          case "tool_call": {
            // Full tool input received — update existing part or create new.
            const tcName = evt.name as string;
            const existingIdx = toolPartIndex[tcName];
            if (existingIdx !== undefined && parts[existingIdx]) {
              parts[existingIdx] = {
                ...parts[existingIdx],
                toolCallId: (evt.id as string) || parts[existingIdx].toolCallId,
                args: evt.input as Record<string, unknown>,
                argsText: JSON.stringify(evt.input),
              };
            } else {
              currentText = "";
              const toolCallId = (evt.id as string) || `tool_${Date.now()}`;
              const idx = parts.length;
              toolPartIndex[tcName] = idx;
              parts.push({
                type: "tool-call" as const,
                toolCallId,
                toolName: tcName,
                args: evt.input as Record<string, unknown>,
                argsText: JSON.stringify(evt.input),
              });
            }
            yield { content: [...parts] };
            break;
          }

          case "tool_result": {
            // Update the matching tool-call part with the full result object
            // (text, execution info, files) so McpToolUI can display them.
            const name = evt.name as string;
            const idx = toolPartIndex[name];
            if (idx !== undefined && parts[idx]) {
              const toolResult: Record<string, unknown> = {
                text: evt.result as string,
              };
              if (evt.execution) toolResult.execution = evt.execution;
              if (evt.files) toolResult.files = evt.files;
              parts[idx] = { ...parts[idx], result: toolResult };
            }
            yield { content: [...parts] };
            break;
          }

          case "response": {
            // Final response — make sure text is included
            if (evt.content && typeof evt.content === "string" && evt.content !== currentText) {
              const lastPart = parts[parts.length - 1];
              if (lastPart && lastPart.type === "text") {
                lastPart.text = evt.content as string;
              } else {
                parts.push({ type: "text" as const, text: evt.content as string });
              }
            }
            yield { content: [...parts] };
            done = true;
            break;
          }

          case "error": {
            throw new Error((evt.message as string) || "Server error");
          }

          case "status":
          case "tool_input_delta":
          case "ping": {
            // Informational / keepalive — ignore
            break;
          }

          default:
            break;
        }
      }

      ws.close();
    },
  };
}
