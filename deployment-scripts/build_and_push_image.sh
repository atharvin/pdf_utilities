#!/bin/bash
set -e

echo "----------------------------------------"
echo "Building & Pushing Docker Image"
echo "Environment: $Environment"
echo "----------------------------------------"

#apt-get update && upgrade -y
# Required ENV Vars from Bitbucket:
# Environment
if [[ -z "$Environment" ]]; then
    echo "ERROR: Missing required environment variable: Environment"
    exit 1
fi

# Docker latest tag
latest_tag="latest"

# Set AWS credentials and region based on Environment
case "$Environment" in
    demo)
        export AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID"
        export AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY"
        export AWS_DEFAULT_REGION="$AWS_REGION"
        AWS_IMAGE_NAME="$AWS_IMAGE_NAME_DEMO"
        ;;
    dev)
        export AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID"
        export AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY"
        export AWS_DEFAULT_REGION="$AWS_REGION"
        AWS_IMAGE_NAME="$AWS_IMAGE_NAME_DEV"
        ;;
    uat)
        export AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID"
        export AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY"
        export AWS_DEFAULT_REGION="$AWS_REGION"
        AWS_IMAGE_NAME="$AWS_IMAGE_NAME_UAT"
        ;;
    prod)
        export AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID"
        export AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY"
        export AWS_DEFAULT_REGION="$AWS_REGION"
        AWS_IMAGE_NAME="$AWS_IMAGE_NAME_PROD"
        ;;
    *)
        echo "ERROR: Unknown environment: $Environment"
        exit 1
        ;;
esac

#cd app/

echo "Building Docker image: $AWS_IMAGE_NAME:$latest_tag"

# Authenticate Docker with AWS ECR
aws ecr get-login-password --region "$AWS_DEFAULT_REGION" | docker login --username AWS --password-stdin "$AWS_REPO_ADDRESS"

# Build Docker image
docker build -t "$AWS_IMAGE_NAME:$latest_tag" .

# Tag Docker image for ECR
docker tag "$AWS_IMAGE_NAME:$latest_tag" "$AWS_REPO_ADDRESS/$AWS_IMAGE_NAME:$latest_tag"

# Push Docker image to ECR
docker push "$AWS_REPO_ADDRESS/$AWS_IMAGE_NAME:$latest_tag"

echo "----------------------------------------"
echo "Docker Image pushed successfully!"
echo "Image: $AWS_REPO_ADDRESS/$AWS_IMAGE_NAME:latest"
echo "----------------------------------------"
