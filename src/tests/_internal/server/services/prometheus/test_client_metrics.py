from unittest.mock import MagicMock

from dstack._internal.server.services.prometheus.client_metrics import run_metrics


class TestRunMetrics:
    def test_log_submit_to_provision_duration(self, monkeypatch):
        mock_histogram = MagicMock()
        mock_labels = MagicMock()
        mock_histogram.labels.return_value = mock_labels
        monkeypatch.setattr(run_metrics, "_submit_to_provision_duration", mock_histogram)

        duration = 120.5
        project_name = "test-project"
        run_type = "dev"

        run_metrics.log_submit_to_provision_duration(duration, project_name, run_type)

        mock_histogram.labels.assert_called_once_with(project_name=project_name, run_type=run_type)
        mock_labels.observe.assert_called_once_with(duration)

    def test_increment_pending_runs(self, monkeypatch):
        mock_counter = MagicMock()
        mock_labels = MagicMock()
        mock_counter.labels.return_value = mock_labels

        monkeypatch.setattr(run_metrics, "_pending_runs_total", mock_counter)

        project_name = "test-project"
        run_type = "train"

        run_metrics.increment_pending_runs(project_name, run_type)
        mock_counter.labels.assert_called_once_with(project_name=project_name, run_type=run_type)
        mock_labels.inc.assert_called_once()

    def test_multiple_calls_to_log_submit_to_provision_duration(self):
        run_metrics.log_submit_to_provision_duration(60.0, "project1", "dev")
        run_metrics.log_submit_to_provision_duration(120.0, "project1", "prod")
        run_metrics.log_submit_to_provision_duration(30.0, "project2", "dev")

    def test_multiple_calls_to_increment_pending_runs(self):
        run_metrics.increment_pending_runs("project1", "dev")
        run_metrics.increment_pending_runs("project1", "prod")
        run_metrics.increment_pending_runs("project2", "dev")
        run_metrics.increment_pending_runs("project1", "dev")
