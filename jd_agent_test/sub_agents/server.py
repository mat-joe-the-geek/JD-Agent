# test/jd_agent/server.py

import asyncio
import json
import logging
import os
import sqlite3
from pathlib import Path
import google.generativeai as genai
from dotenv import load_dotenv

# MCP Server Stdio Import Fix
from mcp.server import stdio
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.mcp_tool.conversion_utils import adk_to_mcp_tool_type

# MCP Server Imports
from mcp import types as mcp_types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

load_dotenv()

# --- Logging Setup ---
LOG_FILE_PATH = os.path.join(os.path.dirname(__file__), "jd_agent_test_server.log")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, mode="w"),
        logging.StreamHandler()
    ],
)
# --- End Logging Setup ---

current_script_path = Path(__file__).resolve()
DATABASE_PATH = str((current_script_path.parent.parent.parent / "dbs" / "database.db"))
logging.info(f"Database path set to: {DATABASE_PATH}")

# --- Configure Generative AI ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logging.critical("GEMINI_API_KEY not found in .env file. AI classification/ranking will NOT work.")
else:
    genai.configure(api_key=GEMINI_API_KEY)
    logging.info("Generative AI configured successfully.")

# Initialize the LLMs for various tasks
llm_model = genai.GenerativeModel('gemini-1.5-flash') # A single model for all LLM tasks

# Define the categories for classification (used by analyze_jd_industry)
CATEGORIES = [
    "Software Development",
    "IT Services",
    "Banking",
    "Insurance",
    "Healthcare",
    "Travel",
    "Real Estate"
]

# --- Database Utility Functions ---
def get_db_connection():
    """Establishes and returns a SQLite database connection."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row  # To access columns by name
        logging.debug(f"Successfully connected to database at: {DATABASE_PATH}")
        return conn
    except sqlite3.Error as e:
        logging.critical(f"Failed to connect to database at {DATABASE_PATH}: {e}")
        raise

def get_table_schema(table_name: str) -> dict:
    """Gets the schema (column names and types) of a specific table.
    Returns empty list for columns if table does not exist.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"PRAGMA table_info('{table_name}');")
        schema_info = cursor.fetchall()
        if not schema_info:
            return {"table_name": table_name, "columns": []}

        columns = [{"name": row["name"], "type": row["type"]} for row in schema_info]
        return {"table_name": table_name, "columns": columns}
    except sqlite3.Error as e:
        logging.error(f"Error getting schema for table '{table_name}': {e}")
        raise
    finally:
        conn.close()

# --- Tool Functions (exposed via MCP Server) ---

async def analyze_jd_industry(job_description: str) -> str:
    """
    Analyzes a Job Description to determine its primary industry category.
    The industry must be one of the predefined categories.
    """
    if not job_description:
        logging.warning("analyze_jd_industry received empty job description.")
        return "Unknown"

    if not GEMINI_API_KEY:
        logging.error("GEMINI_API_KEY is not set. Cannot perform AI industry analysis.")
        return "Error: API Key Missing"

    classification_prompt = f"""
    You are an expert in classifying professional job descriptions into industry categories.
    Your task is to classify the provided Job Description into the SINGLE BEST category from the following precise categories:
    {', '.join(CATEGORIES)}.

    You MUST choose one of the categories provided. Do NOT return 'Unclassified' or any other category not explicitly listed.

    Return ONLY the exact category name. Do NOT include any other words, punctuation, explanations, or conversational filler.
    Ensure your response is ONLY one of the specified category names.

    Job Description:
    ---
    {job_description}
    ---

    Category:
    """
    logging.debug(f"Sending classification prompt to LLM for industry analysis: \n{classification_prompt}")

    try:
        response = await llm_model.generate_content_async(
            classification_prompt,
            generation_config=genai.types.GenerationConfig(temperature=0.0)
        )

        ai_classification = "Unknown"
        if response and response.text:
            ai_classification = response.text.strip()
            logging.debug(f"LLM raw response for industry analysis: '{response.text}'")
            logging.debug(f"Parsed AI industry classification: '{ai_classification}'")
        else:
            logging.warning("LLM returned empty or no text for industry analysis. Defaulting to 'Unknown'.")

        if ai_classification not in CATEGORIES:
            logging.error(f"LLM returned an invalid category '{ai_classification}'. Defaulting to '{CATEGORIES[0]}'.")
            ai_classification = CATEGORIES[0]

        logging.info(f"Job Description classified as '{ai_classification}'.")
        return ai_classification

    except Exception as e:
        logging.error(f"Error during AI industry analysis: {e}", exc_info=True)
        return f"Error: {str(e)}"

def query_table(table_name: str, columns: str = "*", condition: str = "1=1") -> list[dict]:
    """Queries a table with an optional condition.

    Args:
        table_name: The name of the table to query.
        columns: Comma-separated list of columns to retrieve (e.g., "id, name"). Defaults to "*".
        condition: Optional SQL WHERE clause condition (e.g., "id = 1" or "completed = 0").
    Returns:
        A list of dictionaries, where each dictionary represents a row.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    query = f"SELECT {columns} FROM {table_name}"
    if condition and condition.strip() != "1=1":
        query += f" WHERE {condition}"
    query += ";"

    try:
        logging.info(f"Executing query_table: {query}")
        cursor.execute(query)
        results = [dict(row) for row in cursor.fetchall()]
        logging.info(f"Query returned {len(results)} rows from '{table_name}'.")
    except sqlite3.Error as e:
        logging.error(f"Error querying table '{table_name}' with query '{query}': {e}")
        raise ValueError(f"Error querying table '{table_name}': {e}")
    finally:
        conn.close()
    return results

# --- MCP Server Setup ---
logging.info("Creating MCP Server instance for JD Agent's combined tools...")
app = Server("jd-tool-server") # Unique name for this server

# Wrap all tool functions as ADK FunctionTools
ADK_ALL_TOOLS = {
    "analyze_jd_industry": FunctionTool(func=analyze_jd_industry),
    "query_table": FunctionTool(func=query_table),
}

@app.list_tools()
async def list_mcp_tools() -> list[mcp_types.Tool]:
    logging.info("MCP Server (JD Agent Tools): Received list_tools request.")
    mcp_tools_list = []
    for tool_name, adk_tool_instance in ADK_ALL_TOOLS.items():
        if not adk_tool_instance.name:
            adk_tool_instance.name = tool_name
        mcp_tools_list.append(adk_to_mcp_tool_type(adk_tool_instance))
    return mcp_tools_list

@app.call_tool()
async def call_mcp_tool(name: str, arguments: dict) -> list[mcp_types.TextContent]:
    logging.info(f"MCP Server (JD Agent Tools): Received call_tool request for '{name}' with args: {arguments}")
    if name in ADK_ALL_TOOLS:
        adk_tool_instance = ADK_ALL_TOOLS[name]
        try:
            # Handle list[dict] response for query_table, rank_candidates and save_ranked_candidates
            # Ensure JSON serialization for complex objects
            if name in ["query_table"]:
                adk_tool_response = await adk_tool_instance.run_async(
                    args=arguments,
                    tool_context=None,
                )
                response_text = json.dumps(adk_tool_response, indent=2)
            else: # For analyze_jd_industry, which returns a string
                adk_tool_response = await adk_tool_instance.run_async(
                    args=arguments,
                    tool_context=None,
                )
                response_text = str(adk_tool_response) # Convert to string for simple output

            logging.info(f"MCP Server (JD Agent Tools): ADK tool '{name}' executed. Response: {response_text}")
            return [mcp_types.TextContent(type="text", text=response_text)]
        except Exception as e:
            logging.error(f"MCP Server (JD Agent Tools): Error executing ADK tool '{name}': {e}", exc_info=True)
            error_payload = {
                "success": False,
                "message": f"Failed to execute tool '{name}': {str(e)}",
            }
            error_text = json.dumps(error_payload)
            return [mcp_types.TextContent(type="text", text=error_text)]
    else:
        logging.warning(f"MCP Server (JD Agent Tools): Tool '{name}' not found/exposed by this server.")
        error_payload = {
            "success": False,
            "message": f"Tool '{name}' not implemented by this server.",
        }
        error_text = json.dumps(error_payload)
        return [mcp_types.TextContent(type="text", text=error_text)]

# --- MCP Server Runner ---
async def run_mcp_stdio_server():
    async with stdio.stdio_server() as (read_stream, write_stream):
        logging.info("MCP Stdio Server (JD Agent Tools): Starting handshake with client...")
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=app.name,
                server_version="0.1.0",
                capabilities=app.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
        logging.info("MCP Stdio Server (JD Agent Tools): Run loop finished or client disconnected.")

if __name__ == "__main__":
    logging.info("Launching JD Agent's combined tool MCP Server via stdio...")
    try:
        asyncio.run(run_mcp_stdio_server())
    except KeyboardInterrupt:
        logging.info("\nJD Agent's combined tool MCP Server (stdio) stopped by user.")
    except Exception as e:
        logging.critical(f"JD Agent's combined tool MCP Server (stdio) encountered an unhandled error: {e}", exc_info=True)
    finally:
        logging.info("JD Agent's combined tool MCP Server (stdio) process exiting.")