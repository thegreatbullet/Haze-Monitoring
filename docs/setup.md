# Setup

Run once. 
Region: ap-southeast-1 (Singapore).

## Every session

To run

```bash
aws sso login --profile haze
export AWS_PROFILE=haze
conda activate haze
```

## 1. Secure the AWS account

Root user:
- Turn MFA on
- Never create root access keys
- Create IAM user instead

Daily user (IAM Identity Center):
- One user with MFA
- AdministratorAccess permission set, assigned to the account
- Copy the AWS access portal URL for the CLI

***Never use root after this.***

## 2. Cost alerts

- AWS Budgets: $15 a month, alerts at $10, $15 and $15 forecasted
- Cost Anomaly Detection: email alert, $5 threshold
- Cost Explorer turned on

## 3. Install tools (macOS, Apple Silicon)

For Apple Mac.

Start with the AWS CLI. 
I tried Homebrew first, but on my macOS version it kept crashing because of a missing library called `libexpat`. 
The official installer ships with its own Python, so just use that one:
```bash
curl "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o "AWSCLIV2.pkg"
sudo installer -pkg AWSCLIV2.pkg -target /
rm AWSCLIV2.pkg
```

Next, the GitHub CLI, Node.js and AWS CDK. 
For Python I went with conda, since Homebrew's Python ran into the same `libexpat` problem:
```bash
conda create -n haze python=3.12 -y
conda activate haze
which python3
```

Make sure everything installed properly:
```bash
aws --version && node --version && cdk --version && conda --version
```

## 4. Connect the CLI to AWS
Used IAM Identity Center. 

```bash
aws configure sso
#   SSO session name: haze
#   SSO start URL: <your AWS access portal URL>
#   SSO region: ap-southeast-1
#   SSO registration scopes: (press Enter)
#   -> browser opens: approve, then pick your account and AdministratorAccess
#   Default client Region: ap-southeast-1
#   Default output format: json
#   Profile name: haze
```

Sign in using:
```bash
export AWS_PROFILE=haze
aws sts get-caller-identity          # Account ID
aws sso login --profile haze          # Login
```

## 5. Conda Python environment

Use conda's own environment
```bash
conda activate haze
cd infra
pip install -r requirements.txt
cdk synth                                       
cdk bootstrap --tags Project=haze-monitoring    
cdk deploy                                     
```

## 7. Cost tag (next day)

Everything in this project is tagged `Project=haze-monitoring`, which lets me see exactly what it costs.

- Activate the `Project` tag under Billing > Cost allocation tags
- It only appears once something with the tag exists, and bootstrap takes care of that

