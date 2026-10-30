import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from infra.github_oidc_stack import GitHubOidcStack, repo_subject

REPO = "thegreatbullet/Haze-Monitoring"
OIDC = "token.actions.githubusercontent.com"


def _template(**ids) -> Template:
    app = cdk.App()
    stack = GitHubOidcStack(app, "TestOidc", github_repo=REPO, **ids)
    return Template.from_stack(stack)


def _trust_condition(sub: str) -> dict:
    return {
        "AssumeRolePolicyDocument": {
            "Statement": Match.array_with(
                [
                    Match.object_like(
                        {
                            "Condition": {
                                "StringEquals": {f"{OIDC}:aud": "sts.amazonaws.com"},
                                "StringLike": {f"{OIDC}:sub": sub},
                            }
                        }
                    )
                ]
            )
        },
        "MaxSessionDuration": 3600,
    }


def test_subject_uses_immutable_ids_when_given():
    assert repo_subject(REPO, "111", "222") == "repo:thegreatbullet@111/Haze-Monitoring@222"
    assert repo_subject(REPO, None, None) == "repo:thegreatbullet/Haze-Monitoring"


def test_oidc_provider_trusts_github():
    _template().has_resource_properties(
        "AWS::IAM::OIDCProvider",
        {"Url": "https://token.actions.githubusercontent.com", "ClientIdList": ["sts.amazonaws.com"]},
    )


def test_role_only_trusts_main_branch_of_this_repo_by_id():
    template = _template(github_owner_id="111", github_repo_id="222")
    sub = "repo:thegreatbullet@111/Haze-Monitoring@222:ref:refs/heads/main"
    template.has_resource_properties("AWS::IAM::Role", _trust_condition(sub))


def test_role_falls_back_to_name_only_subject():
    sub = f"repo:{REPO}:ref:refs/heads/main"
    _template().has_resource_properties("AWS::IAM::Role", _trust_condition(sub))


def test_role_can_only_assume_roles():
    _template().has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": [Match.object_like({"Action": "sts:AssumeRole", "Effect": "Allow"})],
            }
        },
    )
