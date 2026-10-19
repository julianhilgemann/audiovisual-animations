from datapipe.cli import main
from datapipe.config import load_config, resolve_path


def test_frame_grid_hop_is_whole_samples():
    grid = load_config()["grid"]
    assert grid["sample_rate"] / grid["fps"] == 800


def test_repo_paths_resolve():
    cfg = load_config()
    assert resolve_path(cfg, "template").name == "neon_tunnel.blend"
    assert resolve_path(cfg, "inbox").is_dir()


def test_planned_command_reports_phase(capsys):
    assert main(["analyze", "song.mp4"]) == 2
    assert "P2" in capsys.readouterr().err
