"""
MCP Client module for Q-2001
Provides integration with Model Context Protocol servers
"""

import asyncio
import json
import subprocess
from typing import Dict, List, Any

# Import MCP modules
import mcp.client
from mcp.client import stdio


class MCPClient:
    """Client for Model Context Protocol servers"""

    def __init__(self):
        """Initialize MCP client"""
        self.servers = {}  # Dictionary of server name -> server info
        self.initialized = False

    def has_servers(self):
        """Check if any servers are registered"""
        return len(self.servers) > 0

    def register_server(
        self, name: str, command: str, args: List[str], env: Dict[str, str] = None
    ) -> bool:
        """Register an MCP server"""
        try:
            # Register server
            self.servers[name] = {
                "name": name,
                "command": command,
                "args": args,
                "env": env,
                "tools": [],
            }
            return True
        except:
            return False

    async def initialize(self):
        """Initialize all registered servers"""
        if self.initialized or not self.servers:
            return True

        # Initialize each server
        for server in list(self.servers.values()):
            try:
                await self._initialize_server(server)
            except:
                pass

        self.initialized = any(server.get("tools") for server in self.servers.values())
        return self.initialized

    async def _initialize_server(self, server):
        """Initialize a single server and get its tools"""
        params = stdio.StdioServerParameters(
            command=server["command"],
            args=server["args"],
            name=f"q-2001-{server['name']}",
            env=server.get("env"),  # Pass environment variables if available
        )

        # Start server and create session
        async with stdio.stdio_client(params) as (read, write):
            async with mcp.client.session.ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()

                if tools_result and hasattr(tools_result, "tools"):
                    server["tools"] = [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": tool.inputSchema,
                            "server": server["name"],
                        }
                        for tool in tools_result.tools
                    ]
                    return True
                return False

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools from all servers"""
        if not self.initialized:
            await self.initialize()

        all_tools = []
        for server in self.servers.values():
            all_tools.extend(server.get("tools", []))
        return all_tools

    async def call_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """Call a tool with the given input"""
        if not self.initialized:
            await self.initialize()

        # Find server with this tool
        server_info = None
        for server in self.servers.values():
            if any(tool["name"] == tool_name for tool in server.get("tools", [])):
                server_info = server
                break

        if not server_info:
            return f"Error: Tool '{tool_name}' not found"

        try:
            # Create a fresh session for the tool call
            params = stdio.StdioServerParameters(
                command=server_info["command"],
                args=server_info["args"],
                name=f"q-2001-tool-call",
                env=server_info.get("env"),  # Pass environment variables if available
            )

            # Execute tool with timeout protection
            async with stdio.stdio_client(params) as (read, write):
                async with mcp.client.session.ClientSession(read, write) as session:
                    await session.initialize()

                    result = await asyncio.wait_for(
                        session.call_tool(tool_name, tool_input), timeout=30.0
                    )

                    # Format response
                    if isinstance(result, (dict, list)):
                        return json.dumps(result, indent=2)
                    return str(result)

        except asyncio.TimeoutError:
            return "Error: Tool call timed out after 30 seconds"
        except Exception as e:
            return f"Error: {str(e)}"

    def get_bedrock_format(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get tools in the format required for Bedrock API"""
        if not self.initialized:
            return None

        tools = []
        for server in self.servers.values():
            for tool in server.get("tools", []):
                tools.append(
                    {
                        "toolSpec": {
                            "name": tool["name"],
                            "description": tool["description"],
                            "inputSchema": {"json": tool["inputSchema"]},
                        }
                    }
                )

        return {"tools": tools} if tools else None
