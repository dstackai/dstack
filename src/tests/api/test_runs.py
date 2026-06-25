from dstack.api._public.runs import RunCollection


class _RunsAPI:
    def __init__(self):
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return []
        return ["finished-run"]


class _APIClient:
    def __init__(self):
        self.runs = _RunsAPI()


class TestRunCollectionList:
    def test_default_list_fallback_limits_job_submissions(self):
        api_client = _APIClient()
        runs = RunCollection(api_client=api_client, project="main", client=None)
        runs._model_to_run = lambda run: run

        assert runs.list() == ["finished-run"]

        assert api_client.runs.calls[0]["job_submissions_limit"] == 1
        assert api_client.runs.calls[1]["job_submissions_limit"] == 1
