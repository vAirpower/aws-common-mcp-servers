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
# Adjust imports based on the actual FastMCP library structure
from fastmcp import McpServer, McpTransport, StdioTransport, Tool, ToolParameter, ToolInputSchema, ErrorCode, McpError  # type: ignore

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Boto3 S3 Client ---
# Use environment variables for credentials when running in ECS/EKS via IAM Role
# For local testing, ensure AWS credentials are configured (e.g., ~/.aws/credentials)
s3_client = boto3.client('s3')

# --- Tool Definitions ---

async def list_buckets_handler(args: Dict[str, Any]) -> Dict[str, Any]:
    """Lists all S3 buckets."""
    try:
        response = s3_client.list_buckets()
        buckets = [bucket['Name'] for bucket in response.get('Buckets', [])]
        return {"buckets": buckets}
    except ClientError as e:
        logger.error(f"Error listing buckets: {e}")
        raise McpError(ErrorCode.InternalError, f"AWS S3 API Error: {e.response['Error']['Message']}")

async def list_objects_handler(args: Dict[str, Any]) -> Dict[str, Any]:
    """Lists objects in a specific S3 bucket."""
    bucket_name = args.get('bucket_name')
    prefix = args.get('prefix', '')
    max_keys = args.get('max_keys', 1000)

    if not bucket_name:
        raise McpError(ErrorCode.InvalidParams, "Missing required parameter: bucket_name")

    try:
        paginator = s3_client.get_paginator('list_objects_v2')
        objects = []
        page_iterator = paginator.paginate(Bucket=bucket_name, Prefix=prefix, PaginationConfig={'MaxItems': max_keys})
        for page in page_iterator:
            for obj in page.get('Contents', []):
                objects.append({
                    "key": obj['Key'],
                    "size": obj['Size'],
                    "last_modified": obj['LastModified'].isoformat()
                })
        return {"objects": objects}
    except ClientError as e:
        logger.error(f"Error listing objects in bucket {bucket_name}: {e}")
        raise McpError(ErrorCode.InternalError, f"AWS S3 API Error: {e.response['Error']['Message']}")

async def get_object_handler(args: Dict[str, Any]) -> Dict[str, Any]:
    """Gets the content of an object from an S3 bucket."""
    bucket_name = args.get('bucket_name')
    key = args.get('key')

    if not bucket_name or not key:
        raise McpError(ErrorCode.InvalidParams, "Missing required parameters: bucket_name, key")

    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=key)
        # Read content - handle potential encoding issues if not text
        # For simplicity, assuming UTF-8 text. Binary data might need base64 encoding.
        body = response['Body'].read().decode('utf-8')
        return {"content": body, "content_type": response.get('ContentType', 'unknown')}
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
             raise McpError(ErrorCode.NotFound, f"Object not found: s3://{bucket_name}/{key}")
        logger.error(f"Error getting object s3://{bucket_name}/{key}: {e}")
        raise McpError(ErrorCode.InternalError, f"AWS S3 API Error: {e.response['Error']['Message']}")
    except UnicodeDecodeError:
         raise McpError(ErrorCode.InternalError, "Failed to decode object content as UTF-8. Object might be binary.")


async def put_object_handler(args: Dict[str, Any]) -> Dict[str, Any]:
    """Puts an object into an S3 bucket."""
    bucket_name = args.get('bucket_name')
    key = args.get('key')
    content = args.get('content')
    content_type = args.get('content_type', 'text/plain') # Default content type

    if not bucket_name or not key or content is None:
        raise McpError(ErrorCode.InvalidParams, "Missing required parameters: bucket_name, key, content")

    try:
        # Assuming content is string, encode to bytes
        body_bytes = content.encode('utf-8')
        response = s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=body_bytes,
            ContentType=content_type
        )
        return {"status": "success", "version_id": response.get('VersionId')}
    except ClientError as e:
        logger.error(f"Error putting object s3://{bucket_name}/{key}: {e}")
        raise McpError(ErrorCode.InternalError, f"AWS S3 API Error: {e.response['Error']['Message']}")

async def delete_object_handler(args: Dict[str, Any]) -> Dict[str, Any]:
    """Deletes an object from an S3 bucket."""
    bucket_name = args.get('bucket_name')
    key = args.get('key')

    if not bucket_name or not key:
        raise McpError(ErrorCode.InvalidParams, "Missing required parameters: bucket_name, key")

    try:
        response = s3_client.delete_object(Bucket=bucket_name, Key=key)
        # delete_object returns 204 No Content on success, response dict might be minimal
        return {"status": "success", "delete_marker": response.get('DeleteMarker'), "version_id": response.get('VersionId')}
    except ClientError as e:
        logger.error(f"Error deleting object s3://{bucket_name}/{key}: {e}")
        raise McpError(ErrorCode.InternalError, f"AWS S3 API Error: {e.response['Error']['Message']}")


# --- MCP Server Setup ---

class S3McpServer:
    def __init__(self, transport: McpTransport):
        self.server = McpServer(
            info={
                "name": "aws-s3-mcp-server",
                "version": "0.1.0",
                "description": "MCP Server for interacting with AWS S3",
            },
            transport=transport,
            tools=self._get_tools()
        )
        self.server.onerror = self._handle_error

    def _handle_error(self, error: Exception):
        logger.error(f"MCP Server Error: {error}")
        # Optionally implement more specific error handling or reporting

    def _get_tools(self) -> List[Tool]:
        return [
            Tool(
                name="list_buckets",
                description="Lists all S3 buckets accessible by the configured credentials.",
                input_schema=ToolInputSchema(properties={}), # No input params
                handler=list_buckets_handler
            ),
            Tool(
                name="list_objects",
                description="Lists objects within a specified S3 bucket.",
                input_schema=ToolInputSchema(
                    required=["bucket_name"],
                    properties={
                        "bucket_name": ToolParameter(type="string", description="The name of the S3 bucket."),
                        "prefix": ToolParameter(type="string", description="Optional prefix to filter objects."),
                        "max_keys": ToolParameter(type="integer", description="Optional maximum number of keys to return (default 1000).")
                    }
                ),
                handler=list_objects_handler
            ),
             Tool(
                name="get_object",
                description="Retrieves the content of an object from an S3 bucket (assumes UTF-8 text).",
                input_schema=ToolInputSchema(
                    required=["bucket_name", "key"],
                    properties={
                        "bucket_name": ToolParameter(type="string", description="The name of the S3 bucket."),
                        "key": ToolParameter(type="string", description="The key (path) of the object within the bucket.")
                    }
                ),
                handler=get_object_handler
            ),
             Tool(
                name="put_object",
                description="Uploads content to an object in an S3 bucket.",
                input_schema=ToolInputSchema(
                    required=["bucket_name", "key", "content"],
                    properties={
                        "bucket_name": ToolParameter(type="string", description="The name of the S3 bucket."),
                        "key": ToolParameter(type="string", description="The key (path) for the object within the bucket."),
                        "content": ToolParameter(type="string", description="The string content to upload (will be UTF-8 encoded)."),
                        "content_type": ToolParameter(type="string", description="Optional MIME type for the object (default: text/plain).")
                    }
                ),
                handler=put_object_handler
            ),
             Tool(
                name="delete_object",
                description="Deletes an object from an S3 bucket.",
                input_schema=ToolInputSchema(
                    required=["bucket_name", "key"],
                    properties={
                        "bucket_name": ToolParameter(type="string", description="The name of the S3 bucket."),
                        "key": ToolParameter(type="string", description="The key (path) of the object to delete.")
                    }
                ),
                handler=delete_object_handler
            ),
        ]

    async def run(self):
        logger.info("Starting S3 MCP Server...")
        await self.server.run()
        logger.info("S3 MCP Server stopped.")

async def main():
    # Use StdioTransport for communication when run as a standalone process
    transport = StdioTransport()
    server_instance = S3McpServer(transport)
    await server_instance.run()

if __name__ == "__main__":
    asyncio.run(main())