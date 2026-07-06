from dstack._internal.core.backends.slurm.client import _parse_scontrol_show_line


class TestParseScontrolShowLine:
    # A single `scontrol show -o node` line for an allocated node. It exercises the tricky
    # cases the parser must handle:
    # - multi-word value (OS) containing spaces and `#`
    # - values with embedded `=` that must not be split into new keys (CfgTRES/AllocTRES)
    # - "(null)" and "N/A" sentinels kept verbatim
    # - underscore in a key (MCS_label)
    # - double spaces between some fields
    SCONTROL_SHOW_NODE_LINE = (
        "NodeName=worker-1 Arch=x86_64 CoresPerSocket=1  CPUAlloc=4 CPUEfctv=4 CPUTot=4 "
        "CPULoad=0.10 AvailableFeatures=(null) ActiveFeatures=(null) Gres=(null) GresDrain=N/A "
        "NodeAddr=worker-1 NodeHostName=worker-1 Version=25.11.2 "
        "OS=Linux 7.0.0-22-generic #22-Ubuntu SMP PREEMPT_DYNAMIC Mon May 25 15:54:34 UTC 2026  "
        "RealMemory=15000 AllocMem=0 FreeMem=14769 Sockets=4 Boards=1 State=ALLOCATED "
        "ThreadsPerCore=1 TmpDisk=0 Weight=1 Owner=N/A MCS_label=N/A Partitions=main,wrk-1  "
        "BootTime=2026-06-16T10:02:01 SlurmdStartTime=2026-06-16T10:02:13 "
        "LastBusyTime=2026-06-16T11:09:07 ResumeAfterTime=None "
        "CfgTRES=cpu=4,mem=15000M,billing=4 AllocTRES=cpu=4,mem=15000M,billing=4 "
        "CurrentWatts=0 AveWatts=0"
    )

    def test_parses_full_node_line(self):
        assert _parse_scontrol_show_line(self.SCONTROL_SHOW_NODE_LINE) == {
            "nodename": "worker-1",
            "arch": "x86_64",
            "corespersocket": "1",
            "cpualloc": "4",
            "cpuefctv": "4",
            "cputot": "4",
            "cpuload": "0.10",
            "availablefeatures": "(null)",
            "activefeatures": "(null)",
            "gres": "(null)",
            "gresdrain": "N/A",
            "nodeaddr": "worker-1",
            "nodehostname": "worker-1",
            "version": "25.11.2",
            "os": "Linux 7.0.0-22-generic #22-Ubuntu SMP PREEMPT_DYNAMIC Mon May 25 15:54:34 UTC 2026",
            "realmemory": "15000",
            "allocmem": "0",
            "freemem": "14769",
            "sockets": "4",
            "boards": "1",
            "state": "ALLOCATED",
            "threadspercore": "1",
            "tmpdisk": "0",
            "weight": "1",
            "owner": "N/A",
            "mcs_label": "N/A",
            "partitions": "main,wrk-1",
            "boottime": "2026-06-16T10:02:01",
            "slurmdstarttime": "2026-06-16T10:02:13",
            "lastbusytime": "2026-06-16T11:09:07",
            "resumeaftertime": "None",
            "cfgtres": "cpu=4,mem=15000M,billing=4",
            "alloctres": "cpu=4,mem=15000M,billing=4",
            "currentwatts": "0",
            "avewatts": "0",
        }

    def test_keeps_multi_word_value_intact(self):
        result = _parse_scontrol_show_line(self.SCONTROL_SHOW_NODE_LINE)

        # The whole `OS=...` value is captured up to the next key, with surrounding
        # whitespace (including the trailing double space) stripped.
        assert (
            result["os"]
            == "Linux 7.0.0-22-generic #22-Ubuntu SMP PREEMPT_DYNAMIC Mon May 25 15:54:34 UTC 2026"
        )

    def test_does_not_split_value_on_embedded_equals(self):
        result = _parse_scontrol_show_line(self.SCONTROL_SHOW_NODE_LINE)

        # `cpu=...`, `mem=...`, `billing=...` are part of the value, not new keys,
        # because they are not preceded by whitespace.
        assert result["cfgtres"] == "cpu=4,mem=15000M,billing=4"
        assert result["alloctres"] == "cpu=4,mem=15000M,billing=4"
        assert "cpu" not in result
        assert "mem" not in result
        assert "billing" not in result

    def test_keeps_null_and_na_sentinels_verbatim(self):
        result = _parse_scontrol_show_line(self.SCONTROL_SHOW_NODE_LINE)

        assert result["gres"] == "(null)"
        assert result["availablefeatures"] == "(null)"
        assert result["gresdrain"] == "N/A"
        assert result["owner"] == "N/A"

    def test_normalizes_keys_to_lowercase_by_default(self):
        result = _parse_scontrol_show_line(self.SCONTROL_SHOW_NODE_LINE)

        assert "nodename" in result
        assert "mcs_label" in result
        assert "NodeName" not in result

    def test_preserves_key_case_when_normalize_key_is_false(self):
        result = _parse_scontrol_show_line(self.SCONTROL_SHOW_NODE_LINE, normalize_key=False)

        assert result["NodeName"] == "worker-1"
        assert result["MCS_label"] == "N/A"
        assert result["CfgTRES"] == "cpu=4,mem=15000M,billing=4"
        assert "nodename" not in result

    def test_strips_surrounding_whitespace_on_the_line(self):
        assert _parse_scontrol_show_line("  NodeName=worker-1 CPUTot=4  \n") == {
            "nodename": "worker-1",
            "cputot": "4",
        }

    def test_returns_empty_dict_for_blank_line(self):
        assert _parse_scontrol_show_line("") == {}
        assert _parse_scontrol_show_line("   \n") == {}
