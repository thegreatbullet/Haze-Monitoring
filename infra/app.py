#!/usr/bin/env python3
import os

import aws_cdk as cdk
from cdk_nag import AwsSolutionsChecks

from infra.github_oidc_stack import GitHubOidcStack
from infra.infra_stack import InfraStack

app = cdk.App()

# Settings come from cdk.json "context", so nothing is hard-coded here.
region = app.node.try_get_context("region") or "ap-southeast-1"
project_tag = app.node.try_get_context("project_tag") or "haze-monitoring"
github_repo = app.node.try_get_context("github_repo")
github_owner_id = app.node.try_get_context("github_owner_id")
github_repo_id = app.node.try_get_context("github_repo_id")

env = cdk.Environment(account=os.getenv("CDK_DEFAULT_ACCOUNT"), region=region)

InfraStack(app, "HazeFoundation", env=env)

if github_repo:
    GitHubOidcStack(
        app,
        "HazeGitHubOidc",
        env=env,
        github_repo=github_repo,
        github_owner_id=github_owner_id,
        github_repo_id=github_repo_id,
    )

# Tag everything so cost can be tracked for this project.
cdk.Tags.of(app).add("Project", project_tag)

# Security checks on every synth. Findings must be fixed or suppressed with a reason.
cdk.Aspects.of(app).add(AwsSolutionsChecks(verbose=True))

app.synth()
