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
      // When an assistant message contains tool-call parts with results,
      // we must emit the assistant message (with tool_use blocks) followed
      // by a user message (with tool_result blocks) — Anthropic requires this.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const apiMessages: any[] = [];
      for (const m of messages) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const content: any[] = [];
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const toolResults: any[] = [];

        for (const c of m.content) {
          if (c.type === "text") {
            content.push({ type: "text", text: c.text });
          } else if (c.type === "tool-call") {
            content.push({
              type: "tool_use",
              id: c.toolCallId,
              name: c.toolName,
              input: c.args,
            });
            // If this tool call has a result, queue a tool_result block
            if (c.result !== undefined) {
              toolResults.push({
                type: "tool_result",
                tool_use_id: c.toolCallId,
                content: typeof c.result === "string" ? c.result : JSON.stringify(c.result),
              });
            }
          } else {
            content.push(c);
          }
        }

        apiMessages.push({ role: m.role, content });

        // Append the required user tool_result message after the assistant message
        if (toolResults.length > 0) {
          apiMessages.push({ role: "user", content: toolResults });
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

          case "tool_call": {
            // A new tool invocation is starting.  Reset text accumulator
            // so subsequent text_delta events go into a new text part.
            currentText = "";
            const toolCallId = (evt.id as string) || `tool_${Date.now()}`;
            const idx = parts.length;
            toolPartIndex[evt.name as string] = idx;
            parts.push({
              type: "tool-call" as const,
              toolCallId,
              toolName: evt.name as string,
              args: evt.input as Record<string, unknown>,
              argsText: JSON.stringify(evt.input),
            });
            yield { content: [...parts] };
            break;
          }

          case "tool_result": {
            // Update the matching tool-call part with the result
            const name = evt.name as string;
            const idx = toolPartIndex[name];
            if (idx !== undefined && parts[idx]) {
              parts[idx] = { ...parts[idx], result: evt.result as string };
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

          case "status": {
            // Informational (e.g. "Loaded 43 tools") — ignore
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
