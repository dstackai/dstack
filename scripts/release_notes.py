# /// script
# dependencies = [
#   "requests",
#   "litellm",
#   "boto3", # for AWS Bedrock
# ]
# ///

import argparse
import os
import re
from pathlib import Path

import requests
from litellm import completion

REPO = "dstackai/dstack"
BRANCH = "master"

# GITHUB_TOKEN to avoid rate limiting
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]

# Model can be any supported by LiteLLM: https://docs.litellm.ai/docs/providers
# Prover-specific credentials are picked up from env
# e.g. AWS_REGION=us-east-1 AWS_PROFILE=... for AWS Bedrock
MODEL = os.getenv("LLM_MODEL", "bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0")


def get_draft_release_by_tag(tag: str) -> dict:
    r = requests.get(
        f"https://api.github.com/repos/{REPO}/releases",
        headers={"Authorization": f"token {GITHUB_TOKEN}"},
        timeout=10,
    )
    for release in r.json():
        if release["tag_name"] == tag and release["draft"]:
            return release
    # May error if the draft not on the first page - we assume draft was created recently
    raise ValueError(f"Release for tag {tag} not found")


def get_prs_from_draft(draft_body: str) -> list[dict]:
    prs = []
    pr_numbers = extract_pr_numbers_from_draft(draft_body)
    for pr_number in pr_numbers:
        r = requests.get(
            f"https://api.github.com/repos/{REPO}/pulls/{pr_number}",
            headers={"Authorization": f"token {GITHUB_TOKEN}"},
            timeout=10,
        )
        prs.append(r.json())
    return prs


def extract_pr_numbers_from_draft(notes: str) -> list[int]:
    return [int(num) for num in re.findall(r"/pull/(\d+)", notes)]


def generate_release_notes(
    draft_body: str,
    prs: list[dict],
    examples: str,
) -> str:
    pr_summaries = "\n\n".join(f"PR #{pr['number']}: {pr['title']}\n{pr['body']}" for pr in prs)
    prompt = f"""
You are a release notes generator.

Here are the draft GitHub release notes:
{draft_body}

Here are the PR details (titles + descriptions):
{pr_summaries}

Task:
* Keep the 'What's Changed' and 'Contributors' sections as they are.
* Add expanded sections in the beginning for major features and changes. Do not mention minor fixes.
* Use clear, user-friendly prose. Avoid emojis.
* Use the PR descriptions to enrich the expanded sections.
* Include examples of how to use the new features when they are available in the PR descriptions.
* Do not group sections based on functionality (like "New features"). Instead, group by domain (e.g. "Runs", "Backends", "Examples") or do not group at all.
* Include "Deprecations" and "Breaking changes" sections if there are any.

Examples of good release notes:
{examples}

"""
    response = completion(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return response["choices"][0]["message"]["content"]


if __name__ == "__main__":
    # TODO: When the script is sufficiently polished, we may automate draft release generation and its update,
    # and integrate the script into the CI.
    parser = argparse.ArgumentParser(
        description=(
            "Generate expanded `dstack` release notes from a release draft using LLM."
            " The script accepts a release tag for which you must generate automatic release notes beforehand."
            " The script does not publish or change anything on GitHub and only outputs the generated release notes."
        )
    )
    parser.add_argument("tag", help="Release tag (e.g., 0.19.25)")
    args = parser.parse_args()

    with open(Path(__file__).parent / "release_notes_examples.md") as f:
        examples = f.read()
    draft_release = get_draft_release_by_tag(args.tag)
    draft_body = draft_release["body"]
    prs = get_prs_from_draft(draft_body)
    notes = generate_release_notes(draft_body, prs, examples)
    print(notes)
