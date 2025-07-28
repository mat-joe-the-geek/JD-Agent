from google.adk.agents import LlmAgent
import os
from pathlib import Path
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioConnectionParams, StdioServerParameters
SERVER_SCRIPT_PATH = str((Path(__file__).parent.parent / "server.py").resolve())

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True" 

insurance_agent = LlmAgent(
    name="Insurance_Agent",
    description="An agent that queries the insurance_candidates table and ranks them according to the JD for Insurance roles.",
    model="gemini-2.0-flash",
    instruction=(
        "You are a specialized JD agent focusing solely on **Insurance**."
        "Your primary role is to receive a user-provided Job Description (JD)."
        "Upon receiving the JD, you must call the `query_table` tool with `table_name: 'insurance_candidates'` to retrieve all candidate profiles."
        "After retrieving the candidates, you are to **rank** each candidate based on how well their profile matches the requirements outlined in the user's JD."
        "Consider factors such as underwriting experience, claims processing knowledge, actuarial skills, insurance sales background, risk assessment capabilities, compliance understanding, and any specific keywords mentioned in the JD relevant to the insurance industry."
        "Finally, present the ranked candidates in a **clear and concise table format**, including relevant details that support their ranking."
        "Ensure the output table is easy to read and provides sufficient information for evaluation."
        "Do not try to shorten the response; rather, explain the ranking criteria briefly and present the results clearly in the table."
    ),   
    tools=[
        MCPToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command="python3", # Use the explicit Python executable
                    args=[SERVER_SCRIPT_PATH],
                )
            )
        )
    ],
    output_key="insurance_output",
)