# Q-2001

Q-2001 is a command-line AI assistant powered by AWS Bedrock. It uses advanced large language models to answer questions, provide help, and engage in conversations, with intelligent tool capabilities through Model Context Protocol (MCP) integration.

<img width="963" alt="image" src="https://github.com/user-attachments/assets/198a861e-b863-4047-bcd3-c4b8622b65f9" />


## Features

- Simple and easy-to-use command line interface with rich formatting
- Support for multiple AWS Bedrock models (Claude, DeepSeek, Nova, etc.)
- Real-time streaming responses
- Conversation history and context management
- Tool usage capabilities through MCP integration
- Customizable configuration

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

# Specify AWS region
python Q-2001.py --region us-east-1

# Show version
python Q-2001.py --version
```

## Commands

The following commands are available in Q-2001:

- `/quit` or `/exit`: Exit the application
- `/help`: Display help information
- `/clear`: Clear conversation history
- `/model <model_id>`: Change AI model
- `/tools`: List all available MCP tools

## MCP Integration

Q-2001 supports extended functionality through Model Context Protocol (MCP). The MCP client handles the integration with various tool servers.

### Configuration

Q-2001 creates a configuration file at `~/.q2001_mcp_config.json` which can be manually edited to change default settings.

Example configuration:

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

## Tool Capabilities

When MCP servers are configured and initialized, Q-2001 can:

1. Automatically detect when tools are needed to solve a problem
2. Call appropriate tools with proper parameters
3. Process tool results and incorporate them into responses
4. Handle multiple tool calls in a single conversation

<img width="1024" alt="image" src="https://github.com/user-attachments/assets/5ff8bbc1-6946-47c3-bf67-0ac2e01b1fc5" />


## Requirements

- Python 3.11+
- Required Python packages:
  - boto3
  - rich
  - mcp
  - anyio
  - markdown-it-py
  - uvicorn
  - python-dotenv
  - httpx
  - pygments
- AWS account and appropriate permissions to access Bedrock services
- Configured AWS credentials
- Node.js and npm (for npx commands with certain MCP servers)

## Notes

- Using this tool will incur AWS Bedrock API call costs
- Ensure your AWS account has Bedrock service enabled and access to required models
