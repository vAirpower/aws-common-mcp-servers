# AWS Common MCP Servers with CDK Deployment

This project provides deployable Model Context Protocol (MCP) servers for common AWS services, along with AWS Cloud Development Kit (CDK) code (Python) to provision the necessary infrastructure for running these servers, typically on ECS Fargate.

The goal is to offer reusable components that AI developers (e.g., using Amazon Bedrock, LangChain) can easily deploy into their AWS accounts to interact with AWS services through the standardized MCP interface.

## Included MCP Servers

1.  **AWS Location Service:** (TypeScript) Exposes functionalities like searching places, getting place details, calculating routes, etc. Based on the [aws-location-server](https://github.com/modelcontextprotocol/servers/tree/main/src/aws-location).
2.  **Amazon S3:** (Python) Provides tools for basic S3 operations like listing buckets/objects, getting, putting, and deleting objects.
3.  **Amazon Aurora PostgreSQL (via RDS Data API):** (Python) Allows executing SQL statements against a specified Aurora PostgreSQL cluster using the secure RDS Data API.

## Prerequisites

*   AWS Account
*   AWS CLI configured locally with appropriate permissions (for CDK deployment). Credentials should be set up via `~/.aws/credentials` or environment variables.
*   Node.js and npm (for the Location Service server build process and CDK)
*   Python 3.9+ (for CDK and Python-based MCP servers)
*   AWS CDK CLI (`npm install -g aws-cdk`)
*   Docker (running locally for CDK to build container images)
*   Git

**Specific Prerequisites for Aurora PostgreSQL Data API Server:**

*   An existing Aurora PostgreSQL-Compatible cluster running in your target AWS region.
*   The cluster must have the RDS Data API enabled.
*   An AWS Secrets Manager secret containing the database credentials (username, password) for the cluster. The ARN of this secret is required for deployment.

## Project Structure

```
aws-mcp-infra/
├── mcp_servers/             # Source code for the MCP servers
│   ├── location_service/    # TypeScript server for AWS Location Service
│   ├── s3/                  # Python server for S3
│   └── aurora_pg_data_api/  # Python server for Aurora PG Data API
├── cdk_deployment/          # AWS CDK code (Python)
│   ├── app.py               # CDK App entry point
│   ├── cdk.json             # CDK configuration
│   ├── requirements.txt     # CDK Python dependencies
│   └── aws_mcp_infra/       # CDK Stack definitions
│       ├── __init__.py
│       ├── location_service_stack.py
│       ├── s3_stack.py
│       └── aurora_pg_data_api_stack.py
├── .gitignore
└── README.md                # This file
```

## Deployment

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/vAirpower/aws-common-mcp-servers.git
    cd aws-common-mcp-servers
    ```
2.  **Configure Aurora Prerequisites (if deploying Aurora server):**
    *   Ensure your Aurora PostgreSQL cluster exists and has the Data API enabled.
    *   Create a secret in AWS Secrets Manager (same region as deployment) containing the DB credentials (e.g., keys `username`, `password`).
    *   Update the `db_cluster_arn` and `db_secret_arn` variables in `cdk_deployment/aws_mcp_infra/aurora_pg_data_api_stack.py` with your specific cluster ARN and the ARN of the secret you created.
3.  **Install CDK Dependencies:**
    ```bash
    cd cdk_deployment
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```
4.  **Bootstrap CDK (if first time using CDK in this account/region):**
    ```bash
    cdk bootstrap aws://ACCOUNT-NUMBER/REGION # Replace with your AWS account number and region
    ```
5.  **Deploy Stacks:** Deploy all stacks (creates VPC, Cluster, and all three services):
    ```bash
    cdk deploy --all --require-approval never
    ```
    Or deploy specific stacks:
    ```bash
    cdk deploy LocationServiceMcpStack S3McpStack AuroraPgDataApiMcpStack --require-approval never
    ```

Deployment will build the Docker images for each server, push them to ECR repositories created by CDK, and provision the ECS Fargate services.

## Usage

Once deployed, the MCP servers run as tasks within ECS Fargate services. They are not publicly exposed by default. Interaction typically occurs from within your AWS environment:

*   **From Lambda Functions / Bedrock Agents:** Use the AWS SDK (e.g., `boto3` for Python) to invoke the ECS tasks or potentially interact via AWS Systems Manager Session Manager (if configured). The exact mechanism depends on how the client application is designed to communicate with MCP servers running in ECS.
*   **Local Testing (Requires Adaptation):** To test these servers locally *before* deployment, you would typically run them directly (`node build/index.js` or `python aurora_pg_data_api_server.py`) after installing their respective dependencies (`npm install` or `pip install -r requirements.txt`) and ensuring your local environment has AWS credentials configured. For the Aurora server, you'd also need to set the `DB_CLUSTER_ARN` and `DB_SECRET_ARN` environment variables locally.

## Cleanup

To remove all deployed resources, run:
```bash
cd cdk_deployment
source .venv/bin/activate
cdk destroy --all
```