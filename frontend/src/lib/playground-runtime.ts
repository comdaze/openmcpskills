/**
 * Playground Runtime Adapter for @assistant-ui/react
 * Connects to backend Bedrock API for Claude inference with MCP tool support
 */

import type { ChatModelAdapter, ChatModelRunOptions } from "@assistant-ui/react";
import type { MutableRefObject } from "react";

export interface PlaygroundConfig {
  model: string;
  useMcpServer: boolean;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

export function createPlaygroundAdapter(
  configRef: MutableRefObject<PlaygroundConfig>
): ChatModelAdapter {
  return {
    async *run({ messages, abortSignal }: ChatModelRunOptions) {
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
      const content: Array<{ type: string; text?: string; toolCallId?: string; toolName?: string; args?: unknown; result?: unknown }> = [];
      
      for (const block of data.content || []) {
        if (block.type === 'text') {
          content.push({ type: 'text', text: block.text });
        } else if (block.type === 'tool_use') {
          content.push({
            type: 'tool-call',
            toolCallId: block.id,
            toolName: block.name,
            args: block.input,
          });
        } else if (block.type === 'tool_result') {
          content.push({
            type: 'tool-result',
            toolCallId: block.tool_use_id,
            result: block.content,
          });
        }
      }

      yield {
        content,
      };
    },
  };
}
