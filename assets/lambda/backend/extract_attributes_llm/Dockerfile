# Copyright © Amazon.com and Affiliates
# ----------------------------------------------------------------------
# File content:
#       Docker image of the Lambda container

FROM --platform=linux/amd64 public.ecr.aws/lambda/python:3.13

# Install the specified packages
COPY requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install --no-cache-dir -r requirements.txt
RUN dnf install -y poppler-utils && dnf clean all

# Copy function code
COPY . ${LAMBDA_TASK_ROOT}

# Set the CMD to your handler (could also be done as a parameter override outside of the Dockerfile)
CMD ["extract_attributes_llm.lambda_handler"]
