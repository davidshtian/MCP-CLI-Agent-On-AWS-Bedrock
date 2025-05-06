#!/usr/bin/env python3
"""Q-2001 - An agentic command-line AI assistant powered by AWS Bedrock"""

import os, json, argparse, asyncio, uuid
import boto3
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.theme import Theme
from mcp_client import MCPClient

# Setup console with streamlined theme
console = Console(
    theme=Theme(
        {
            "user": "bold blue",
            "assistant": "bold green",
            "system": "yellow",
            "error": "bold red",
        }
    )
)


class Q2001:
    """Q-2001 - AI assistant with tool capabilities"""

    def __init__(self, model=None, profile=None, region=None):
        # Initialize settings
        self.model_id = model or "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
        self.region = (
            region
            or os.environ.get("AWS_REGION")
            or boto3.Session().region_name
            or "us-east-1"
        )
        self.history = []
        self.running = True

        # Set up AWS client and MCP client for tools
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        self.bedrock = session.client("bedrock-runtime", region_name=self.region)
        self.mcp = MCPClient()

        # Load MCP configuration
        self._register_mcp_servers()

    def _load_mcp_config(self):
        """Load MCP configuration from JSON file"""
        config_path = os.path.expanduser("~/.q2001_mcp_config.json")
        try:
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    return json.load(f)
        except Exception as e:
            console.print(f"[error]Error loading MCP config: {str(e)}[/error]")
        return {"mcpServers": {}}

    def _register_mcp_servers(self):
        """Register all MCP servers from config"""
        config = self._load_mcp_config()
        for server_name, server_info in config.get("mcpServers", {}).items():
            if "command" in server_info and "args" in server_info:
                self.mcp.register_server(
                    name=server_name,
                    command=server_info["command"],
                    args=server_info["args"],
                )

    async def _run_tool_call(self, tool_call):
        """Run a tool call and return the result"""
        try:
            result = await self.mcp.call_tool(tool_call["name"], tool_call["input"])
            return f"Tool: {tool_call['name']} Result: {result}"
        except Exception as e:
            return f"Tool: {tool_call['name']} Error: {str(e)}"

    def _process_response(self, stream):
        """Process streaming response and extract tool calls"""
        current_response = ""
        tool_calls = []
        tool_info = None
        json_accumulator = ""

        for event in stream:
            # Handle text content
            if "contentBlockDelta" in event and "delta" in event["contentBlockDelta"]:
                delta = event["contentBlockDelta"]["delta"]
                if "text" in delta:
                    chunk_text = delta["text"]
                    print(chunk_text, end="", flush=True)
                    current_response += chunk_text
                elif "toolUse" in delta and "input" in delta["toolUse"] and tool_info:
                    json_accumulator += delta["toolUse"]["input"]

            # Handle tool call start
            if "contentBlockStart" in event and "start" in event["contentBlockStart"]:
                start = event["contentBlockStart"]["start"]
                if "toolUse" in start:
                    tool_name = start["toolUse"].get("name", "")
                    tool_id = start["toolUse"].get("toolUseId", "") or str(uuid.uuid4())
                    tool_info = {"name": tool_name, "id": tool_id}
                    print()  # Add a line break before the tool call
                    json_accumulator = ""

            # Complete tool call
            if "contentBlockStop" in event and tool_info:
                try:
                    tool_input = json.loads(json_accumulator)
                except:
                    tool_input = {}

                # Display the tool call panel
                input_str = (
                    json.dumps(tool_input, indent=2)
                    if tool_input
                    else "No input parameters"
                )
                console.print(
                    Panel(
                        f"Using Tool: {tool_info['name']}\nTool Input: {input_str}",
                        title="Tool Call",
                        border_style="yellow",
                    )
                )

                tool_calls.append(
                    {
                        "name": tool_info["name"],
                        "input": tool_input,
                        "id": tool_info["id"],
                    }
                )
                tool_info = None
                json_accumulator = ""

            # Check if message is complete
            if "messageStop" in event:
                return (
                    current_response,
                    tool_calls,
                    event["messageStop"].get("stopReason", "") != "tool_use",
                )

        return current_response, tool_calls, False

    async def get_response(self, user_input):
        """Get response with tool support - simplified workflow"""
        if not user_input.strip():
            return "Please enter a message."

        try:
            # Initialize tools if needed
            if not self.mcp.initialized and self.mcp.has_servers():
                await self.mcp.initialize()

            # Format message history for API
            messages = self._format_history()
            messages.append({"role": "user", "content": [{"text": user_input}]})

            # Streamlined system prompt
            system_message = {
                "text": "You are Q-2001, a helpful AI agent with tool access. Use tools when needed to satisfy user requests. Respond in the same language as the user's query. Think carefully about when tools are necessary and use them only when appropriate."
            }

            # Conversation loop for multiple tool calls
            full_response = ""
            finished = False
            first_response = True

            while not finished:
                if first_response:
                    console.print("[assistant]Q-2001:[/assistant] ", end="")
                    first_response = False

                # Prepare API parameters
                api_params = {
                    "modelId": self.model_id,
                    "messages": messages,
                    "system": [system_message],
                    "inferenceConfig": {"maxTokens": 32768, "temperature": 0.7},
                }

                # Add tools if available
                if self.mcp.initialized:
                    bedrock_tools = self.mcp.get_bedrock_format()
                    if bedrock_tools:
                        api_params["toolConfig"] = bedrock_tools

                # Call model API and process response
                response = self.bedrock.converse_stream(**api_params)
                current_response, tool_calls, conversation_finished = (
                    self._process_response(response.get("stream", []))
                )
                full_response += current_response

                # Handle tool calls if any
                if tool_calls:
                    # Create assistant message with tool uses
                    assistant_message = {
                        "role": "assistant",
                        "content": [{"text": full_response}],
                    }

                    # Add tool calls to the assistant message
                    for tool_call in tool_calls:
                        assistant_message["content"].append(
                            {
                                "toolUse": {
                                    "toolUseId": tool_call["id"],
                                    "name": tool_call["name"],
                                    "input": tool_call["input"],
                                }
                            }
                        )

                    # Run tools and process results
                    tool_results = await asyncio.gather(
                        *[self._run_tool_call(tc) for tc in tool_calls]
                    )
                    tool_result_messages = self._process_tool_results(
                        tool_results, tool_calls
                    )

                    # Update messages and history
                    messages.append(assistant_message)
                    messages.extend(tool_result_messages)
                    self.history.append(assistant_message)
                    self.history.extend(tool_result_messages)
                else:
                    # If no tool calls, conversation is complete
                    finished = conversation_finished

            return full_response

        except Exception as e:
            console.print(f"[error]Error: {str(e)}[/error]")
            return f"Error: {str(e)}"

    def _format_history(self):
        """Format conversation history for the API"""
        messages = []
        history_items = self.history[-10:]  # Get last 10 messages for context

        for i, item in enumerate(history_items):
            # Skip the last history item if it's a user message (to avoid duplication)
            if (
                i == len(history_items) - 1
                and isinstance(item, tuple)
                and item[0] == "user"
            ):
                continue

            if isinstance(item, tuple):
                role, content = item
                if role == "user":
                    messages.append({"role": "user", "content": [{"text": content}]})
                elif role == "assistant":
                    messages.append(
                        {"role": "assistant", "content": [{"text": content}]}
                    )
            elif isinstance(item, dict):  # This handles tool messages
                messages.append(item)  # Add the pre-formatted message directly

        return messages

    def _process_tool_results(self, tool_results, tool_calls):
        """Process tool results and return formatted messages"""
        tool_result_messages = []

        for result, tool_call in zip(tool_results, tool_calls):
            tool_result = (
                result.split(" Result:", 1)[1].strip()
                if " Result:" in result
                else result
            )

            # Display tool result
            panel_style = "green" if "Error:" not in tool_result else "red"
            console.print(
                Panel(tool_result, title="Tool Call Result", border_style=panel_style)
            )

            # Create tool result message
            tool_result_messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "toolResult": {
                                "toolUseId": tool_call["id"],
                                "content": [{"text": tool_result}],
                                "status": (
                                    "success"
                                    if "Error:" not in tool_result
                                    else "error"
                                ),
                            }
                        }
                    ],
                }
            )

        return tool_result_messages

    def handle_command(self, cmd):
        """Handle special commands"""
        cmd_parts = cmd.lower().strip().split()
        cmd_base = cmd_parts[0]

        # Command handlers dictionary
        command_handlers = {
            "/quit": self._cmd_quit,
            "/exit": self._cmd_quit,
            "/help": self._cmd_help,
            "/clear": self._cmd_clear,
            "/model": self._cmd_model,
            "/tools": self._cmd_tools,
        }

        handler = command_handlers.get(cmd_base)
        return (
            handler(cmd_parts[1:] if len(cmd_parts) > 1 else []) if handler else False
        )

    def _cmd_quit(self, args):
        """Handle quit command"""
        self.running = False
        console.print("[system]Thank you for using Q-2001. Goodbye![/system]")
        return True

    def _cmd_help(self, args):
        """Handle help command"""
        console.print(
            Markdown(
                """
            # Q-2001 Commands
            - `/quit` or `/exit`: Exit the application
            - `/help`: Show this help message
            - `/clear`: Clear the conversation history
            - `/model <model_id>`: Change the AI model
            - `/tools`: List all available tools
            """
            )
        )
        return True

    def _cmd_clear(self, args):
        """Handle clear command"""
        self.history = []
        console.print("[system]Conversation history cleared.[/system]")
        return True

    def _cmd_model(self, args):
        """Handle model command"""
        if not args:
            console.print("[system]Please specify a model ID.[/system]")
            return True

        self.model_id = " ".join(args)
        console.print(f"[system]Model changed to: {self.model_id}[/system]")
        return True

    def _cmd_tools(self, args):
        """Handle tools command"""
        if not self.mcp.initialized:
            console.print("[system]Initializing tools...[/system]")
            return True

        if not self.mcp.servers:
            console.print(
                "[system]No tools available. Configure in ~/.q2001_mcp_config.json[/system]"
            )
            return True

        console.print("[system]Available tools:[/system]")
        for server_name, server_info in self.mcp.servers.items():
            console.print(f"[system]Server: {server_name}[/system]")
            for tool in server_info.get("tools", []):
                console.print(
                    f"[system]  - {tool['name']}: {tool['description']}[/system]"
                )
        return True

    async def run_async(self):
        """Run the chat interface (async version)"""
        # Welcome message
        console.print(
            Panel.fit(
                "Welcome to Q-2001 - Your AI Assistant powered by AWS Bedrock\n"
                "Type '/help' for commands, '/quit' to exit",
                title="Q-2001",
                border_style="green",
            )
        )

        # Initialize MCP if servers are registered
        if self.mcp.has_servers():
            console.print("[system]Initializing MCP servers...[/system]")
            await self.mcp.initialize()

            # Show loaded servers in bulleted list format
            loaded_servers = [
                name for name, info in self.mcp.servers.items() if info.get("tools")
            ]
            if loaded_servers:
                console.print("[system]MCP servers loaded:[/system]")
                for server in loaded_servers:
                    console.print(f"[system]- {server}[/system]")
            else:
                console.print(
                    "[system]No MCP servers were successfully loaded[/system]"
                )

        # Initial greeting
        console.print(
            "[assistant]Q-2001:[/assistant] Hello! I'm your assistant. How can I help you today?"
        )

        # Main interaction loop
        while self.running:
            try:
                print("\033[1;34m\n\nHuman: \033[0m", end="", flush=True)
                user_input = input()

                if not user_input.strip():
                    continue

                # Handle commands or get response
                if user_input.startswith("/") and self.handle_command(user_input):
                    continue

                # Add to history and get response
                self.history.append(("user", user_input))
                response = await self.get_response(user_input)

                # Add to history if not a tool interaction
                if not any(isinstance(item, dict) for item in self.history[-2:]):
                    self.history.append(("assistant", response))

            except KeyboardInterrupt:
                console.print("[system]Exiting Q-2001. Goodbye![/system]")
                self.running = False
            except Exception as e:
                console.print(f"[error]Error: {str(e)}[/error]")

    def run(self):
        """Run the chat interface"""
        asyncio.run(self.run_async())


def main():
    """Parse arguments and start Q-2001"""
    parser = argparse.ArgumentParser(
        description="Q-2001 - AI Assistant powered by AWS Bedrock"
    )
    parser.add_argument("--model", help="Bedrock model ID to use")
    parser.add_argument("--profile", help="AWS profile to use")
    parser.add_argument("--region", help="AWS region to use")
    parser.add_argument(
        "--version", action="store_true", help="Show version information"
    )

    args = parser.parse_args()

    if args.version:
        print("Q-2001 v1.5.0")
        return

    # Start chat
    Q2001(model=args.model, profile=args.profile, region=args.region).run()


if __name__ == "__main__":
    main()
