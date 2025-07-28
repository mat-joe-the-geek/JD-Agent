import asyncio
import json
import logging
import os
import sqlite3
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
LOG_FILE_PATH = os.path.join(os.path.dirname(__file__), "mcp_server_activity.log")
logging.basicConfig(
    level=logging.DEBUG, # Set to DEBUG to see detailed LLM prompts/responses
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, mode="w"),
        logging.StreamHandler() # Also print logs to console for easier debugging
    ],
)
# --- End Logging Setup ---

current_dir = os.path.dirname(__file__)
DATABASE_PATH = os.path.join(current_dir, "..", "dbs", "database.db")

# --- Configure Generative AI ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logging.critical("GEMINI_API_KEY not found in .env file. AI classification will NOT work.")
    # Consider exiting or raising an error here in a production environment
    # For now, we'll continue, but classification will fail.
else:
    genai.configure(api_key=GEMINI_API_KEY)
    logging.info("Generative AI configured successfully.")

# Initialize the LLM for classification
# Using a small, fast model for classification, as it's just classification
classification_model = genai.GenerativeModel('gemini-1.5-flash')

# Define the categories for classification - these are the 7 classifications
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


def query_db_table(table_name: str, columns: str = "*", condition: str = "1=1") -> list[dict]:
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
    if condition and condition.strip() != "1=1": # Only add WHERE clause if a real condition is provided
        query += f" WHERE {condition}"
    query += ";"

    try:
        logging.info(f"Executing query_db_table: {query}")
        cursor.execute(query)
        results = [dict(row) for row in cursor.fetchall()]
        logging.info(f"Query returned {len(results)} rows from '{table_name}'.")
    except sqlite3.Error as e:
        logging.error(f"Error querying table '{table_name}' with query '{query}': {e}")
        raise ValueError(f"Error querying table '{table_name}': {e}")
    finally:
        conn.close()
    return results

async def classify_and_transfer_candidates(candidates_data: list[dict]) -> dict:
    """
    Analyzes the 'skill' of each candidate using AI, determines their best fit
    into predefined categories, and inserts them into corresponding tables.
    Tables will be created if they don't exist.

    Args:
        candidates_data (list[dict]): A list of dictionaries, where each dict
                                      represents a candidate row from the database.
                                      Expected to have at least a 'skill' key.

    Returns:
        dict: A summary of the classification and transfer operation.
    """
    if not candidates_data:
        logging.info("classify_and_transfer_candidates received no data. Returning early.")
        return {"success": True, "message": "No candidate data provided for classification.", "transferred_counts": {}}

    if not GEMINI_API_KEY:
        logging.error("GEMINI_API_KEY is not set. Cannot perform AI classification.")
        return {"success": False, "message": "AI Classification API key is missing.", "transferred_counts": {}}

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Ensure transaction safety
        conn.execute("BEGIN TRANSACTION;") # Start a transaction

        transferred_counts = {category: 0 for category in CATEGORIES}

        # Build prompt for AI classification
        # Modified prompt to force classification into one of the defined categories
        classification_prompt_base = f"""
        You are an expert in classifying professional skills into industry categories.
        Your task is to classify the provided candidate's skill description into the SINGLE BEST category from the following precise categories:
        {', '.join(CATEGORIES)}.

        You MUST choose one of the categories provided. Do NOT return 'Unclassified' or any other category not explicitly listed.

        Return ONLY the exact category name. Do NOT include any other words, punctuation, explanations, or conversational filler.
        Ensure your response is ONLY one of the specified category names.

        Examples:
        Candidate Skill: "Python, Django, SQL, Cloud Architecture"
        Category: Software Development

        Candidate Skill: "IT Support, Network Troubleshooting, Helpdesk, VoIP"
        Category: IT Services

        Candidate Skill: "Mortgage Lending, Financial Analysis, Risk Management, Loan Processing"
        Category: Banking

        Candidate Skill: "Underwriting, Claims Processing, Actuarial Science"
        Category: Insurance

        Candidate Skill: "Nursing, Patient Care, Medical Records, Pharmacy Operations"
        Category: Healthcare

        Candidate Skill: "Tour Operations, Hotel Management, Event Planning, Ticketing"
        Category: Travel

        Candidate Skill: "Property Management, Real Estate Sales, Market Analysis, Leasing"
        Category: Real Estate

        Candidate Skill: "{{skill_description}}"
        Category:
        """

        logging.info(f"Starting AI classification and transfer for {len(candidates_data)} candidates...")

        # Keep track of created tables to avoid redundant schema checks
        created_tables = set()

        # Fetch the schema of the original 'candidates' table once
        original_candidates_schema = get_table_schema("candidates")
        original_column_types = {col['name']: col['type'] for col in original_candidates_schema['columns']}


        for i, candidate in enumerate(candidates_data):
            skill_description = candidate.get('skills', '').strip()
            # Use ID if available, otherwise a unique identifier for logging
            candidate_identifier = candidate.get('id', f"idx_{i}")

            logging.debug(f"Processing candidate ID: {candidate_identifier}, Skill: '{skill_description}'")

            if not skill_description:
                logging.warning(f"Candidate {candidate_identifier} has no skill description. Skipping classification.")
                continue

            try:
                # Prepare the prompt for the current candidate
                prompt_for_llm = classification_prompt_base.format(skill_description=skill_description)
                logging.debug(f"Sending prompt to LLM for candidate {candidate_identifier}: \n{prompt_for_llm}")

                # Call the LLM with a low temperature for more deterministic output
                response = await classification_model.generate_content_async(
                    prompt_for_llm,
                    generation_config=genai.types.GenerationConfig(temperature=0.0)
                )

                ai_classification = "Unclassified" # Default in case of parsing/empty response, though prompt aims to avoid this
                if response and response.text:
                    ai_classification = response.text.strip()
                    logging.debug(f"LLM raw response for {candidate_identifier}: '{response.text}'")
                    logging.debug(f"Parsed AI classification for {candidate_identifier}: '{ai_classification}'")
                else:
                    logging.warning(f"LLM returned empty or no text for candidate {candidate_identifier}. This should not happen with current prompt. Defaulting to 'Unclassified'.")

                # Ensure classification is one of the valid categories.
                # If LLM returns something unexpected despite prompt, we fall back to a default if necessary
                if ai_classification not in CATEGORIES:
                    logging.error(f"LLM returned an invalid category '{ai_classification}' for candidate {candidate_identifier}. This should be prevented by the prompt. Attempting to choose a default category or log for review.")
                    # For prototyping, we can assign to a generic category or the first one
                    # For a robust solution, you might need a more sophisticated fallback or re-prompting
                    ai_classification = CATEGORIES[0] # Fallback to Software Development for now, for prototyping
                    logging.info(f"Forced candidate {candidate_identifier} into '{ai_classification}' category due to invalid LLM response.")


                logging.info(f"Candidate {candidate_identifier} (Skill: '{skill_description}') classified as '{ai_classification}'.")
                target_table_name = ai_classification.replace(" ", "_").lower() + "_candidates"

                # Check and create table only if not already done in this run
                if target_table_name not in created_tables:
                    db_schema = get_table_schema(target_table_name)
                    if not db_schema['columns']:
                        column_definitions = []
                        # Use all keys from the current candidate for schema definition, preserving original types
                        for col_name, _ in candidate.items():
                            col_type = original_column_types.get(col_name, "TEXT") # Get original type, default to TEXT
                            column_definitions.append(f'"{col_name}" {col_type}')
                        create_table_sql = f"CREATE TABLE IF NOT EXISTS {target_table_name} ({', '.join(column_definitions)});"
                        cursor.execute(create_table_sql)
                        logging.info(f"Created new table: {target_table_name} for '{ai_classification}' category with schema derived from original data types.")
                    created_tables.add(target_table_name) # Mark as created for this session

                # Prepare data for insertion
                columns_sql = ", ".join(f'"{key}"' for key in candidate.keys()) # Quote column names
                placeholders = ", ".join(["?" for _ in candidate])
                values = tuple(candidate.values())

                insert_query = f"INSERT INTO {target_table_name} ({columns_sql}) VALUES ({placeholders})"
                cursor.execute(insert_query, values)
                transferred_counts[ai_classification] += 1

            except Exception as e:
                logging.error(f"Error processing candidate {candidate_identifier} (Skill: '{skill_description}'): {e}", exc_info=True)
                # If an error occurs during classification, we can log it but still try to move on
                # For prototyping, we might just skip this one or assign to a default as a last resort
                # Here, we'll let it be skipped from counts if an error prevents insertion
                continue

        conn.commit() # Commit all changes from the transaction
        logging.info("Finished processing all candidates. Transaction committed.")

        return {
            "success": True,
            "message": "Candidate classification and transfer completed.",
            "transferred_counts": transferred_counts
        }

    except sqlite3.Error as e:
        if conn:
            conn.rollback() # Rollback on any SQLite error
        logging.error(f"Database error during classification and transfer: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Database error during classification and transfer: {e}",
            "transferred_counts": {}
        }
    except Exception as e:
        if conn:
            conn.rollback() # Rollback on any other error
        logging.critical(f"An unexpected critical error occurred in classify_and_transfer_candidates: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"An unexpected error occurred during classification and transfer: {e}",
            "transferred_counts": {}
        }
    finally:
        if conn:
            conn.close()


# --- MCP Server Setup ---
logging.info("Creating MCP Server instance for SQLite DB...")
app = Server("sqlite-db-mcp-server")

# Wrap database utility functions as ADK FunctionTools
ADK_DB_TOOLS = {
    "query_db_table": FunctionTool(func=query_db_table),
    "classify_and_transfer_candidates": FunctionTool(func=classify_and_transfer_candidates),
    "get_table_schema": FunctionTool(func=get_table_schema), # Helper for internal use by classify_and_transfer_candidates
}


@app.list_tools()
async def list_mcp_tools() -> list[mcp_types.Tool]:
    """MCP handler to list tools this server exposes."""
    logging.info("MCP Server: Received list_tools request.")
    mcp_tools_list = []
    for tool_name, adk_tool_instance in ADK_DB_TOOLS.items():
        if not adk_tool_instance.name:
            adk_tool_instance.name = tool_name

        mcp_tool_schema = adk_to_mcp_tool_type(adk_tool_instance)
        logging.info(f"MCP Server: Advertising tool: {mcp_tool_schema.name}, InputSchema: {mcp_tool_schema.inputSchema}")
        mcp_tools_list.append(mcp_tool_schema)
    return mcp_tools_list


@app.call_tool()
async def call_mcp_tool(name: str, arguments: dict) -> list[mcp_types.TextContent]:
    """MCP handler to execute a tool call requested by an MCP client."""
    logging.info(f"MCP Server: Received call_tool request for '{name}' with args: {arguments}")

    if name in ADK_DB_TOOLS:
        adk_tool_instance = ADK_DB_TOOLS[name]
        try:
            # CORRECTED: Always call run_async() on the FunctionTool instance.
            # The ADK FunctionTool is designed to be called asynchronously,
            # even if the underlying function (adk_tool_instance.func) is synchronous.
            adk_tool_response = await adk_tool_instance.run_async(
                args=arguments,
                tool_context=None,
            )

            logging.info(f"MCP Server: ADK tool '{name}' executed. Response: {adk_tool_response}")
            response_text = json.dumps(adk_tool_response, indent=2)
            return [mcp_types.TextContent(type="text", text=response_text)]

        except Exception as e:
            logging.error(f"MCP Server: Error executing ADK tool '{name}': {e}", exc_info=True)
            error_payload = {
                "success": False,
                "message": f"Failed to execute tool '{name}': {str(e)}",
            }
            error_text = json.dumps(error_payload)
            return [mcp_types.TextContent(type="text", text=error_text)]
    else:
        logging.warning(f"MCP Server: Tool '{name}' not found/exposed by this server.")
        error_payload = {
            "success": False,
            "message": f"Tool '{name}' not implemented by this server.",
        }
        error_text = json.dumps(error_payload)
        return [mcp_types.TextContent(type="text", text=error_text)]



# --- MCP Server Runner ---
async def run_mcp_stdio_server():
    """Runs the MCP server, listening for connections over standard input/output."""
    async with stdio.stdio_server() as (read_stream, write_stream):
        logging.info("MCP Stdio Server: Starting handshake with client...")
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
        logging.info("MCP Stdio Server: Run loop finished or client disconnected.")


if __name__ == "__main__":
    logging.info("Launching SQLite DB MCP Server via stdio...")
    try:
        asyncio.run(run_mcp_stdio_server())
    except KeyboardInterrupt:
        logging.info("\nMCP Server (stdio) stopped by user.")
    except Exception as e:
        logging.critical(f"MCP Server (stdio) encountered an unhandled error: {e}", exc_info=True)
    finally:
        logging.info("MCP Server (stdio) process exiting.")