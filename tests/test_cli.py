"""The command line's flags (homeset/__main__.py).  Found by a cold read on 2026-10-16."""

import pytest

from homeset import __main__ as cli


def test_the_usage_line_names_every_flag():
    for flag in cli.FLAGS:
        assert flag in cli.USAGE


@pytest.mark.parametrize("flag", ["--svae", "--saves", "--sav", "--help", "--Save"])
def test_an_unknown_flag_stops_the_run_before_the_model(monkeypatch, capsys, flag):
    monkeypatch.setattr(cli, "run_once", lambda *a, **k: pytest.fail("the model path ran"))
    assert cli.main(["I have 20 minutes and a mat.  Legs.", flag]) == 2
    out = capsys.readouterr().out
    assert f"Unknown option: {flag}" in out and "usage:" in out


def test_no_arguments_prints_the_usage(capsys):
    assert cli.main([]) == 2 and "[--save] [--saved]" in capsys.readouterr().out
