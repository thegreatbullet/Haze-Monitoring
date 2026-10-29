# Setup

Run once. 
Region: ap-southeast-1 (Singapore).

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

AWS CLI (official installer, the Homebrew version can break):
```bash
curl "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o "AWSCLIV2.pkg"
sudo installer -pkg AWSCLIV2.pkg -target /
rm AWSCLIV2.pkg
```

Everything else:
```bash
brew install gh python@3.12
nvm install --lts && nvm alias default 'lts/*'
npm install -g aws-cdk
```

Check:
```bash
aws --version && node --version && cdk --version && python3.12 --version
```

If you use conda, stop it from starting in every terminal:
```bash
conda config --set auto_activate_base false   # then open a new terminal
```

## 4. Connect the CLI to AWS

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

Test:
```bash
export AWS_PROFILE=haze
aws sts get-caller-identity   # shows your account ID
```

Login expires after a while. Run `aws sso login` to log in again.

## 5. Create the GitHub repo

```bash
mkdir -p ~/Projects && cd ~/Projects
unzip ~/Downloads/aws-haze-monitoring.zip
cd aws-haze-monitoring
git init -b main
git status                     
git add . && git commit -m "Design, simulator, tests and docs"
gh auth login
gh repo create aws-haze-monitoring --public --source=. --push
```

## 6. Create the CDK app

```bash
mkdir infra && cd infra
cdk init app --language python
source .venv/bin/activate
pip install -r requirements.txt
```

Replace `infra/app.py` with:
```python
#!/usr/bin/env python3
import os

import aws_cdk as cdk

from infra.infra_stack import InfraStack

app = cdk.App()

InfraStack(
    app,
    "HazeFoundation",
    env=cdk.Environment(account=os.getenv("CDK_DEFAULT_ACCOUNT"), region="ap-southeast-1"),
)

# Tag everything so cost can be tracked for this project.
cdk.Tags.of(app).add("Project", "haze-monitoring")

app.synth()
```

Deploy:
```bash
cdk synth                                       # prints a template, no errors
cdk bootstrap --tags Project=haze-monitoring    # only once per account and region
cdk deploy                                      # deploys the empty HazeFoundation stack
cd .. && git add infra && git commit -m "Add CDK app" && git push
```

## 7. Cost tag (next day)

- Activate the `Project` tag in Billing > Cost allocation tags
- It only shows up after a tagged resource exists (bootstrap creates one)