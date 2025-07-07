from dstack._internal.core.models.configurations import (
    DevEnvironmentConfiguration,
    ServiceConfiguration,
    TaskConfiguration,
)
from dstack._internal.core.models.runs import RunSpec
from dstack._internal.server.services.runs import run_configuration_to_yaml


class TestRunConfigurationYaml:
    def test_task_configuration_to_yaml(self):
        """Test converting task configuration to YAML"""
        config = TaskConfiguration(
            name="test-task",
            commands=["echo 'Hello World'"],
            resources={"cpu": 1, "memory": "1GB"},
            image="python:3.9",
        )

        run_spec = RunSpec(
            run_name="test-run", configuration=config, ssh_key_pub="ssh-rsa test-key"
        )

        yaml_content = run_configuration_to_yaml(run_spec)

        assert "name: test-run" in yaml_content
        assert "type: task" in yaml_content
        assert "commands:" in yaml_content
        assert "echo 'Hello World'" in yaml_content
        assert "image: python:3.9" in yaml_content

    def test_service_configuration_to_yaml(self):
        """Test converting service configuration to YAML"""
        config = ServiceConfiguration(
            name="test-service",
            commands=["python app.py"],
            port=8080,
            resources={"cpu": 2, "memory": "2GB"},
            image="python:3.9",
        )

        run_spec = RunSpec(
            run_name="test-service-run", configuration=config, ssh_key_pub="ssh-rsa test-key"
        )

        yaml_content = run_configuration_to_yaml(run_spec)

        assert "name: test-service-run" in yaml_content
        assert "type: service" in yaml_content
        assert "commands:" in yaml_content
        assert "python app.py" in yaml_content
        assert "port:" in yaml_content

    def test_dev_environment_configuration_to_yaml(self):
        """Test converting dev environment configuration to YAML"""
        config = DevEnvironmentConfiguration(
            name="test-dev",
            ide="vscode",
            resources={"cpu": 1, "memory": "1GB"},
            image="python:3.9",
        )

        run_spec = RunSpec(
            run_name="test-dev-run", configuration=config, ssh_key_pub="ssh-rsa test-key"
        )

        yaml_content = run_configuration_to_yaml(run_spec)

        assert "name: test-dev-run" in yaml_content
        assert "type: dev-environment" in yaml_content
        assert "ide: vscode" in yaml_content

    def test_configuration_without_run_name(self):
        """Test converting configuration when run_name is not set"""
        config = TaskConfiguration(
            name="test-task",
            commands=["echo 'Hello World'"],
            resources={"cpu": 1, "memory": "1GB"},
            image="python:3.9",
        )

        run_spec = RunSpec(configuration=config, ssh_key_pub="ssh-rsa test-key")

        yaml_content = run_configuration_to_yaml(run_spec)

        assert "name: test-task" in yaml_content
        assert "type: task" in yaml_content
