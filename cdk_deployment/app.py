#!/usr/bin/env python3

import os
import aws_cdk as cdk  # type: ignore

# Import the stack classes we created
from aws_mcp_infra.location_service_stack import LocationServiceStack  # type: ignore
from aws_mcp_infra.s3_stack import S3Stack  # type: ignore
from aws_mcp_infra.aurora_pg_data_api_stack import AuroraPgDataApiStack  # type: ignore

app = cdk.App()

# Instantiate the Location Service stack
# We need the VPC and Cluster from this stack to pass to other stacks
location_stack = LocationServiceStack(app, "LocationServiceMcpStack",
    # If you don't specify 'env', this stack will be environment-agnostic.
    # Account/Region-dependent features and context lookups will not work,
    # but a single synthesized template can be deployed anywhere.

    # Uncomment the next line to specialize this stack for the AWS Account
    # and Region that are implied by the current CLI configuration.
    # env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),

    # Uncomment the next line if you know exactly what Account and Region you
    # want to deploy the stack to. */
    # env=cdk.Environment(account='123456789012', region='us-west-2'), # Replace with your account/region if needed

    # For more information, see https://docs.aws.amazon.com/cdk/latest/guide/environments.html
    )

# Instantiate the S3 stack, passing the VPC and Cluster from the location_stack
S3Stack(app, "S3McpStack",
    vpc=location_stack.vpc,
    cluster=location_stack.cluster,
    env=location_stack.env # Deploy in the same environment
    )

# Instantiate the Aurora PG Data API stack
AuroraPgDataApiStack(app, "AuroraPgDataApiMcpStack", # Updated class and stack name
    vpc=location_stack.vpc,
    cluster=location_stack.cluster,
    env=location_stack.env # Deploy in the same environment
    )

app.synth()
