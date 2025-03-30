from aws_cdk import (  # type: ignore
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecr_assets as ecr_assets,
    aws_iam as iam,
    RemovalPolicy
)
from constructs import Construct  # type: ignore
import os

class S3Stack(Stack):

    # Accept vpc and cluster as input parameters
    def __init__(self, scope: Construct, construct_id: str, vpc: ec2.IVpc, cluster: ecs.ICluster, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- ECR Asset (Build Docker Image) ---
        docker_build_path = os.path.join(os.path.dirname(__file__), "..", "..", "mcp_servers", "s3")

        # Basic sanity check for Dockerfile existence
        if not os.path.exists(os.path.join(docker_build_path, "Dockerfile")):
             raise FileNotFoundError(f"Dockerfile not found in: {docker_build_path}")

        docker_asset = ecr_assets.DockerImageAsset(self, "S3ServiceImageAsset",
            directory=docker_build_path
        )

        # --- IAM Role for ECS Task ---
        task_role = iam.Role(self, "S3ServiceTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description="IAM role for S3 MCP server task"
        )
        # Add permissions to call AWS S3 APIs
        task_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "s3:ListAllMyBuckets", # For list_buckets tool
                "s3:ListBucket",       # For list_objects tool
                "s3:GetObject",        # For get_object tool
                "s3:PutObject",        # For put_object tool
                "s3:DeleteObject"      # For delete_object tool
                # Add other S3 permissions if more tools are added
            ],
            # Grant access to all buckets/objects for simplicity.
            # Consider restricting this in production environments.
            resources=["*"]
        ))

        # --- ECS Task Definition (Fargate) ---
        fargate_task_definition = ecs.FargateTaskDefinition(self, "S3ServiceTaskDef",
            memory_limit_mib=512,
            cpu=256,
            task_role=task_role,
            runtime_platform=ecs.RuntimePlatform(
                operating_system_family=ecs.OperatingSystemFamily.LINUX,
                cpu_architecture=ecs.CpuArchitecture.X86_64 # Match base image in Dockerfile
            )
        )

        container = fargate_task_definition.add_container("S3ServiceContainer",
            image=ecs.ContainerImage.from_docker_image_asset(docker_asset),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="S3ServiceMcp"
            )
            # Add environment variables if needed
        )

        # --- ECS Service (Fargate) ---
        # Use the VPC and Cluster passed in from the LocationServiceStack (or main app)
        fargate_service = ecs.FargateService(self, "S3ServiceFargateService",
            cluster=cluster, # Use the existing cluster
            task_definition=fargate_task_definition,
            desired_count=1,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS), # Run in private subnets of the existing VPC
            assign_public_ip=False
        )