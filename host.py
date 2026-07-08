import asyncio
import json
import traceback
from contextlib import AsyncExitStack
from typing import Any

from google import genai
from google.genai import types

from client import MCPClient
from dotenv import load_dotenv

load_dotenv()

class ChatHost:
    def __init__(self):
        self.mcp_clients: list[MCPClient] = [
            MCPClient("./weather_USA.py"),
            MCPClient("./weather_Israel.py"),
        ]
        self.tool_clients: dict[str, tuple[MCPClient, str]] = {}
        self.clients_connected = False
        self.exit_stack = AsyncExitStack()
        self.genai_client = genai.Client()
        self.genai_chat = self.genai_client.aio.chats.create(
            model="gemini-2.5-flash"
        )

    async def connect_mcp_clients(self):
        """Connect all configured MCP clients once."""
        if self.clients_connected:
            return

        for client in self.mcp_clients:
            if client.session is None:
                await client.connect_to_server()

        if not self.mcp_clients:
            raise RuntimeError("No MCP clients are connected")

        self.clients_connected = True

    async def get_available_tools(self) -> list[dict[str, Any]]:
        """Collect tools from all MCP clients and map them back to their owner."""
        await self.connect_mcp_clients()
        self.tool_clients = {}
        available_tools: list[dict[str, Any]] = []

        for client in self.mcp_clients:
            if client.session is None:
                print(f"Warning: MCP client {client.client_name} is not connected, skipping")
                continue

            try:
                response = await client.session.list_tools()
                for tool in response.tools:
                    exposed_name = f"{client.client_name}__{tool.name}"
                    if exposed_name in self.tool_clients:
                        raise RuntimeError(f"Duplicate tool name detected: {exposed_name}")

                    self.tool_clients[exposed_name] = (client, tool.name)
                    available_tools.append(
                        {
                            "name": exposed_name,
                            "description": f"[{client.client_name}] {tool.description}",
                            "input_schema": tool.inputSchema,
                        }
                    )
            except Exception as e:
                print(f"Warning: Failed to get tools from {client.client_name}: {str(e)}")
                continue

        if not available_tools:
            raise RuntimeError("No tools available from any MCP client")

        return available_tools


    def _build_tool_definitions(self, available_tools: list[dict[str, Any]]) -> list[types.Tool]:
        return [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name=tool["name"],
                        description=tool.get("description", "MCP tool"),
                        parameters=tool.get("input_schema", {"type": "object"}),
                    )
                ]
            )
            for tool in available_tools
        ]


    def _extract_response_text(self, response: Any) -> str:
        if hasattr(response, "text") and response.text:
            return response.text

        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return ""

        content = getattr(candidates[0], "content", None)
        if content is None:
            return ""

        if hasattr(content, "text") and content.text:
            return content.text

        texts = []
        for part in getattr(content, "parts", []) or []:
            if hasattr(part, "text") and part.text:
                texts.append(part.text)
            elif hasattr(part, "plain_text") and part.plain_text:
                texts.append(part.plain_text)

        return "".join(texts).strip()


    def _extract_tool_call(self, response: Any) -> Any:
        function_calls = getattr(response, "function_calls", None) or []
        if function_calls:
            return function_calls[0]

        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return None

        content = getattr(candidates[0], "content", None)
        if content is None:
            return None

        for part in getattr(content, "parts", []) or []:
            tool_call = getattr(part, "function_call", None)
            if tool_call is not None:
                return tool_call

        return None


    def _normalize_tool_args(self, args: Any) -> dict[str, Any]:
        if args is None:
            return {}
        if isinstance(args, str):
            try:
                return json.loads(args)
            except json.JSONDecodeError:
                return {"raw": args}
        if isinstance(args, dict):
            return args
        return {"raw": args}


    def _normalize_tool_result(self, result: Any) -> str:
        if result is None:
            return ""

        content = getattr(result, "content", result)
        if isinstance(content, str):
            return content
        if hasattr(content, "text") and content.text:
            return content.text

        if hasattr(content, "parts"):
            parts = []
            for part in getattr(content, "parts") or []:
                part_text = getattr(part, "text", None) or getattr(part, "plain_text", None)
                if part_text:
                    parts.append(part_text)
            if parts:
                return "".join(parts)

        return repr(content)


    async def _generate_model_response(
        self, query: str, tool_definitions: list[types.Tool]
    ) -> Any:
        return await self.genai_chat.send_message(
            query,
            config={
                "tools": tool_definitions,
                "tool_config": {"function_calling_config": {"mode": "auto"}},
                "max_output_tokens": 1000,
            },
        )


    async def process_query(self, query: str) -> str:
        """Process a query using Gemini and available tools."""
        available_tools = await self.get_available_tools()
        tool_definitions = self._build_tool_definitions(available_tools)
        final_text = []
        prompt = query

        while True:
            response = await self._generate_model_response(prompt, tool_definitions)
            tool_call = self._extract_tool_call(response)
            assistant_text = self._extract_response_text(response)
            if assistant_text:
                final_text.append(assistant_text)

            if tool_call is None:
                break

            tool_name = getattr(tool_call, "name", None)
            tool_args = self._normalize_tool_args(getattr(tool_call, "args", None))

            if tool_name not in self.tool_clients:
                raise RuntimeError(f"Unknown tool requested by model: {tool_name}")

            client, original_tool_name = self.tool_clients[tool_name]
            if client.session is None:
                raise RuntimeError(f"MCP client {client.client_name} is not connected")

            result = await client.session.call_tool(original_tool_name, tool_args)
            tool_result_text = self._normalize_tool_result(result)
            final_text.append(f"[Calling tool {tool_name} with args {tool_args}]")
            prompt = f"Tool {tool_name} returned: {tool_result_text}"

        return "\n".join(final_text)
    
    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")
        
        while True:
            try:
                query = input("\nQuery: ").strip()
                
                if query.lower() == 'quit':
                    break
                
                response = await self.process_query(query)
                print("\n" + response)
                
            except Exception as e:
                print(f"\nchat_loop Error: {type(e).__name__}: {repr(e)}")
                traceback.print_exc()

    async def cleanup(self):
        """Clean up resources"""
        for client in reversed(self.mcp_clients):
            await client.cleanup()
        await self.exit_stack.aclose()
        
        
async def main():
    host = ChatHost()
    try:
        await host.chat_loop()
    finally:
        await host.cleanup()
        
if __name__ == "__main__":
    asyncio.run(main())
