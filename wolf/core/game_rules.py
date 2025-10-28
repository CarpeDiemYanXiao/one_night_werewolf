import json
from typing import Dict

# 用于定义和读取 roles_config.json 的辅助函数

def load_rules(path: str = "resources/roles_config.json") -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_rules(rules: Dict) -> bool:
    # 简单校验：检查键为人数字符串，值为模式字典
    for k, v in rules.items():
        if not k.isdigit():
            return False
        if not isinstance(v, dict):
            return False
        for mode, pool in v.items():
            if not isinstance(pool, list):
                return False
    return True
