import random
import json
from typing import List, Tuple, Dict

class WerewolfDealer:
    """核心发牌引擎。

    功能：
    - 从配置 (roles_config.json) 读取各人数、各模式的角色池
    - 为给定人数生成 N+3 的角色集合，洗牌后分配给玩家与中央
    - 提供基础的胜负判定框架（可扩展）
    """

    def __init__(self, config_path: str = "resources/roles_config.json"):
        self.config_path = config_path
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.rules = json.load(f)
        except FileNotFoundError:
            # 提供最小内置默认规则以便测试与开发
            self.rules = self._default_rules()

    def _default_rules(self) -> Dict:
        # 内置简单规则，保证 4~9 的基本配置
        return {
            "4": {
                "入门": ["狼人","狼人","预言家","强盗","捣蛋鬼","酒鬼","村民"]
            },
            "5": {
                "入门": ["狼人","狼人","预言家","强盗","捣蛋鬼","酒鬼","失眠者","村民"]
            },
            "6": {
                "入门": ["化身幽灵","狼人","狼人","预言家","强盗","捣蛋鬼","酒鬼","失眠者","村民"]
            },
            "7": {
                "入门": ["化身幽灵","狼人","狼人","预言家","强盗","捣蛋鬼","酒鬼","失眠者","村民","皮匠"]
            },
            "8": {
                "入门": ["化身幽灵","狼人","狼人","爪牙","预言家","强盗","捣蛋鬼","酒鬼","失眠者","村民","猎人"]
            },
            "9": {
                "入门": ["化身幽灵","狼人","狼人","爪牙","预言家","强盗","捣蛋鬼","酒鬼","失眠者","村民","猎人","皮匠"]
            }
        }

    def get_available_modes(self, player_count: int) -> List[str]:
        key = str(player_count)
        if key not in self.rules:
            return []
        return list(self.rules[key].keys())

    def deal(self, player_count: int, mode: str = "入门") -> Tuple[List[str], List[str]]:
        """发牌：返回 (player_roles, center_roles)

        - player_roles: 长度 = player_count
        - center_roles: 长度 = 3
        """
        if player_count < 3 or player_count > 10:
            raise ValueError("玩家人数需在3~10之间")
        key = str(player_count)
        if key not in self.rules:
            raise ValueError(f"未在规则中找到对应人数 {player_count}")
        modes = self.rules[key]
        if mode not in modes:
            raise ValueError(f"未找到模式 '{mode}'，可用模式：{list(modes.keys())}")

        role_pool = modes[mode].copy()
        # 确保角色池至少为 N+3
        required = player_count + 3
        if len(role_pool) < required:
            raise ValueError(f"为 {player_count} 人模式，角色池需至少 {required} 张，当前 {len(role_pool)} 张")

        # 随机选择 required 张（先打乱全池再切片）
        random.shuffle(role_pool)
        selected = role_pool[:required]
        # 再次洗牌以打散
        random.shuffle(selected)
        player_roles = selected[:player_count]
        center_roles = selected[player_count:]
        return player_roles, center_roles

    def evaluate_win(self, final_identities: List[str]) -> Dict[str, bool]:
        """
        一个非常基础的胜负判定示例：
        - 接受 final_identities（玩家的最终身份列表，不含中央牌）
        - 返回一个字典说明各阵营是否胜利
        注意：这里只实现核心示例逻辑，复杂规则需按项目规则扩展。
        """
        results = {"狼人": False, "村民": False, "皮匠": False, "爪牙": False}
        # 判断是否有狼人
        wolf_present = any(r == "狼人" for r in final_identities)
        wolf_dead = False  # 需要外部传入死亡信息，示例暂置为 False

        if wolf_present and not wolf_dead:
            results["狼人"] = True
        if wolf_dead:
            results["村民"] = True
        # 皮匠特殊情况需要在外部传入死亡和狼人死亡的状态
        return results
