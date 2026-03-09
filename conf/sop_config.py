import os

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

sop_config = {
    "base_dir": BASE_DIR,
    "sops": [
        {
            "path": "sop/mock_sop.yaml",
            "triggers": ["", "", "", "", ""],
        },
        {"path": "sop/mock_sop.yaml"},
    ],
}
