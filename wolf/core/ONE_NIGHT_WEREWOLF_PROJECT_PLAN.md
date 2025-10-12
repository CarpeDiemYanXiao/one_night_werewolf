# 《一夜终极狼人发牌器》 — 项目分工与开发计划（四人开发版）

> 该文档为可交付项目计划，适用于四人团队开发《一夜终极狼人发牌器》。文档为 Markdown 格式，可直接另存为 Word。

---

## 🎯 一、项目目标

制作一个带图形界面（GUI）的桌游发牌器，支持《一夜终极狼人》的核心玩法：

- 输入玩家人数（3–10人）
- 根据推荐或自定义规则自动抽取角色（N+3张）
- 随机洗牌并发牌（每人一张 + 桌面三张）
- 可展示或隐藏身份牌（支持单独查看模式）
- 支持角色图片显示、阵营标识
- 可扩展不同模式（入门、进阶、欢乐、探索）
- 支持发牌结果导出（TXT / CSV）或保存局面

---

## 🧩 二、角色与人数配置（核心内置规则）

### ✅ 基础配置（官方推荐）

| 玩家人数 | 对应身份牌 |
| ---- | ---------------------------------------- |
| 4人局  | 狼人 ×2、预言家、强盗、捣蛋鬼、酒鬼、村民 |
| 5人局  | 狼人 ×2、预言家、强盗、捣蛋鬼、酒鬼、失眠者、村民 |
| 6人局  | 化身幽灵、狼人 ×2、预言家、强盗、捣蛋鬼、酒鬼、失眠者、村民 |
| 7人局  | 化身幽灵、狼人 ×2、预言家、强盗、捣蛋鬼、酒鬼、失眠者、村民、皮匠 |
| 8人局  | 化身幽灵、狼人 ×2、爪牙、预言家、强盗、捣蛋鬼、酒鬼、失眠者、村民、猎人 |
| 9人局  | 化身幽灵、狼人 ×2、爪牙、预言家、强盗、捣蛋鬼、酒鬼、失眠者、村民、猎人、皮匠 |

> 规则：每局总是选取 N+3 张角色牌，3张放中央，其余分配给玩家。

---

## 🧠 三、阵营与胜利条件逻辑

| 阵营        | 胜利条件概要 |
| --------- | ------------------- |
| 狼人阵营      | 狼人存在且无人狼人死亡 |
| 村民阵营      | 至少一只狼人死亡 |
| 无狼人 + 无爪牙 | 平票则全胜，有人死则全败 |
| 无狼人 + 有爪牙 | 爪牙以自己以外玩家死亡为胜 |
| 有皮匠       | 若皮匠死亡且无狼人死亡 → 皮匠单独胜 |

> 所有胜负判定以最终身份为准（执行完夜晚技能后）。

---

## 👥 四、四人分工（狼人发牌器团队版）

| 成员                      | 模块        | 主要任务                                                                             | 技术要点                           |
| ----------------------- | --------- | -------------------------------------------------------------------------------- | ------------------------------ |
| **A：核心逻辑开发者（Dealer引擎）** | 游戏规则与发牌逻辑 | - 编写 `WerewolfDealer` 类  
- 根据人数、模式返回角色池（N+3）  
- 随机洗牌与发牌分配逻辑  
- 胜负条件逻辑框架    | `random.shuffle()`、角色规则映射、逻辑校验 |
| **B：界面与交互设计师（GUI）**     | 图形界面开发    | - 负责整体 UI 布局（tkinter / PyQt）  
- 输入人数、选择模式、点击发牌  
- 玩家身份显示与隐藏  
- 显示阵营图标与角色图片 | GUI 布局、图片显示、交互按钮、动态更新 |
| **C：资源与数据管理者（UI素材）**    | 图片与配置文件   | - 收集角色图片（统一命名）  
- 制作阵营标志与背景  
- 提供配置文件 `roles_config.json` 用于模式扩展             | 资源管理、路径组织、配置可扩展性 |
| **D：测试与扩展功能开发者**        | 功能测试与增强   | - 设计单元测试（人数、重复、模式切换）  
- 实现身份隐藏模式/揭示模式  
- 导出结果（TXT/CSV）  
- 可能加入夜晚技能演示动画     | 单元测试、异常处理、文件导出、动画演示 |

---

## 📁 五、项目结构建议

```plaintext
Werewolf_Dealer/
│
├── main.py                      # 主程序入口
│
├── core/                        # A 负责
│   ├── werewolf_dealer.py       # 发牌与逻辑核心
│   ├── game_rules.py            # 角色与模式规则
│   └── __init__.py
│
├── gui/                         # B 负责
│   ├── main_window.py           # GUI 主界面
│   ├── player_cards.py          # 玩家牌显示组件
│   ├── mode_selector.py         # 模式选择器（入门/进阶/欢乐/探索）
│   └── __init__.py
│
├── resources/                   # C 负责
│   ├── roles/                   # 各角色图片
│   │   ├── 狼人.png
│   │   ├── 预言家.png
│   │   ├── 捣蛋鬼.png
│   │   ├── 强盗.png
│   │   ├── 酒鬼.png
│   │   ├── 守夜人.png
│   │   ├── 皮匠.png
│   │   ├── 猎人.png
│   │   ├── 爪牙.png
│   │   └── 村民.png
│   ├── icon.png
│   ├── background.png
│   └── roles_config.json        # 可扩展的模式配置文件
│
├── tests/                       # D 负责
│   ├── test_dealer.py
│   ├── test_ui.py
│   └── test_rules.py
│
└── README.md
```

---

## 💡 六、关键逻辑示例

### ✅ `core/werewolf_dealer.py`（示例）

```python
import random
import json

class WerewolfDealer:
    def __init__(self, config_path="resources/roles_config.json"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.rules = json.load(f)

    def deal(self, player_count: int, mode: str = "入门配置"):
        if str(player_count) not in self.rules:
            raise ValueError("暂不支持该人数，请输入 4~10。")
        role_pool = self.rules[str(player_count)][mode]
        # 取 N+3 张角色牌
        roles = role_pool.copy()
        random.shuffle(roles)
        player_roles = roles[:player_count]
        center_roles = roles[player_count:]
        return player_roles, center_roles
```

---

## 🖥️ 七、界面主程序示例（tkinter）

### ✅ `gui/main_window.py`（示例）

```python
import tkinter as tk
from core.werewolf_dealer import WerewolfDealer
from PIL import Image, ImageTk

class WerewolfApp:
    def __init__(self, root):
        self.root = root
        self.root.title("一夜终极狼人发牌器")
        self.dealer = WerewolfDealer()

        self.label = tk.Label(root, text="请输入玩家人数 (4~10)：", font=("微软雅黑", 12))
        self.label.pack(pady=8)

        self.entry = tk.Entry(root, font=("微软雅黑", 12))
        self.entry.pack()

        self.btn = tk.Button(root, text="发牌", command=self.deal_cards, font=("微软雅黑", 12))
        self.btn.pack(pady=10)

        self.cards_frame = tk.Frame(root)
        self.cards_frame.pack()

    def deal_cards(self):
        for widget in self.cards_frame.winfo_children():
            widget.destroy()
        count = int(self.entry.get())
        player_roles, center = self.dealer.deal(count)
        all_roles = player_roles + ["中央1", "中央2", "中央3"]
        for i, role in enumerate(player_roles):
            img = Image.open(f"resources/roles/{role}.png").resize((100, 150))
            tk_img = ImageTk.PhotoImage(img)
            lbl = tk.Label(self.cards_frame, image=tk_img, text=f"玩家{i+1}", compound="top")
            lbl.image = tk_img
            lbl.grid(row=i//5, column=i%5, padx=10, pady=10)
```

---

## ✨ 八、可扩展功能建议

| 功能        | 难度  | 描述                 |
| --------- | --- | ------------------ |
| 自定义角色组合   | ⭐⭐  | 玩家自由勾选角色组成 N+3 角色池 |
| 身份隐藏 / 揭示 | ⭐   | 随机分配但先不显示，点击揭示后显示 |
| 模式切换      | ⭐⭐  | 入门 / 进阶 / 欢乐 / 探索 |
| 夜晚技能演示    | ⭐⭐⭐ | 模拟上帝叫醒各角色的顺序动画 |
| 导出发牌结果    | ⭐   | 输出 TXT/CSV 方便复盘 |
| 背景音乐与音效   | ⭐   | 增加沉浸感 |

---

## 📆 九、开发阶段与交付目标

| 阶段          | 时间    | 主要目标                   | 负责人 |
| ----------- | ----- | ---------------------- | --- |
| 阶段1：框架搭建    | 第1–2天 | 建立项目结构，完成基础逻辑类         | A   |
| 阶段2：基础GUI实现 | 第3天   | 完成基本窗口、人数输入与发牌显示       | B   |
| 阶段3：资源整合    | 第4天   | 导入角色图片、制作背景与图标         | C   |
| 阶段4：测试与优化   | 第5天   | 功能测试、逻辑验证、异常处理         | D   |
| 阶段5：扩展功能与打包 | 第6–7天 | 加入模式选择、导出、动画演示；打包可执行文件 | 全组  |

---

## ✅ 十、验收标准（交付条件）

- 能运行 GUI，接受玩家人数 4–10 并正确分配 N+3 角色牌。
- 每名玩家与中央三张牌正确显示（图片/文字），支持手动隐藏/显示身份。
- 能按模式切换内置角色组合，并支持自定义组合保存。
- 输出发牌结果为 TXT 或 CSV 文件，包含玩家序号与角色。
- 包含单元测试：核心发牌逻辑覆盖常见人数与重复性检查。

---

## 🧪 十一、建议的单元测试清单

- test_dealer.py
  - 测试不同玩家数（4–10）角色分配是否为 N+3 总数。
  - 测试随机性（多次运行，统计分布）。
  - 测试无效人数抛出异常。

- test_rules.py
  - 测试模式配置读取与规则字段完整性。

- test_ui.py（轻量）
  - 测试主窗口创建不抛异常。

---

## 🛠️ 十二、开发与运行（快速指南）

- 依赖（建议）：Python 3.10+、Pillow（图片支持）
- 运行（开发环境）示例：

```bash
pip install pillow
python main.py
```

---

## ✍️ 十三、后续建议与交付物

- 编写更详细的用户手册（如何自定义角色、如何打包、Windows 可执行说明）。
- 增加持续集成（GitHub Actions）来跑单元测试和打包 artefacts。
- 若需要跨平台 GUI 美观可考虑迁移到 PyQt 或 Electron + 后端。

---

## 📌 最后说明

- 本文档基于你提供的方案进行了格式化、补充与工程化建议，已准备为可直接交付的 Markdown 文件。若需要我可以：
  - 将该 Markdown 自动转换为 Word（.docx）并保存到工作区；
  - 继续完成步骤 2–7（创建骨架、实现核心类、GUI、测试用例、资源占位等），并逐步执行并运行测试。


---

创作于：一夜终极狼人发牌器 项目计划生成器
