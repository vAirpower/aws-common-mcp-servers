from aws_cdk import (  # type: ignore
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecr_assets as ecr_assets,
    aws_iam as iam,
    aws_secretsmanager as secretsmanager,
    RemovalPolicy
)
from constructs import Construct  # type: ignore
import os
import json # Required if creating secret template

class AuroraPgDataApiStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, vpc: ec2.IVpc, cluster: ecs.ICluster, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- Database Configuration ---
        # Cluster ARN provided by user (derived from instance ARN)
        db_cluster_arn = "arn:aws:rds:us-west-2:023035850529:cluster:mcp-sql-db-cluster" # IMPORTANT: Verify this is the CLUSTER ARN
        # Secret ARN for the existing RDS-managed secret provided by the user
        db_secret_arn = "arn:aws:secretsmanager:us-west-2:023035850529:secret:rds!cluster-c00a3156-11cf-4395-8f6a-a41de63f6aaa-0Kzuvu"
        default_db_name = "postgres" # Default database to connect to if not specified in tool args

        # Import the existing secret using its ARN
        db_secret = secretsmanager.Secret.from_secret_complete_arn(self, "ImportedRdsDbSecret", db_secret_arn)

        # --- ECR Asset (Build Docker Image) ---
        docker_build_path = os.path.join(os.path.dirname(__file__), "..", "..", "mcp_servers", "aurora_pg_data_api")

        if not os.path.exists(os.path.join(docker_build_path, "Dockerfile")):
             raise FileNotFoundError(f"Dockerfile not found in: {docker_build_path}")

        docker_asset = ecr_assets.DockerImageAsset(self, "AuroraPgDataApiImageAsset",
            directory=docker_build_path
        )

        # --- IAM Role for ECS Task ---
        task_role = iam.Role(self, "AuroraPgDataApiTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description="IAM role for Aurora PG Data API MCP server task"
        )
        # Grant permission to execute statements via RDS Data API on the specific cluster
        task_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "rds-data:ExecuteStatement",
                "rds-data:BatchExecuteStatement"
                # Add other rds-data actions if needed (e.g., BeginTransaction)
            ],
            resources=[db_cluster_arn] # Scope permissions to the specific cluster
        ))
        # Grant permission to read the specific secret
        db_secret.grant_read(task_role)

        # --- ECS Task Definition (Fargate) ---
        fargate_task_definition = ecs.FargateTaskDefinition(self, "AuroraPgDataApiTaskDef",
            memory_limit_mib=512, # Data API might be less memory intensive than direct driver
            cpu=256,
            task_role=task_role,
            runtime_platform=ecs.RuntimePlatform(
                operating_system_family=ecs.OperatingSystemFamily.LINUX,
                cpu_architecture=ecs.CpuArchitecture.X86_64
            )
        )

        container = fargate_task_definition.add_container("AuroraPgDataApiContainer",
            image=ecs.ContainerImage.from_docker_image_asset(docker_asset),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="AuroraPgDataApiMcp"
            ),
            # Pass cluster ARN, secret ARN, and default DB name to the container
            environment={
                "DB_CLUSTER_ARN": db_cluster_arn,
                "DB_SECRET_ARN": db_secret.secret_arn,
                "DEFAULT_DB_NAME": default_db_name
            }
        )

        # --- ECS Service (Fargate) ---
        fargate_service = ecs.FargateService(self, "AuroraPgDataApiFargateService",
            cluster=cluster, # Use the existing cluster
            task_definition=fargate_task_definition,
            desired_count=1,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS), # Run in private subnets
            assign_public_ip=False
            # No specific DB security group rules needed for Data API
        )