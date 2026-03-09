/**
 * Playground Runtime Adapter for @assistant-ui/react
 * Connects to backend Bedrock API for Claude inference with MCP tool support
 */

import type { ChatModelAdapter, ChatModelRunOptions, ChatModelRunResult } from "@assistant-ui/react";
import type { MutableRefObject } from "react";
import { API_BASE_URL } from "./api";

export interface PlaygroundConfig {
  model: string;
  useMcpServer: boolean;
}

export function createPlaygroundAdapter(
  configRef: MutableRefObject<PlaygroundConfig>
): ChatModelAdapter {
  return {
    async *run({ messages, abortSignal }: ChatModelRunOptions): AsyncGenerator<ChatModelRunResult> {
      const config = configRef.current;
      
      // Get settings from localStorage
      const mcpServerUrl = localStorage.getItem('mcp_server_url') || 
        `${API_BASE_URL}/mcp`;
      const bedrockApiKey = localStorage.getItem('bedrock_api_key') || '';
      const bedrockEndpoint = localStorage.getItem('bedrock_endpoint') || '';

      const response = await fetch(`${API_BASE_URL}/playground/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          messages: messages.map(m => ({
            role: m.role,
            content: m.content.map(c => {
              if (c.type === 'text') return { type: 'text', text: c.text };
              if (c.type === 'tool-call') return {
                type: 'tool_use',
                id: c.toolCallId,
                name: c.toolName,
                input: c.args,
              };
              return c;
            }),
          })),
          model: config.model,
          use_mcp_server: config.useMcpServer,
          mcp_server_url: mcpServerUrl,
          bedrock_api_key: bedrockApiKey,
          bedrock_endpoint: bedrockEndpoint,
        }),
        signal: abortSignal,
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(error.detail || `API error: ${response.status}`);
      }

      const data = await response.json();
      
      // Convert response to assistant-ui format
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const content: any[] = [];
      
      for (const block of data.content || []) {
        if (block.type === 'text') {
          content.push({ type: 'text' as const, text: block.text });
        } else if (block.type === 'tool_use') {
          content.push({
            type: 'tool-call' as const,
            toolCallId: block.id,
            toolName: block.name,
            args: block.input,
            argsText: JSON.stringify(block.input),
          });
        } else if (block.type === 'tool_result') {
          content.push({
            type: 'tool-result' as const,
            toolCallId: block.tool_use_id,
            result: block.content,
          });
        }
      }

      yield { content };
    },
  };
}
