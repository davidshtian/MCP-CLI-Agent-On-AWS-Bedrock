"""
MCP Client module for Q-2001
Provides integration with Model Context Protocol servers for extended functionality
"""

import asyncio
import json
import logging
import subprocess
import sys
from typing import Dict, List, Any

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MCPClient:
    """Client for Model Context Protocol servers"""

    def __init__(self, debug_mode=False):
        """Initialize MCP client"""
        self.servers = {}  # Dictionary of server name -> server info
        self.initialized = False
        self.mcp = None
        self.stdio = None

        # Set debug level
        logger.setLevel(logging.DEBUG if debug_mode else logging.INFO)

    def has_servers(self):
        """Check if any servers are registered"""
        return len(self.servers) > 0

    def register_server(self, name: str, command: str, args: List[str]) -> bool:
        """
        Register an MCP server

        Args:
            name: Unique identifier for this server
            command: Command to run (e.g., npx, python)
            args: List of arguments to pass to the command

        Returns:
            bool: Success status
        """
        try:
            # Check if command is available
            try:
                subprocess.run([command, "--version"], check=True, capture_output=True)
            except Exception as e:
                logger.error(f"Command '{command}' is not available: {str(e)}")
                return False

            # Register server
            self.servers[name] = {
                "name": name,
                "command": command,
                "args": args,
                "tools": []
            }
            logger.debug(f"Registered server '{name}' with command: {command}")
            return True

        except Exception as e:
            logger.error(f"Failed to register server '{name}': {str(e)}")
            return False

    async def _import_mcp(self):
        """Import or install MCP modules"""
        try:
            # Try to import
            import mcp.client
            from mcp.client import stdio
            self.mcp = mcp.client
            self.stdio = stdio
        except ImportError:
            # Install if not found
            logger.debug("Installing mcp-client package...")
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", "mcp-client"], 
                              check=True, capture_output=True)
                import mcp.client
                from mcp.client import stdio
                self.mcp = mcp.client
                self.stdio = stdio
            except Exception as e:
                logger.error(f"Failed to install mcp-client: {str(e)}")
                raise

    async def initialize(self):
        """Initialize all registered servers"""
        if self.initialized:
            return True

        try:
            # Import MCP modules
            await self._import_mcp()

            # Initialize each server
            success_count = 0
            for server_name, server in list(self.servers.items()):
                try:
                    await self._initialize_server(server)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to initialize server '{server_name}': {str(e)}")

            # Set initialized flag if any servers were initialized
            self.initialized = success_count > 0
            return self.initialized

        except Exception as e:
            logger.error(f"Failed to initialize MCP client: {str(e)}")
            return False

    async def _initialize_server(self, server):
        """Initialize a single server and get its tools"""
        # Create parameters for server process
        params = self.stdio.StdioServerParameters(
            command=server["command"],
            args=server["args"],
            name=f"q-2001-{server['name']}"
        )

        # Start server and create session
        async with self.stdio.stdio_client(params) as (read, write):
            async with self.mcp.session.ClientSession(read, write) as session:
                # Initialize the session
                await session.initialize()

                # List available tools
                tools_result = await session.list_tools()

                if tools_result and hasattr(tools_result, 'tools'):
                    server["tools"] = [{
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.inputSchema,
                        "server": server["name"]  # Track which server provides this tool
                    } for tool in tools_result.tools]

                    logger.debug(f"Server '{server['name']}' initialized with {len(server['tools'])} tools")
                    return True
                else:
                    logger.warning(f"No tools found for server '{server['name']}'")
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
            raise ValueError(f"Tool '{tool_name}' not found on any server")

        try:
            # Create a fresh session for the tool call
            params = self.stdio.StdioServerParameters(
                command=server_info["command"],
                args=server_info["args"],
                name=f"q-2001-tool-call"
            )

            # Execute tool with timeout protection
            async with self.stdio.stdio_client(params) as (read, write):
                async with self.mcp.session.ClientSession(read, write) as session:
                    await session.initialize()

                    result = await asyncio.wait_for(
                        session.call_tool(tool_name, tool_input),
                        timeout=30.0
                    )

                    # Format response as JSON string if possible
                    if isinstance(result, (dict, list)):
                        return json.dumps(result, indent=2)
                    return str(result)

        except asyncio.TimeoutError:
            logger.error(f"Timeout calling tool '{tool_name}'")
            return f"Error: Tool call timed out after 30 seconds"
        except Exception as e:
            logger.error(f"Error calling tool '{tool_name}': {str(e)}")
            return f"Error: {str(e)}"

    def get_bedrock_format(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get tools in the format required for Bedrock API"""
        if not self.initialized:
            return None

        tools = []
        for server in self.servers.values():
            for tool in server.get("tools", []):
                tools.append({
                    "toolSpec": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "inputSchema": {"json": tool["inputSchema"]}
                    }
                })

        return {"tools": tools} if tools else None