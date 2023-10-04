def get_service_account_name(project_name: str) -> str:
    return f"dstack-{project_name}"


def get_service_account_email(project_id: str, name: str) -> str:
    return f"{name}@{project_id}.iam.gserviceaccount.com"
