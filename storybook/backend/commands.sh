# Build Local
#docker build -t storybook-api .
docker buildx build --platform linux/amd64 -t storybook-api .

# Run Docker Image Locally
#docker run -p 8080:8080 storybook-api
docker run --platform linux/amd64 -p 8080:8080 storybook-api

# Build Docker Image

# Register Docket with AWS Account
aws ecr get-login-password --region 'us-east-1' | docker login --username AWS --password-stdin 704202188703.dkr.ecr.us-east-1.amazonaws.com

# Tag Docker Image with ECR
docker tag storybook-api:latest 704202188703.dkr.ecr.us-east-1.amazonaws.com/storybook-api:latest

# Push ECR
docker push 704202188703.dkr.ecr.us-east-1.amazonaws.com/storybook-api:latest

# Build-Tag-Push
docker buildx build --platform linux/amd64 -t storybook-api . && \
docker tag storybook-api:latest 704202188703.dkr.ecr.us-east-1.amazonaws.com/storybook-api:latest && \
docker push 704202188703.dkr.ecr.us-east-1.amazonaws.com/storybook-api:latest
