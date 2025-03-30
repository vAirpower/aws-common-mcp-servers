#!/bin/bash

# This script will push the remaining files, including TypeScript source code to GitHub

# Set the repository information
GITHUB_REPO="https://github.com/vAirpower/aws-common-mcp-servers.git"
BRANCH="main"

# Navigate to the root of the project directory
cd "$(dirname "$0")"

# Check if this is already a git repository
if [ ! -d ".git" ]; then
  echo "Initializing Git repository..."
  git init
fi

# Check if the remote already exists
if ! git remote | grep -q "origin"; then
  echo "Adding GitHub remote..."
  git remote add origin $GITHUB_REPO
else
  echo "GitHub remote already exists"
fi

# Pull the latest changes to avoid conflicts
echo "Pulling latest changes from GitHub..."
git pull origin $BRANCH --allow-unrelated-histories -X theirs

# Add all files
echo "Adding all files to Git..."
git add .

# Commit the changes
echo "Committing changes..."
git commit -m "Add all remaining files including TypeScript source code"

# Push to GitHub
echo "Pushing to GitHub..."
git push -u origin $BRANCH

echo "Completed! All files have been pushed to $GITHUB_REPO"
