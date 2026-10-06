# Lambda container image for VisionGuard.
# Build from the repo root:
#   docker build -f infra/docker/Dockerfile -t visionguard:latest .
# Push to ECR, then pass the image URI as var.lambda_image_uri.
FROM public.ecr.aws/lambda/python:3.11

COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY visionguard/ ${LAMBDA_TASK_ROOT}/visionguard/

# CMD is overridden per function in Terraform:
#   inspect -> visionguard.aws.lambda_handler.handler
#   api     -> visionguard.aws.api_handler.handler
CMD ["visionguard.aws.lambda_handler.handler"]
