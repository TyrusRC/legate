import sys

import pytest

import legate.sandbox as sb


def test_wrap_denies_net_by_default_and_binds_workdir(tmp_path):
    argv = sb.wrap(["echo", "hi"], tmp_path)
    assert "--unshare-net" in argv          # no network by default
    assert "--bind" in argv
    assert str(tmp_path.resolve()) in argv
    assert argv[-2:] == ["echo", "hi"]


def test_wrap_allows_net_when_opted_in(tmp_path):
    argv = sb.wrap(["echo", "hi"], tmp_path, allow_net=True)
    assert "--unshare-net" not in argv


def test_wrap_fails_closed_without_backend(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "available", lambda: None)
    with pytest.raises(sb.SandboxUnavailable):
        sb.wrap(["echo", "hi"], tmp_path, require=True)
    # non-required falls back to the bare argv
    assert sb.wrap(["echo", "hi"], tmp_path, require=False) == ["echo", "hi"]


@pytest.mark.skipif(sb.available() is None, reason="bwrap not installed")
def test_sandboxed_command_runs_and_confines_writes(tmp_path):
    # runs, and the writable dir works
    r = sb.run([sys.executable, "-c", "open('out.txt','w').write('ok'); print('ran')"], tmp_path)
    assert r.returncode == 0 and "ran" in r.stdout
    assert (tmp_path / "out.txt").read_text() == "ok"


@pytest.mark.skipif(sb.available() is None, reason="bwrap not installed")
def test_sandboxed_write_outside_workdir_is_blocked(tmp_path):
    # /home is read-only in the sandbox → writing there must fail
    r = sb.run([sys.executable, "-c",
                "import os\n"
                "try:\n open('/home/legate_should_not_exist','w').write('x'); print('WROTE')\n"
                "except OSError as e:\n print('BLOCKED')"], tmp_path)
    assert "BLOCKED" in r.stdout
    assert "WROTE" not in r.stdout
