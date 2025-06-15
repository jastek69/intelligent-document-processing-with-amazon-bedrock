"""
Copyright © Amazon.com and Affiliates
"""

from aws_cdk import Aws, RemovalPolicy
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as _s3
from constructs import Construct

# https://docs.aws.amazon.com/elasticloadbalancing/latest/application/enable-access-logging.html#attach-bucket-policy
ELB_ACCOUNT_ID_PER_PRE_AUG_2022_REGION = {
    "us-east-1": "127311923021",
    "us-east-2": "033677994240",
    "us-west-1": "027434742980",
    "us-west-2": "797873946194",
    "af-south-1": "098369216593",
    "ap-east-1": "754344448648",
    "ap-southeast-3": "589379963580",
    "ap-south-1": "718504428378",
    "ap-northeast-3": "383597477331",
    "ap-northeast-2": "600734575887",
    "ap-southeast-1": "114774131450",
    "ap-southeast-2": "783225319266",
    "ap-northeast-1": "582318560864",
    "ca-central-1": "985666609251",
    "eu-central-1": "054676820928",
    "eu-west-1": "156460612806",
    "eu-west-2": "652711504416",
    "eu-south-1": "635631232127",
    "eu-west-3": "009996457667",
    "eu-north-1": "897822967062",
    "me-south-1": "076674570225",
    "sa-east-1": "507241528517",
    "us-gov-west-1": "048591011584",
    "us-gov-east-1": "190560391635",
}


def get_elb_server_access_logging_principal(region: str) -> iam.IPrincipal:
    if region in ELB_ACCOUNT_ID_PER_PRE_AUG_2022_REGION:
        return iam.AccountPrincipal(ELB_ACCOUNT_ID_PER_PRE_AUG_2022_REGION[region])
    return iam.ServicePrincipal("logdelivery.elasticloadbalancing.amazonaws.com")


class ServerAccessLogsBucket(Construct):
    def __init__(self, scope: Construct, id: str, stack_name: str) -> None:
        super().__init__(scope, id)
        bucket_name = f"{stack_name.lower()}-server-access-logs-{Aws.ACCOUNT_ID}"
        self.bucket = _s3.Bucket(
            self,
            id=f"{stack_name}-server-access-logs-bucket",
            bucket_name=bucket_name,
            block_public_access=_s3.BlockPublicAccess.BLOCK_ALL,
            auto_delete_objects=True,
            removal_policy=RemovalPolicy.DESTROY,
            encryption=_s3.BucketEncryption.S3_MANAGED,  # Only supported encryption option
            enforce_ssl=True,
        )

        self.bucket.add_to_resource_policy(
            iam.PolicyStatement(
                principals=[
                    iam.ServicePrincipal("delivery.logs.amazonaws.com"),
                    iam.ServicePrincipal("logging.s3.amazonaws.com"),
                    get_elb_server_access_logging_principal(region=scope.region),
                ],
                actions=["s3:PutObject"],
                effect=iam.Effect.ALLOW,
                resources=[f"arn:aws:s3:::{self.bucket.bucket_name}/*"],
            )
        )

        self.bucket.add_to_resource_policy(
            iam.PolicyStatement(
                principals=[
                    iam.ServicePrincipal("delivery.logs.amazonaws.com"),
                ],
                actions=["s3:GetBucketAcl"],
                effect=iam.Effect.ALLOW,
                resources=[f"arn:aws:s3:::{self.bucket.bucket_name}"],
            )
        )
