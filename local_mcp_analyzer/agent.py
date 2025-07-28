from pathlib import Path

from google.adk.agents import LlmAgent
# Import both StdioConnectionParams and StdioServerParameters
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioConnectionParams, StdioServerParameters 

from local_mcp_analyzer.prompt import DB_MCP_PROMPT

# IMPORTANT: Dynamically compute the absolute path to your server.py script
PATH_TO_YOUR_MCP_SERVER_SCRIPT = str((Path(__file__).parent / "server.py").resolve())


root_agent = LlmAgent(
    model="gemini-2.0-flash",
    name="db_mcp_client_agent",
    instruction=DB_MCP_PROMPT,
    tools=[
        MCPToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command="python3",
                    args=[PATH_TO_YOUR_MCP_SERVER_SCRIPT],
                ),
            )
        )
    ],
)