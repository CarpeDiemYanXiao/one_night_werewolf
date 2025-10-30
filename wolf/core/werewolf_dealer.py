import random
import json
from typing import List, Tuple, Dict

class WerewolfDealer:
    ROLE_ALIASES = {
        "狼人": "werewolf",
        "werewolf": "werewolf",
        "爪牙": "minion",
        "minion": "minion",
        "守夜人": "mason",
        "mason": "mason",
        "预言家": "seer",
        "seer": "seer",
        "强盗": "robber",
        "robber": "robber",
        "捣蛋鬼": "troublemaker",
        "troublemaker": "troublemaker",
        "酒鬼": "drunk",
        "drunk": "drunk",
        "失眠者": "insomniac",
        "insomniac": "insomniac",
        "村民": "villager",
        "villager": "villager",
        "皮匠": "tanner",
        "tanner": "tanner",
        "保镖": "bodyguard",
        "bodyguard": "bodyguard",
        "化身幽灵": "doppelganger",
        "doppelganger": "doppelganger",
    }

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
            # 不再使用内置默认规则，若缺少配置则置为空字典（当前 GUI 随机发牌不依赖该配置）
            self.rules = {}


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
        if player_count < 4 or player_count > 12:
            raise ValueError("玩家人数需在4~12之间")
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

    # ---- 新增：基于玩家自选卡牌的会话管理 ----
    def start_game_with_selection(self, chosen_roles: List[str]):
        """
        基于外部（比如开始界面）传入的角色列表启动一局游戏。

        - chosen_roles: 长度必须 = players + 3（其中 players 会由函数根据长度自动推断）
        - 随机分配给玩家（每人一张）并留下三张中央牌
        初始化会话状态以便后续查看/交换/回合推进调用。
        """
        # 根据 chosen_roles 推断玩家人数
        if len(chosen_roles) < 6:
            # 最少 3 名玩家 => chosen_roles 最少为 6 张（3 + 3）
            raise ValueError("chosen_roles 长度过短，至少需 players+3（players 最小为3）")
        player_count = len(chosen_roles) - 3
        if player_count < 4 or player_count > 12:
            raise ValueError("推断的玩家人数需在4~12之间")

        required = player_count + 3
        if len(chosen_roles) != required:
            # 这一般不会发生，因为 player_count 是根据 length 推断的，仅作防护
            raise ValueError(f"chosen_roles 长度需为 players+3 ({required})，当前 {len(chosen_roles)}")

        # 深拷贝并随机分配
        pool = chosen_roles.copy()
        random.shuffle(pool)

        player_cards = pool[:player_count]
        center_cards = pool[player_count:]

        # 初始化会话状态
        self.session = {
            "player_count": player_count,
            "player_cards": player_cards,
            "center_cards": center_cards,
            # 初始分配快照（用于夜晚行动顺序与目标玩家绑定）
            "initial_player_cards": player_cards.copy(),
            # 每位玩家是否已查看（每人只允许查看一次）
            "viewed": [False] * player_count,
            # 当前行动的玩家索引（0-based），默认从 0 开始
            "turn_index": 0,
            # 记录是否处于行动阶段（允许 swap），外部可根据具体技能与阶段控制
            "action_phase": True,
            # 简单的交换/操作历史，用于调试或回放
            "history": []
        }
        return {
            "player_cards": player_cards.copy(),
            "center_cards": center_cards.copy()
        }

    def get_session(self):
        """返回当前会话的只读快照（如果存在）。"""
        if not hasattr(self, "session"):
            return None
        s = self.session
        return {
            "player_count": s["player_count"],
            "player_cards": s["player_cards"].copy(),
            "center_cards": s["center_cards"].copy(),
            "initial_player_cards": s.get("initial_player_cards", []).copy(),
            "viewed": s["viewed"].copy(),
            "turn_index": s["turn_index"],
            "action_phase": s["action_phase"]
        }

    @classmethod
    def normalize_role(cls, role: str) -> str:
        if not role:
            return ""
        key = role.lower() if isinstance(role, str) else role
        return cls.ROLE_ALIASES.get(key, key)

    def view_card(self, player_index: int) -> str:
        """
        玩家查看自己当前持有的一张牌。每个玩家只能查看一次。
        返回该玩家当前的身份字符串。
        """
        if not hasattr(self, "session"):
            raise RuntimeError("游戏尚未开始")
        s = self.session
        if player_index < 0 or player_index >= s["player_count"]:
            raise IndexError("player_index 越界")
        if s["viewed"][player_index]:
            raise RuntimeError("该玩家已查看过卡牌，不能再次查看")

        s["viewed"][player_index] = True
        card = s["player_cards"][player_index]
        s["history"].append({"action": "view", "player": player_index, "card": card})
        return card

    def swap_with_player(self, player_index: int, other_player_index: int):
        """将 player_index 的卡牌与 other_player_index 的卡牌互换。"""
        if not hasattr(self, "session"):
            raise RuntimeError("游戏尚未开始")
        s = self.session
        pc = s["player_cards"]
        n = s["player_count"]
        if not (0 <= player_index < n and 0 <= other_player_index < n):
            raise IndexError("player_index 越界")
        pc[player_index], pc[other_player_index] = pc[other_player_index], pc[player_index]
        s["history"].append({"action": "swap_player", "by": player_index, "with": other_player_index})
        return True

    def swap_with_center(self, player_index: int, center_index: int):
        """将 player_index 的卡牌与中央第 center_index 张牌互换（center_index = 0..2）。"""
        if not hasattr(self, "session"):
            raise RuntimeError("游戏尚未开始")
        s = self.session
        pc = s["player_cards"]
        cc = s["center_cards"]
        n = s["player_count"]
        if not (0 <= player_index < n):
            raise IndexError("player_index 越界")
        if not (0 <= center_index < len(cc)):
            raise IndexError("center_index 越界")
        pc[player_index], cc[center_index] = cc[center_index], pc[player_index]
        s["history"].append({"action": "swap_center", "by": player_index, "center_index": center_index})
        return True

    def next_turn(self):
        """推进到下一个玩家的行动（循环）。返回新的 turn_index。"""
        if not hasattr(self, "session"):
            raise RuntimeError("游戏尚未开始")
        s = self.session
        s["turn_index"] = (s["turn_index"] + 1) % s["player_count"]
        return s["turn_index"]

    def end_action_phase(self):
        """结束动作阶段（后续可禁止 swap/view）。"""
        if not hasattr(self, "session"):
            raise RuntimeError("游戏尚未开始")
        self.session["action_phase"] = False

    # ---- 夜晚流程与角色辅助 ----
    def get_role_indices(self, role_name: str, use_initial: bool = True) -> List[int]:
        if not hasattr(self, "session"):
            return []
        cards = self.session.get("initial_player_cards") if use_initial else self.session.get("player_cards")
        res = []
        if not cards:
            return res
        target = self.normalize_role(role_name)
        for i, r in enumerate(cards):
            if self.normalize_role(r) == target:
                res.append(i)
        return res

    def get_night_steps(self) -> List[Dict]:
        """返回夜晚步骤列表，包含出现的角色及相关玩家（基于初始身份）。"""
        order = ["doppelganger", "werewolf", "minion", "mason", "seer", "robber", "troublemaker", "drunk", "insomniac"]
        steps = []
        for role in order:
            players = self.get_role_indices(role, use_initial=True)
            if role == "mason" and len(players) not in (0, 2):
                # 守夜人必须成对出现，否则忽略以防配置问题
                players = []
            if players:
                steps.append({"role": role, "players": players})
        return steps

    # ---- 一键夜晚自动流程（默认策略，必要时可传入 choices 指定目标） ----
    def run_night_automation(self, choices: Dict = None) -> List[Dict]:
        """
        按顺序自动执行夜晚行动；不要求用户逐步操作，使用默认/随机策略。
        可通过 choices 指定目标，例如：
            {
              "robber": {robber_index: target_index},
              "troublemaker": {tm_index: (a_index, b_index)},
              "drunk": {drunk_index: center_index},
              "seer": {seer_index: {"type": "player", "target": idx} 或 {"type": "center", "targets": [i,j]}}
            }
        返回：行动日志列表。
        说明：化身幽灵（doppelganger）暂未实现具体复制规则，仅记录占位日志。
        """
        if not hasattr(self, "session"):
            raise RuntimeError("游戏尚未开始")
        s = self.session
        n = s["player_count"]
        log: List[Dict] = []
        rnd = random.Random()
        if choices is None:
            choices = {}

        def rand_other(i):
            cand = [x for x in range(n) if x != i]
            return rnd.choice(cand) if cand else None

        def rand_two_excl(exclude: List[int]):
            cand = [x for x in range(n) if x not in exclude]
            if len(cand) < 2:
                return None
            a = rnd.choice(cand)
            cand.remove(a)
            b = rnd.choice(cand)
            return a, b

        # 以初始身份确定出手人；卡牌交换在 s["player_cards"] 上进行
        steps = self.get_night_steps()
        for step in steps:
            role = step["role"]
            players = step["players"]
            if role == "doppelganger":
                #  需要确认化身幽灵的复制与后续行动规则
                log.append({"role": role, "players": players, "note": "未实现，需规则确认"})
                continue

            if role == "werewolf":
                # 多狼互相确认；若仅 1 狼，则可查看一张中央牌
                wolves = players
                if len(wolves) == 1 and s["center_cards"]:
                    ci = rnd.randrange(0, len(s["center_cards"]))
                    seen = s["center_cards"][ci]
                    log.append({"role": role, "wolves": wolves, "center_peek": ci, "card": seen})
                else:
                    log.append({"role": role, "wolves": wolves})
                continue

            if role == "minion":
                wolves_now = self.get_role_indices("werewolf", use_initial=True)
                log.append({"role": role, "minions": players, "wolves_seen": wolves_now})
                continue

            if role == "mason":
                # 两位守夜人互认
                log.append({"role": role, "masons": players})
                continue

            if role == "seer":
                for si in players:
                    choice = (choices.get("seer", {}) or {}).get(si)
                    if choice and choice.get("type") == "player":
                        tgt = choice.get("target")
                        card = s["player_cards"][tgt] if 0 <= tgt < n else None
                        log.append({"role": role, "seer": si, "peek_player": tgt, "card": card})
                    elif choice and choice.get("type") == "center":
                        idxs = choice.get("targets", [])[:2]
                        cards = [s["center_cards"][k] for k in idxs if 0 <= k < len(s["center_cards"])][:2]
                        log.append({"role": role, "seer": si, "peek_center": idxs, "cards": cards})
                    else:
                        # 默认：查看两张中央
                        idxs = list(range(len(s["center_cards"])));
                        rnd.shuffle(idxs)
                        idxs = idxs[:2]
                        cards = [s["center_cards"][k] for k in idxs]
                        log.append({"role": role, "seer": si, "peek_center": idxs, "cards": cards})
                continue

            if role == "robber":
                # 与一名其他玩家交换；然后查看新牌（这里仅记录日志）
                for ri in players:
                    tgt = (choices.get("robber", {}) or {}).get(ri)
                    if tgt is None:
                        tgt = rand_other(ri)
                    if tgt is None or not (0 <= tgt < n) or tgt == ri:
                        log.append({"role": role, "robber": ri, "note": "未找到可交换目标"})
                        continue
                    s["player_cards"][ri], s["player_cards"][tgt] = s["player_cards"][tgt], s["player_cards"][ri]
                    log.append({"role": role, "robber": ri, "swapped_with": tgt, "new_card": s["player_cards"][ri]})
                continue

            if role == "troublemaker":
                for ti in players:
                    pair = (choices.get("troublemaker", {}) or {}).get(ti)
                    if not pair:
                        pair = rand_two_excl([ti])
                    if not pair:
                        log.append({"role": role, "troublemaker": ti, "note": "可交换目标不足"})
                        continue
                    a, b = pair
                    s["player_cards"][a], s["player_cards"][b] = s["player_cards"][b], s["player_cards"][a]
                    log.append({"role": role, "troublemaker": ti, "swapped": (a, b)})
                continue

            if role == "drunk":
                for di in players:
                    ci = (choices.get("drunk", {}) or {}).get(di)
                    if ci is None:
                        ci = rnd.randrange(0, len(s["center_cards"])) if s["center_cards"] else None
                    if ci is None or not (0 <= ci < len(s["center_cards"])):
                        log.append({"role": role, "drunk": di, "note": "中央牌不存在"})
                        continue
                    s["player_cards"][di], s["center_cards"][ci] = s["center_cards"][ci], s["player_cards"][di]
                    log.append({"role": role, "drunk": di, "center_index": ci})
                continue

            if role == "insomniac":
                for ii in players:
                    log.append({"role": role, "insomniac": ii, "final_card": s["player_cards"][ii]})
                continue

        return log

    def reveal_player_card(self, player_index: int) -> str:
        if not hasattr(self, "session"):
            raise RuntimeError("游戏尚未开始")
        s = self.session
        if player_index < 0 or player_index >= s["player_count"]:
            raise IndexError("player_index 越界")
        return s["player_cards"][player_index]

    def reveal_center_cards(self, indices: List[int]) -> List[str]:
        if not hasattr(self, "session"):
            raise RuntimeError("游戏尚未开始")
        s = self.session
        res = []
        for idx in indices:
            if 0 <= idx < len(s["center_cards"]):
                res.append(s["center_cards"][idx])
            else:
                raise IndexError("center_index 越界")
        return res

    def swap_between_players(self, i: int, j: int):
        if not hasattr(self, "session"):
            raise RuntimeError("游戏尚未开始")
        s = self.session
        n = s["player_count"]
        if not (0 <= i < n and 0 <= j < n):
            raise IndexError("player_index 越界")
        s["player_cards"][i], s["player_cards"][j] = s["player_cards"][j], s["player_cards"][i]
        s["history"].append({"action": "swap_between", "i": i, "j": j})
        return True

    def get_current_player_card(self, player_index: int) -> str:
        if not hasattr(self, "session"):
            raise RuntimeError("游戏尚未开始")
        s = self.session
        if player_index < 0 or player_index >= s["player_count"]:
            raise IndexError("player_index 越界")
        return s["player_cards"][player_index]

    def evaluate_victory(self, executed_indices: List[int], is_tie: bool = False) -> Dict[str, bool]:
        """
        根据最终玩家面前身份（不含中央）与处决结果计算胜负。
        规则简化实现：
        a. 若被处决的是狼人，则好人阵营胜利；
        b. 若被处决的是皮匠，且没有狼人死去，则皮匠单独获胜；
        c. 若被处决的不是狼人或皮匠，则狼人阵营胜利；
        d. 平票：不死人；若场上有狼人（或无狼人但有爪牙按狼人算），狼人胜；否则好人胜。
        另外：若无狼人且有爪牙，则视为有狼人存在（用于以上判断）。
        返回：{"good": bool, "wolf": bool, "tanner": bool}
        """
        if not hasattr(self, "session"):
            raise RuntimeError("游戏尚未开始")
        s = self.session
        final_cards = s["player_cards"]
        final_norm = [self.normalize_role(r) for r in final_cards]
        wolf_present = any(r == "werewolf" for r in final_norm)
        minion_present = any(r == "minion" for r in final_norm)
        if not wolf_present and minion_present:
            wolf_present = True  # 爪牙视为狼人

        result = {"good": False, "wolf": False, "tanner": False}

        if is_tie:
            if wolf_present:
                result["wolf"] = True
            else:
                result["good"] = True
            return result

        # 非平票，检查被处决者身份
        executed_roles = []
        for idx in executed_indices:
            if 0 <= idx < len(final_norm):
                executed_roles.append(final_norm[idx])

        if any(r == "werewolf" for r in executed_roles):
            result["good"] = True
            return result
        if any(r == "tanner" for r in executed_roles):
            # 皮匠单独胜，若没有狼人死去（上面已经 return 了狼被处决的情况）
            result["tanner"] = True
            return result

        # 否则狼人阵营胜（狼或爪牙）
        result["wolf"] = True
        return result

