from pathlib import Path
from typing import Optional

from aws_cdk import (Aws, CfnOutput, Duration, RemovalPolicy, Stack, aws_dynamodb as dynamodb,
                     aws_events as events, aws_events_targets as targets, aws_iam as iam,
                     aws_lambda as _lambda)
from constructs import Construct

try:
    from aws_cdk.aws_lambda_python_alpha import PythonFunction
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "aws-cdk-lib aws_lambda_python_alpha module is required. Ensure the dependency is added."
    ) from exc


class LambdaStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        openai_secret_arn: str,
        gmail_secret_arn: str,
        environment_name: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        table = dynamodb.Table(
            self,
            "EventsTable",
            table_name="Events",
            partition_key=dynamodb.Attribute(name="id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
        )

        table.add_global_secondary_index(
            index_name="category-index",
            partition_key=dynamodb.Attribute(name="category", type=dynamodb.AttributeType.STRING),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        table.add_global_secondary_index(
            index_name="source_name-index",
            partition_key=dynamodb.Attribute(name="source_name", type=dynamodb.AttributeType.STRING),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        table.add_global_secondary_index(
            index_name="start_time-index",
            partition_key=dynamodb.Attribute(name="start_time", type=dynamodb.AttributeType.STRING),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        lambda_function = PythonFunction(
            self,
            "GmailEventsIngestionLambda",
            entry=str(Path(__file__).resolve().parents[1] / "lambda"),
            index="lambda_function.py",
            handler="handler",
            runtime=_lambda.Runtime.PYTHON_3_11,
            environment={
                "OPENAI_SECRET_ARN": openai_secret_arn,
                "GMAIL_SECRET_ARN": gmail_secret_arn,
                "TABLE_NAME": table.table_name,
                "TIMEZONE": "America/New_York",
            },
            timeout=Duration.minutes(5),
        )

        table.grant_read_write_data(lambda_function)

        for secret_arn in [openai_secret_arn, gmail_secret_arn]:
            lambda_function.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["secretsmanager:GetSecretValue"],
                    resources=[secret_arn],
                )
            )

        lambda_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=["*"]
                if environment_name is None
                else [f"arn:{Aws.PARTITION}:logs:{Aws.REGION}:{Aws.ACCOUNT_ID}:*"],
            )
        )

        schedule = events.Schedule.cron(
            minute="0",
            hour="17",
            week_day="MON",
            time_zone=events.TimeZone("America/New_York"),
        )

        rule = events.Rule(
            self,
            "WeeklyGmailIngestionRule",
            schedule=schedule,
            description="Triggers the Gmail ingestion Lambda every Monday at 5 PM America/New_York",
        )
        rule.add_target(targets.LambdaFunction(lambda_function))

        CfnOutput(self, "EventsTableName", value=table.table_name)
        CfnOutput(self, "GmailLambdaArn", value=lambda_function.function_arn)
