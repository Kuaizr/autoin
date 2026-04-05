import json

from autoin.adapters.drivers import WindowReference
from autoin.tools.wechat_uia_dump import main


class StubDriver:
    def dump_wechat_uia_tree(self, max_nodes: int = 200) -> dict[str, object]:
        return {
            "driver": "pywinauto",
            "app": "wechat",
            "window": WindowReference(
                app="wechat",
                target_uid=None,
                backend="uia",
                locator="微信",
                locator_status="resolved",
            ),
            "nodes": [
                {
                    "depth": 0,
                    "control_type": "Window",
                    "class_name": "WeChatMainWndForPC",
                    "automation_id": None,
                    "name": "微信",
                    "texts": ["微信"],
                }
            ],
        }


def test_wechat_uia_dump_main_prints_json(capsys, monkeypatch) -> None:
    monkeypatch.setattr("autoin.tools.wechat_uia_dump.PywinautoDriver", lambda: StubDriver())

    exit_code = main(["--max-nodes", "20"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["app"] == "wechat"
    assert payload["nodes"][0]["class_name"] == "WeChatMainWndForPC"
