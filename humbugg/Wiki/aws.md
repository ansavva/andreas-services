# Amazon Web Services (AWS)

## Common Commands

- Installing AWS CLI using Python PIP (Python 2.x)
    - `pip install awscli --upgrade --user`

- Installing AWS CLI using Python PIP (Python 3.x)
    - `pip3 install awscli --upgrade --user`

- Installing AWS CLI Using APT Package Manager
    - `sudo apt install awscli`

- configure aws (look in password1 for keys)
    - `aws configure`

- login to aws (linux)
    - `sudo $(aws ecr get-login --no-include-email --region us-east-1) | eval`

- login to aws (powershell)
    - `$(aws ecr get-login --no-include-email --region us-east-1) | Invoke-Expression`

## ECR

- Gets a list of available repositories from ECR
    - `aws ecr describe-repositories`

## Cloud Formation Commands

- Create Prod
    - `aws cloudformation create-stack --stack-name humbugg-prod --template-body file://humbugg-prod.yml --capabilities CAPABILITY_IAM`
    - `aws cloudformation create-stack --stack-name humbugg-stage --template-body file://humbugg-stage.yml --capabilities CAPABILITY_IAM`

- Delete Prod
    - `aws cloudformation delete-stack --stack-name humbugg-prod`
    - `aws cloudformation delete-stack --stack-name humbugg-stage`

- Update Prod
    - `aws cloudformation update-stack --stack-name humbugg-prod --template-body file://humbugg-prod.yml --capabilities CAPABILITY_IAM`
    - `aws cloudformation update-stack --stack-name humbugg-stage --template-body file://humbugg-stage.yml --capabilities CAPABILITY_IAM`

## Helperful Links

- Docker on Amazon ECS Fargate using CloudFormation - Episode #9
    - https://www.youtube.com/watch?time_continue=11&v=Gr2yTSsVSqg
