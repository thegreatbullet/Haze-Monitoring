from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_iam as iam
from cdk_nag import NagSuppressions
from constructs import Construct

GITHUB_OIDC_URL = "https://token.actions.githubusercontent.com"
GITHUB_OIDC_HOST = "token.actions.githubusercontent.com"


class GitHubOidcStack(Stack):
    """Lets GitHub Actions deploy this project with short-lived credentials.

    No access keys are stored in GitHub. The workflow exchanges its OIDC token
    for this role, and the role can only assume the CDK bootstrap roles.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        github_repo: str,
        branch: str = "main",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        provider = iam.CfnOIDCProvider(
            self,
            "GitHubProvider",
            url=GITHUB_OIDC_URL,
            client_id_list=["sts.amazonaws.com"],
            thumbprint_list=[
                "6938fd4d98bab03faadb97b34396831e3780aea1",
                "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
            ],
        )

        role = iam.Role(
            self,
            "GitHubDeployRole",
            role_name="haze-github-deploy",
            description=f"Assumed by GitHub Actions in {github_repo} ({branch} branch) to run cdk deploy",
            max_session_duration=Duration.hours(1),
            assumed_by=iam.WebIdentityPrincipal(
                provider.attr_arn,
                conditions={
                    "StringEquals": {f"{GITHUB_OIDC_HOST}:aud": "sts.amazonaws.com"},
                    "StringLike": {
                        f"{GITHUB_OIDC_HOST}:sub": f"repo:{github_repo}:ref:refs/heads/{branch}",
                    },
                },
            ),
        )

        # Least privilege: only allowed to hand over to the roles `cdk bootstrap` created.
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["sts:AssumeRole"],
                resources=[
                    f"arn:aws:iam::{self.account}:role/cdk-hnb659fds-*-role-{self.account}-{self.region}",
                ],
            )
        )

        NagSuppressions.add_resource_suppressions(
            role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Wildcard only matches the CDK bootstrap roles in this account and region.",
                }
            ],
            apply_to_children=True,
        )

        CfnOutput(self, "DeployRoleArn", value=role.role_arn)
