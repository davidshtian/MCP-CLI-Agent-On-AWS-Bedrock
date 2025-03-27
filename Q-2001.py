#!/usr/bin/env python3
"""Q-2001 - An agentic command-line AI assistant powered by AWS Bedrock"""

import os, json, argparse, asyncio, configparser, uuid
import boto3
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.theme import Theme

# Import MCP client
from mcp_client import MCPClient

# Setup console
console = Console(theme=Theme({
    "user": "bold blue", "assistant": "bold green", 
    "system": "yellow", "error": "bold red",
    "agent": "bold magenta", "plan": "cyan", "reflect": "italic yellow"
}))

class Q2001:
    """Q-2001 - Agentic AI Assistant powered by AWS Bedrock with tool capabilities"""

    def __init__(self, model=None, profile=None, region=None):
        # Load config and initialize
        self.config = self._load_config()
        self.model_id = model or self.config["DEFAULT"].get("model_id", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
        self.region = region or self._get_region()
        self.history = []
        self.running = True

        # Set up AWS client
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        self.bedrock = session.client("bedrock-runtime", region_name=self.region)

        # Set up MCP client for tools
        self.mcp = MCPClient(debug_mode=False)

        # Register servers from config file
        self._register_mcp_servers()

    def _load_config(self):
        """Load or create config file"""
        config = configparser.ConfigParser()
        path = os.path.expanduser("~/.q_2001_config")

        if os.path.exists(path):
            config.read(path)
        else:
            config["DEFAULT"] = {
                "model_id": "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                "region": "us-east-1",
            }
            config["AGENT"] = {
                "max_iterations": "5",
            }
            os.makedirs(os.path.dirname(path), exist_ok=True)

            with open(path, "w") as f:
                config.write(f)

        return config

    def _save_config(self):
        """Save configuration"""
        with open(os.path.expanduser("~/.q_2001_config"), "w") as f:
            self.config.write(f)

    def _get_region(self):
        """Get AWS region from config, environment or session"""
        if "region" in self.config["DEFAULT"]:
            return self.config["DEFAULT"]["region"]
        return os.environ.get("AWS_REGION") or boto3.Session().region_name or "us-east-1"

    def _load_mcp_config(self):
        """Load MCP configuration from JSON file"""
        config_path = os.path.expanduser("~/.q2001_mcp_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                console.print(f"[error]Error loading MCP config: {str(e)}[/error]")
        return {"mcpServers": {}}

    def _register_mcp_servers(self):
        """Register all MCP servers from config"""
        config = self._load_mcp_config()

        if not config.get("mcpServers"):
            return False

        success = False
        for server_name, server_info in config["mcpServers"].items():
            if "command" in server_info and "args" in server_info:
                if self.mcp.register_server(
                    name=server_name,
                    command=server_info["command"],
                    args=server_info["args"]
                ):
                    console.print(f"[system]Registered {server_name} server[/system]")
                    success = True
                else:
                    console.print(f"[error]Failed to register {server_name} server[/error]")

        return success

    def _list_mcp_servers(self):
        """List MCP servers from config file"""
        config = self._load_mcp_config()

        if not config.get("mcpServers"):
            console.print("[system]No MCP servers configured in ~/.q2001_mcp_config.json[/system]")
            return True

        console.print("[system]MCP servers configured in ~/.q2001_mcp_config.json:[/system]")
        for server_name, server_info in config["mcpServers"].items():
            console.print(f"[system]- {server_name}:[/system]")
            console.print(f"[system]  command: {server_info.get('command')}[/system]")
            console.print(f"[system]  args: {' '.join(server_info.get('args', []))}[/system]")
        return True

    async def _run_tool_call(self, tool_call):
        """Run a tool call and return the result"""
        try:
            result = await self.mcp.call_tool(tool_call['name'], tool_call['input'])
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
            if 'contentBlockDelta' in event and 'delta' in event['contentBlockDelta']:
                delta = event['contentBlockDelta']['delta']
                if 'text' in delta:
                    chunk_text = delta['text']
                    print(chunk_text, end="", flush=True)
                    current_response += chunk_text

            # Handle tool call start
            if 'contentBlockStart' in event and 'start' in event['contentBlockStart']:
                start = event['contentBlockStart']['start']
                if 'toolUse' in start:
                    tool_name = start['toolUse'].get('name', '')
                    tool_id = start['toolUse'].get('toolUseId', '') or str(uuid.uuid4())
                    tool_info = {
                        "name": tool_name,
                        "id": tool_id
                    }
                    print()  # Add a line break before the tool call
                    json_accumulator = ""

            # Accumulate tool input JSON
            if 'contentBlockDelta' in event and 'delta' in event['contentBlockDelta']:
                delta = event['contentBlockDelta']['delta']
                if 'toolUse' in delta and 'input' in delta['toolUse'] and tool_info:
                    json_accumulator += delta['toolUse']['input']

            # Complete tool call
            if 'contentBlockStop' in event and tool_info:
                try:
                    tool_input = json.loads(json_accumulator)
                except:
                    # Simple cleanup for common JSON errors
                    clean_json = json_accumulator.strip()
                    if not clean_json.startswith('{'): clean_json = '{' + clean_json
                    if not clean_json.endswith('}'): clean_json = clean_json + '}'

                    try:
                        tool_input = json.loads(clean_json)
                    except:
                        # Handle path-like strings
                        if "/" in json_accumulator:
                            path = json_accumulator[json_accumulator.find('/'):]
                            path = path.split('"')[0].split('}')[0].strip()
                            tool_input = {"path": path}
                        else:
                            tool_input = {}

                # Display the tool call panel with input parameters
                input_str = json.dumps(tool_input, indent=2) if tool_input else "No input parameters"
                console.print(Panel(
                    f"Using Tool: {tool_info['name']}\nTool Input: {input_str}",
                    title="Tool Call",
                    border_style="yellow"
                ))

                tool_calls.append({
                    "name": tool_info["name"],
                    "input": tool_input,
                    "id": tool_info["id"]
                })
                tool_info = None
                json_accumulator = ""

            # Check if message is complete
            if 'messageStop' in event:
                stop_reason = event['messageStop'].get('stopReason', '')
                if stop_reason != 'tool_use':
                    # Normal completion (not waiting for tool results)
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
                inferenceConfig={"maxTokens": 4096, "temperature": 0.7}
            )
            return response.get('output', {}).get('message', {}).get('content', [{}])[0].get('text', '')
        except Exception as e:
            console.print(f"[error]Error getting model response: {str(e)}[/error]")
            return f"Error: {str(e)}"

    async def _analyze_task(self, user_input):
        """Analyze user input to determine its complexity and requirements"""
        system_prompt = """
        You are an expert at task analysis. Analyze the user's request and intent briefly:
        1. Is this a simple greeting, casual conversation, or direct question that can be answered immediately? 
        2. Or it can be resolved by a simple tool call?
        3. Does this require multi-step planning, or complex reasoning?

        Output a JSON ONLY with following keys and values (NO MARKDOWN FORMAT):
        - is_simple_interaction: true if this is just a greeting, conversation or simple tool call that needs no planning
        - task_description: a clear description of what the user wants
        - requires_tools: true if tools would likely be needed
        - complexity: a number from 1-10 indicating task complexity
        """

        messages = [{"role": "user", "content": [{"text": f"Analyze this input: '{user_input}'"}]}]
        response = await self._get_model_response(messages, system_prompt)

        result = json.loads(response)
        return result


    async def _create_plan(self, task):
        """Create a step-by-step plan to complete the task"""
        system_prompt = """
        As an expert planner, create a detailed step-by-step plan for completing this task.
        Break down complex tasks into smaller, manageable steps.
        For each step, consider:
        - What specific action needs to be taken
        - What tools might be needed
        - What information must be gathered or verified
        - How to handle potential errors or edge cases

        Return your plan as a JSON array of step objects with:
        1. description: A detailed description of what to do in this step
        2. requires_tools: Whether tools are needed (true/false)
        3. tool_names: If tools are required, list the specific tools needed
        4. expected_outcome: What should result from this step
        5. error_handling: How to deal with potential failures in this step
        """

        # Include tool info if MCP is initialized
        tool_info = ""
        if self.mcp.initialized:
            tools = await self.mcp.list_tools()
            if tools:
                tool_info = "Available tools: " + " ".join([f"- {t['name']}: {t['description']}" for t in tools])

        message_content = f"Task: {task}  {tool_info}  Create a step-by-step plan."
        messages = [{"role": "user", "content": [{"text": message_content}]}]

        response = await self._get_model_response(messages, system_prompt)

        try:
            plan = json.loads(response)
            if not isinstance(plan, list):
                raise ValueError("Plan not in list format")
        except:
            # Improved fallback plan extraction from text
            steps = response.split(" ")
            plan = []
            current_step = {}
            step_number = 1

            for line in steps:
                line = line.strip()

                # Detect new step by step number or keyword
                if line.startswith(f"{step_number}.") or line.startswith(f"Step {step_number}:") or (line.startswith("Step") and ":" in line):
                    if current_step and "description" in current_step:
                        plan.append(current_step)

                    description = line.split(":", 1)[1].strip() if ":" in line else line
                    current_step = {
                        "description": description,
                        "requires_tools": False,
                        "expected_outcome": "Complete this step successfully"
                    }
                    step_number += 1

                # Extract tool information
                elif "tool" in line.lower():
                    current_step["requires_tools"] = True
                    if "tool_names" not in current_step:
                        current_step["tool_names"] = []
                    if ":" in line:
                        tool_name = line.split(":", 1)[1].strip()
                        current_step["tool_names"].append(tool_name)

                # Extract expected outcome
                elif any(kw in line.lower() for kw in ["outcome", "result", "expect"]):
                    if ":" in line:
                        current_step["expected_outcome"] = line.split(":", 1)[1].strip()

                # Error handling information
                elif any(kw in line.lower() for kw in ["error", "fail", "exception"]):
                    if ":" in line:
                        current_step["error_handling"] = line.split(":", 1)[1].strip()

            # Add the last step
            if current_step and "description" in current_step:
                plan.append(current_step)

            # If still empty, create a more detailed fallback plan
            if not plan:
                plan = [
                    {
                        "description": f"Analyze the task: {task}",
                        "requires_tools": False,
                        "expected_outcome": "Clear understanding of what needs to be done"
                    },
                    {
                        "description": "Gather necessary information and resources",
                        "requires_tools": True,
                        "expected_outcome": "All required data and tools are ready"
                    },
                    {
                        "description": "Execute the task",
                        "requires_tools": True,
                        "expected_outcome": "Task is performed according to requirements"
                    },
                    {
                        "description": "Verify results and handle any errors",
                        "requires_tools": False,
                        "expected_outcome": "Confirm task completion and success"
                    }
                ]

        return plan

    async def _execute_step(self, task, step, working_memory):
        """Execute a single step of the plan"""
        system_prompt = f"""
        You are executing this specific step in a plan:

        TASK: {task}
        STEP: {step['description']}
        EXPECTED OUTCOME: {step.get('expected_outcome', 'Complete the step successfully')}

        Use tools if needed. Focus only on this step.
        Be thorough but concise in your execution.
        """

        # Prepare context from working memory
        context_message = "Context from previous steps: "
        for key, value in working_memory.items():
            context_message += f"- {key}: {value} "

        step_message = f"Execute step: {step['description']}"
        # Get response with tool support
        return await self.get_response(f"{context_message}  {step_message}", system_prompt=system_prompt)

    async def _reflect(self, task, plan, step_results, working_memory):
        """Reflect on progress and determine if task is complete"""
        system_prompt = """
        Reflect deeply on the task progress and determine:
        1. What has been accomplished so far (be specific)
        2. Whether each step of the plan has been completed successfully
        3. Whether any steps had unexpected outcomes
        4. Whether the overall goal has been achieved

        Return your reflection and clearly state if the task is COMPLETE or INCOMPLETE.
        If INCOMPLETE, explain exactly what still needs to be done.
        """

        # Prepare the reflection context
        reflection_context = f"TASK: {task}  PLAN: "
        for i, step in enumerate(plan):
            reflection_context += f"{i+1}. {step['description']} "

        reflection_context += " RESULTS SO FAR: "
        for i, result in enumerate(step_results):
            reflection_context += f"Step {i+1} Result: {result[:200]}... " if len(result) > 200 else f"Step {i+1} Result: {result} "

        reflection_context += " WORKING MEMORY: "
        for key, value in working_memory.items():
            reflection_context += f"- {key}: {value} "

        messages = [{"role": "user", "content": [{"text": f"{reflection_context}  Reflect and determine completion status."}]}]

        reflection = await self._get_model_response(messages, system_prompt)

        # Check if task is complete
        is_complete = "COMPLETE" in reflection.upper() or "task is complete" in reflection.lower()

        return {
            "reflection": reflection,
            "is_complete": is_complete
        }

    async def execute_agent_workflow(self, user_input):
        """Execute the full agent workflow"""
        # Initialize tools if needed
        if not self.mcp.initialized and self.mcp.has_servers():
            with console.status("[yellow]Initializing tools...[/yellow]"):
                await self.mcp.initialize()

        # 1. Analyze the task
        with console.status("[agent]Analyzing task...[/agent]"):
            task_analysis = await self._analyze_task(user_input)

        # Display task understanding
        task_description = task_analysis.get("task_description", user_input)
        subtasks = task_analysis.get("subtasks", [])
        subtasks_text = " ".join([f"- {subtask}" for subtask in subtasks]) if subtasks else ""
        understanding_content = f"[agent]Task: {task_description}[/agent]"
        if subtasks_text:
            understanding_content += f"  [agent]Subtasks:[/agent] {subtasks_text}"

        console.print(Panel(understanding_content, title="Understanding", border_style="magenta"))

        # 2. Create plan
        with console.status("[agent]Creating plan...[/agent]"):
            plan = await self._create_plan(task_description)

        # Display plan with more detail
        plan_md = "## Plan  "
        for i, step in enumerate(plan):
            plan_md += f"### Step {i+1}: {step['description']}\n\n"

            if "tool_names" in step and step["tool_names"]:
                tools = ", ".join(step["tool_names"]) if isinstance(step["tool_names"], list) else step["tool_names"]
                plan_md += f"**Tools needed**: {tools} "

            if "expected_outcome" in step:
                plan_md += f"**Expected outcome**: {step['expected_outcome']} "

            if "error_handling" in step:
                plan_md += f"**Error handling**: {step['error_handling']} "

            plan_md += " "

        console.print(Panel(Markdown(plan_md), title="Task Plan", border_style="cyan"))

        # 3. Execute plan step by step
        step_results = []
        working_memory = {}

        for i, step in enumerate(plan):
            current_step = f"Step {i+1}/{len(plan)}: {step['description']}"
            print()
            console.print(f"[agent]Executing {current_step}[/agent]")

            # Execute step
            result = await self._execute_step(task_description, step, working_memory)
            step_results.append(result)

            # Update working memory with key information from this step
            lines = result.split(' ')
            for line in lines:
                if ':' in line and len(line.split(':', 1)[0].strip()) < 30:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    if key and key not in working_memory:
                        working_memory[key] = value.strip()

            # Check if we should reflect after this step
            should_reflect = (i+1) % 2 == 0 or i == len(plan)-1

            if should_reflect:
                console.print("[agent]\nReflecting on progress...[/agent]")
                reflection = await self._reflect(task_description, plan, step_results, working_memory)

                console.print(Panel(reflection["reflection"], title="Reflection", border_style="italic yellow"))

                # If task is complete, we can stop
                if reflection["is_complete"] and i < len(plan)-1:
                    console.print("[agent]Task completed ahead of schedule![/agent]")
                    break

        # Return the last response as the summary (no need for additional summary)
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
            for role, content in self.history[-10:]:  # Last 10 messages for context
                if role == "user" and content != user_input:
                    messages.append({"role": "user", "content": [{"text": content}]})
                elif role == "assistant":
                    messages.append({"role": "assistant", "content": [{"text": content}]})

            # Add current user input
            messages.append({"role": "user", "content": [{"text": user_input}]})

            # Use custom system prompt if provided
            system_message = {"text": system_prompt} if system_prompt else {"text": "You are Q-2001, a helpful AI assistant. Be concise and accurate."}

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
                    "inferenceConfig": {"maxTokens": 4096, "temperature": 0.7},
                }

                # Add toolConfig only if we have initialized tools
                if self.mcp.initialized:
                    bedrock_tools = self.mcp.get_bedrock_format()
                    if bedrock_tools:  # Only add if we actually have tools
                        api_params["toolConfig"] = bedrock_tools

                # Call model API
                response = self.bedrock.converse_stream(**api_params)

                # Process response stream
                current_response, tool_calls, conversation_finished = self._process_response(response.get('stream', []))

                full_response += current_response

                # Handle tool calls if any
                if tool_calls:
                    # Run tools in parallel
                    tool_results = await asyncio.gather(*[self._run_tool_call(tc) for tc in tool_calls])

                    if tool_results:
                        # Reset messages with tool results for continuation
                        messages = [
                            {"role": "user", "content": [{"text": user_input}]},
                            {"role": "assistant", "content": [{"text": full_response}]}
                        ]

                        # Add tool results to conversation
                        for result, tool_call in zip(tool_results, tool_calls):
                            tool_name = tool_call["name"]
                            tool_result = result.split(' Result:', 1)[1].strip() if ' Result:' in result else result

                            # Display the tool result in a panel
                            panel_style = "green" if "Error:" not in tool_result else "red"
                            panel_title = "Tool Call Result"
                            console.print(Panel(
                                tool_result,
                                title=panel_title,
                                border_style=panel_style
                            ))

                            # Add tool use to assistant message
                            messages[-1]["content"].append({
                                "toolUse": {
                                    "toolUseId": tool_call["id"],
                                    "name": tool_name,
                                    "input": tool_call["input"]
                                }
                            })

                            # Add tool result as user message
                            messages.append({
                                "role": "user",
                                "content": [{
                                    "toolResult": {
                                        "toolUseId": tool_call["id"],
                                        "content": [{"text": tool_result}],
                                        "status": "success" if "Error:" not in tool_result else "error"
                                    }
                                }]
                            })
                    else:
                        finished = True
                else:
                    finished = conversation_finished

            return full_response

        except Exception as e:
            console.print(f"[error]Error: {str(e)}[/error]")
            return f"I encountered an error: {str(e)}"

    def handle_command(self, cmd):
        """Handle special commands"""
        cmd_base = cmd.lower().strip().split()[0]  # Get the base command

        # Simple commands
        commands = {
            "/quit": lambda: self._quit(),
            "/exit": lambda: self._quit(),
            "/help": lambda: self._show_help(),
            "/clear": lambda: self._clear_history(),
            "/config": lambda: self._show_config(),
            "/tools": lambda: self._list_tools(),
            "/mcp": lambda: self._list_mcp_servers(),
        }

        if cmd_base in commands:
            return commands[cmd_base]()

        # Commands with arguments
        parts = cmd.lower().strip().split()
        args = parts[1:] if len(parts) > 1 else []

        if cmd_base == "/model" and args:
            return self._set_model(" ".join(args))
        if cmd_base == "/save" and args:
            return self._save_conversation(" ".join(args))

        # Provide help for removed commands
        if cmd_base in ["/files", "/time"]:
            console.print("[system]The /files and /time commands have been replaced by MCP configuration.[/system]")
            console.print("[system]Edit ~/.q2001_mcp_config.json to configure MCP servers.[/system]")
            console.print("[system]Use /mcp to see current configuration.[/system]")
            return True

        return False

    # Command handlers
    def _quit(self):
        self.running = False
        console.print("[system]Thank you for using Q-2001. Goodbye![/system]")
        return True

    def _show_help(self):
        help_text = """
        # Q-2001 Commands
        - `/quit` or `/exit`: Exit the application
        - `/help`: Show this help message
        - `/clear`: Clear the conversation history
        - `/model <model_id>`: Change the AI model
        - `/save <filename>`: Save conversation to file
        - `/config`: Show current configuration
        - `/tools`: List all available tools
        - `/mcp`: List configured MCP servers

        # MCP Configuration
        MCP servers are configured in ~/.q2001_mcp_config.json
        """
        console.print(Markdown(help_text))
        return True

    def _clear_history(self):
        self.history = []
        console.print("[system]Conversation history cleared.[/system]")
        return True

    def _set_model(self, model_id):
        self.model_id = model_id
        self.config["DEFAULT"]["model_id"] = model_id
        self._save_config()
        console.print(f"[system]Model changed to: {model_id}[/system]")
        return True

    def _save_conversation(self, filename):
        try:
            with open(filename, "w") as f:
                f.write("# Q-2001 Conversation  ")
                for role, content in self.history:
                    f.write(f"## {'Human' if role == 'user' else 'Q-2001'} {content}")
            console.print(f"[system]Conversation saved to {filename}[/system]")
            return True
        except Exception as e:
            console.print(f"[error]Error saving conversation: {str(e)}[/error]")
            return True

    def _show_config(self):
        console.print("[system]Current configuration:[/system]")
        for section in self.config.sections():
            console.print(f"[system][{section}][/system]")
            for key, value in self.config[section].items():
                console.print(f"[system]  {key} = {value}[/system]")
        console.print("[system][DEFAULT][/system]")
        for key, value in self.config["DEFAULT"].items():
            console.print(f"[system]  {key} = {value}[/system]")
        return True


    def _list_tools(self):
        """Handle the /tools command"""
        if not self.mcp.initialized:
            console.print("[system]Tools not initialized. Initializing now...[/system]")
            self.list_tools_after_init = True
            return True

        # List servers and their registered tools
        console.print("[system]Registered servers and tools:[/system]")

        # If there are no servers registered
        if not self.mcp.servers:
            console.print("[system]No servers registered. Edit ~/.q2001_mcp_config.json to register tools.[/system]")
            return True

        for server_name, server_info in self.mcp.servers.items():
            console.print(f"[system]Server: {server_name}[/system]")

            if not server_info.get("tools"):
                console.print(f"[system]  No tools available from this server[/system]")
                continue

            for tool in server_info.get("tools", []):
                console.print(f"[system]  - {tool['name']}: {tool['description']}[/system]")

        return True

    async def run_async(self):
        """Run the chat interface (async version)"""
        console.print(Panel.fit(
            "Welcome to Q-2001 - Your Agentic AI Assistant. "
            "Any questions or task to do?\n"
            "Tips: Type '/quit' to exit, '/help' for more commands.",
            title="Q-2001", border_style="green"
        ))

        # Add flag for listing tools after initialization
        self.list_tools_after_init = False

        # Initialize MCP if servers are registered
        if self.mcp.has_servers():
            try:
                await self.mcp.initialize()
                console.print("[system]Tools initialized successfully[/system]")

                # List tools if requested
                if self.list_tools_after_init:
                    self.list_tools_after_init = False
                    self._list_tools()

            except Exception as e:
                console.print(f"[error]Error initializing tools: {str(e)}[/error]")

        # Initial greeting
        console.print("[assistant]Q-2001:[/assistant] Hello! I'm your agentic assistant. I can plan and execute tasks efficiently. How can I help you today? ")

        while self.running:
            try:
                print("\033[1;34m\n\nHuman: \033[0m", end="", flush=True)
                user_input = input()

                if not user_input.strip():
                    continue

                # Handle commands
                if user_input.startswith("/") and self.handle_command(user_input):
                    # If we need to initialize after a command, do so
                    if self.mcp.has_servers() and not self.mcp.initialized:
                        await self.mcp.initialize()
                        console.print("[system]Tools reinitialized[/system]")

                        # List tools if requested
                        if self.list_tools_after_init:
                            self.list_tools_after_init = False
                            self._list_tools()
                    continue

                # Add to history
                self.history.append(("user", user_input))

                # Analyze task to determine approach
                task_analysis = await self._analyze_task(user_input)

                # For simple interactions or questions with low complexity that don't need tools,
                # use direct response without showing the agent workflow
                if task_analysis.get("is_simple_interaction", False) or (
                    task_analysis.get("complexity", 5) < 3 and not task_analysis.get("requires_tools", False)):
                    response = await self.get_response(user_input)
                else:
                    # For more complex tasks, use the full agent workflow
                    response = await self.execute_agent_workflow(user_input)

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
    parser.add_argument("--file-path", dest="filesystem_paths", action="append", help="Path to allow for filesystem access")
    parser.add_argument("--version", action="store_true", help="Show version information")

    args = parser.parse_args()

    if args.version:
        print("Q-2001 v1.5.0")
        return

    # Start chat with provided arguments
    kwargs = {k: v for k, v in vars(args).items() if v is not None and k != "version"}
    Q2001(**kwargs).run()


if __name__ == "__main__":
    main()