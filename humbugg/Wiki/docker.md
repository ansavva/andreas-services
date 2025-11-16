
# Docker

## Common Commands
- List all docker containers
    - `docker ps -a -q`

- Stop all docker containers
     - `docker stop $(docker ps -a -q)`

- Force remove all docker containers
    - `docker rm -f $(docker ps -a -q)`

- Force remove all images
    - `docker rmi -f $(docker images -a -q)`

- Docker create new image with a tag
    -  `docker build -t 704202188703.dkr.ecr.us-east-1.amazonaws.com/savva-solutions/wedding-web:$(git log -1 --pretty=%H) .`

- Run docker container in detached mode (in the background) that is removed when stopped
    - `docker run -d -p 3001:3001 -e NODE_ENV=staging -e ASPNETCORE_ENVIRONMENT=Staging --name humbuggweb1 --rm 704202188703.dkr.ecr.us-east-1.amazonaws.com/savva-solutions/wedding-web:$(git log -1 --pretty=%H)`

    - `docker run -p 3001:3001 -e NODE_ENV=staging -e ASPNETCORE_ENVIRONMENT=Staging --name humbuggweb1 --rm 704202188703.dkr.ecr.us-east-1.amazonaws.com/savva-solutions/wedding-web:$(git log -1 --pretty=%H)`

- Docker update latest tag with most recent image
    - `docker tag 704202188703.dkr.ecr.us-east-1.amazonaws.com/savva-solutions/wedding-web:$(git log -1 --pretty=%H) 704202188703.dkr.ecr.us-east-1.amazonaws.com/savva-solutions/wedding-web:latest`

- Push Docker push the Image tagged as latest to AWS
    - `docker push 704202188703.dkr.ecr.us-east-1.amazonaws.com/savva-solutions/wedding-web:$(git log -1 --pretty=%H)`
    
    - `docker push 704202188703.dkr.ecr.us-east-1.amazonaws.com/savva-solutions/wedding-web:latest`

- Push all images to AWS
    - `docker push 704202188703.dkr.ecr.us-east-1.amazonaws.com/savva-solutions/wedding-web`