import os
import sys
import math
from collections import Counter
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk


# 当直接以脚本运行时（python wolf/gui/main_window.py），确保项目的 `wolf` 目录在 sys.path 中
# 这样可以使用顶级包导入方式（from core import ...）而不报错
proj_wolf_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if proj_wolf_dir not in sys.path:
    sys.path.insert(0, proj_wolf_dir)

from core.werewolf_dealer import WerewolfDealer

ROLE_DISPLAY_NAMES = {
    "werewolf": "狼人",
    "minion": "爪牙",
    "mason": "守夜人",
    "seer": "预言家",
    "robber": "强盗",
    "troublemaker": "捣蛋鬼",
    "drunk": "酒鬼",
    "insomniac": "失眠者",
    "villager": "村民",
    "tanner": "皮匠",
    "bodyguard": "保镖",
    "hunter": "猎人",
    "doppelganger": "化身幽灵",
    "minion": "爪牙",
    "hunter": "猎人",
}


class WerewolfApp:
    def __init__(self, root):
        self.root = root
        self.root.title("一夜终极狼人发牌器")
        self.dealer = WerewolfDealer()
        # 图片缓存，避免 PhotoImage 被 GC
        self._img_cache = {}
        self.current_role_pool = None

        # 背景图相关
        self._bg_label = None
        self._bg_img_orig = None
        self._bg_img_tk = None
        self._setup_background()

        frm = ttk.Frame(root, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(frm)
        top.pack(fill=tk.X, pady=6)

        ttk.Label(top, text="玩家人数:").pack(side=tk.LEFT)
        # 支持 4-12 人
        self.spin = ttk.Spinbox(top, from_=4, to=12, width=5)
        self.spin.set(4)
        self.spin.pack(side=tk.LEFT, padx=6)
        self.spin.configure(command=self._update_selection_summary)
        self.spin.bind("<FocusOut>", lambda e: self._update_selection_summary())

        # 角色选择区：图形化选择（点击图片卡片），狼人使用计数，守夜人自动两张
        self.available_roles = self._load_available_roles()

        self.roles_frame = ttk.LabelFrame(frm, text="选择角色（玩家人数 + 3）", padding=6)
        self.roles_frame.pack(fill=tk.BOTH, expand=False, pady=6)
        self.roles_frame_visible = True

        # 图形化网格
        self.roles_grid = ttk.Frame(self.roles_frame)
        self.roles_grid.pack(fill=tk.BOTH, expand=True)
        self.role_tiles = {}  # internal -> {selected_var, img_label, frame}
        self._build_graphical_role_selector()

        self.selected_count_var = tk.StringVar(value="已选择 0 张")
        ttk.Label(self.roles_frame, textvariable=self.selected_count_var).pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(
            self.roles_frame,
            text="提示：点击图片切换选中；点击狼人图片循环数量；选择守夜人默认两张"
        ).pack(anchor=tk.W, pady=(2, 0))
        self._update_selection_summary()

        # 开始局（使用玩家选定的角色进行随机发牌）
        self.start_btn = ttk.Button(top, text="开始局", command=self.start_game)
        self.start_btn.pack(side=tk.LEFT, padx=6)

        # 兼容旧按钮：随机从规则池发牌
        self.deal_btn = ttk.Button(top, text="随机发牌", command=self.deal)
        self.deal_btn.pack(side=tk.LEFT, padx=6)

        self.export_btn = ttk.Button(top, text="导出结果", command=self.export, state=tk.DISABLED)
        self.export_btn.pack(side=tk.LEFT, padx=6)

        self.cards_frame = ttk.Frame(frm)
        self.cards_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self._last_result = None

    def _load_available_roles(self):
        """加载可选角色，返回 [{'display': str, 'internal': str}, ...]，排除狼人，由数量输入控制。"""
        role_dirs = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'resources', 'roles')),
            os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'images', 'roles'))
        ]
        role_dict = {}

        for internal, display in ROLE_DISPLAY_NAMES.items():
            if internal == "werewolf":
                continue
            role_dict.setdefault(internal, display)

        for path in role_dirs:
            if not os.path.isdir(path):
                continue
            for fn in os.listdir(path):
                name, ext = os.path.splitext(fn)
                if ext.lower() not in ('.png', '.jpg', '.jpeg', '.gif'):
                    continue
                internal = WerewolfDealer.normalize_role(name)
                if internal == "werewolf":
                    continue
                role_dict.setdefault(internal, ROLE_DISPLAY_NAMES.get(internal, name))

        sorted_roles = sorted(role_dict.items(), key=lambda kv: kv[1])
        return [{"internal": internal, "display": display} for internal, display in sorted_roles]

    def _build_graphical_role_selector(self):
        """创建基于图片的角色选择网格。狼人用计数，其它角色点击切换选中。"""
        # 清空旧部件
        for w in self.roles_grid.winfo_children():
            w.destroy()

        # 预加载图像
        def load_img_for(role_name, size=(140, 210)):
            path = self._find_image_file(role_name) or self._find_image_file('background')
            if not path:
                return None
            try:
                try:
                    resample = Image.Resampling.LANCZOS
                except Exception:
                    resample = Image.LANCZOS
                img = Image.open(path).resize(size, resample)
                return ImageTk.PhotoImage(img)
            except Exception:
                return None

        cols = 5
        r = c = 0

        # 狼人数量专用 tile
        werewolf_frame = ttk.Frame(self.roles_grid, padding=4, relief=tk.GROOVE)
        w_img = load_img_for('werewolf')
        w_img_lbl = ttk.Label(werewolf_frame, image=w_img)
        w_img_lbl.image = w_img  # 防 GC
        w_img_lbl.pack(side=tk.TOP)
        ttk.Label(werewolf_frame, text=f"{ROLE_DISPLAY_NAMES.get('werewolf','werewolf')}（数量）").pack(side=tk.TOP, pady=(4, 0))
        self.werewolf_count_var = tk.StringVar(value="2")
        sp = ttk.Spinbox(werewolf_frame, from_=0, to=5, width=5, textvariable=self.werewolf_count_var,
                         command=self._update_selection_summary)
        sp.pack(side=tk.TOP, pady=(2, 2))
        def inc_wolf(_e=None):
            try:
                v = int(self.werewolf_count_var.get())
            except Exception:
                v = 0
            v = (v + 1) if v < 5 else 0
            self.werewolf_count_var.set(str(v))
            self._update_selection_summary()
        w_img_lbl.bind('<Button-1>', inc_wolf)
        self.werewolf_count_var.trace_add('write', lambda *a: self._update_selection_summary())

        werewolf_frame.grid(row=r, column=c, padx=6, pady=6, sticky='n')
        c += 1
        if c >= cols:
            r += 1; c = 0

        # 其它角色：点击切换选中
        self.role_tiles.clear()
        for role in self.available_roles:
            internal = role['internal']
            display = role['display']
            # 使用 tk.Frame 便于自定义背景与边框
            frame = tk.Frame(self.roles_grid, bd=2, relief=tk.RIDGE, bg="#F9FAFB")
            content = tk.Frame(frame, bg="#F9FAFB")
            content.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

            img = load_img_for(internal)
            img_lbl = tk.Label(content, image=img, bg="#F9FAFB")
            img_lbl.image = img  # 防 GC
            img_lbl.pack(side=tk.TOP)
            txt = tk.Label(content, text=display, bg="#F9FAFB")
            txt.pack(side=tk.TOP, pady=(4, 0))

            # 选中角标（默认隐藏）
            sel_badge = tk.Label(frame, text="✓ 已选", bg="#22C55E", fg="white", font=(None, 10, 'bold'))

            sel = tk.BooleanVar(value=False)
            # 选中高亮效果（改变 relief、背景和角标）
            def toggle(_e=None, var=sel, fr=frame, badge=sel_badge):
                var.set(not var.get())
                if var.get():
                    fr.configure(relief=tk.SOLID, bd=3, bg="#DCFCE7")
                    content.configure(bg="#DCFCE7")
                    img_lbl.configure(bg="#DCFCE7")
                    txt.configure(bg="#DCFCE7")
                    badge.place(relx=1.0, rely=0.0, anchor='ne', x=-2, y=2)
                    badge.lift()
                else:
                    fr.configure(relief=tk.RIDGE, bd=2, bg="#F9FAFB")
                    content.configure(bg="#F9FAFB")
                    img_lbl.configure(bg="#F9FAFB")
                    txt.configure(bg="#F9FAFB")
                    badge.place_forget()
                self._update_selection_summary()
            img_lbl.bind('<Button-1>', toggle)
            txt.bind('<Button-1>', toggle)
            frame.grid(row=r, column=c, padx=6, pady=6, sticky='n')
            self.role_tiles[internal] = {
                'selected_var': sel,
                'frame': frame,
                'image_label': img_lbl,
                'text_label': txt,
                'badge_label': sel_badge,
            }
            c += 1
            if c >= cols:
                r += 1; c = 0

    def _expected_card_count(self):
        try:
            return int(self.spin.get()) + 3
        except Exception:
            return 0

    def _get_werewolf_count(self):
        try:
            value = int(self.werewolf_count_var.get())
        except Exception:
            value = 0
        return max(0, value)

    def _compute_role_selection(self):
        roles = ['werewolf'] * self._get_werewolf_count()
        # 从图形化 tile 中读取选中状态
        for internal, info in self.role_tiles.items():
            if info['selected_var'].get():
                if internal == 'mason':
                    roles.extend(['mason', 'mason'])
                else:
                    roles.append(internal)
        return roles

    def _update_selection_summary(self, *args):
        roles = self._compute_role_selection()
        counts = Counter(roles)
        expected = self._expected_card_count()
        parts = [f"{ROLE_DISPLAY_NAMES.get(role, role)}×{cnt}" for role, cnt in counts.items()]
        detail = ", ".join(parts) if parts else "未选择牌"
        self.selected_count_var.set(f"已选择 {len(roles)} 张（需 {expected} 张）：{detail}")

    def _hide_role_selection(self):
        if self.roles_frame_visible:
            self.roles_frame.pack_forget()
            self.roles_frame_visible = False

    def _show_role_selection(self):
        if not self.roles_frame_visible:
            self.roles_frame.pack(fill=tk.BOTH, expand=False, pady=6)
            self.roles_frame_visible = True
            self.roles_grid.focus_set()

    def deal(self):
        if self.current_role_pool:
            try:
                res = self.dealer.start_game_with_selection(self.current_role_pool.copy())
            except Exception as e:
                messagebox.showerror("发牌失败", str(e))
                return

            player_roles = res['player_cards']
            center = res['center_cards']
        else:
            try:
                count = int(self.spin.get())
            except Exception:
                messagebox.showerror("错误", "请输入有效人数")
                return

            modes = self.dealer.get_available_modes(count)
            mode = modes[0] if modes else "入门"

            try:
                player_roles, center = self.dealer.deal(count, mode=mode)
            except Exception as e:
                messagebox.showerror("发牌失败", str(e))
                return

            # 初始化 dealer.session
            self.dealer.session = {
                "player_count": count,
                "player_cards": player_roles.copy(),
                "center_cards": center.copy(),
                "viewed": [False] * count,
                "turn_index": 0,
                "action_phase": True,
                "history": []
            }
            self.current_role_pool = player_roles.copy() + center.copy()

        self._last_result = (player_roles, center)
        self.export_btn['state'] = tk.NORMAL

        # 启动按序查看流程
        self.start_sequential_viewing(player_roles, center)
        self._hide_role_selection()

    def start_game(self):
        """从用户在 listbox 中选择的角色开始一局（数量 = 玩家数 + 3），并进入按序查看流程。"""
        if not self.roles_frame_visible:
            # 首次点击用于展开角色选择
            self._show_role_selection()
            return

        sel = self._compute_role_selection()
        expected = self._expected_card_count()
        if expected < 4:
            messagebox.showerror("错误", "至少需要 1 名玩家（共 4 张牌含中央）。")
            return
        if len(sel) != expected:
            messagebox.showerror("错误", f"当前选择的牌数量为 {len(sel)} 张，应为 {expected} 张。")
            return
        try:
            self.current_role_pool = sel.copy()
            res = self.dealer.start_game_with_selection(sel)
        except Exception as e:
            messagebox.showerror("开始失败", str(e))
            return

        self._last_result = (res['player_cards'], res['center_cards'])
        self.export_btn['state'] = tk.NORMAL
        self.start_sequential_viewing(res['player_cards'], res['center_cards'])
        self._hide_role_selection()

    def display_cards(self, player_roles, center):
        """把给定的玩家牌和中央牌显示在界面上（与原有 deal 复用逻辑）。"""
        for w in self.cards_frame.winfo_children():
            w.destroy()

        roles_dir = os.path.join("resources", "roles")
        # 垂直排列：为每个玩家创建一个带标题的框，标题为“玩家N”，下方显示该角色图片
        # 选择 resampling 常量，以兼容不同 PIL 版本
        try:
            resample = Image.Resampling.LANCZOS
        except Exception:
            resample = Image.LANCZOS

        for i, role in enumerate(player_roles):
            pframe = ttk.Frame(self.cards_frame, padding=4, relief=tk.RIDGE)
            pframe.grid(row=i, column=0, padx=6, pady=6, sticky='nsew')
            ttk.Label(pframe, text=f"玩家{i+1}").pack(side=tk.TOP)
            img_label = ttk.Label(pframe)
            img_path = os.path.join(roles_dir, f"{role}.png")
            if os.path.exists(img_path):
                try:
                    img = Image.open(img_path).resize((160, 240), resample)
                    tk_img = ImageTk.PhotoImage(img)
                    img_label.config(image=tk_img)
                    self._img_cache[f"p{i}"] = tk_img
                except Exception:
                    pass
            img_label.pack(side=tk.TOP, pady=4)

        # 中央三张也使用竖排框展示标题和图片
        base_row = len(player_roles)
        for j, role in enumerate(center):
            cframe = ttk.Frame(self.cards_frame, padding=4, relief=tk.GROOVE)
            cframe.grid(row=base_row + j, column=0, padx=6, pady=6, sticky='nsew')
            ttk.Label(cframe, text=f"中央{j+1}").pack(side=tk.TOP)
            img_label = ttk.Label(cframe)
            img_path = os.path.join(roles_dir, f"{role}.png")
            if os.path.exists(img_path):
                try:
                    img = Image.open(img_path).resize((180, 270), resample)
                    tk_img = ImageTk.PhotoImage(img)
                    img_label.config(image=tk_img)
                    self._img_cache[f"c{j}"] = tk_img
                except Exception:
                    pass
            img_label.pack(side=tk.TOP, pady=4)

        self.export_btn['state'] = tk.NORMAL

    # ---- 新增: 序列查看与夜晚交互流程 ----
    def _roles_dir(self):
        # 返回资源图片目录（优先 wolf/resources/roles）
        p = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'resources', 'roles'))
        if os.path.isdir(p):
            return p
        # fallback to repo images
        p2 = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'images', 'roles'))
        return p2

    def _find_image_file(self, role):
        # 支持 png/jpg
        d = self._roles_dir()
        for ext in ('.png', '.jpg', '.jpeg'):
            p = os.path.join(d, f"{role}{ext}")
            if os.path.exists(p):
                return p
        return None

    def _setup_background(self):
        """设置窗口背景图，自动覆盖整个窗口并随大小变化缩放。"""
        # 查找背景图片
        bg_path = None
        for name in ("background.jpg", "background.png"):
            p = os.path.join(self._roles_dir(), name)
            if os.path.exists(p):
                bg_path = p
                break
        if not bg_path:
            return

        try:
            self._bg_img_orig = Image.open(bg_path)
        except Exception:
            self._bg_img_orig = None
            return

        if not self._bg_label:
            self._bg_label = tk.Label(self.root)
            self._bg_label.place(x=0, y=0, relwidth=1, relheight=1)
            self._bg_label.lower()

        def on_resize(_e=None):
            if not self._bg_img_orig:
                return
            w = max(1, self.root.winfo_width())
            h = max(1, self.root.winfo_height())
            ow, oh = self._bg_img_orig.size
            # cover: 按比例放大以覆盖窗口
            scale = max(w / ow, h / oh)
            nw, nh = int(ow * scale), int(oh * scale)
            try:
                resample = Image.Resampling.LANCZOS
            except Exception:
                resample = Image.LANCZOS
            resized = self._bg_img_orig.resize((nw, nh), resample)
            # 居中裁剪到窗口大小
            left = max(0, (nw - w) // 2)
            top = max(0, (nh - h) // 2)
            right = min(nw, left + w)
            bottom = min(nh, top + h)
            cropped = resized.crop((left, top, right, bottom))
            self._bg_img_tk = ImageTk.PhotoImage(cropped)
            self._bg_label.configure(image=self._bg_img_tk)

        # 首次渲染和大小改变时更新
        self.root.bind('<Configure>', on_resize)
        self.root.after(60, on_resize)

    def _load_placeholder_images(self):
        # 加载 card_back(140x210) 与 center_back(160x240)
        roles_dir = self._roles_dir()
        candidates = ["background.jpg", "background.png", "back.png", "card_back.png", "unknown.png"]
        placeholder = None
        for fn in candidates:
            p = os.path.join(roles_dir, fn)
            if os.path.exists(p):
                placeholder = p
                break

        try:
            resample = Image.Resampling.LANCZOS
        except Exception:
            resample = Image.LANCZOS

        if placeholder:
            try:
                b = Image.open(placeholder).resize((140, 210), resample)
                self._img_cache['card_back'] = ImageTk.PhotoImage(b)
            except Exception:
                self._img_cache['card_back'] = None
            try:
                c = Image.open(placeholder).resize((160, 240), resample)
                self._img_cache['center_back'] = ImageTk.PhotoImage(c)
            except Exception:
                self._img_cache['center_back'] = None
        else:
            self._img_cache['card_back'] = None
            self._img_cache['center_back'] = None

    def start_sequential_viewing(self, player_roles, center_roles):
        """按玩家顺序查看：初始只显示 玩家1 的占位；第一次点击显示该玩家图片与名字；第二次点击进入下一个玩家。"""
        # 保存数据
        self.player_roles = list(player_roles)
        self.center_roles = list(center_roles)
        self.player_count = len(self.player_roles)
        self.viewed = [False] * self.player_count
        self.view_index = 0

        # 初始化占位图
        self._load_placeholder_images()

        # 清空画面并创建viewer区域
        for w in self.cards_frame.winfo_children():
            w.destroy()

        self.viewer_frame = ttk.Frame(self.cards_frame, padding=8)
        self.viewer_frame.pack(fill=tk.BOTH, expand=True)

        self.viewer_title = ttk.Label(self.viewer_frame, text=f"玩家{self.view_index+1}", font=(None, 12))
        self.viewer_title.pack(side=tk.TOP)

        self.viewer_img_lbl = ttk.Label(self.viewer_frame)
        back = self._img_cache.get('card_back')
        if back:
            self.viewer_img_lbl.config(image=back)
        self.viewer_img_lbl.pack(side=tk.TOP, pady=8)

        self.viewer_name_lbl = ttk.Label(self.viewer_frame, text="")
        self.viewer_name_lbl.pack(side=tk.TOP)

        # 绑定点击行为
        self.viewer_img_lbl.bind("<Button-1>", self._on_view_click)

        # ensure dealer.session is present
        if not hasattr(self.dealer, 'session') or not self.dealer.session:
            # minimal session
            self.dealer.session = {
                'player_count': self.player_count,
                'player_cards': self.player_roles.copy(),
                'center_cards': self.center_roles.copy(),
                'viewed': [False] * self.player_count,
                'turn_index': 0,
                'action_phase': True,
                'history': []
            }

    def _on_view_click(self, event=None):
        idx = self.view_index
        if idx >= self.player_count:
            return

        # 如果未揭示，先揭示并显示名称
        if not self.viewed[idx]:
            role = self.player_roles[idx]
            img_file = self._find_image_file(role)
            try:
                if img_file:
                    try:
                        resample = Image.Resampling.LANCZOS
                    except Exception:
                        resample = Image.LANCZOS
                    img = Image.open(img_file).resize((180, 270), resample)
                    tkimg = ImageTk.PhotoImage(img)
                    self._img_cache[f'p_real_{idx}'] = tkimg
                    self.viewer_img_lbl.config(image=tkimg)
                # 显示角色名
                self.viewer_name_lbl.config(text=role)
            except Exception:
                # fallback: show role text only
                self.viewer_name_lbl.config(text=role)

            # 通知 dealer
            try:
                self.dealer.view_card(idx)
            except Exception:
                pass

            self.viewed[idx] = True
            # update session viewed
            if hasattr(self.dealer, 'session'):
                self.dealer.session['viewed'][idx] = True
            return

        # 如果已经揭示，再次点击：前往下一位玩家或全部完成
        self.view_index += 1
        if self.view_index < self.player_count:
            # 切换到下一个玩家，恢复占位图和清空名称
            self.viewer_title.config(text=f"玩家{self.view_index+1}")
            back = self._img_cache.get('card_back')
            if back:
                self.viewer_img_lbl.config(image=back)
            else:
                self.viewer_img_lbl.config(image='')
            self.viewer_name_lbl.config(text='')
        else:
            # 全部玩家查看完毕，显示中央三张（横向排列）并进入夜晚
            self.viewer_frame.destroy()
            self.on_all_viewed()

    def _show_centers_horizontal(self):
        # 在 cards_frame 中横向显示三张中央牌，初始为卡背
        for w in self.cards_frame.winfo_children():
            w.destroy()
        roles_dir = self._roles_dir()
        cframe = ttk.Frame(self.cards_frame, padding=8)
        cframe.pack()
        try:
            resample = Image.Resampling.LANCZOS
        except Exception:
            resample = Image.LANCZOS

        for j, role in enumerate(self.center_roles):
            cf = ttk.Frame(cframe, padding=4, relief=tk.GROOVE)
            cf.grid(row=0, column=j, padx=6)
            ttk.Label(cf, text=f"中央{j+1}").pack(side=tk.TOP)
            lbl = ttk.Label(cf)
            back = self._img_cache.get('center_back')
            if back:
                lbl.config(image=back)
            lbl.pack(side=tk.TOP)
            # store reference
            if not hasattr(self, 'center_widgets'):
                self.center_widgets = []
            self.center_widgets.append({'role': role, 'label': lbl, 'frame': cf})

    # 夜晚可执行的简单操作：查看中央牌、与玩家交换
    def on_all_viewed(self):
        """所有玩家查看完毕后，搭建桌面供自由查看与交换。"""
        self._setup_board_area()

    def _setup_board_area(self):
        """构建玩家和中央牌的桌面区域，可重复使用用于刷新。"""
        self._sync_from_session()

        for w in self.cards_frame.winfo_children():
            w.destroy()

        container = ttk.Frame(self.cards_frame, padding=6)
        container.pack(fill=tk.BOTH, expand=True)

        self.board_player_widgets = []
        self.center_widgets = []

        self.player_grid_frame = ttk.Frame(container, padding=6)
        self.player_grid_frame.pack(fill=tk.BOTH, expand=True)

        self.center_frame = ttk.Frame(container, padding=6)
        self.center_frame.pack(fill=tk.X)

        controls = ttk.Frame(container, padding=6)
        controls.pack(fill=tk.X)
        ttk.Button(controls, text="交换两名玩家角色", command=self._manual_swap_players).pack(side=tk.LEFT)

        self._populate_board_widgets()

    def _populate_board_widgets(self):
        for w in self.player_grid_frame.winfo_children():
            w.destroy()
        for w in self.center_frame.winfo_children():
            w.destroy()

        player_count = len(self.player_roles)
        cols = min(4, max(1, player_count))

        try:
            resample = Image.Resampling.LANCZOS
        except Exception:
            resample = Image.LANCZOS

        self.board_player_widgets = []
        for idx, role in enumerate(self.player_roles):
            r = idx // cols
            c = idx % cols
            frame = ttk.Frame(self.player_grid_frame, padding=6, relief=tk.RIDGE)
            frame.grid(row=r, column=c, padx=6, pady=6, sticky='nsew')
            ttk.Label(frame, text=f"玩家{idx+1}").pack(side=tk.TOP)
            label = ttk.Label(frame)
            back = self._img_cache.get('card_back')
            if back:
                label.config(image=back)
            label.pack(side=tk.TOP, pady=4)
            label.bind("<Button-1>", lambda e, idx=idx: self._toggle_player_card(idx))

            front = self._load_role_photo(role, (140, 210), f"board_player_{idx}", resample)

            self.board_player_widgets.append({
                "index": idx,
                "label": label,
                "front": front,
                "back": back,
                "revealed": False,
                "frame": frame
            })

        back_center = self._img_cache.get('center_back') or self._img_cache.get('card_back')
        self.center_widgets = []
        for j, role in enumerate(self.center_roles):
            frame = ttk.Frame(self.center_frame, padding=6, relief=tk.GROOVE)
            frame.grid(row=0, column=j, padx=6)
            ttk.Label(frame, text=f"中央{j+1}").pack(side=tk.TOP)
            label = ttk.Label(frame)
            if back_center:
                label.config(image=back_center)
            label.pack(side=tk.TOP, pady=4)
            front = self._load_role_photo(role, (160, 240), f"center_{j}", resample)
            widget = {
                "index": j,
                "label": label,
                "front": front,
                "back": back_center,
                "revealed": False
            }
            label.bind("<Button-1>", lambda e, idx=j: self._toggle_center_card(idx))
            self.center_widgets.append(widget)

    def _load_role_photo(self, role, size, cache_key, resample=None):
        img_path = self._find_image_file(role)
        if not img_path:
            return None
        if not resample:
            try:
                resample = Image.Resampling.LANCZOS
            except Exception:
                resample = Image.LANCZOS
        try:
            img = Image.open(img_path).resize(size, resample)
            photo = ImageTk.PhotoImage(img)
            self._img_cache[f"{cache_key}_{role}_{size[0]}x{size[1]}"] = photo
            return photo
        except Exception:
            return None

    def _toggle_player_card(self, idx):
        if idx < 0 or idx >= len(getattr(self, 'board_player_widgets', [])):
            return
        widget = self.board_player_widgets[idx]
        if widget["revealed"]:
            if widget["back"]:
                widget["label"].config(image=widget["back"])
            else:
                widget["label"].config(image='')
            widget["revealed"] = False
        else:
            if not widget["front"]:
                widget["front"] = self._load_role_photo(
                    self.player_roles[idx],
                    (140, 210),
                    f"board_player_{idx}"
                )
            if widget["front"]:
                widget["label"].config(image=widget["front"])
            widget["revealed"] = True

    def _toggle_center_card(self, idx):
        if idx < 0 or idx >= len(self.center_widgets):
            return
        widget = self.center_widgets[idx]
        if widget["revealed"]:
            if widget["back"]:
                widget["label"].config(image=widget["back"])
            widget["revealed"] = False
        else:
            if widget["front"]:
                widget["label"].config(image=widget["front"])
            widget["revealed"] = True

    def _manual_swap_players(self):
        if not getattr(self, 'board_player_widgets', None):
            return
        total = len(self.board_player_widgets)
        raw = simpledialog.askstring(
            "交换角色",
            f"输入要交换的两个玩家编号 (1-{total})，用空格或逗号分隔",
            parent=self.root
        )
        if not raw:
            return
        for sep in [',', '，']:
            raw = raw.replace(sep, ' ')
        parts = [p for p in raw.split() if p]
        if len(parts) != 2:
            messagebox.showerror("错误", "请准确输入两个不同的编号。")
            return
        try:
            idx_a, idx_b = int(parts[0]) - 1, int(parts[1]) - 1
        except ValueError:
            messagebox.showerror("错误", "请输入有效的数字编号。")
            return
        if idx_a == idx_b or any(idx < 0 or idx >= total for idx in (idx_a, idx_b)):
            messagebox.showerror("错误", "编号无效或重复，请重新输入。")
            return
        try:
            self.dealer.swap_between_players(idx_a, idx_b)
        except Exception as exc:
            messagebox.showerror("错误", str(exc))
            return
        self._refresh_board_images()
        for idx in (idx_a, idx_b):
            widget = self.board_player_widgets[idx]
            widget["revealed"] = False
            if widget["back"]:
                widget["label"].config(image=widget["back"])
            else:
                widget["label"].config(image='')
        messagebox.showinfo("完成", f"玩家{idx_a+1} 与 玩家{idx_b+1} 已交换角色。")

    def _get_role_display_name(self, role):
        normalized = WerewolfDealer.normalize_role(role)
        return ROLE_DISPLAY_NAMES.get(normalized, role)

    def _sync_from_session(self):
        session = self.dealer.get_session()
        if session:
            self.player_roles = session["player_cards"]
            self.center_roles = session["center_cards"]

    def _refresh_board_images(self):
        self._sync_from_session()
        try:
            resample = Image.Resampling.LANCZOS
        except Exception:
            resample = Image.LANCZOS
        for idx, widget in enumerate(getattr(self, 'board_player_widgets', [])):
            role = self.player_roles[idx]
            front = self._load_role_photo(role, (140, 210), f"board_player_{idx}", resample)
            widget["front"] = front
            if widget.get("revealed") and front:
                widget["label"].config(image=front)
        for j, widget in enumerate(getattr(self, 'center_widgets', [])):
            role = self.center_roles[j]
            front = self._load_role_photo(role, (160, 240), f"center_{j}", resample)
            widget["front"] = front
            if widget.get("revealed") and front:
                widget["label"].config(image=front)

    def export(self):
        if not self._last_result:
            messagebox.showinfo("导出", "当前没有可导出的局面")
            return
        player_roles, center = self._last_result
        # 简单导出到 core/output_deal.txt
        path = "core/output_deal.txt"
        with open(path, "w", encoding="utf-8") as f:
            for i, r in enumerate(player_roles, start=1):
                f.write(f"玩家{i},{r}\n")
            f.write("中央,1," + center[0] + "\n")
            f.write("中央,2," + center[1] + "\n")
            f.write("中央,3," + center[2] + "\n")
        messagebox.showinfo("导出完成", f"已导出到 {path}")


if __name__ == '__main__':
    root = tk.Tk()
    app = WerewolfApp(root)
    root.mainloop()
