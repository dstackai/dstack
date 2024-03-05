from dstack.gateway.core.nginx import Nginx


class TestNginxConf:
    def test_add_upstream(self):
        conf = "upstream hex123 {\n" "  server http://fallback backup;\n" "}"
        expected = (
            "upstream hex123 {\n"
            "  server unix:/tmp/job1.sock; # REPLICA:12345\n"
            "  server http://fallback backup;\n"
            "}"
        )
        conf_out = Nginx.add_upstream_to_conf(conf, "unix:/tmp/job1.sock", "12345")
        assert conf_out == expected

    def test_remove_upstream(self):
        conf = (
            "upstream hex123 {\n"
            "  server unix:/tmp/job1.sock; # REPLICA:12345\n"
            "  server unix:/tmp/job2.sock; # REPLICA:67890\n"
            "  server http://fallback backup;\n"
            "}"
        )
        expected = (
            "upstream hex123 {\n"
            "  server unix:/tmp/job1.sock; # REPLICA:12345\n"
            "  server http://fallback backup;\n"
            "}"
        )
        conf_out = Nginx.remove_upstream_from_conf(conf, "67890")
        assert conf_out == expected
