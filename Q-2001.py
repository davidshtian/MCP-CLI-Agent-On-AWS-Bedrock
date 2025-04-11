#!/usr/bin/env python3
"""Q-2001 - An agentic command-line AI assistant powered by AWS Bedrock"""

import os, json, argparse, asyncio, uuid
import boto3
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.theme import Theme

# Import MCP client
from mcp_client import MCPClient

# Setup console
console = Console(
    theme=Theme({
        "user": "bold blue",
        "assistant": "bold green", 
        "system": "yellow",
        "error": "bold red",
        "agent": "bold magenta",
        "plan": "cyan"
    })
)


class Q2001:
    """Q-2001 - Agentic AI Assistant powered by AWS Bedrock with tool capabilities"""

    def __init__(self, model=None, profile=None, region=None):
        # Initialize settings
        self.model_id = model or "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
        self.region = region or os.environ.get("AWS_REGION") or boto3.Session().region_name or "us-east-1"
        self.history = []
        self.running = True

        # Set up AWS client
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        self.bedrock = session.client("bedrock-runtime", region_name=self.region)

        # Set up MCP client for tools
        self.mcp = MCPClient()
        self._register_mcp_servers()

    def _load_mcp_config(self):
        """Load MCP configuration from JSON file"""
        config_path = os.path.expanduser("~/.q2001_mcp_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                console.print(f"[error]Error loading MCP config: {str(e)}[/error]")
        return {"mcpServers": {}}

    def _register_mcp_servers(self):
        """Register all MCP servers from config"""
        config = self._load_mcp_config()
        servers = config.get("mcpServers", {})

        for server_name, server_info in servers.items():
            if "command" in server_info and "args" in server_info:
                self.mcp.register_server(
                    name=server_name,
                    command=server_info["command"],
                    args=server_info["args"]
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

            # Handle tool call start
            if "contentBlockStart" in event and "start" in event["contentBlockStart"]:
                start = event["contentBlockStart"]["start"]
                if "toolUse" in start:
                    tool_name = start["toolUse"].get("name", "")
                    tool_id = start["toolUse"].get("toolUseId", "") or str(uuid.uuid4())
                    tool_info = {"name": tool_name, "id": tool_id}
                    print()  # Add a line break before the tool call
                    json_accumulator = ""

            # Accumulate tool input JSON
            if "contentBlockDelta" in event and "delta" in event["contentBlockDelta"]:
                delta = event["contentBlockDelta"]["delta"]
                if "toolUse" in delta and "input" in delta["toolUse"] and tool_info:
                    json_accumulator += delta["toolUse"]["input"]

            # Complete tool call
            if "contentBlockStop" in event and tool_info:
                try:
                    tool_input = json.loads(json_accumulator)
                except:
                    tool_input = {}

                # Display the tool call panel
                input_str = json.dumps(tool_input, indent=2) if tool_input else "No input parameters"
                console.print(
                    Panel(f"Using Tool: {tool_info['name']}\nTool Input: {input_str}",
                         title="Tool Call", border_style="yellow")
                )

                tool_calls.append({
                    "name": tool_info["name"],
                    "input": tool_input,
                    "id": tool_info["id"]
                })
                tool_info = None
                json_accumulator = ""

            # Check if message is complete
            if "messageStop" in event:
                stop_reason = event["messageStop"].get("stopReason", "")
                if stop_reason != "tool_use":
                    return current_response, tool_calls, True

        return current_response, tool_calls, False

    async def _get_model_response(self, messages, system_prompt=None):
        """Get a direct response from the model with specified messages and system"""
        system_prompt = system_prompt or "You are Q-2001, a helpful AI assistant. Be concise and accurate."
        try:
            response = self.bedrock.converse(
                modelId=self.model_id,
                messages=messages,
                system=[{"text": system_prompt}],
                inferenceConfig={"maxTokens": 4096, "temperature": 0.7},
            )
            return response.get("output", {}).get("message", {}).get("content", [{}])[0].get("text", "")
        except Exception as e:
            console.print(f"[error]Error getting model response: {str(e)}[/error]")
            return f"Error: {str(e)}"

    async def _analyze_task(self, user_input):
        """Analyze user input to determine its complexity and requirements"""
        system_prompt = """
        Analyze the user's request and determine:
        1. Is this a simple greeting or question that can be answered directly?
        2. Does this require multi-step planning or tools?

        Output a JSON with (NO MARKDOWN FORMAT, NO quotes like ```json```):
        - is_simple_interaction: true if this is just a greeting or simple question
        - task_description: a clear description of what the user wants
        - requires_tools: true if tools would likely be needed
        - complexity: a number from 1-10 indicating task complexity
        """

        messages = [{"role": "user", "content": [{"text": f"Analyze this input: '{user_input}'"}]}]
        response = await self._get_model_response(messages, system_prompt)

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # Fallback to default values if JSON parsing fails
            console.print(f"[error]Error parsing task analysis response[/error]")
            return {
                "is_simple_interaction": True,
                "task_description": user_input,
                "requires_tools": False,
                "complexity": 1
            }

    async def _create_plan(self, task):
        """Create a step-by-step plan to complete the task"""
        system_prompt = """
        Create a step-by-step plan for completing this task.
        For each step include:
        1. description: What to do in this step
        2. requires_tools: Whether tools are needed (true/false)
        3. tool_names: If tools are required, list the specific tools
        4. expected_outcome: What should result from this step

        Return as a JSON array of steps.
        """

        # Include tool info if available
        tool_info = ""
        if self.mcp.initialized:
            tools = await self.mcp.list_tools()
            if tools:
                tool_info = "Available tools: " + ", ".join([f"{t['name']}" for t in tools])

        messages = [{"role": "user", "content": [{"text": f"Task: {task}. {tool_info} Create a plan."}]}]
        response = await self._get_model_response(messages, system_prompt)

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # Fallback to a simple plan if JSON parsing fails
            console.print(f"[error]Error parsing plan. Using simplified plan instead.[/error]")
            return [{
                "description": f"Complete the task: {task}",
                "requires_tools": False,
                "expected_outcome": "Task completed successfully"
            }]

    async def _execute_step(self, task, step, working_memory):
        """Execute a single step of the plan"""
        system_prompt = f"""
        Execute this specific step in the plan:
        TASK: {task}
        STEP: {step['description']}
        EXPECTED OUTCOME: {step.get('expected_outcome', 'Complete the step')}
        Use tools if needed. Focus only on this step.
        """

        # Include context from working memory
        context = "Context from previous steps: " + " ".join([f"{k}: {v}" for k, v in working_memory.items()])
        message = f"{context} Execute step: {step['description']}"
        return await self.get_response(message, system_prompt=system_prompt)

    async def _reflect(self, task, plan, step_results, working_memory):
        """Reflect on progress and determine if the task is complete"""
        system_prompt = """
        Reflect on task progress and determine if the task is COMPLETE or INCOMPLETE.
        If incomplete, explain what still needs to be done.
        """

        # Build context for reflection
        context = f"TASK: {task} "
        # Include plan steps
        context += "PLAN: " + " ".join([f"{i+1}. {s['description']}" for i, s in enumerate(plan)])
        # Include step results (summary)
        context += " RESULTS: " + " ".join([f"Step {i+1}: {r[:1000]}..." for i, r in enumerate(step_results)])
        # Include working memory
        context += " CONTEXT: " + " ".join([f"{k}: {v}" for k, v in working_memory.items()])

        messages = [{"role": "user", "content": [{"text": context}]}]
        reflection = await self._get_model_response(messages, system_prompt)

        # Fixed logic to properly check for complete vs incomplete
        if "COMPLETE" in reflection.upper() and "INCOMPLETE" not in reflection.upper():
            is_complete = True
        else:
            is_complete = False

        return {"reflection": reflection, "is_complete": is_complete}

    async def execute_agent_workflow(self, user_input):
        """Execute the full agent workflow"""
        # Initialize tools if needed
        if not self.mcp.initialized and self.mcp.has_servers():
            await self.mcp.initialize()

        # 1. Analyze the task
        with console.status("[agent]Analyzing task...[/agent]"):
            task_analysis = await self._analyze_task(user_input)

        # Display task understanding
        task_description = task_analysis.get("task_description", user_input)
        console.print(Panel(f"[agent]Task: {task_description}[/agent]", 
                           title="Understanding", border_style="magenta"))

        # 2. Create plan
        with console.status("[agent]Creating plan...[/agent]"):
            plan = await self._create_plan(task_description)

        # Display plan
        plan_md = "## Plan\n"
        for i, step in enumerate(plan):
            plan_md += f"### Step {i+1}: {step['description']}\n"
            if step.get("tool_names"):
                tools = step["tool_names"]
                if isinstance(tools, list):
                    tools = ", ".join(tools)
                plan_md += f"**Tools**: {tools}\n"
            if step.get("expected_outcome"):
                plan_md += f"**Outcome**: {step['expected_outcome']}\n"

        console.print(Panel(Markdown(plan_md), title="Task Plan", border_style="cyan"))

        # 3. Execute plan step by step
        step_results = []
        working_memory = {}

        for i, step in enumerate(plan):
            print()
            console.print(f"[agent]Executing Step {i+1}/{len(plan)}: {step['description']}[/agent]")

            # Execute step
            result = await self._execute_step(task_description, step, working_memory)
            step_results.append(result)

            # Update working memory with key information
            for line in result.split("\n"):
                if ":" in line and len(line.split(":", 1)[0]) < 30:
                    key, value = line.split(":", 1)
                    key = key.strip()
                    if key and key not in working_memory:
                        working_memory[key] = value.strip()

            # Reflect after every other step or at the end
            if (i + 1) % 2 == 0 or i == len(plan) - 1:
                console.print("[agent]\nReflecting on progress...[/agent]")
                reflection = await self._reflect(task_description, plan, step_results, working_memory)
                console.print(Panel(reflection["reflection"], title="Reflection", border_style="italic yellow"))

                # Stop if task is complete
                if reflection["is_complete"] and i < len(plan) - 1:
                    console.print("[agent]Task completed ahead of schedule![/agent]")
                    break

        return step_results[-1] if step_results else "Task execution failed."

    async def get_response(self, user_input, system_prompt=None):
        """Get response with tool support"""
        if not user_input.strip():
            return "Please enter a message."

        try:
            # Initialize tools if needed
            if not self.mcp.initialized and self.mcp.has_servers():
                await self.mcp.initialize()

            # Format message history for API
            messages = []
            history_items = self.history[-10:]  # Get last 10 messages for context

            # Process all history EXCEPT the last user message which will be added separately
            for i, item in enumerate(history_items):
                # Skip the last history item if it's a simple user message (to avoid duplication)
                if i == len(history_items) - 1 and isinstance(item, tuple) and item[0] == "user":
                    continue

                if isinstance(item, tuple):
                    role, content = item
                    if role == "user":
                        messages.append({"role": "user", "content": [{"text": content}]})
                    elif role == "assistant":
                        messages.append({"role": "assistant", "content": [{"text": content}]})
                elif isinstance(item, dict):  # This handles tool messages
                    messages.append(item)  # Add the pre-formatted message directly

            # Add current user input
            messages.append({"role": "user", "content": [{"text": user_input}]})

            # Use custom system prompt if provided
            system_message = {"text": system_prompt or "You are Q-2001, a helpful AI assistant. Be concise and accurate."}

            # Conversation loop for multiple tool calls
            full_response = ""
            finished = False
            first_response = True
            base_messages = messages.copy()  # Store the original conversation history

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

                # Call model API
                response = self.bedrock.converse_stream(**api_params)

                # Process response stream
                current_response, tool_calls, conversation_finished = self._process_response(response.get("stream", []))
                full_response += current_response

                # Handle tool calls if any
                if tool_calls:
                    # Create assistant message with tool uses
                    assistant_message = {
                        "role": "assistant",
                        "content": [{"text": full_response}]
                    }

                    # Add tool calls to the assistant message
                    for tool_call in tool_calls:
                        assistant_message["content"].append({
                            "toolUse": {
                                "toolUseId": tool_call["id"],
                                "name": tool_call["name"],
                                "input": tool_call["input"],
                            }
                        })

                    # Run tools in parallel
                    tool_results = await asyncio.gather(*[self._run_tool_call(tc) for tc in tool_calls])

                    # Store tool results
                    tool_result_messages = []
                    for result, tool_call in zip(tool_results, tool_calls):
                        tool_name = tool_call["name"]
                        tool_result = result.split(" Result:", 1)[1].strip() if " Result:" in result else result

                        # Display tool result
                        panel_style = "green" if "Error:" not in tool_result else "red"
                        console.print(Panel(tool_result, title="Tool Call Result", border_style=panel_style))

                        # Create tool result message
                        tool_result_message = {
                            "role": "user",
                            "content": [{
                                "toolResult": {
                                    "toolUseId": tool_call["id"],
                                    "content": [{"text": tool_result}],
                                    "status": "success" if "Error:" not in tool_result else "error",
                                }
                            }]
                        }
                        tool_result_messages.append(tool_result_message)

                    # Add assistant message with tool uses to messages
                    messages.append(assistant_message)

                    # Add tool result messages to messages
                    messages.extend(tool_result_messages)

                    # Add to history for future conversations
                    self.history.append(assistant_message)
                    self.history.extend(tool_result_messages)
                else:
                    # If no tool calls, conversation is complete
                    finished = conversation_finished

            # Don't add response to history here - it will be done in run_async
            return full_response

        except Exception as e:
            console.print(f"[error]Error: {str(e)}[/error]")
            return f"Error: {str(e)}"
        
    def handle_command(self, cmd):
        """Handle special commands"""
        cmd_parts = cmd.lower().strip().split()
        cmd_base = cmd_parts[0]

        # Simple commands
        if cmd_base == "/quit" or cmd_base == "/exit":
            self.running = False
            console.print("[system]Thank you for using Q-2001. Goodbye![/system]")
            return True
        elif cmd_base == "/help":
            console.print(Markdown("""
            # Q-2001 Commands
            - `/quit` or `/exit`: Exit the application
            - `/help`: Show this help message
            - `/clear`: Clear the conversation history
            - `/model <model_id>`: Change the AI model
            - `/tools`: List all available tools
            """))
            return True
        elif cmd_base == "/clear":
            self.history = []
            console.print("[system]Conversation history cleared.[/system]")
            return True
        elif cmd_base == "/model" and len(cmd_parts) > 1:
            self.model_id = " ".join(cmd_parts[1:])
            console.print(f"[system]Model changed to: {self.model_id}[/system]")
            return True
        elif cmd_base == "/tools":
            self._list_tools()
            return True

        return False

    def _list_tools(self):
        """List available tools"""
        if not self.mcp.initialized:
            console.print("[system]Initializing tools...[/system]")
            return

        if not self.mcp.servers:
            console.print("[system]No tools available. Configure in ~/.q2001_mcp_config.json[/system]")
            return

        console.print("[system]Available tools:[/system]")
        for server_name, server_info in self.mcp.servers.items():
            console.print(f"[system]Server: {server_name}[/system]")
            for tool in server_info.get("tools", []):
                console.print(f"[system]  - {tool['name']}: {tool['description']}[/system]")

    async def run_async(self):
        """Run the chat interface (async version)"""
        console.print(Panel.fit(
            "Welcome to Q-2001 - Your Agentic AI Assistant powered by AWS Bedrock\n"
            "Type '/help' for commands, '/quit' to exit",
            title="Q-2001",
            border_style="green",
        ))

        # Initialize MCP if servers are registered
        if self.mcp.has_servers():
            console.print("[system]Initializing MCP servers...[/system]")
            await self.mcp.initialize()

            # Show which servers were successfully loaded
            loaded_servers = [name for name, info in self.mcp.servers.items() if info.get("tools")]
            if loaded_servers:
                console.print("[system]MCP servers loaded:[/system]")
                for server_name in loaded_servers:
                    console.print(f"[system]- {server_name}[/system]")
            else:
                console.print("[system]No MCP servers were successfully loaded[/system]")

        # Initial greeting
        console.print("[assistant]Q-2001:[/assistant] Hello! I'm your agentic assistant. How can I help you today?")

        while self.running:
            try:
                print("\033[1;34m\n\nHuman: \033[0m", end="", flush=True)
                user_input = input()

                if not user_input.strip():
                    continue

                # Handle commands
                if user_input.startswith("/") and self.handle_command(user_input):
                    continue

                # Add to history (ONLY ONCE)
                self.history.append(("user", user_input))

                # Direct response for simple inputs
                if user_input.strip().lower() in ["hi", "hello", "hey"]:
                    response = await self.get_response(user_input)
                    # Only add simple text response to history if it's not a tool interaction
                    # (tool interactions are added in get_response)
                    if not any(isinstance(item, dict) for item in self.history[-2:]):
                        self.history.append(("assistant", response))
                else:
                    # Analyze task to determine approach
                    try:
                        task_analysis = await self._analyze_task(user_input)

                        # Simple response or agent workflow based on complexity
                        if task_analysis.get("is_simple_interaction", False) or (
                            task_analysis.get("complexity", 5) < 3 and not task_analysis.get("requires_tools", False)
                        ):
                            response = await self.get_response(user_input)
                            # Only add simple text response if it's not a tool interaction
                            if not any(isinstance(item, dict) for item in self.history[-2:]):
                                self.history.append(("assistant", response))
                        else:
                            response = await self.execute_agent_workflow(user_input)
                            # Add agent workflow response to history
                            self.history.append(("assistant", response))
                    except Exception as e:
                        console.print(f"[error]Error in task processing: {str(e)}[/error]")
                        response = await self.get_response(user_input)  # Fallback to direct response
                        # Only add simple text response if it's not a tool interaction
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
    parser = argparse.ArgumentParser(description="Q-2001 - Agentic AI Assistant powered by AWS Bedrock")
    parser.add_argument("--model", help="Bedrock model ID to use")
    parser.add_argument("--profile", help="AWS profile to use")
    parser.add_argument("--region", help="AWS region to use")
    parser.add_argument("--version", action="store_true", help="Show version information")

    args = parser.parse_args()

    if args.version:
        print("Q-2001 v1.5.0")
        return

    # Start chat
    Q2001(
        model=args.model,
        profile=args.profile,
        region=args.region
    ).run()


if __name__ == "__main__":
    main()