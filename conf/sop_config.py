import os

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

sop_config = {
    "base_dir": BASE_DIR,
    "sops": [
        {
            "path": "sop/mock_prd_sop.yaml",
            "triggers": ["存款", "定期", "大额存单", "通知存款", "结构性存款"],
        },
        {"path": "sop/mock_loan_sop.yaml"},
    ],
}
