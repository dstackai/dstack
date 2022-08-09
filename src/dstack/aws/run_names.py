import yaml
from botocore.client import BaseClient


def next_run_name_index(client: BaseClient, bucket_name: str, run_name: str) -> int:
    count = 0
    key = f"run-names/{run_name}.yaml"
    try:
        obj = client.get_object(Bucket=bucket_name, Key=key)
        count = yaml.load(obj['Body'].read().decode('utf-8'), Loader=yaml.FullLoader)["count"]
        client.put_object(Body=yaml.dump({"count": count + 1}), Bucket=bucket_name, Key=key)
    except Exception as e:
        if hasattr(e, "response") and e.response.get("Error") and e.response["Error"].get("Code") == "NoSuchKey":
            client.put_object(Body=yaml.dump({"count": count + 1}), Bucket=bucket_name, Key=key)
        else:
            raise e
    return count + 1
