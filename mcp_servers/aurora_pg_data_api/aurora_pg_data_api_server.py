#!/usr/bin/env python3

import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

import boto3  # type: ignore
from botocore.exceptions import ClientError  # type: ignore

# Assuming FastMCP is installed and provides these components
from fastmcp import McpServer, McpTransport, StdioTransport, Tool, ToolParameter, ToolInputSchema, ErrorCode, McpError  # type: ignore

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Boto3 Client for RDS Data API ---
rds_data_client = boto3.client('rds-data')

# --- Configuration from Environment Variables ---
# These will be provided by the CDK stack
CLUSTER_ARN = os.environ.get("DB_CLUSTER_ARN")
SECRET_ARN = os.environ.get("DB_SECRET_ARN")
DEFAULT_DATABASE_NAME = os.environ.get("DEFAULT_DB_NAME", "postgres") # Default DB, often 'postgres' for PG

if not CLUSTER_ARN or not SECRET_ARN:
    logger.error("Missing required environment variables: DB_CLUSTER_ARN and DB_SECRET_ARN")
    sys.exit(1)

# --- Tool Handlers ---

def format_records(records: List[List[Dict[str, Any]]], column_metadata: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """ Formats RDS Data API results into a list of dictionaries """
    formatted_results = []
    column_names = [meta['label'] for meta in column_metadata] # Use label as column name

    for record in records:
        row = {}
        for i, field in enumerate(record):
            key = column_names[i]
            # Extract value based on type hint from Data API
            if 'stringValue' in field:
                row[key] = field['stringValue']
            elif 'longValue' in field:
                row[key] = field['longValue']
            elif 'doubleValue' in field:
                row[key] = field['doubleValue']
            elif 'booleanValue' in field:
                row[key] = field['booleanValue']
            elif 'blobValue' in field:
                row[key] = f"BLOB (length: {len(field['blobValue'])})" # Represent blob as string placeholder
            elif 'isNull' in field and field['isNull']:
                row[key] = None
            else:
                 # Handle other types like arrayValue if needed
                 row[key] = f"Unsupported type: {list(field.keys())[0]}"
        formatted_results.append(row)
    return formatted_results

async def execute_sql_handler(args: Dict[str, Any]) -> Dict[str, Any]:
    """Executes a SQL statement using the RDS Data API."""
    sql = args.get('sql_statement')
    database = args.get('database_name', DEFAULT_DATABASE_NAME) # Use default DB if not specified
    include_result_metadata = args.get('include_result_metadata', False)
    continue_after_timeout = args.get('continue_after_timeout', False)
    # Parameters for prepared statements (optional)
    parameters = args.get('parameters') # Expects a list of {'name': 'param_name', 'value': {'stringValue': 'val', ...}}

    if not sql:
        raise McpError(ErrorCode.InvalidParams, "Missing required parameter: sql_statement")

    try:
        logger.info(f"Executing SQL via Data API on DB '{database}': {sql[:100]}...")
        params_to_pass = {
            'resourceArn': CLUSTER_ARN,
            'secretArn': SECRET_ARN,
            'database': database,
            'sql': sql,
            'includeResultMetadata': include_result_metadata,
            'continueAfterTimeout': continue_after_timeout,
        }
        if parameters:
            params_to_pass['parameters'] = parameters

        response = rds_data_client.execute_statement(**params_to_pass)

        result = {
            "status": "success",
            "records_updated": response.get('numberOfRecordsUpdated', 0),
            "generated_fields": response.get('generatedFields', []), # For INSERT with RETURNING
        }
        if 'records' in response:
            if include_result_metadata and 'columnMetadata' in response:
                 result['column_metadata'] = response['columnMetadata']
                 result['records'] = format_records(response['records'], response['columnMetadata'])
            else:
                 # If no metadata, return raw records structure or attempt basic formatting
                 result['records'] = response['records'] # Raw format might be less useful

        return result

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code')
        error_message = e.response.get('Error', {}).get('Message', str(e))
        logger.error(f"RDS Data API Error ({error_code}): {error_message}")
        # Map common RDS Data API errors to MCP errors
        if error_code == 'BadRequestException':
            # Could be syntax error, invalid params, etc.
             raise McpError(ErrorCode.InvalidRequest, f"RDS Data API Bad Request: {error_message}")
        elif error_code == 'StatementTimeoutException':
             raise McpError(ErrorCode.Timeout, f"RDS Data API Statement Timeout: {error_message}")
        elif error_code == 'ForbiddenException':
             raise McpError(ErrorCode.PermissionDenied, f"RDS Data API Forbidden: {error_message}")
        elif error_code == 'NotFoundException':
             raise McpError(ErrorCode.NotFound, f"RDS Data API Not Found (e.g., DB): {error_message}")
        elif error_code == 'ServiceUnavailableError':
             raise McpError(ErrorCode.Unavailable, f"RDS Data API Service Unavailable: {error_message}")
        else:
             raise McpError(ErrorCode.InternalError, f"RDS Data API Error: {error_message}")
    except Exception as e:
        logger.exception(f"Unexpected error during SQL execution: {e}")
        raise McpError(ErrorCode.InternalError, f"Unexpected server error: {e}")


# --- MCP Server Setup ---

class AuroraPgDataApiMcpServer:
    def __init__(self, transport: McpTransport):
        self.server = McpServer(
            info={
                "name": "aws-aurora-pg-data-api-mcp-server",
                "version": "0.1.0",
                "description": "MCP Server for executing SQL on Aurora PostgreSQL via RDS Data API",
            },
            transport=transport,
            tools=self._get_tools()
        )
        self.server.onerror = self._handle_error

    def _handle_error(self, error: Exception):
        logger.error(f"MCP Server Error: {error}")

    def _get_tools(self) -> List[Tool]:
        return [
            Tool(
                name="execute_sql",
                description="Executes a SQL statement against the configured Aurora PostgreSQL cluster using the RDS Data API.",
                input_schema=ToolInputSchema(
                    required=["sql_statement"],
                    properties={
                        "sql_statement": ToolParameter(type="string", description="The SQL statement to execute."),
                        "database_name": ToolParameter(type="string", description=f"Optional name of the database to target (default: {DEFAULT_DATABASE_NAME})."),
                        "include_result_metadata": ToolParameter(type="boolean", description="Optional. Include column metadata in the response (default: false)."),
                        "continue_after_timeout": ToolParameter(type="boolean", description="Optional. Continue running query after timeout (default: false)."),
                        "parameters": ToolParameter(
                            type="array",
                            description="Optional. Parameters for the SQL statement (use :param_name syntax in SQL).",
                            items={
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "value": {
                                        "type": "object",
                                        "description": "Value with type hint, e.g., {'stringValue': 'value'}, {'longValue': 123}, {'isNull': true}"
                                    }
                                },
                                "required": ["name", "value"]
                            }
                        )
                    }
                ),
                handler=execute_sql_handler
            ),
            # Add helper tools if desired, e.g., list_databases (executes specific SQL)
            # Tool(name="list_databases", description="Lists databases using SQL.", input_schema=..., handler=...)
        ]

    async def run(self):
        if not CLUSTER_ARN or not SECRET_ARN:
             logger.critical("Server cannot start: DB_CLUSTER_ARN and DB_SECRET_ARN must be set.")
             return # Prevent server from running without config

        logger.info(f"Starting Aurora PG Data API MCP Server for cluster: {CLUSTER_ARN}")
        await self.server.run()
        logger.info("Aurora PG Data API MCP Server stopped.")

async def main():
    transport = StdioTransport()
    server_instance = AuroraPgDataApiMcpServer(transport)
    await server_instance.run()

if __name__ == "__main__":
    asyncio.run(main())