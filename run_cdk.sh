#!/bin/bash

# Activate the virtual environment
source venv/bin/activate

# Change directory to cdk_deployment
cd cdk_deployment

# Run CDK commands passed as arguments
cdk --app "python3 app.py" "$@"
