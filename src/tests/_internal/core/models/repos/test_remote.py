import pytest

from dstack._internal.core.models.repos.remote import GitRepoURL, RepoError


class TestGitRepoURL:
    def test_parse_https_url(self):
        url = GitRepoURL.parse("https://github.com/dstackai/dstack.git")
        assert url.as_https() == "https://github.com/dstackai/dstack.git"
        assert url.as_ssh() == "ssh://git@github.com/dstackai/dstack.git"

    def test_parse_https_url_with_port(self):
        url = GitRepoURL.parse("https://github.com:8443/dstackai/dstack.git")
        assert url.as_https() == "https://github.com:8443/dstackai/dstack.git"
        assert url.as_ssh() == "ssh://git@github.com/dstackai/dstack.git"

    def test_parse_https_url_with_ssh_config(self):
        ssh_config = {
            "github.com": {
                "user": "test-user",
                "port": "2222",
                "hostname": "test.github.com",
            }
        }
        url = GitRepoURL.parse(
            "https://github.com:8443/dstackai/dstack.git",
            get_ssh_config=lambda host: ssh_config.get(host, {}),
        )
        assert url.as_https() == "https://github.com:8443/dstackai/dstack.git"
        assert url.as_ssh() == "ssh://test-user@github.com:2222/dstackai/dstack.git"

    def test_parse_scp_location(self):
        url = GitRepoURL.parse("test-user@test.example:a/b/c.git")
        assert url.as_https() == "https://test.example/a/b/c.git"
        assert url.as_ssh() == "ssh://test-user@test.example/a/b/c.git"

    def test_parse_scp_location_with_ssh_config(self):
        ssh_config = {
            "test.example": {
                "user": "test-user-2",
                "port": "2222",
                "hostname": "test2.example",
            }
        }
        url = GitRepoURL.parse(
            "test-user@test.example:a/b/c.git",
            get_ssh_config=lambda host: ssh_config.get(host, {}),
        )
        assert url.as_https() == "https://test2.example/a/b/c.git"
        assert url.as_ssh() == "ssh://test-user@test2.example:2222/a/b/c.git"

    def test_parse_ssh_url_with_ssh_config(self):
        ssh_config = {
            "test": {
                "user": "test-user",
                "port": "2222",
                "hostname": "test.example",
            }
        }
        url = GitRepoURL.parse(
            "ssh://test/repo.git", get_ssh_config=lambda host: ssh_config.get(host, {})
        )
        assert url.as_https() == "https://test.example/repo.git"
        assert url.as_ssh() == "ssh://test-user@test.example:2222/repo.git"

    def test_parse_unsupported_scheme(self):
        with pytest.raises(RepoError):
            GitRepoURL.parse("ftp://test.example/group/repo.git")

    def test_parse_garbage(self):
        with pytest.raises(RepoError):
            GitRepoURL.parse("garbage")

    def test_oauth_token(self):
        url = GitRepoURL.parse("https://github.com/dstackai/dstack.git")
        assert (
            url.as_https("secret-token")
            == "https://anything:secret-token@github.com/dstackai/dstack.git"
        )
