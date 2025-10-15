import os
import sys
import math
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

        frm = ttk.Frame(root, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(frm)
        top.pack(fill=tk.X, pady=6)

        ttk.Label(top, text="玩家人数:").pack(side=tk.LEFT)
        # 支持 4-12 人
        self.spin = ttk.Spinbox(top, from_=4, to=12, width=5)
        self.spin.set(4)
        self.spin.pack(side=tk.LEFT, padx=6)

        # 角色选择区：左侧为可选角色，右侧为已选择列表，可重复添加（满足狼人多张/守夜人约束）
        self.available_roles = self._load_available_roles()

        self.roles_frame = ttk.LabelFrame(frm, text="选择角色（玩家人数 + 3）", padding=6)
        self.roles_frame.pack(fill=tk.BOTH, expand=False, pady=6)
        self.roles_frame_visible = True

        roles_inner = ttk.Frame(self.roles_frame)
        roles_inner.pack(fill=tk.BOTH, expand=True)

        left_panel = ttk.Frame(roles_inner)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Label(left_panel, text="可选角色").pack(anchor=tk.W)
        self.available_listbox = tk.Listbox(left_panel, selectmode=tk.SINGLE, height=10)
        for r in self.available_roles:
            self.available_listbox.insert(tk.END, r)
        self.available_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_left = ttk.Scrollbar(left_panel, orient=tk.VERTICAL, command=self.available_listbox.yview)
        self.available_listbox.config(yscrollcommand=sb_left.set)
        sb_left.pack(side=tk.RIGHT, fill=tk.Y)

        mid_panel = ttk.Frame(roles_inner, padding=6)
        mid_panel.pack(side=tk.LEFT, fill=tk.Y)
        ttk.Button(mid_panel, text="添加 →", command=self._add_selected_role).pack(pady=4)
        ttk.Button(mid_panel, text="← 移除", command=self._remove_selected_role).pack(pady=4)
        ttk.Button(mid_panel, text="清空", command=self._clear_chosen_roles).pack(pady=4)

        right_panel = ttk.Frame(roles_inner)
        right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Label(right_panel, text="已选择角色").pack(anchor=tk.W)
        self.chosen_listbox = tk.Listbox(right_panel, selectmode=tk.SINGLE, height=10)
        self.chosen_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_right = ttk.Scrollbar(right_panel, orient=tk.VERTICAL, command=self.chosen_listbox.yview)
        self.chosen_listbox.config(yscrollcommand=sb_right.set)
        sb_right.pack(side=tk.RIGHT, fill=tk.Y)

        self.chosen_roles = []
        self.selected_count_var = tk.StringVar(value="已选择: 0 张")
        ttk.Label(self.roles_frame, textvariable=self.selected_count_var).pack(anchor=tk.W, pady=(4, 0))

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
        """收集 resources/roles 或 images/roles 下的角色文件名（去扩展名）。"""
        candidates = set()
        role_dirs = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'resources', 'roles')),
            os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'images', 'roles'))
        ]
        for path in role_dirs:
            if os.path.isdir(path):
                for fn in os.listdir(path):
                    name, ext = os.path.splitext(fn)
                    if ext.lower() in ('.png', '.jpg', '.jpeg', '.gif'):
                        candidates.add(name)
        return sorted(candidates)

    def _update_selected_count(self):
        self.selected_count_var.set(f"已选择: {len(self.chosen_roles)} 张")

    def _add_selected_role(self):
        sel = self.available_listbox.curselection()
        if not sel:
            messagebox.showinfo("提示", "请先在左侧选择一个角色后再添加")
            return
        role = self.available_listbox.get(sel[0])
        self.chosen_roles.append(role)
        self.chosen_listbox.insert(tk.END, role)
        self._update_selected_count()

    def _remove_selected_role(self):
        sel = self.chosen_listbox.curselection()
        if not sel:
            messagebox.showinfo("提示", "请选择右侧已选择列表中的角色进行移除")
            return
        idx = sel[0]
        self.chosen_listbox.delete(idx)
        del self.chosen_roles[idx]
        self._update_selected_count()

    def _clear_chosen_roles(self):
        if not self.chosen_roles:
            return
        self.chosen_roles.clear()
        self.chosen_listbox.delete(0, tk.END)
        self._update_selected_count()

    def _hide_role_selection(self):
        if self.roles_frame_visible:
            self.roles_frame.pack_forget()
            self.roles_frame_visible = False

    def _show_role_selection(self):
        if not self.roles_frame_visible:
            self.roles_frame.pack(fill=tk.BOTH, expand=False, pady=6)
            self.roles_frame_visible = True
            self.available_listbox.focus_set()

    def deal(self):
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

        sel = list(self.chosen_roles)
        if not sel:
            messagebox.showerror("错误", "请先选择一些角色（玩家人数 + 3）")
            return
        # 推断玩家数 = len(sel) - 3
        if len(sel) < 4:
            messagebox.showerror("错误", "至少需要 4 张牌（最少 1 名玩家 + 3 张中央？）请至少选择 4 张。")
            return

        mason_count = sel.count("mason") + sel.count("守夜人")
        if mason_count not in (0, 2):
            messagebox.showerror("错误", "守夜人必须要么不选，要么选择两张。")
            return
        try:
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
                    img = Image.open(img_path).resize((100, 150), resample)
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
                    img = Image.open(img_path).resize((120, 180), resample)
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

    def _load_placeholder_images(self):
        # 加载 card_back(100x150) 与 center_back(120x180)
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
                b = Image.open(placeholder).resize((100, 150), resample)
                self._img_cache['card_back'] = ImageTk.PhotoImage(b)
            except Exception:
                self._img_cache['card_back'] = None
            try:
                c = Image.open(placeholder).resize((120, 180), resample)
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
                    img = Image.open(img_file).resize((100, 150), resample)
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
    def night_view_center(self, center_index):
        # show center card image and name in a dialog
        if center_index < 0 or center_index >= len(self.center_roles):
            return
        role = self.center_roles[center_index]
        img_file = self._find_image_file(role)
        # show a simple popup with image and name
        dlg = tk.Toplevel(self.root)
        dlg.title(f"查看中央{center_index+1}")
        ttk.Label(dlg, text=f"中央{center_index+1}").pack()
        lbl = ttk.Label(dlg)
        lbl.pack()
        if img_file:
            try:
                try:
                    resample = Image.Resampling.LANCZOS
                except Exception:
                    resample = Image.LANCZOS
                img = Image.open(img_file).resize((160, 240), resample)
                tkimg = ImageTk.PhotoImage(img)
                lbl.config(image=tkimg)
                # keep reference
                dlg._img = tkimg
            except Exception:
                ttk.Label(dlg, text=role).pack()
        else:
            ttk.Label(dlg, text=role).pack()

    def night_swap_with_player(self, current_idx):
        # 当前玩家与另一名玩家交换牌（询问目标玩家编号）
        target = simpledialog.askinteger("交换玩家", f"输入要与玩家{current_idx+1}交换的玩家编号 (1-{self.player_count})", minvalue=1, maxvalue=self.player_count, parent=self.root)
        if not target:
            return
        target_idx = target - 1
        if target_idx == current_idx:
            messagebox.showinfo("无效", "不能与自己交换")
            return
        try:
            self.dealer.swap_with_player(current_idx, target_idx)
        except Exception:
            pass
        # 交换本地数据并更新显示（如果已查看则显示新图）
        self.player_roles[current_idx], self.player_roles[target_idx] = self.player_roles[target_idx], self.player_roles[current_idx]
        # 如果已经揭示了任一方，更新对应的小图（这里简单刷新中心或完整界面）
        self._refresh_after_swap()

    def night_swap_with_center(self, current_idx):
        # 当前玩家与中央某张交换
        target = simpledialog.askinteger("交换中央", f"输入要与玩家{current_idx+1}交换的中央编号 (1-3)", minvalue=1, maxvalue=3, parent=self.root)
        if not target:
            return
        center_idx = target - 1
        try:
            self.dealer.swap_with_center(current_idx, center_idx)
        except Exception:
            pass
        # 交换本地数据
        self.player_roles[current_idx], self.center_roles[center_idx] = self.center_roles[center_idx], self.player_roles[current_idx]
        self._refresh_after_swap()

    def _refresh_after_swap(self):
        # 当在夜晚交换后，更新界面上的已揭示图或中央图
        # 更新中央
        if hasattr(self, 'center_widgets'):
            for j, cw in enumerate(self.center_widgets):
                role = self.center_roles[j]
                img_file = self._find_image_file(role)
                if img_file:
                    try:
                        try:
                            resample = Image.Resampling.LANCZOS
                        except Exception:
                            resample = Image.LANCZOS
                        img = Image.open(img_file).resize((120, 180), resample)
                        tkimg = ImageTk.PhotoImage(img)
                        cw['label'].config(image=tkimg)
                        self._img_cache[f'center_{j}'] = tkimg
                    except Exception:
                        pass

        # 玩家可能被揭示过，刷新那些已揭示的玩家（这里我们简单不重建查看器 UI）
        # 若需要更复杂的行为，可在此加入

    def on_all_viewed(self):
        """当所有玩家完成查看后，布置桌面并进入夜晚阶段。"""
        self.setup_board_display()
        self.start_night_phase()

    def setup_board_display(self):
        """将所有玩家和中央牌按照桌面布局摆放，中央牌独立一行。"""
        self._sync_from_session()

        for w in self.cards_frame.winfo_children():
            w.destroy()

        player_count = len(self.player_roles)
        cols = min(4, max(1, player_count))
        rows = math.ceil(player_count / cols)

        self.board_player_widgets = []

        try:
            resample = Image.Resampling.LANCZOS
        except Exception:
            resample = Image.LANCZOS

        for idx, role in enumerate(self.player_roles):
            r = idx // cols
            c = idx % cols
            frame = ttk.Frame(self.cards_frame, padding=6, relief=tk.RIDGE)
            frame.grid(row=r, column=c, padx=6, pady=6, sticky='nsew')
            ttk.Label(frame, text=f"玩家{idx+1}").pack(side=tk.TOP)
            label = ttk.Label(frame)
            back = self._img_cache.get('card_back')
            if back:
                label.config(image=back)
            label.pack(side=tk.TOP, pady=4)

            front = self._load_role_photo(role, (100, 150), f"board_player_{idx}", resample)

            self.board_player_widgets.append({
                "index": idx,
                "label": label,
                "front": front,
                "back": back,
                "revealed": False
            })

        center_frame = ttk.Frame(self.cards_frame, padding=8)
        center_frame.grid(row=rows, column=0, columnspan=cols, pady=(12, 0))

        self.center_widgets = []
        back_center = self._img_cache.get('center_back') or self._img_cache.get('card_back')
        for j, role in enumerate(self.center_roles):
            frame = ttk.Frame(center_frame, padding=6, relief=tk.GROOVE)
            frame.grid(row=0, column=j, padx=6)
            ttk.Label(frame, text=f"中央{j+1}").pack(side=tk.TOP)
            label = ttk.Label(frame)
            if back_center:
                label.config(image=back_center)
            label.pack(side=tk.TOP, pady=4)
            front = self._load_role_photo(role, (120, 180), f"center_{j}", resample)
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

    def _get_role_display_name(self, role):
        normalized = WerewolfDealer.normalize_role(role)
        return ROLE_DISPLAY_NAMES.get(normalized, role)

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
            front = self._load_role_photo(role, (100, 150), f"board_player_{idx}", resample)
            widget["front"] = front
            if widget["revealed"] and front:
                widget["label"].config(image=front)
        for j, widget in enumerate(getattr(self, 'center_widgets', [])):
            role = self.center_roles[j]
            front = self._load_role_photo(role, (120, 180), f"center_{j}", resample)
            widget["front"] = front
            if widget["revealed"] and front:
                widget["label"].config(image=front)

    def start_night_phase(self):
        self.night_steps = self.dealer.get_night_steps()
        self.night_step_index = 0
        self._setup_night_controls()
        self._show_night_step()

    def _setup_night_controls(self):
        if hasattr(self, 'night_frame') and self.night_frame.winfo_exists():
            self.night_frame.destroy()
        self.night_frame = ttk.Frame(self.root, padding=8)
        self.night_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self.night_instr_var = tk.StringVar()
        self.night_details_var = tk.StringVar()

        ttk.Label(self.night_frame, textvariable=self.night_instr_var, font=(None, 11, 'bold')).pack(anchor=tk.W)
        ttk.Label(self.night_frame, textvariable=self.night_details_var, wraplength=480, justify=tk.LEFT).pack(anchor=tk.W, pady=(4, 6))

        self.action_buttons_frame = ttk.Frame(self.night_frame)
        self.action_buttons_frame.pack(anchor=tk.W, pady=(0, 6))

        control_frame = ttk.Frame(self.night_frame)
        control_frame.pack(fill=tk.X)
        self.next_button = ttk.Button(control_frame, text="下一角色", command=self._next_night_step)
        self.next_button.pack(side=tk.RIGHT)
        ttk.Button(control_frame, text="结束夜晚", command=self._finish_night_phase).pack(side=tk.RIGHT, padx=6)

    def _clear_action_buttons(self):
        for child in self.action_buttons_frame.winfo_children():
            child.destroy()

    def _render_action_button(self, text, command):
        btn = ttk.Button(self.action_buttons_frame, text=text, command=command)
        btn.pack(side=tk.LEFT, padx=4)
        return btn

    def _show_night_step(self):
        if self.night_step_index >= len(self.night_steps):
            self._finish_night_phase()
            return

        step = self.night_steps[self.night_step_index]
        role = step["role"]
        players = step["players"]
        role_name = self._get_role_display_name(role)
        players_str = ", ".join(f"玩家{p+1}" for p in players) or "无"
        self.night_instr_var.set(f"夜晚行动：{role_name} ({players_str})")
        self.night_details_var.set("")
        self._clear_action_buttons()
        self._night_action_done = False

        if role == "werewolf":
            if len(players) > 1:
                info = f"狼人互相确认：{', '.join(f'玩家{p+1}' for p in players)}"
            else:
                info = "只有一名狼人，无法确认同伴。"
            self._mark_night_action_done(info)
        elif role == "minion":
            wolves = self.dealer.get_role_indices("werewolf", use_initial=True)
            if wolves:
                info = f"狼人是：{', '.join(f'玩家{p+1}' for p in wolves)}"
            else:
                info = "本局没有狼人。"
            self._mark_night_action_done(info)
        elif role == "mason":
            if len(players) == 2:
                info = f"守夜人互相确认：玩家{players[0]+1} 与 玩家{players[1]+1}"
            else:
                info = "守夜人未成对出现，跳过。"
            self._mark_night_action_done(info)
        elif role == "seer":
            self.night_details_var.set("预言家可以查看一名玩家，或中央任意两张牌。")
            self._render_action_button("查看玩家身份", lambda: self._seer_view_player(players))
            self._render_action_button("查看中央两张", lambda: self._seer_view_center(players))
        elif role == "robber":
            self.night_details_var.set("强盗必须与一名玩家交换并查看自己的新身份。")
            self._render_action_button("执行强盗行动", lambda: self._robber_action(players))
        elif role == "troublemaker":
            self.night_details_var.set("捣蛋鬼可以选择两名除自己外的玩家交换身份。")
            self._render_action_button("执行捣蛋鬼行动", lambda: self._troublemaker_action(players))
        elif role == "drunk":
            self.night_details_var.set("酒鬼必须与中央一张牌交换，且不能查看。")
            self._render_action_button("执行酒鬼行动", lambda: self._drunk_action(players))
        elif role == "insomniac":
            cards = [self.dealer.get_current_player_card(p) for p in players]
            info = "; ".join(
                f"玩家{players[i]+1} 当前身份：{self._get_role_display_name(cards[i])}"
                for i in range(len(players))
            )
            self._mark_night_action_done(info)
        else:
            self._mark_night_action_done("该角色夜晚无特殊行动。")

        self.next_button['state'] = tk.NORMAL if self._night_action_done else tk.DISABLED

    def _mark_night_action_done(self, info=None):
        if info:
            self.night_details_var.set(info)
        self._night_action_done = True
        self.next_button['state'] = tk.NORMAL

    def _next_night_step(self):
        if not getattr(self, '_night_action_done', False):
            messagebox.showinfo("提示", "请先完成当前角色的行动。")
            return
        self.night_step_index += 1
        self._show_night_step()

    def _finish_night_phase(self):
        if hasattr(self, 'night_frame') and self.night_frame.winfo_exists():
            self.night_instr_var.set("夜晚结束，等待白天流程。")
            self.night_details_var.set("")
            self.next_button['state'] = tk.DISABLED

    def _seer_view_player(self, players):
        target = simpledialog.askinteger(
            "预言家",
            f"输入要查看的玩家编号 (1-{len(self.player_roles)})",
            parent=self.root,
            minvalue=1,
            maxvalue=len(self.player_roles)
        )
        if not target:
            return
        card = self.dealer.reveal_player_card(target - 1)
        info = f"玩家{target} 的身份是：{self._get_role_display_name(card)}"
        self._mark_night_action_done(info)

    def _seer_view_center(self, players):
        raw = simpledialog.askstring("预言家", "输入要查看的两个中央编号 (1-3)，用空格或逗号分隔", parent=self.root)
        if not raw:
            return
        for sep in [',', '，']:
            raw = raw.replace(sep, ' ')
        parts = [p for p in raw.split() if p]
        if len(parts) != 2:
            messagebox.showerror("错误", "需要输入两个不同的编号。")
            return
        try:
            idx1, idx2 = sorted({int(parts[0]), int(parts[1])})
        except ValueError:
            messagebox.showerror("错误", "请输入有效数字。")
            return
        if idx1 < 1 or idx2 > len(self.center_roles) or idx1 == idx2:
            messagebox.showerror("错误", "编号必须在 1-3 且不能相同。")
            return
        cards = self.dealer.reveal_center_cards([idx1 - 1, idx2 - 1])
        info = f"中央{idx1}：{self._get_role_display_name(cards[0])}，中央{idx2}：{self._get_role_display_name(cards[1])}"
        self._mark_night_action_done(info)

    def _robber_action(self, players):
        robber_idx = players[0]
        target = simpledialog.askinteger(
            "强盗",
            f"选择要交换的玩家编号 (1-{len(self.player_roles)}，不可选择自己)",
            parent=self.root,
            minvalue=1,
            maxvalue=len(self.player_roles)
        )
        if not target:
            return
        if target - 1 == robber_idx:
            messagebox.showerror("错误", "强盗不能与自己交换。")
            return
        try:
            self.dealer.swap_with_player(robber_idx, target - 1)
        except Exception as exc:
            messagebox.showerror("错误", str(exc))
            return
        self._refresh_board_images()
        new_card = self.dealer.get_current_player_card(robber_idx)
        info = f"强盗与玩家{target} 交换，现在的身份是：{self._get_role_display_name(new_card)}"
        self._mark_night_action_done(info)

    def _troublemaker_action(self, players):
        tm_idx = players[0]
        raw = simpledialog.askstring(
            "捣蛋鬼",
            f"输入要交换的两名玩家编号 (1-{len(self.player_roles)}，不可包含自己)",
            parent=self.root
        )
        if not raw:
            return
        for sep in [',', '，']:
            raw = raw.replace(sep, ' ')
        parts = [p for p in raw.split() if p]
        if len(parts) != 2:
            messagebox.showerror("错误", "需要输入两名不同的玩家编号。")
            return
        try:
            idx_a, idx_b = int(parts[0]) - 1, int(parts[1]) - 1
        except ValueError:
            messagebox.showerror("错误", "请输入有效编号。")
            return
        if idx_a == idx_b or idx_a < 0 or idx_b < 0 or idx_a >= len(self.player_roles) or idx_b >= len(self.player_roles):
            messagebox.showerror("错误", "编号不合法。")
            return
        if idx_a == tm_idx or idx_b == tm_idx:
            messagebox.showerror("错误", "捣蛋鬼不能选择自己。")
            return
        try:
            self.dealer.swap_between_players(idx_a, idx_b)
        except Exception as exc:
            messagebox.showerror("错误", str(exc))
            return
        self._refresh_board_images()
        info = f"捣蛋鬼交换了玩家{idx_a+1} 与 玩家{idx_b+1} 的身份。"
        self._mark_night_action_done(info)

    def _drunk_action(self, players):
        drunk_idx = players[0]
        target = simpledialog.askinteger(
            "酒鬼",
            "选择要交换的中央编号 (1-3)",
            parent=self.root,
            minvalue=1,
            maxvalue=len(self.center_roles)
        )
        if not target:
            return
        try:
            self.dealer.swap_with_center(drunk_idx, target - 1)
        except Exception as exc:
            messagebox.showerror("错误", str(exc))
            return
        self._refresh_board_images()
        info = f"酒鬼与中央{target} 交换了身份牌。"
        self._mark_night_action_done(info)

    def show_night_controls(self):
        """在界面下方显示夜晚行动控制：当前行动玩家、下一位、结束夜晚。"""
        # 创建或复用一个控制框
        if hasattr(self, 'night_frame') and self.night_frame.winfo_exists():
            self.night_frame.destroy()
        self.night_frame = ttk.Frame(self.root, padding=8)
        self.night_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self.current_label = ttk.Label(self.night_frame, text=f"当前行动: 玩家{self.dealer.session['turn_index']+1}")
        self.current_label.pack(side=tk.LEFT, padx=6)

        next_btn = ttk.Button(self.night_frame, text="完成行动/下一位", command=self.advance_turn)
        next_btn.pack(side=tk.LEFT, padx=6)

        end_btn = ttk.Button(self.night_frame, text="结束夜晚", command=self.end_night)
        end_btn.pack(side=tk.LEFT, padx=6)

    def advance_turn(self):
        """调用 dealer.next_turn 并更新当前行动玩家标签。"""
        try:
            new_idx = self.dealer.next_turn()
        except Exception:
            # 如果 dealer 没有会话则简单递增
            if hasattr(self, 'player_widgets'):
                new_idx = (getattr(self, 'current_turn', 0) + 1) % len(self.player_widgets)
                self.current_turn = new_idx
        self.current_label.config(text=f"当前行动: 玩家{new_idx+1}")

    def end_night(self):
        """结束夜晚：移除夜晚面板并显示提示（这里只做简单处理）。"""
        if hasattr(self, 'night_frame') and self.night_frame.winfo_exists():
            self.night_frame.destroy()
        messagebox.showinfo("夜晚结束", "夜晚行动结束，进入白天结算（未实现具体判定）。")

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
