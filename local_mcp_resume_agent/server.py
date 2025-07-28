import asyncio
import json
import logging
import os
import sqlite3
import io  # New import for CSV handling
import csv # New import for CSV handling

# MCP Server Stdio Import Fix
from mcp.server import stdio
from dotenv import load_dotenv

# ADK Tool Imports
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
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, mode="w"),
    ],
)
# --- End Logging Setup ---

current_dir = os.path.dirname(__file__)
DATABASE_PATH = os.path.join(current_dir, "..", "dbs", "database.db")


# --- Database Utility Functions ---
def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row  # To access columns by name
    return conn


def list_db_tables(dummy_param: str) -> dict:
    """Lists all tables in the SQLite database.

    Args:
        dummy_param (str): This parameter is not used by the function
                           but helps ensure schema generation. A non-empty string is expected.
    Returns:
        dict: A dictionary with keys 'success' (bool), 'message' (str),
              and 'tables' (list[str]) containing the table names if successful.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        return {
            "success": True,
            "message": "Tables listed successfully.",
            "tables": tables,
        }
    except sqlite3.Error as e:
        return {"success": False, "message": f"Error listing tables: {e}", "tables": []}
    except Exception as e:
        return {
            "success": False,
            "message": f"An unexpected error occurred while listing tables: {e}",
            "tables": [],
        }


def get_table_schema(table_name: str) -> dict:
    """Gets the schema (column names and types) of a specific table."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info('{table_name}');")  # Use PRAGMA for schema
    schema_info = cursor.fetchall()
    conn.close()
    if not schema_info:
        raise ValueError(f"Table '{table_name}' not found or no schema information.")

    columns = [{"name": row["name"], "type": row["type"]} for row in schema_info]
    return {"table_name": table_name, "columns": columns}


def query_db_table(table_name: str, columns: str, condition: str) -> list[dict]:
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
    if condition:
        query += f" WHERE {condition}"
    query += ";"

    try:
        cursor.execute(query)
        results = [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        conn.close()
        raise ValueError(f"Error querying table '{table_name}': {e}")
    conn.close()
    return results


def insert_data(table_name: str, data: dict) -> dict:
    """Inserts a new row of data into the specified table.

    Args:
        table_name (str): The name of the table to insert data into.
        data (dict): A dictionary where keys are column names and values are the
                     corresponding values for the new row.

    Returns:
        dict: A dictionary with keys 'success' (bool) and 'message' (str).
              If successful, 'message' includes the ID of the newly inserted row.
    """
    if not data:
        return {"success": False, "message": "No data provided for insertion."}

    conn = get_db_connection()
    cursor = conn.cursor()

    columns = ", ".join(data.keys())
    placeholders = ", ".join(["?" for _ in data])
    values = tuple(data.values())

    query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"

    try:
        cursor.execute(query, values)
        conn.commit()
        last_row_id = cursor.lastrowid
        return {
            "success": True,
            "message": f"Data inserted successfully. Row ID: {last_row_id}",
            "row_id": last_row_id,
        }
    except sqlite3.Error as e:
        conn.rollback()  # Roll back changes on error
        return {
            "success": False,
            "message": f"Error inserting data into table '{table_name}': {e}",
        }
    finally:
        conn.close()

def update_data(table_name: str, new_values: dict, condition: str) -> dict:
    """Updates existing rows in a table based on a given condition.

    Args:
        table_name (str): The name of the table to update.
        new_values (dict): A dictionary where keys are column names to update
                           and values are the new values for those columns.
        condition (str): The SQL WHERE clause condition to specify which rows to update.
                         This condition MUST NOT be empty to prevent accidental mass updates.

    Returns:
        dict: A dictionary with keys 'success' (bool) and 'message' (str).
              If successful, 'message' includes the count of updated rows.
    """
    if not new_values:
        return {"success": False, "message": "No new values provided for update."}

    if not condition or not condition.strip():
        return {
            "success": False,
            "message": "Update condition cannot be empty. This is a safety measure to prevent accidental update of all rows.",
        }

    conn = get_db_connection()
    cursor = conn.cursor()

    set_clauses = []
    values_to_set = []
    for column, value in new_values.items():
        set_clauses.append(f"{column} = ?")
        values_to_set.append(value)

    set_clause_str = ", ".join(set_clauses)

    query = f"UPDATE {table_name} SET {set_clause_str} WHERE {condition}"

    try:
        cursor.execute(query, tuple(values_to_set))
        rows_updated = cursor.rowcount
        conn.commit()
        return {
            "success": True,
            "message": f"{rows_updated} row(s) updated successfully in table '{table_name}'.",
            "rows_updated": rows_updated,
        }
    except sqlite3.Error as e:
        conn.rollback()
        return {
            "success": False,
            "message": f"Error updating data in table '{table_name}': {e}",
        }
    finally:
        conn.close()


def delete_data(table_name: str, condition: str) -> dict:
    """Deletes rows from a table based on a given SQL WHERE clause condition.

    Args:
        table_name (str): The name of the table to delete data from.
        condition (str): The SQL WHERE clause condition to specify which rows to delete.
                         This condition MUST NOT be empty to prevent accidental mass deletion.

    Returns:
        dict: A dictionary with keys 'success' (bool) and 'message' (str).
              If successful, 'message' includes the count of deleted rows.
    """
    if not condition or not condition.strip():
        return {
            "success": False,
            "message": "Deletion condition cannot be empty. This is a safety measure to prevent accidental deletion of all rows.",
        }

    conn = get_db_connection()
    cursor = conn.cursor()

    query = f"DELETE FROM {table_name} WHERE {condition}"

    try:
        cursor.execute(query)
        rows_deleted = cursor.rowcount
        conn.commit()
        return {
            "success": True,
            "message": f"{rows_deleted} row(s) deleted successfully from table '{table_name}'.",
            "rows_deleted": rows_deleted,
        }
    except sqlite3.Error as e:
        conn.rollback()
        return {
            "success": False,
            "message": f"Error deleting data from table '{table_name}': {e}",
        }
    finally:
        conn.close()


# --- New CSV Import Function ---
def insert_data_from_csv(table_name: str, csv_content: str) -> dict:
    """
    Inserts data from a CSV string into the specified SQLite table.
    The CSV header must match the table's column names.

    Args:
        table_name (str): The name of the table to insert data into.
        csv_content (str): The entire content of the CSV file as a string.

    Returns:
        dict: A dictionary with 'success' (bool) and 'message' (str),
              and 'rows_inserted' (int) if successful.
    """
    if not csv_content.strip():
        return {"success": False, "message": "No CSV content provided for insertion."}

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        csv_file_like_object = io.StringIO(csv_content)
        reader = csv.DictReader(csv_file_like_object)

        csv_columns = reader.fieldnames
        if not csv_columns:
            raise ValueError("CSV file is empty or missing headers.")

        # Get table schema from the database
        db_schema = get_table_schema(table_name) # Re-use existing get_table_schema
        db_column_names = {col['name'] for col in db_schema['columns']}

        # Validate if CSV columns exist in the database table
        for col in csv_columns:
            if col not in db_column_names:
                raise ValueError(f"CSV column '{col}' not found in table '{table_name}'. "
                                 "Please ensure CSV headers match database column names.")

        # Prepare for batch insertion
        placeholders = ", ".join("?" * len(csv_columns))
        columns_sql = ", ".join(f'"{col}"' for col in csv_columns) # Quote column names for safety
        insert_query = f"INSERT INTO {table_name} ({columns_sql}) VALUES ({placeholders})"

        data_to_insert = []
        for row_num, row_data in enumerate(reader):
            values = [row_data.get(col, None) for col in csv_columns]
            data_to_insert.append(tuple(values))

        if not data_to_insert:
            return {"success": True, "message": "CSV content parsed but no rows found to insert.", "rows_inserted": 0}

        cursor.executemany(insert_query, data_to_insert)
        conn.commit()
        rows_inserted = cursor.rowcount

        return {
            "success": True,
            "message": f"Successfully inserted {rows_inserted} row(s) into table '{table_name}'.",
            "rows_inserted": rows_inserted,
        }

    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        return {
            "success": False,
            "message": f"Database error during CSV insert: {e}",
            "rows_inserted": 0,
        }
    except ValueError as e:
        if conn:
            conn.rollback()
        return {
            "success": False,
            "message": f"CSV data validation error: {e}",
            "rows_inserted": 0,
        }
    except Exception as e:
        if conn:
            conn.rollback()
        return {
            "success": False,
            "message": f"An unexpected error occurred during CSV insert: {e}",
            "rows_inserted": 0,
        }
    finally:
        if conn:
            conn.close()


# --- MCP Server Setup ---
logging.info(
    "Creating MCP Server instance for SQLite DB..."
)
app = Server("sqlite-db-mcp-server")

# Wrap database utility functions as ADK FunctionTools
ADK_DB_TOOLS = {
    "list_db_tables": FunctionTool(func=list_db_tables),
    "get_table_schema": FunctionTool(func=get_table_schema),
    "query_db_table": FunctionTool(func=query_db_table),
    "insert_data": FunctionTool(func=insert_data),
    "update_data":FunctionTool(func=update_data),
    "delete_data": FunctionTool(func=delete_data),
    "insert_data_from_csv": FunctionTool(func=insert_data_from_csv), # NEW: CSV Import Tool
}


@app.list_tools()
async def list_mcp_tools() -> list[mcp_types.Tool]:
    """MCP handler to list tools this server exposes."""
    logging.info(
        "MCP Server: Received list_tools request."
    )
    mcp_tools_list = []
    for tool_name, adk_tool_instance in ADK_DB_TOOLS.items():
        if not adk_tool_instance.name:
            adk_tool_instance.name = tool_name

        mcp_tool_schema = adk_to_mcp_tool_type(adk_tool_instance)
        logging.info(
            f"MCP Server: Advertising tool: {mcp_tool_schema.name}, InputSchema: {mcp_tool_schema.inputSchema}"
        )
        mcp_tools_list.append(mcp_tool_schema)
    return mcp_tools_list


@app.call_tool()
async def call_mcp_tool(name: str, arguments: dict) -> list[mcp_types.TextContent]:
    """MCP handler to execute a tool call requested by an MCP client."""
    logging.info(
        f"MCP Server: Received call_tool request for '{name}' with args: {arguments}"
    )

    if name in ADK_DB_TOOLS:
        adk_tool_instance = ADK_DB_TOOLS[name]
        try:
            adk_tool_response = await adk_tool_instance.run_async(
                args=arguments,
                tool_context=None,
            )
            logging.info(
                f"MCP Server: ADK tool '{name}' executed. Response: {adk_tool_response}"
            )
            response_text = json.dumps(adk_tool_response, indent=2)
            return [mcp_types.TextContent(type="text", text=response_text)]

        except Exception as e:
            logging.error(
                f"MCP Server: Error executing ADK tool '{name}': {e}", exc_info=True
            )
            error_payload = {
                "success": False,
                "message": f"Failed to execute tool '{name}': {str(e)}",
            }
            error_text = json.dumps(error_payload)
            return [mcp_types.TextContent(type="text", text=error_text)]
    else:
        logging.warning(
            f"MCP Server: Tool '{name}' not found/exposed by this server."
        )
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
        logging.info(
            "MCP Stdio Server: Starting handshake with client..."
        )
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
        logging.info(
            "MCP Stdio Server: Run loop finished or client disconnected."
        )


if __name__ == "__main__":
    logging.info(
        "Launching SQLite DB MCP Server via stdio..."
    )
    try:
        asyncio.run(run_mcp_stdio_server())
    except KeyboardInterrupt:
        logging.info(
            "\nMCP Server (stdio) stopped by user."
        )
    except Exception as e:
        logging.critical(
            f"MCP Server (stdio) encountered an unhandled error: {e}", exc_info=True
        )
    finally:
        logging.info(
            "MCP Server (stdio) process exiting."
        )