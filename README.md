# Intelligent Document Processing with Generative AI

🚀 Extract information from unstructured documents at scale with Amazon Bedrock

![media/diagram.png](media/diagram.png)

Converting documents into a structured database is a recurring business task. Common use cases include creating a product feature table from article descriptions, extracting meta-data from legal contracts, analyzing customer reviews, and more.

This repo provides an AWS CDK solution for intelligent document processing in seconds using generative AI.

**Key features:**
- Extract different information, including:
  - Well-defined entities (name, title, etc)
  - Numeric scores (sentiment, urgency, etc)
  - Free-form content (summary, suggested response, etc)
- Simply describe the attributes to be extracted without costly data annotation or model training
- Leverage Amazon Bedrock Data Automation and multi-modal LLMs on Amazon Bedrock
- Use [Python API](demo/idp_bedrock_demo.ipynb) or [demo frontend](src/ecs/src/Home.py) to process PDFs, MS Office, images, and other formats


## Contents

- [Demo](#demo)
- [Architecture](#architecture)
- [Deployment](#deployment)
- [Usage](#usage)
- [Team](#team)
- [Security](#security)
- [License](#license)


# 📹 Demo

**Example API Call**

Refer to [the demo notebook](api/idp_bedrock_demo.ipynb) for the API implementation and usage examples:

```python
docs = ['doc1', 'doc2']

features = [
    {"name": "delay", "description": "delay of the shipment in days"},
    {"name": "shipment_id", "description": "unique shipment identifier"},
    {"name": "summary", "description": "one-sentence summary of the doc"},
]

run_idp_bedrock_api(
    documents=docs,
    features=features,
)
# [{'delay': 2, 'shipment_id': '123890', 'summary': 'summary1'},
# {'delay': 3, 'shipment_id': '678623', 'summary': 'summary2'}]
```

**Web UI Video**

https://github.com/user-attachments/assets/cac8a6e1-2e70-4ca0-a9e7-d959619941f4

# 🏗️ Architecture

This diagram depicts a high-level architecture of the solution:

![media/architecture.png](media/architecture.png)


# 🔧 Deployment

To deploy the app to your AWS account, you can use a local IDE or create a SageMaker Notebook instance.

We recommend using SageMaker to avoid installing extra requirements. Set up `ml.t3.large` instance and make sure the IAM role attached to the notebook has sufficient permissions for deploying CloudFormation stacks.

### 1. Clone the Repo

Clone the repo to a location of your choice:

```bash
git clone https://github.com/aws-samples/intelligent-document-processing-with-amazon-bedrock.git
```


### 2. Install Prerequisites

When working from a SageMaker Notebook instance, run this script to install all missing requirements:

```bash
cd intelligent-document-processing-with-amazon-bedrock
sh install_deps.sh
```

When working locally, make sure you have installed the following, as well as access to the target AWS account:

- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- [AWS Account](https://docs.aws.amazon.com/cli/v1/userguide/cli-chap-configure.html): configure an AWS account with a profile `$ aws configure --profile [profile-name]`
- [Node.js](https://nodejs.org/en/download/package-manager)
- [AWS CDK Toolkit](https://docs.aws.amazon.com/cdk/v2/guide/cli.html)
- [Python 3.9+](https://www.python.org/downloads/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) - Fast Python package installer and resolver
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)


### 3. Activate the Environment

Navigate to the repo folder and execute the following script to create a virtual environment on macOS or Linux:

```bash
sh install_env.sh
source .venv/bin/activate
```

### 4. Configure the Stack

Copy the `config-example.yml` to a `config.yml` file and specify your project name and modules you would like to deploy (e.g., whether to deploy a UI). Make sure you add your user email to the Amazon Cognito users list.

```yaml
stack_name: idp-test  # Used as stack name and prefix for resources (<16 chars, cannot start with "aws")

...

frontend:
  deploy_ecs: True  # Whether to deploy demo frontend on ECS
```


### 5. Configure Bedrock Model Access

- Open the target AWS account
- Open AWS Bedrock console and navigate to the region specified in `config.yml`
- Select "Model Access" in the left sidebar and browse through the list of available LLMs
- Make sure to request and enable access for the model IDs specified in `config.yml`


### 6. CDK Bootstrap

Bootstrap CDK in your account. When working locally, use the profile name you have used in the `aws configure` step. When working from a SageMaker Notebook instance, profile specification is not required.

```bash
cdk bootstrap --profile [PROFILE_NAME]
```

### 7. CDK Deploy

Make sure the Docker daemon is running. On Mac, you can open Docker Desktop. On SageMaker, Docker daemon is already running.

```bash
cdk deploy --profile [PROFILE_NAME]
```

### Clean up

You can delete the CDK stack from your AWS account by running:

```bash
cdk destroy --profile [AWS_PROFILE_NAME]
```

or manually delete the CloudFormation stack from the AWS console.


### Common Issues

#### Permissions to run CDK deploy

Deploying CDK / CloudFormation stacks requires near Admin Permissions. Make sure to have the necessary IAM account permissions before running CDK deploy. Here is a detailed list of [minimal required permissions](https://stackoverflow.com/a/61102280) to deploy a stack.

#### Empty S3 before deleting the stack

When deleting the stack, it may delete everything except for the created S3 bucket, which will contain the uploaded documents by the user and their processed versions. In order to actually delete this s3 bucket, you may need to empty it first. This is an expected behavior as all s3 buckets may contain sensitive data to the users.

#### `/bin/sh: python3: command not found`

This happens die to a wrong Python path. Change `python3` in `cdk.json` to your Python alias.


# 💻 Usage

## Option 1: Run API from Python

Follow steps in this [notebook](demo/idp_bedrock_demo.ipynb) to run a job via an API call. You will need to:
- provide input document(s)
- provide a list of features to be extracted

## Option 2: Run a web app

### Access the Frontend

- The URL to access the frontend appears as output at the end of the CDK deployment under "CloudfrontDistributionName"

or

- Open the AWS console, and go to CloudFront
- Copy the Domain name of the created distribution

Login credentials are available from:
- User name: email from a list of Cognito user emails in `config.yml` in `authentication` section
- Password: temporary password received by email from `no-reply@verificationemail.com` after deployment

#### Local Testing

You can run the demo frontend locally for testing and development by following these steps:

- Deploy the CDK stack once
- Go to ```src/ecs/.env``` and set ```STACK_NAME``` to your stack name in the `config.yml`
- Provide AWS credentials
  - You can add AWS credentials to the ```src/ecs/.env``` file
  - Or simply export credentials in your terminal, e.g. ```export AWS_PROFILE=<profile>```
- Navigate to the frontend folder, create environment and install dependencies:
```bash
cd src/ecs
uv venv
source .venv/bin/activate
uv sync --extra dev
```
- Start frontend on localhost: ```streamlit run src/Home.py```
- Copy the local URL from the terminal output and paste in the address bar of your browser
- Make sure that the local URL you use is http://localhost:8501. It will not work otherwise


# 👥 Team

**Core team:**

| ![image](media/team/nikita.jpeg) | ![image](media/team/nuno.jpeg) |
|---|---|
| [Nikita Kozodoi](https://www.linkedin.com/in/kozodoi/) | [Nuno Castro](https://www.linkedin.com/in/nunoconstantinocastro/) |

**Contributors:**

| ![image](media/team/romain.jpeg) | ![image](media/team/zainab.jpeg) | ![image](media/team/egor.jpeg) | ![image](media/team/huong.jpeg) | ![image](media/team/aiham.jpeg) | ![image](media/team/elizaveta.jpeg) | ![image](media/team/babs.jpeg) | ![image](media/team/ennio.jpeg) |
|---|---|---|---|---|---|---|---|
| [Romain Besombes](https://www.linkedin.com/in/romainbesombes/) | [Zainab Afolabi](https://www.linkedin.com/in/zainabafolabi/) | [Egor Krasheninnikov](https://www.linkedin.com/in/egorkrash/) | [Huong Vu](https://www.linkedin.com/in/huong-vu/) | [Aiham Taleb](https://www.linkedin.com/in/aihamtaleb/) | [Elizaveta Zinovyeva](https://www.linkedin.com/in/zinov-liza/) | [Babs Khalidson](https://www.linkedin.com/in/babskhalidson/) | [Ennio Pastore](https://www.linkedin.com/in/enniopastore/) |

**Acknowledgements:**

- [Tan Takher](https://www.linkedin.com/in/tanrajbir/)
- [Ivan Sosnovik](https://www.linkedin.com/in/ivan-sosnovik/)


## 🔒️ Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

Note: this asset represents a proof-of-value for the services included and is not intended as a production-ready solution. You must determine how the AWS Shared Responsibility applies to their specific use case and implement the needed controls to achieve their desired security outcomes. AWS offers a broad set of security tools and configurations to enable out customers.

- **Input data:**
  - Note that the solution is not scoped for processing regulated data.
- **Network & Delivery:**
  - CloudFront:
    - Use geography-aware rules to block or allow access to CloudFront distributions where required.
    - Use AWS WAF on public CloudFront distributions.
    - Ensure that solution CloudFront distributions use a security policy with minimum TLSv1.1 or TLSv1.2 and appropriate security ciphers for HTTPS viewer connections. Currently, the CloudFront distribution allows for SSLv3 or TLSv1 for HTTPS viewer connections and uses SSLv3 or TLSv1 for communication to the origin.
  - API Gateway:
    - Activate request validation on API Gateway endpoints to do first-pass input validation.
    - Use AWS WAF on public-facing API Gateway Endpoints.
- **Machine Learning and AI:**
  - Bedrock
    - Enable model invocation logging and set alerts to ensure adherence to any responsible AI policies. Model invocation logging is disabled by default. See https://docs.aws.amazon.com/bedrock/latest/userguide/model-invocation-logging.html
    - Consider enabling Bedrock Guardrails to add baseline protections against analyzing documents or extracting attributes covering certain protected topics.
  - Comprehend
    - Consider using Amazon COmprehend for detecting and masking PII data in the user-uploaded inputs.
- **Security & Compliance**:
  - Cognito
    - Implement multi-factor authentication (MFA) in each Cognito User Pool.
    - Consider implementing AdvanceSecurityMode to ENFORCE in Cognito User Pools.
  - KMS
    - Implement KMS key rotation for regulatory compliance or other specific cases.
    - Configure, monitor, and alert on KMS events according to lifecycle policies.
- **Serverless**:
  - Lambda
    - Periodically scan all AWS Lambda container images for vulnerabilities according to lifecycle policies. AWS Inspector can be used for that.

In order to keep coding standards and formatting consistent, we use `pre-commit`. This can be run from the terminal via `uv run pre-commit run -a`.


## 📝 License

This library is licensed under the MIT-0 License. See the LICENSE file.
