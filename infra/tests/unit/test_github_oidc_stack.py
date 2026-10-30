import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from infra.github_oidc_stack import GitHubOidcStack

REPO = "thegreatbullet/Haze-Monitoring"
OIDC = "token.actions.githubusercontent.com"


def _template() -> Template:
    app = cdk.App()
    stack = GitHubOidcStack(app, "TestOidc", github_repo=REPO)
    return Template.from_stack(stack)


def test_oidc_provider_trusts_github():
    _template().has_resource_properties(
        "AWS::IAM::OIDCProvider",
        {"Url": "https://token.actions.githubusercontent.com", "ClientIdList": ["sts.amazonaws.com"]},
    )


def test_role_only_trusts_main_branch_of_this_repo():
    _template().has_resource_properties(
        "AWS::IAM::Role",
        {
            "AssumeRolePolicyDocument": {
                "Statement": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Condition": {
                                    "StringEquals": {f"{OIDC}:aud": "sts.amazonaws.com"},
                                    "StringLike": {f"{OIDC}:sub": f"repo:{REPO}:ref:refs/heads/main"},
                                }
                            }
                        )
                    ]
                )
            },
            "MaxSessionDuration": 3600,
        },
    )


def test_role_can_only_assume_roles():
    _template().has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": [Match.object_like({"Action": "sts:AssumeRole", "Effect": "Allow"})],
            }
        },
    )
