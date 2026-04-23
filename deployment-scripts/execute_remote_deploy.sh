#!/bin/bash
set -e

echo "------------------------------------------------"
echo "Starting EC2 Deployment via SSM"
echo "Environment: $Environment"
echo "------------------------------------------------"

#apt-get update && upgrade -y
# Required ENV Vars from Bitbucket:
# Environment and INSTANCE_ID per environment
if [[ -z "$Environment" ]]; then
    echo "ERROR: Missing required environment variable: Environment"
    exit 1
fi

# Map Environment to INSTANCE_ID if you store multiple in repo variables
case "$Environment" in
    demo)
        INSTANCE_ID="$INSTANCE_ID_DEMO"
        export AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID"
        export AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY"
        export AWS_DEFAULT_REGION="$AWS_REGION"
        ;;
    dev)
        INSTANCE_ID="$INSTANCE_ID_DEV"
        export AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID"
        export AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY"
        export AWS_DEFAULT_REGION="$AWS_REGION"
        ;;
    uat)
        INSTANCE_ID="$INSTANCE_ID_UAT"
        export AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID"
        export AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY"
        export AWS_DEFAULT_REGION="$AWS_REGION"
        ;;
    prod)
        INSTANCE_ID="$INSTANCE_ID_PROD"
        export AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID"
        export AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY"
        export AWS_DEFAULT_REGION="$AWS_REGION"
        ;;
    *)
        echo "ERROR: Unknown environment: $Environment"
        exit 1
        ;;
esac

if [[ -z "$INSTANCE_ID" ]]; then
    echo "ERROR: INSTANCE_ID for environment $Environment is not set."
    exit 1
fi

DEPLOY_SCRIPT="/apps/deploy_moodys_insurance_google_translation.sh"

# Get EC2 instance name from tags
INSTANCE_NAME=$(aws ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" \
    --query "Reservations[0].Instances[0].Tags[?Key=='Name'].Value | [0]" \
    --output text \
    --region "$AWS_DEFAULT_REGION")
# Check EC2 instance state
INSTANCE_STATE=$(aws ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" \
    --query "Reservations[0].Instances[0].State.Name" \
    --output text \
    --region "$AWS_DEFAULT_REGION")

if [[ -z "$INSTANCE_NAME" ]]; then
    INSTANCE_NAME="Unknown-Name"
fi

echo "Deploying to EC2 Instance:"
echo "Instance Name: $INSTANCE_NAME"
echo "Running script: $DEPLOY_SCRIPT"
echo "EC2 Instance State: $INSTANCE_STATE"

if [[ "$INSTANCE_STATE" != "running" ]]; then
    echo "❌Instance is NOT running. Please start the instance manually before deploying"
    exit 1
fi

echo "✅ Instance is running... continuing."

# Send SSM command
COMMAND_ID=$(aws ssm send-command \
    --instance-ids "$INSTANCE_ID" \
    --document-name "AWS-RunShellScript" \
    --comment "WB-FSS-ML Deployment" \
    --parameters commands="['sudo $DEPLOY_SCRIPT']" \
    --query "Command.CommandId" \
    --output text \
    --region "$AWS_DEFAULT_REGION")

echo "SSM Command ID: $COMMAND_ID"
echo "Checking execution status..."

STATUS="InProgress"
while [[ "$STATUS" == "InProgress" || "$STATUS" == "Pending" ]]; do
    sleep 10
    STATUS=$(aws ssm list-command-invocations \
        --command-id "$COMMAND_ID" \
        --instance-id "$INSTANCE_ID" \
        --details \
        --query 'CommandInvocations[0].Status' \
        --output text \
        --region "$AWS_DEFAULT_REGION")
    echo "Status: $STATUS"
done

if [[ "$STATUS" != "Success" ]]; then
    echo "❌ Deployment Failed: $STATUS"
    exit 1
fi

echo "------------------------------------------------"
echo "✅ Deployment Successful"
echo "------------------------------------------------"
