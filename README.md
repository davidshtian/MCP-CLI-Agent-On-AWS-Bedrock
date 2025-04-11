# Q-2001

> Built by Amazon Q Developer itself ❤️ (and rounds of debug...) A tiny learning project 📚

Q-2001 is an agentic AI assistant based on the command line, powered by AWS Bedrock. It uses advanced large language models (such as Claude) to answer questions, provide help, and engage in conversations, with powerful intelligent Agent capabilities.

**MCP Servers**

<img width="738" alt="image" src="https://github.com/user-attachments/assets/e4c6c2c6-07ef-46c1-a033-761c6e6118ac" />

**MCP Tool Call Example**

<img width="986" alt="image" src="https://github.com/user-attachments/assets/1e827280-7a0a-4a18-851d-033627749df9" />

## Features

- Simple and easy-to-use command line interface
- Support for multiple AWS Bedrock models (Claude, DeepSeek, Nova, etc.)
- Markdown rendering support
- Real-time streaming responses (Claude model)
- Conversation history and context management
- Customizable configuration
- Support for saving conversations to files
- **Agent Mode** - Automatically detects and handles complex tasks, plans and executes steps
- **MCP Integration** - Extended functionality through Model Context Protocol

## Installation

1. Ensure Python 3.11+ is installed
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Ensure AWS credentials are configured (via AWS CLI or environment variables)

## Usage

```bash
# Basic usage
python Q-2001.py

# Specify model
python Q-2001.py --model us.anthropic.claude-3-7-sonnet-20250219-v1:0

# Use other models
python Q-2001.py --model us.deepseek.r1-v1:0
python Q-2001.py --model us.amazon.nova-micro-v1:0

# Specify AWS profile
python Q-2001.py --profile myprofile
```

## Commands

The following commands are available in Q-2001:

- `/quit` or `/exit`: Exit the application
- `/help`: Display help information
- `/clear`: Clear conversation history
- `/model <model_id>`: Change AI model
- `/save <filename>`: Save conversation to file
- `/config`: Display current configuration
- `/mcp <path1> [path2...]`: Register MCP filesystem server and specify allowed access paths
- `/tools`: List all available MCP tools

## Intelligent Agent Features

Q-2001 has powerful intelligent Agent capabilities for handling complex tasks:

### Automatic Task Analysis

Q-2001 automatically analyzes the complexity of user requests:
- Provides direct answers for simple questions
- Automatically switches to Agent mode for complex tasks

### Agent Mode Workflow

When a complex task is detected, Q-2001 will:

1. **Plan** - Create a detailed step-by-step plan
2. **Execute** - Carry out operations in the plan step by step
3. **Observe** - Record the results of each step
4. **Reflect** - Analyze progress and adjust the plan
5. **Iterate** - Update the plan as needed and continue execution
6. **Complete** - Determine if the task is finished and provide final answer

## MCP Integration

Q-2001 supports extended functionality through Model Context Protocol (MCP):

## Configuration

Q-2001 creates a configuration file at `~/.q2001_mcp_config.json` which can be manually edited to change default settings.

```json
{
    "mcpServers": {
        "aws-document": {
            "command": "uvx",
            "args": [
                "awslabs.aws-documentation-mcp-server@latest"
            ]
        },
        "mcp-server-time": {
            "command": "uvx",
            "args": [
                "mcp-server-time",
                "--local-timezone=America/New_York"
            ]
        },
        "filesystem": {
            "command": "npx",
            "args": [
                "-y",
                "@modelcontextprotocol/server-filesystem",
                "/home/ec2-user/"
            ]
        },
        "sequential-thinking": {
            "command": "npx",
            "args": [
                "-y",
                "@modelcontextprotocol/server-sequential-thinking"
            ]
        }
    }
}
```

## Requirements

- Python 3.11+
- AWS account and appropriate permissions to access Bedrock services
- Configured AWS credentials
- Node.js and npm (for npx commands)

## Notes

- Using this tool will incur AWS Bedrock API call costs
- Ensure your AWS account has Bedrock service enabled and access to required models
- When using the MCP filesystem server, carefully specify allowed access paths to protect sensitive data
