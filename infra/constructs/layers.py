"""
Copyright © Amazon.com and Affiliates
"""

from aws_cdk import Aws, BundlingOptions, BundlingOutput, DockerImage, RemovalPolicy
from aws_cdk import aws_lambda as _lambda
from aws_cdk.aws_s3_assets import Asset
from constructs import Construct

AWS_LAMBDA_POWERTOOL_LAYER_VERSION_ARN = "arn:aws:lambda:{region}:017000801446:layer:AWSLambdaPowertoolsPythonV2:45"


class IDPBedrockLambdaLayers(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        stack_name,
        architecture: _lambda.Architecture,
        python_runtime: _lambda.Runtime,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Custom Modules
        self._runtime = python_runtime
        self._architecture = architecture

        self.idp_bedrock = _lambda.LayerVersion(
            self,
            f"{stack_name}-idp-bedrock-layer",
            compatible_runtimes=[self._runtime],
            compatible_architectures=[self._architecture],
            code=_lambda.Code.from_asset("./src/layers/idp_bedrock"),
            description="IDP Bedrock layer for with different retrieval and model options",
            layer_version_name=f"{stack_name}-idp-bedrock-layer",
        )

        # Libraries
        self.idp_bedrock_deps = self._create_layer_from_asset(
            layer_name=f"{stack_name}-idp-bedrock-third-party-deps-layer",
            path_to_layer_assets="./src/layers/idp_bedrock/python",
            description="Lambda layer including upgraded boto3 (e.g. for Bedrock), Langchain, OpenSearchPy, etc.",
        )

        self.textractor = self._create_layer_from_asset(
            layer_name=f"{stack_name}-textractor",
            path_to_layer_assets="./src/layers/textractor/",
            description="Lambda layer that contains dependencies for textract",
        )

        self.epd = self._create_layer_from_asset(
            layer_name=f"{stack_name}-epd",
            path_to_layer_assets="./src/layers/extra_deps/",
            description="Lambda layer that contains pandas for textractor",
        )

        # AWS Lambda PowerTools
        self.aws_lambda_powertools = _lambda.LayerVersion.from_layer_version_arn(
            self,
            f"{stack_name}-lambda-powertools-layer",
            layer_version_arn=AWS_LAMBDA_POWERTOOL_LAYER_VERSION_ARN.format(region=Aws.REGION),
        )

    def _create_layer_from_asset(
        self, layer_name: str, path_to_layer_assets: str, description: str
    ) -> _lambda.LayerVersion:
        """Create a layer from an S3 asset

        This is a valid option if the layer only requires to install Python packages on top of base Lambda Python images

        Parameters
        ----------
        layer_name : str
            Name of the layer
        path_to_layer_assets : str
            the disk location of the asset that contains a `requirements.txt` file and, `*.whl` files if needed
        description : str
            describe what the purpose of the layer

        Returns
        -------
        _lambda.LayerVersion
            Lambda layer
        """
        ecr = self._runtime.bundling_image.image + f":latest-{self._architecture.to_string()}"
        bundling_option = BundlingOptions(
            image=DockerImage(ecr),
            command=[
                "bash",
                "-c",
                "pip --no-cache-dir install -r requirements.txt -t /asset-output/python",
            ],
            output_type=BundlingOutput.AUTO_DISCOVER,
            platform=self._architecture.docker_platform,
            network="host",
        )
        layer_asset = Asset(self, f"{layer_name}-BundledAsset", path=path_to_layer_assets, bundling=bundling_option)

        return _lambda.LayerVersion(
            self,
            layer_name,
            code=_lambda.Code.from_bucket(layer_asset.bucket, layer_asset.s3_object_key),
            compatible_runtimes=[self._runtime],
            compatible_architectures=[self._architecture],
            removal_policy=RemovalPolicy.DESTROY,
            layer_version_name=layer_name,
            description=description,
        )
