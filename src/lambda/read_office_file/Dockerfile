# Copyright © Amazon.com and Affiliates

FROM --platform=linux/amd64 public.ecr.aws/lambda/python:3.12

# Install the specified packages
COPY requirements.txt ${LAMBDA_TASK_ROOT}
RUN dnf -y install libxslt-devel libxml2-devel python-lxml gcc && dnf clean all
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir tenacity==8.3.0

# Copy function code
COPY read_office.py utils.py ${LAMBDA_TASK_ROOT}

# Set the CMD to your handler (could also be done as a parameter override outside of the Dockerfile)
CMD ["read_office.lambda_handler"]
