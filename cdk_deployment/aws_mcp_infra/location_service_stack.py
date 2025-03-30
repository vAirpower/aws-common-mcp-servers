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

class LocationServiceStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- VPC ---
        # Create a new VPC or use an existing one
        # Using a default VPC for simplicity, but a dedicated VPC is recommended for production
        self.vpc = ec2.Vpc(self, "McpVpc",
            max_azs=2, # Default is all AZs in region
            nat_gateways=1 # Deploy NAT gateway for outbound internet access if needed by the server
        )

        # --- ECS Cluster ---
        self.cluster = ecs.Cluster(self, "McpCluster", vpc=self.vpc)

        # --- ECR Asset (Build Docker Image) ---
        # Define the path to the Dockerfile and context directory
        docker_build_path = os.path.join(os.path.dirname(__file__), "..", "..", "mcp_servers", "location_service")

        # Check if path exists (basic sanity check)
        if not os.path.exists(docker_build_path):
             raise FileNotFoundError(f"Directory for Docker build not found: {docker_build_path}")
        if not os.path.exists(os.path.join(docker_build_path, "Dockerfile")):
             raise FileNotFoundError(f"Dockerfile not found in: {docker_build_path}")

        docker_asset = ecr_assets.DockerImageAsset(self, "LocationServiceImageAsset",
            directory=docker_build_path
            # platform=ecr_assets.Platform.LINUX_AMD64 # Specify platform if needed
        )

        # --- IAM Role for ECS Task ---
        # Define permissions needed by the Location Service MCP server
        task_role = iam.Role(self, "LocationServiceTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description="IAM role for Location Service MCP server task"
        )
        # Add permissions to call AWS Location Service APIs
        task_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "geo:SearchPlaceIndexForText",
                "geo:GetPlace",
                "geo:CalculateRoute",
                "geo:ListPlaceIndexes",
                "geo:ListRouteCalculators",
                "geo:ListMaps",
                "geo:DescribePlaceIndex",
                "geo:DescribeMap",
                # Add any other specific Location Service actions used by the server
            ],
            resources=["*"] # Consider scoping down resources if possible
        ))

        # --- ECS Task Definition (Fargate) ---
        fargate_task_definition = ecs.FargateTaskDefinition(self, "LocationServiceTaskDef",
            memory_limit_mib=512,  # Adjust as needed
            cpu=256,              # Adjust as needed
            task_role=task_role,
            runtime_platform=ecs.RuntimePlatform(
                operating_system_family=ecs.OperatingSystemFamily.LINUX,
                cpu_architecture=ecs.CpuArchitecture.X86_64 # Or ARM64 if base image supports it
            )
        )

        # Add container to the task definition
        container = fargate_task_definition.add_container("LocationServiceContainer",
            image=ecs.ContainerImage.from_docker_image_asset(docker_asset),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="LocationServiceMcp"
            ),
            # Pass the desired AWS region to the container
            environment={
                "AWS_REGION": "us-west-2"
            }
        )

        # --- ECS Service (Fargate) ---
        fargate_service = ecs.FargateService(self, "LocationServiceFargateService",
            cluster=self.cluster,
            task_definition=fargate_task_definition,
            desired_count=1, # Run one instance of the task
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS), # Run in private subnets
            assign_public_ip=False # No public IP needed if accessed internally or via other means
        )

        # Note: This setup runs the MCP server, but doesn't expose it publicly.
        # Communication with the server (e.g., from a Bedrock Agent or Lambda)
        # would typically happen over AWS internal networking or potentially via
        # AWS Systems Manager Session Manager if direct interaction is needed.
        # For MCP clients outside AWS, additional setup (like an ALB or API Gateway)
        # would be required, which is beyond the scope of just running the server.