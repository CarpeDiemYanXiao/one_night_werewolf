import os
import sys
import math
import random
import threading
import importlib
import time
from collections import Counter
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk
# 延迟导入 playsound，避免在未安装时触发静态检查告警


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
        # 音频目录（优先 PyInstaller 解包路径，再回退到源码相对路径）
        try:
            bundle_base = getattr(sys, '_MEIPASS', None)
        except Exception:
            bundle_base = None
        sd = None
        if bundle_base:
            cand = os.path.join(bundle_base, 'sounds')
            if os.path.isdir(cand):
                sd = cand
        if not sd:
            try:
                sd = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'sounds'))
            except Exception:
                sd = None
        self.sounds_dir = sd

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

        # 设置按钮：打开音频设置（BGM 开关与音量、提示音音量）
        self.settings_btn = ttk.Button(top, text="设置", command=self._open_settings_dialog)
        self.settings_btn.pack(side=tk.LEFT, padx=6)

    # （已移除导出结果按钮）

        self.cards_frame = ttk.Frame(frm)
        self.cards_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        # 初始处于选角主页，隐藏牌面区域，避免留白
        try:
            self.cards_frame.pack_forget()
        except Exception:
            pass

        self._last_result = None
        # 夜晚流程/结果状态
        self.night_started = False
        self.night_finished = False
        self.result_decided = False
        self._night_after_id = None  # Tk after 计时器 id，便于取消
        # 夜晚音频与继续按钮控制
        self._wake_in_progress = False
        # 夜晚背景音乐控制
        self._bgm_playing = False
        self._bgm_thread = None
        self._bgm_stop_flag = False
        self._bgm_channel = None  # pygame 专用通道
        self._bgm_sound = None
        # 音量与开关（0.0~1.0）
        self._bgm_enabled = True
        self._bgm_volume = 0.6
        self._sfx_volume = 0.9  # 角色唤醒/闭眼提示音量，仅 pygame 生效

    # === 声音播放辅助 ===
    def _get_role_sound_file(self, role: str, event: str):
        """根据角色与事件（wake/close）返回音频文件的绝对路径，若不存在则返回 None。"""
        if not self.sounds_dir:
            return None
        role_key = (role or '').lower()
        mapping = {
            'seer': {'wake': 'seer_wake.MP3', 'close': 'seer_close.MP3'},
            'robber': {'wake': 'robber_wake.MP3', 'close': 'robber_close.MP3'},
            'troublemaker': {'wake': 'troublemaker_wake.MP3', 'close': 'troublemaker_close.MP3'},
            'drunk': {'wake': 'drunk_wake.MP3', 'close': 'drunk_close.MP3'},
            'insomniac': {'wake': 'insomniac_wake.MP3', 'close': 'insomniac_close.MP3'},
            'mason': {'wake': 'mason_wake.MP3', 'close': 'mason_close.MP3'},
            'minion': {'wake': 'minion_wake.MP3', 'close': 'minion_close.MP3'},
            'doppelganger': {'wake': 'doppelganger_wake.MP3', 'close': 'doppelganger_close.MP3'},
            # 若后续补充狼人音频，可放开下方映射
            'werewolf': {'wake': 'werewolf_wake.MP3', 'close': 'werewolf_close.MP3'},
        }
        files = mapping.get(role_key)
        if not files:
            return None
        filename = files.get(event)
        if not filename:
            return None
        path = os.path.join(self.sounds_dir, filename)
        return path if os.path.exists(path) else None

    def _find_sound_file(self, name: str):
        """查找通用音频文件，支持 .MP3/.mp3 扩展名。"""
        if not self.sounds_dir:
            return None
        for ext in ('.MP3', '.mp3'):
            p = os.path.join(self.sounds_dir, f"{name}{ext}")
            if os.path.exists(p):
                return p
        return None

    def _find_bgm_file(self):
        """专门查找夜晚背景音乐文件：默认名为 'Mysterious Light.mp3'（大小写均可）。"""
        if not self.sounds_dir:
            return None
        candidates = [
            'Mysterious Light', 'mysterious light', 'Mysterious_Light', 'mysterious_light'
        ]
        for base in candidates:
            p = self._find_sound_file(base)
            if p:
                return p
        # 兜底：直接检测 sounds 目录里是否有该文件
        try:
            for fn in os.listdir(self.sounds_dir):
                if fn.lower().startswith('mysterious light') and fn.lower().endswith('.mp3'):
                    return os.path.join(self.sounds_dir, fn)
        except Exception:
            pass
        return None

    def _play_general_sound(self, name: str, on_complete=None):
        path = None
        try:
            path = self._find_sound_file(name)
        except Exception:
            path = None
        if path:
            self._play_sound_file(path, on_complete=on_complete)
        else:
            if callable(on_complete):
                try:
                    self.root.after(0, on_complete)
                except Exception:
                    pass

    def _play_sound_file(self, filepath: str, on_complete=None):
        """异步播放音频文件，播放完成后回到主线程执行回调。"""
        if not filepath or not os.path.exists(filepath):
            # 无法播放则直接回调
            if callable(on_complete):
                try:
                    self.root.after(0, on_complete)
                except Exception:
                    pass
            return

        def _init_audio_backend():
            # 选择更顺滑的后端：优先 pygame，其次 playsound
            if getattr(self, '_audio_backend', None):
                return
            backend = 'none'
            backend_obj = None
            try:
                mod = importlib.import_module('pygame')
                # 尝试初始化混音器
                try:
                    mod.mixer.init()
                    backend = 'pygame'
                    backend_obj = mod
                except Exception:
                    backend = 'none'
                    backend_obj = None
            except Exception:
                mod = None
            if backend == 'none':
                try:
                    mod2 = importlib.import_module('playsound')
                    backend = 'playsound'
                    backend_obj = mod2
                except Exception:
                    backend = 'none'
                    backend_obj = None
            self._audio_backend = backend
            self._audio_obj = backend_obj

        def _worker():
            try:
                _init_audio_backend()
                backend = getattr(self, '_audio_backend', 'none')
                obj = getattr(self, '_audio_obj', None)
                if backend == 'pygame' and obj is not None:
                    try:
                        # 使用 pygame 播放，通常比 playsound 更顺滑
                        obj.mixer.music.load(filepath)
                        try:
                            vol = float(getattr(self, '_sfx_volume', 1.0))
                            vol = max(0.0, min(1.0, vol))
                            obj.mixer.music.set_volume(vol)
                        except Exception:
                            pass
                        obj.mixer.music.play()
                        # 阻塞等待播放结束（在工作线程中，不阻塞 UI）
                        while obj.mixer.music.get_busy():
                            time.sleep(0.05)
                    except Exception:
                        pass
                elif backend == 'playsound' and obj is not None:
                    try:
                        ps = getattr(obj, 'playsound', None)
                        if callable(ps):
                            ps(filepath, block=True)
                    except Exception:
                        pass
            except Exception:
                pass
            finally:
                if callable(on_complete):
                    try:
                        self.root.after(0, on_complete)
                    except Exception:
                        pass

        threading.Thread(target=_worker, daemon=True).start()

    # === 背景音乐（夜晚阶段） ===
    def _start_bgm(self):
        """在夜晚阶段开始播放循环背景音乐（若找到 'Mysterious Light.mp3'）。"""
        if self._bgm_playing:
            return
        # 尊重开关
        if not bool(getattr(self, '_bgm_enabled', True)):
            return
        path = self._find_bgm_file()
        if not path:
            return

        # 初始化音频后端（与 _play_sound_file 使用相同的初始化逻辑）
        def _init_audio_backend():
            if getattr(self, '_audio_backend', None):
                return
            backend = 'none'
            backend_obj = None
            try:
                mod = importlib.import_module('pygame')
                try:
                    mod.mixer.init()
                    backend = 'pygame'
                    backend_obj = mod
                except Exception:
                    backend = 'none'
                    backend_obj = None
            except Exception:
                mod = None
            if backend == 'none':
                try:
                    mod2 = importlib.import_module('playsound')
                    backend = 'playsound'
                    backend_obj = mod2
                except Exception:
                    backend = 'none'
                    backend_obj = None
            self._audio_backend = backend
            self._audio_obj = backend_obj

        _init_audio_backend()
        backend = getattr(self, '_audio_backend', 'none')
        obj = getattr(self, '_audio_obj', None)

        if backend == 'pygame' and obj is not None:
            try:
                # 使用独立通道播放循环背景音乐，避免与 mixer.music 冲突
                if self._bgm_channel is None:
                    # 预留一个通道（例如 1 号），不强制通道数，自动获取一个空闲通道
                    self._bgm_channel = obj.mixer.find_channel(True)
                self._bgm_sound = obj.mixer.Sound(path)
                try:
                    vol = float(getattr(self, '_bgm_volume', 0.6))
                    vol = max(0.0, min(1.0, vol))
                    # 同时设置 sound 与通道的音量，取其一生效即可
                    self._bgm_sound.set_volume(vol)
                    if self._bgm_channel:
                        self._bgm_channel.set_volume(vol)
                except Exception:
                    pass
                self._bgm_channel.play(self._bgm_sound, loops=-1)
                self._bgm_playing = True
            except Exception:
                self._bgm_playing = False
        elif backend == 'playsound' and obj is not None:
            # 退化方案：在子线程中循环播放，停止可能需要等待当前一轮播放结束
            self._bgm_stop_flag = False
            self._bgm_playing = True

            def _loop():
                try:
                    ps = getattr(obj, 'playsound', None)
                    while self._bgm_playing and not self._bgm_stop_flag and callable(ps):
                        try:
                            ps(path, block=True)
                        except Exception:
                            break
                finally:
                    self._bgm_playing = False

            self._bgm_thread = threading.Thread(target=_loop, daemon=True)
            self._bgm_thread.start()
        else:
            # 无可用后端，忽略背景音乐
            self._bgm_playing = False

    def _stop_bgm(self, fade_ms: int = 0):
        """停止夜晚背景音乐。fade_ms>0 时在 pygame 后端进行淡出。"""
        try:
            backend = getattr(self, '_audio_backend', 'none')
            obj = getattr(self, '_audio_obj', None)
            if self._bgm_playing:
                if backend == 'pygame' and obj is not None:
                    try:
                        if self._bgm_channel:
                            if fade_ms and hasattr(self._bgm_channel, 'fadeout'):
                                self._bgm_channel.fadeout(int(fade_ms))
                            else:
                                self._bgm_channel.stop()
                    except Exception:
                        pass
                elif backend == 'playsound':
                    # playsound 无法中途打断，只能置标志并等待一轮结束
                    self._bgm_stop_flag = True
                self._bgm_playing = False
        finally:
            self._bgm_channel = None
            self._bgm_sound = None

    # === 设置对话框 ===
    def _open_settings_dialog(self):
        # 若已打开则置顶
        if hasattr(self, '_settings_win') and self._settings_win and self._settings_win.winfo_exists():
            try:
                self._settings_win.deiconify(); self._settings_win.lift(); self._settings_win.focus_force()
            except Exception:
                pass
            return

        win = tk.Toplevel(self.root)
        win.title("设置")
        win.transient(self.root)
        win.resizable(False, False)
        self._settings_win = win

        frm = ttk.Frame(win, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        # BGM 开关
        self._bgm_enabled_var = tk.BooleanVar(value=bool(getattr(self, '_bgm_enabled', True)))
        chk = ttk.Checkbutton(frm, text="启用夜晚背景音乐 (BGM)", variable=self._bgm_enabled_var, command=self._on_bgm_enabled_changed)
        chk.grid(row=0, column=0, sticky='w', pady=(0,6))

        # BGM 音量
        ttk.Label(frm, text="BGM 音量").grid(row=1, column=0, sticky='w')
        self._bgm_volume_var = tk.IntVar(value=int(getattr(self, '_bgm_volume', 0.6) * 100))
        bgm_scale = ttk.Scale(frm, from_=0, to=100, orient='horizontal', command=self._on_bgm_volume_slide)
        # ttk.Scale 的 command 传字符串，另配绑定变量以显示当前数值
        bgm_scale.set(self._bgm_volume_var.get())
        bgm_scale.grid(row=2, column=0, sticky='ew', pady=(2,10))

        # 提示音音量（SFX）
        ttk.Label(frm, text="唤醒/闭眼提示音 音量 (pygame 生效)").grid(row=3, column=0, sticky='w')
        self._sfx_volume_var = tk.IntVar(value=int(getattr(self, '_sfx_volume', 0.9) * 100))
        sfx_scale = ttk.Scale(frm, from_=0, to=100, orient='horizontal', command=self._on_sfx_volume_slide)
        sfx_scale.set(self._sfx_volume_var.get())
        sfx_scale.grid(row=4, column=0, sticky='ew', pady=(2,10))

        # 关闭按钮
        btn_close = ttk.Button(frm, text="关闭", command=win.destroy)
        btn_close.grid(row=5, column=0, sticky='e', pady=(4,0))

        # 列宽
        frm.columnconfigure(0, weight=1)

    def _on_bgm_enabled_changed(self):
        enabled = bool(self._bgm_enabled_var.get())
        self._bgm_enabled = enabled
        if not enabled:
            # 若当前在放，则停止
            self._stop_bgm()
        else:
            # 若夜晚进行中且未播放，则启动
            if getattr(self, 'night_mode', False) and not self._bgm_playing:
                self._start_bgm()

    def _on_bgm_volume_slide(self, val):
        try:
            v = float(val)
        except Exception:
            v = float(self._bgm_volume_var.get())
        v = max(0.0, min(100.0, v)) / 100.0
        self._bgm_volume = v
        # 运行期更新音量（pygame）
        try:
            backend = getattr(self, '_audio_backend', 'none')
            obj = getattr(self, '_audio_obj', None)
            if backend == 'pygame' and obj is not None and self._bgm_channel is not None:
                self._bgm_channel.set_volume(v)
                if self._bgm_sound is not None:
                    self._bgm_sound.set_volume(v)
        except Exception:
            pass

    def _on_sfx_volume_slide(self, val):
        try:
            v = float(val)
        except Exception:
            v = float(self._sfx_volume_var.get())
        v = max(0.0, min(100.0, v)) / 100.0
        self._sfx_volume = v
        # 若当前有音乐在播放（pygame.mixer.music），更新音量
        try:
            backend = getattr(self, '_audio_backend', 'none')
            obj = getattr(self, '_audio_obj', None)
            if backend == 'pygame' and obj is not None:
                obj.mixer.music.set_volume(v)
        except Exception:
            pass

    def _play_role_wake(self, role: str):
        """播放某角色唤醒音频（若有）。"""
        try:
            path = self._get_role_sound_file(role, 'wake')
        except Exception:
            path = None
        if path:
            # 开始唤醒音，期间禁用“继续”按钮，结束后统一放开
            self._wake_in_progress = True
            # 让 UI 先完成本次布局刷新，再开始播放，减少初次渲染与音频同时抢占资源导致的卡顿
            try:
                self.root.after(150, lambda p=path: self._play_sound_file(p, on_complete=self._on_wake_complete))
            except Exception:
                self._play_sound_file(path, on_complete=self._on_wake_complete)
        else:
            # 没有音频，视为已完成
            self._wake_in_progress = False
            try:
                self._on_wake_complete()
            except Exception:
                pass

    def _on_wake_complete(self):
        """唤醒音完成，允许点击‘继续’按钮。"""
        self._wake_in_progress = False
        self._refresh_continue_buttons()

    def _can_continue_now(self) -> bool:
        """根据唤醒音状态与步骤约束判断是否可继续。"""
        if self._wake_in_progress:
            return False
        st = getattr(self, 'night_action_state', {}) or {}
        # 独狼必须先看一张中央
        if st.get('require_wolf_peek') and not st.get('wolf_peeked'):
            return False
        # 强盗必须先完成一次交换
        if st.get('require_robber_swap') and not st.get('robber_swapped'):
            return False
        return True

    def _refresh_continue_buttons(self):
        btns = None
        try:
            btns = self.night_action_state.get('continue_buttons')
        except Exception:
            btns = None
        if not btns:
            return
        can = self._can_continue_now()
        for b in btns:
            try:
                b.state(["!disabled"] if can else ["disabled"])
            except Exception:
                pass

    def _create_continue_button(self, text: str = "继续"):
        """创建一个‘继续’按钮，若唤醒音未结束则默认禁用，结束后自动启用。"""
        btn = ttk.Button(self.night_buttons_frame, text=text, command=self._complete_role_and_advance)
        # 记录以便唤醒音结束后统一启用
        try:
            lst = self.night_action_state.get('continue_buttons')
            if not lst:
                self.night_action_state['continue_buttons'] = []
            self.night_action_state['continue_buttons'].append(btn)
        except Exception:
            pass
        btn.pack(side=tk.RIGHT)
        # 初始化按钮可用状态
        try:
            self._refresh_continue_buttons()
        except Exception:
            pass
        return btn

    def _disable_night_buttons(self):
        try:
            for w in self.night_buttons_frame.winfo_children():
                try:
                    w.state(["disabled"])
                except Exception:
                    pass
        except Exception:
            pass

    def _finish_role_and_then(self, callback):
        """播放当前活动角色的闭眼音频（若有），完成后执行回调。"""
        self._disable_night_buttons()
        active_role = getattr(self, 'night_active_sound_role', None) or getattr(self, 'night_current_role', None)
        try:
            path = self._get_role_sound_file(active_role, 'close')
        except Exception:
            path = None
        if path:
            self._play_sound_file(path, on_complete=callback)
        else:
            if callable(callback):
                callback()

    def _complete_role_and_advance(self):
        """当前角色完成：先播闭眼音频（若有），再进入下一步。"""
        def go_next():
            try:
                self._next_night_step()
            except Exception:
                pass
        self._finish_role_and_then(go_next)

    def _load_available_roles(self):
        """加载可选角色，返回 [{'display': str, 'internal': str}, ...]，排除狼人/保镖/background。"""
        role_dirs = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'resources', 'roles')),
            os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'images', 'roles'))
        ]
        role_dict = {}
        excluded = {"werewolf", "background", "bodyguard"}

        for internal, display in ROLE_DISPLAY_NAMES.items():
            if internal in excluded:
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
                if internal in excluded:
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
            # 注意：通过默认参数绑定当前循环的控件，避免闭包晚绑定导致作用到其他卡片
            def toggle(
                _e=None,
                var=sel,
                fr=frame,
                badge=sel_badge,
                cont=content,
                img_label=img_lbl,
                txt_label=txt,
            ):
                var.set(not var.get())
                if var.get():
                    # 保持边框宽度不变，避免触发布局抖动
                    fr.configure(relief=tk.SOLID, bd=2, bg="#DCFCE7")
                    cont.configure(bg="#DCFCE7")
                    img_label.configure(bg="#DCFCE7")
                    txt_label.configure(bg="#DCFCE7")
                    badge.place(relx=1.0, rely=0.0, anchor='ne', x=-2, y=2)
                    badge.lift()
                else:
                    fr.configure(relief=tk.RIDGE, bd=2, bg="#F9FAFB")
                    cont.configure(bg="#F9FAFB")
                    img_label.configure(bg="#F9FAFB")
                    txt_label.configure(bg="#F9FAFB")
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

    def _show_cards_area(self):
        # 确保牌面区域可见
        try:
            if not self.cards_frame.winfo_manager():
                self.cards_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        except Exception:
            pass

    def _hide_cards_area(self):
        # 隐藏牌面区域，回到“主页”状态时使用
        try:
            if self.cards_frame.winfo_manager():
                self.cards_frame.pack_forget()
        except Exception:
            pass

    def deal(self):
        """随机选角：基于可选角色池随机填充（不直接开始）。
        规则：总牌数 = 玩家人数 + 3；狼人数量使用当前选择；守夜人计作两张，其它角色最多选一次。
        """
        # 读取玩家数与狼人数量
        try:
            player_cnt = int(self.spin.get())
        except Exception:
            messagebox.showerror("错误", "请输入有效人数")
            return
        try:
            wolf_cnt = int(self.werewolf_count_var.get())
        except Exception:
            wolf_cnt = 0

        total_needed = player_cnt + 3
        if wolf_cnt < 0:
            wolf_cnt = 0
        if wolf_cnt > total_needed:
            wolf_cnt = total_needed
        # 其余牌数量
        remaining = total_needed - wolf_cnt

        # 构建可选角色池（不含狼人）
        candidates = [r['internal'] for r in self.available_roles if r['internal'] != 'werewolf']
        random.shuffle(candidates)

        picked = []
        for role in candidates:
            weight = 2 if role == 'mason' else 1
            if weight <= remaining:
                picked.append(role)
                remaining -= weight
            if remaining == 0:
                break

        if remaining != 0:
            messagebox.showerror("随机失败", "可选角色不足以组成完整牌堆，请调整狼人数量或玩家人数。")
            return

        # 先清空所有 tile 的选中高亮
        for internal, info in self.role_tiles.items():
            sel = info['selected_var']
            sel.set(False)
            fr = info['frame']; cont = info['frame'].winfo_children()[0] if info['frame'].winfo_children() else None
            img_label = info.get('image_label'); txt_label = info.get('text_label'); badge = info.get('badge_label')
            try:
                fr.configure(relief=tk.RIDGE, bd=2, bg="#F9FAFB")
                if cont: cont.configure(bg="#F9FAFB")
                if img_label: img_label.configure(bg="#F9FAFB")
                if txt_label: txt_label.configure(bg="#F9FAFB")
                if badge: badge.place_forget()
            except Exception:
                pass

        # 应用新选择（mason 代表两张，其它每个代表一张）
        for internal in picked:
            info = self.role_tiles.get(internal)
            if not info:
                continue
            info['selected_var'].set(True)
            fr = info['frame']; cont = info['frame'].winfo_children()[0] if info['frame'].winfo_children() else None
            img_label = info.get('image_label'); txt_label = info.get('text_label'); badge = info.get('badge_label')
            try:
                fr.configure(relief=tk.SOLID, bd=3, bg="#DCFCE7")
                if cont: cont.configure(bg="#DCFCE7")
                if img_label: img_label.configure(bg="#DCFCE7")
                if txt_label: txt_label.configure(bg="#DCFCE7")
                if badge: badge.place(relx=1.0, rely=0.0, anchor='ne', x=-2, y=2); badge.lift()
            except Exception:
                pass

        # 更新选角统计文本，保持选角区可见，等待用户点击“开始局”
        try:
            self.werewolf_count_var.set(str(wolf_cnt))
        except Exception:
            pass
        self._show_role_selection()
        self._hide_cards_area()
        self._update_selection_summary()

    def start_game(self):
        """从用户在 listbox 中选择的角色开始一局（数量 = 玩家数 + 3），并进入按序查看流程。"""
        if not self.roles_frame_visible:
            # 若选择区被折叠，恢复选择区（仅用于还在选角阶段的切换）
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
            res = self.dealer.start_game_with_selection(sel)
        except Exception as e:
            messagebox.showerror("开始失败", str(e))
            return

        self._last_result = (res['player_cards'], res['center_cards'])
        self.start_sequential_viewing(res['player_cards'], res['center_cards'])
        self._hide_role_selection()
        self._switch_start_to_restart()

    def _switch_start_to_restart(self):
        # 将“开始局”按钮切换为“重新开始”
        try:
            self.start_btn.config(text="重新开始", command=self._confirm_restart)
        except Exception:
            pass

    def _switch_restart_to_start(self):
        # 恢复为“开始局”
        try:
            self.start_btn.config(text="开始局", command=self.start_game)
        except Exception:
            pass

    def _confirm_restart(self):
        if messagebox.askyesno("确认", "确定要重新开始吗？当前局面将被重置。"):
            self._restart_game()

    def _restart_game(self):
        # 退出夜晚模式/聚焦模式
        try:
            if getattr(self, 'night_mode', False):
                self.night_mode = False
            if hasattr(self, 'night_panel') and self.night_panel and self.night_panel.winfo_exists():
                self.night_panel.destroy()
            if hasattr(self, 'focus_frame') and self.focus_frame and self.focus_frame.winfo_exists():
                self.focus_frame.destroy()
        except Exception:
            pass
        # 停止夜晚背景音乐
        try:
            self._stop_bgm()
        except Exception:
            pass
        # 取消夜晚计时器并重置标志
        try:
            if getattr(self, '_night_after_id', None):
                self.root.after_cancel(self._night_after_id)
        except Exception:
            pass
        self._night_after_id = None
        self.night_started = False
        self.night_finished = False
        self.result_decided = False
        self.result_text = ""
        # 清空牌桌与查看视图
        try:
            for w in self.cards_frame.winfo_children():
                try:
                    w.destroy()
                except Exception:
                    pass
        except Exception:
            pass
        # 隐藏牌面区域，避免主页顶部留白
        self._hide_cards_area()
        # 重置状态
        self._last_result = None
        # 清空 dealer 会话
        try:
            self.dealer.session = {}
        except Exception:
            pass
        # （已移除导出按钮状态切换）
        # 恢复角色选择区，按钮切回“开始局”
        self._show_role_selection()
        self._switch_restart_to_start()

    def _evaluate_and_display_result(self, target_idx: int):
        """根据翻开的目标玩家判断胜负并在界面显示简要结果。
        简化规则：
        - 若被翻开的玩家是 狼人，则好人阵营胜利（处决狼人）。
        - 否则：若场上仍有狼人，视为狼人阵营胜利；若场上无狼人，视为好人阵营胜利。
        """
        try:
            self._sync_from_session()
        except Exception:
            pass
        try:
            role_clicked = self.player_roles[target_idx]
        except Exception:
            role_clicked = None
        clicked_norm = WerewolfDealer.normalize_role(role_clicked) if role_clicked else None
        has_wolf = False
        try:
            has_wolf = any(WerewolfDealer.normalize_role(r) == 'werewolf' for r in self.player_roles)
        except Exception:
            has_wolf = False

        if clicked_norm == 'werewolf':
            result = "本局结果：好人阵营胜利（处决了狼人）。"
        else:
            result = "本局结果：狼人阵营胜利（未处决狼人）。" if has_wolf else "本局结果：好人阵营胜利（场上无狼人）。"

        name_cn = self._get_role_display_name(role_clicked) if role_clicked else "未知"
        detail = f"你翻开的是 玩家{target_idx+1}（{name_cn}）。\n{result}"
        self.result_text = result
        self.result_decided = True
        # 更新控制区提示
        try:
            self._render_night_controls()
        except Exception:
            pass
        try:
            messagebox.showinfo("结算", detail)
        except Exception:
            pass

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
        # （已移除导出按钮状态切换）

    # ---- 新增: 序列查看与夜晚交互流程 ----
    def _roles_dir(self):
        # 返回资源图片目录，优先 PyInstaller 解包路径
        try:
            bundle_base = getattr(sys, '_MEIPASS', None)
        except Exception:
            bundle_base = None
        candidates = []
        if bundle_base:
            candidates.extend([
                os.path.join(bundle_base, 'resources', 'roles'),
                os.path.join(bundle_base, 'images', 'roles'),
            ])
        # 源码路径候选
        candidates.extend([
            os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'resources', 'roles')),
            os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'images', 'roles')),
        ])
        for p in candidates:
            if os.path.isdir(p):
                return p
        # 最后回退到源码下的 images/roles，即使不存在
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'images', 'roles'))

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
        # 1) 先在角色资源目录查找（兼容打包后的资源路径）
        for name in ("background.jpg", "background.png"):
            p = os.path.join(self._roles_dir(), name)
            if os.path.exists(p):
                bg_path = p
                break
        # 2) 若未找到，再在项目 images/ 根目录查找（开发态常见放置位置）
        if not bg_path:
            try:
                images_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'images'))
                for name in ("background.jpg", "background.png"):
                    p = os.path.join(images_root, name)
                    if os.path.exists(p):
                        bg_path = p
                        break
            except Exception:
                pass
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

        # 背景缩放防抖 + 跳变检测，避免频繁重采样造成卡顿
        self._bg_resize_after_id = None
        self._bg_last_size = (-1, -1)

        def _do_bg_resize():
            self._bg_resize_after_id = None
            if not self._bg_img_orig:
                return
            w = max(1, self.root.winfo_width())
            h = max(1, self.root.winfo_height())
            # 尺寸未变化则跳过
            if self._bg_last_size == (w, h):
                return
            self._bg_last_size = (w, h)
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

        def on_resize(_e=None):
            # 取消上一次计划并在短延时后执行，合并短时间内的多次 Configure 事件
            try:
                if self._bg_resize_after_id:
                    self.root.after_cancel(self._bg_resize_after_id)
            except Exception:
                pass
            try:
                self._bg_resize_after_id = self.root.after(120, _do_bg_resize)
            except Exception:
                # Fallback: 直接执行
                _do_bg_resize()

        # 首次渲染和大小改变时更新
        self.root.bind('<Configure>', on_resize)
        self.root.after(60, _do_bg_resize)

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
        # 若角色资源目录未命中，再尝试项目 images/ 根目录的 background.*
        if not placeholder:
            try:
                images_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'images'))
                for fn in ("background.jpg", "background.png"):
                    p = os.path.join(images_root, fn)
                    if os.path.exists(p):
                        placeholder = p
                        break
            except Exception:
                pass

        try:
            resample = Image.Resampling.LANCZOS
        except Exception:
            resample = Image.LANCZOS

        # 若未找到占位图，则选用任意一张角色图片作为占位（例如 villager / werewolf）
        if not placeholder:
            try:
                for name in ("villager.png", "werewolf.png"):
                    cand = os.path.join(roles_dir, name)
                    if os.path.exists(cand):
                        placeholder = cand
                        break
                if not placeholder:
                    # 遍历目录下任意一张图片
                    for fn in os.listdir(roles_dir):
                        if os.path.splitext(fn)[1].lower() in (".png", ".jpg", ".jpeg"):
                            placeholder = os.path.join(roles_dir, fn)
                            break
            except Exception:
                placeholder = None

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
        # 显示牌面区域
        self._show_cards_area()
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
                # 显示角色名（中文）
                self.viewer_name_lbl.config(text=self._get_role_display_name(role))
            except Exception:
                # fallback: show role text only
                self.viewer_name_lbl.config(text=self._get_role_display_name(role))

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
        """当所有玩家完成查看后，布置桌面并进入夜晚阶段。"""
        self._setup_board_area()

    def _setup_board_area(self):
        """构建玩家和中央牌的桌面区域，可重复使用用于刷新。"""
        # 显示牌面区域
        self._show_cards_area()
        self._sync_from_session()

        for w in self.cards_frame.winfo_children():
            w.destroy()

        container = ttk.Frame(self.cards_frame, padding=6)
        container.pack(fill=tk.BOTH, expand=True)
        # 保存容器，便于进入“聚焦模式”时切换显示
        self.board_container = container

        self.board_player_widgets = []
        self.center_widgets = []

        self.player_grid_frame = ttk.Frame(container, padding=6)
        self.player_grid_frame.pack(fill=tk.BOTH, expand=True)

        self.center_frame = ttk.Frame(container, padding=6)
        self.center_frame.pack(fill=tk.X)

        controls = ttk.Frame(container, padding=6)
        controls.pack(fill=tk.X)
        self.controls_frame = controls
        # 渲染夜晚控制区（按钮或提示文本）
        self._render_night_controls()
        self._populate_board_widgets()

    def _render_night_controls(self):
        # 清空并根据状态渲染控制区域
        for w in self.controls_frame.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass
        if not getattr(self, 'night_started', False):
            # 首次未开始：提供开始按钮
            self.start_night_btn = ttk.Button(self.controls_frame, text="开始夜晚", command=self._start_guided_night)
            self.start_night_btn.pack(side=tk.LEFT, padx=(0, 8))
        else:
            # 已开始过夜晚：显示状态提示
            text = "夜晚进行中，请根据提示完成行动。" if getattr(self, 'night_mode', False) else (
                "夜晚已结束：点击一名玩家翻牌判断胜负。" if getattr(self, 'night_finished', False) and not getattr(self, 'result_decided', False) else
                (getattr(self, 'result_text', "夜晚已开始。"))
            )
            self.night_status_lbl = ttk.Label(self.controls_frame, text=text)
            self.night_status_lbl.pack(side=tk.LEFT)

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
            label.bind("<Button-1>", lambda e, idx=idx: self._on_board_player_click(idx))

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
            label.bind("<Button-1>", lambda e, idx=j: self._on_center_card_click(idx))
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

    # --- 夜晚引导：点击包装 ---
    def _on_board_player_click(self, idx, event=None):
        # 夜晚进行中：交给夜晚处理
        if getattr(self, 'night_mode', False):
            self._night_handle_player_click(idx)
            return
        # 夜晚已结束且尚未判定结果：点击视为处决翻牌并判断胜负
        if getattr(self, 'night_finished', False) and not getattr(self, 'result_decided', False):
            # 翻开该玩家牌
            if 0 <= idx < len(getattr(self, 'board_player_widgets', [])):
                widget = self.board_player_widgets[idx]
                if not widget.get("front"):
                    widget["front"] = self._load_role_photo(self.player_roles[idx], (140, 210), f"board_player_{idx}")
                if widget.get("front"):
                    widget["label"].config(image=widget["front"])
                    widget["revealed"] = True
            # 判定并显示结果
            self._evaluate_and_display_result(idx)
            return
        self._toggle_player_card(idx)

    def _on_center_card_click(self, idx, event=None):
        if getattr(self, 'night_mode', False):
            self._night_handle_center_click(idx)
            return
        self._toggle_center_card(idx)

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

    def _auto_night(self):
        """调用发牌引擎的自动夜晚，刷新桌面并弹出简要摘要。"""
        try:
            log = self.dealer.run_night_automation()
        except Exception as e:
            messagebox.showerror("自动夜晚失败", str(e))
            return
        # 刷新本地缓存并更新图片
        self._sync_from_session()
        self._refresh_board_images()

        # 摘要仅显示有状态变化的动作
        summaries = []
        for item in log:
            r = item.get("role")
            if r == "robber" and "swapped_with" in item:
                summaries.append(f"强盗{item['robber']+1} 与 玩家{item['swapped_with']+1} 交换")
            elif r == "troublemaker" and "swapped" in item:
                a, b = item["swapped"]
                summaries.append(f"捣蛋鬼{item['troublemaker']+1} 交换 玩家{a+1} 与 玩家{b+1}")
            elif r == "drunk" and "center_index" in item:
                summaries.append(f"酒鬼{item['drunk']+1} 与 中央{item['center_index']+1} 交换")
        if not summaries:
            summaries.append("本夜无牌面变化（或仅查看类行动）")
        messagebox.showinfo("夜晚完成", "\n".join(summaries))

    # === 引导式夜晚 ===
    def _start_guided_night(self):
        self.night_mode = True
        self.night_started = True
        self.night_finished = False
        self.result_decided = False
        # 隐藏“开始夜晚”按钮，改为状态提示
        try:
            if hasattr(self, 'start_night_btn') and self.start_night_btn and self.start_night_btn.winfo_exists():
                self.start_night_btn.pack_forget()
        except Exception:
            pass
        try:
            self._render_night_controls()
        except Exception:
            pass
        self.night_steps = self.dealer.get_night_steps()
        self.night_step_idx = 0
        # 构建夜晚面板
        if hasattr(self, 'night_panel') and self.night_panel and self.night_panel.winfo_exists():
            self.night_panel.destroy()
        self.night_panel = ttk.Labelframe(self.cards_frame, text="夜晚阶段", padding=6)
        self.night_panel.pack(fill=tk.X, padx=6, pady=6)
        self.night_text = ttk.Label(self.night_panel, text="")
        self.night_text.pack(side=tk.LEFT)
        self.night_countdown_var = tk.StringVar(value="15")
        self.night_countdown_lbl = ttk.Label(self.night_panel, textvariable=self.night_countdown_var)
        self.night_countdown_lbl.pack(side=tk.RIGHT)
        self.night_buttons_frame = ttk.Frame(self.night_panel)
        self.night_buttons_frame.pack(fill=tk.X, pady=(6,0))
        # 启动夜晚背景音乐
        try:
            self._start_bgm()
        except Exception:
            pass
        # 播放夜晚开始提示，结束后再启动第一步
        try:
            self._play_general_sound('night_start', on_complete=self._run_night_step)
        except Exception:
            self._run_night_step()

    def _run_night_step(self):
        # 清理上一轮的动态按钮
        for w in self.night_buttons_frame.winfo_children():
            w.destroy()
        self.night_click_mode = None
        self.night_action_state = {}
        # 倒计时 15 秒（重置并取消旧的计时器）
        try:
            if getattr(self, '_night_after_id', None):
                self.root.after_cancel(self._night_after_id)
        except Exception:
            pass
        self._night_after_id = None
        self.night_remaining = 15
        self._night_tick()

        if self.night_step_idx >= len(self.night_steps):
            self.night_text.config(text="夜晚结束。")
            end_btn = ttk.Button(self.night_buttons_frame, text="结束夜晚", command=self._end_guided_night)
            try:
                end_btn.state(["disabled"])  # 夜晚结束语音未播完前不允许点击
            except Exception:
                pass
            end_btn.pack(side=tk.LEFT)
            # 夜晚结束时先淡出/停止背景音乐，再播放结束提示音
            try:
                self._stop_bgm(fade_ms=800)
            except Exception:
                pass
            # 播放夜晚结束提示音，结束后放开按钮
            def _enable_end():
                try:
                    end_btn.state(["!disabled"])
                except Exception:
                    pass
            try:
                self._play_general_sound('night_over', on_complete=_enable_end)
            except Exception:
                _enable_end()
            return

        step = self.night_steps[self.night_step_idx]
        role = step.get('role')
        players = step.get('players', [])
        self.night_current_role = role
        # 当前活动角色用于声音播报
        self.night_active_sound_role = role

        # 进入聚焦模式，仅呈现与该角色相关的卡片
        self._enter_focus_mode()
        # 播放唤醒语音（若有）
        try:
            self._play_role_wake(self.night_active_sound_role)
        except Exception:
            pass

        if role == 'doppelganger':
            # 化身幽灵：选择一名其他玩家，查看并复制其角色
            dg_indices = players  # 可能有多个化身幽灵，通常为1
            selectable_players = [i for i in range(len(self.player_roles)) if i not in dg_indices]
            self.night_text.config(text="化身幽灵：请选择一名其他玩家查看并复制其角色。选择后点击‘确认复制’。")
            self._focus_show_players(selectable_players, on_click=lambda i: self._dg_select_target(i))
            btn = ttk.Button(self.night_buttons_frame, text="确认复制", command=self._dg_confirm_copy)
            btn.state(["disabled"])  # 未选择前禁用
            self.night_action_state['dg_confirm_btn'] = btn
            self.night_action_state['dg_player_indices'] = dg_indices
            self.night_action_state['dg_target'] = None
            self.night_action_state['dg_copied_role'] = None
            btn.pack(side=tk.LEFT)
        elif role == 'werewolf':
            if len(players) == 1:
                self.night_text.config(text="狼人：你为独狼，可查看中央任意一张牌。点击一张中央牌后仅展示该牌，随后点击继续。")
                # 独狼需要先查看一张中央
                self.night_action_state['require_wolf_peek'] = True
                self.night_action_state['wolf_peeked'] = False
                # 只显示中央三张（点击后标记已查看并刷新继续按钮）
                self._focus_show_centers([0,1,2], on_click=lambda j: self._werewolf_single_peek(j))
                self._create_continue_button()
            else:
                self.night_text.config(text="狼人：请互相确认身份（提示模式）。")
                self._create_continue_button()
        elif role == 'minion':
            self.night_text.config(text="爪牙：请确认场上有哪些狼人（提示模式）。")
            self._create_continue_button()
        elif role == 'mason':
            self.night_text.config(text="守夜人：两位守夜人请互相确认身份。")
            self._create_continue_button()
        elif role == 'seer':
            self.night_text.config(text="预言家：请选择‘查看两张中央’或‘查看一名玩家’，完成操作后将出现‘继续’按钮。");
            # 先仅显示两种行动按钮，不显示“继续”；选择后隐藏行动按钮
            btn_center = ttk.Button(self.night_buttons_frame, text="查看两张中央", command=self._seer_mode_center)
            btn_center.pack(side=tk.LEFT)
            btn_player = ttk.Button(self.night_buttons_frame, text="查看一名玩家", command=self._seer_mode_player)
            btn_player.pack(side=tk.LEFT)
            self.night_action_state['seer_btns'] = [btn_center, btn_player]
        elif role == 'robber':
            r_idx = players[0] if players else None
            if r_idx is not None:
                self.night_action_state['robber'] = r_idx
                # 强盗必须先完成一次交换
                self.night_action_state['require_robber_swap'] = True
                self.night_action_state['robber_swapped'] = False
                self.night_text.config(text=f"强盗：玩家{r_idx+1}，请选择一名其他玩家交换。单击目标后，仅展示其牌面，然后点击继续。")
                # 展示除强盗本人外的玩家卡
                other_indices = [i for i in range(len(self.player_roles)) if i != r_idx]
                self._focus_show_players(other_indices, on_click=lambda i: self._robber_choose_target_and_show(i))
                self._create_continue_button()
            else:
                self.night_text.config(text="强盗：未找到强盗（提示模式）。")
                self._create_continue_button()
        elif role == 'troublemaker':
            t_idx = players[0] if players else None
            if t_idx is not None:
                self.night_action_state['tm'] = t_idx
                self.night_action_state['sel'] = []
                self.night_text.config(text=f"捣蛋鬼：玩家{t_idx+1}，请选择两名其他玩家交换。再次点击已选卡可取消选择。点击‘确认交换’生效。")
                # 不能选择自己
                other_indices = [i for i in range(len(self.player_roles)) if i != t_idx]
                self._focus_show_players(other_indices, on_click=lambda i: self._tm_toggle_select(i), allow_self=False)
                btn = ttk.Button(self.night_buttons_frame, text="确认交换", command=self._tm_confirm_swap)
                btn.state(["disabled"])  # 至少两张才启用
                self.night_action_state['tm_confirm_btn'] = btn
                btn.pack(side=tk.LEFT)
            else:
                self.night_text.config(text="捣蛋鬼：未找到捣蛋鬼（提示模式）。")
                self._create_continue_button()
        elif role == 'drunk':
            d_idx = players[0] if players else None
            if d_idx is not None:
                self.night_action_state['drunk'] = d_idx
                self.night_action_state['center_sel'] = None
                self.night_text.config(text=f"酒鬼：玩家{d_idx+1}，请选择一张中央牌进行交换（不展示新牌）。选择后点击‘确认交换’。")
                self._focus_show_centers([0,1,2], on_click=lambda j: self._drunk_select_center(j))
                btn = ttk.Button(self.night_buttons_frame, text="确认交换", command=self._drunk_confirm_swap)
                btn.state(["disabled"])  # 未选择中心牌前禁用
                self.night_action_state['drunk_confirm_btn'] = btn
                btn.pack(side=tk.LEFT)
            else:
                self.night_text.config(text="酒鬼：未找到酒鬼（提示模式）。")
                self._create_continue_button()
        elif role == 'insomniac':
            i_idx = players[0] if players else None
            if i_idx is not None:
                self.night_text.config(text=f"失眠者：玩家{i_idx+1}，查看你当前的牌，然后点击继续。")
                # 仅展示该玩家当前牌
                self._focus_show_single_role(self.player_roles[i_idx], title=f"玩家{i_idx+1}")
                self._create_continue_button()
            else:
                self.night_text.config(text="失眠者：未找到失眠者（提示模式）。")
                self._create_continue_button()

    def _night_set_mode(self, mode: str):
        self.night_click_mode = mode

    def _night_tick(self):
        if not getattr(self, 'night_mode', False):
            return
        try:
            self.night_countdown_var.set(str(self.night_remaining))
        except Exception:
            pass
        if self.night_remaining <= 0:
            return
        self.night_remaining -= 1
        # 保存 after id，避免重复计时导致加速
        try:
            self._night_after_id = self.root.after(1000, self._night_tick)
        except Exception:
            self._night_after_id = None

    def _next_night_step(self):
        # 离开当前聚焦模块并刷新牌桌视图
        try:
            self._leave_focus_mode()
        except Exception:
            pass
        # 同步一次数据并刷新底部牌面，避免下一步看到旧图
        try:
            self._sync_from_session()
            self._refresh_board_images()
        except Exception:
            pass
        self.night_step_idx += 1
        self._run_night_step()

    def _end_guided_night(self):
        self.night_mode = False
        self.night_finished = True
        # 取消计时器
        try:
            if getattr(self, '_night_after_id', None):
                self.root.after_cancel(self._night_after_id)
        except Exception:
            pass
        self._night_after_id = None
        # 停止背景音乐
        try:
            self._stop_bgm()
        except Exception:
            pass
        if hasattr(self, 'night_panel') and self.night_panel and self.night_panel.winfo_exists():
            self.night_panel.destroy()
        # 更新控制区提示
        try:
            self._render_night_controls()
        except Exception:
            pass

    # === 聚焦模式（每个角色独立模块的卡片视图） ===
    def _enter_focus_mode(self):
        # 隐藏原有牌桌
        try:
            self.player_grid_frame.pack_forget()
            self.center_frame.pack_forget()
            self.controls_frame.pack_forget()
        except Exception:
            pass
        if hasattr(self, 'focus_frame') and self.focus_frame and self.focus_frame.winfo_exists():
            self.focus_frame.destroy()
        self.focus_frame = tk.Frame(self.board_container, bg="#111")
        self.focus_frame.pack(fill=tk.BOTH, expand=True)
        self.focus_widgets = []

    def _leave_focus_mode(self):
        # 销毁聚焦视图，恢复牌桌
        if hasattr(self, 'focus_frame') and self.focus_frame and self.focus_frame.winfo_exists():
            self.focus_frame.destroy()
        try:
            self.player_grid_frame.pack(fill=tk.BOTH, expand=True)
            self.center_frame.pack(fill=tk.X)
            self.controls_frame.pack(fill=tk.X)
        except Exception:
            pass

    def _focus_clear(self):
        for w in getattr(self, 'focus_widgets', []):
            try:
                w['frame'].destroy()
            except Exception:
                pass
        self.focus_widgets = []

    def _focus_add_player_card(self, idx, on_click=None, reveal_role=None):
        frame = tk.Frame(self.focus_frame, bd=3, relief=tk.GROOVE, bg="#222")
        # 自动布局为流式网格
        row = len(self.focus_widgets) // 5
        col = len(self.focus_widgets) % 5
        frame.grid(row=row, column=col, padx=10, pady=10)
        # 玩家编号标题，便于操作
        ttk.Label(frame, text=f"玩家{idx+1}").pack(side=tk.TOP, pady=(4, 2))
        lbl = ttk.Label(frame)
        if reveal_role is None:
            back = self._img_cache.get('card_back')
            if back:
                lbl.config(image=back)
        else:
            front = self._load_role_photo(reveal_role, (160, 240), f"focus_player_{idx}")
            if front:
                lbl.config(image=front)
        lbl.pack()
        # 中文角色名（仅在 reveal_role 提供时显示）
        name_lbl = ttk.Label(frame, text=self._get_role_display_name(reveal_role) if reveal_role else "")
        if reveal_role:
            name_lbl.pack(pady=(4, 2))
        if on_click:
            lbl.bind("<Button-1>", lambda e, i=idx: on_click(i))
        self.focus_widgets.append({'frame': frame, 'label': lbl, 'name_label': name_lbl, 'type': 'player', 'index': idx, 'selected': False})

    def _focus_add_center_card(self, j, on_click=None, reveal_role=None):
        frame = tk.Frame(self.focus_frame, bd=3, relief=tk.GROOVE, bg="#222")
        row = len(self.focus_widgets) // 5
        col = len(self.focus_widgets) % 5
        frame.grid(row=row, column=col, padx=10, pady=10)
        # 中央编号标题
        ttk.Label(frame, text=f"中央{j+1}").pack(side=tk.TOP, pady=(4, 2))
        lbl = ttk.Label(frame)
        if reveal_role is None:
            img = self._img_cache.get('center_back') or self._img_cache.get('card_back')
            if img:
                lbl.config(image=img)
        else:
            front = self._load_role_photo(reveal_role, (160, 240), f"focus_center_{j}")
            if front:
                lbl.config(image=front)
        lbl.pack()
        # 中文角色名（仅在 reveal_role 提供时显示）
        name_lbl = ttk.Label(frame, text=self._get_role_display_name(reveal_role) if reveal_role else "")
        if reveal_role:
            name_lbl.pack(pady=(4, 2))
        if on_click:
            lbl.bind("<Button-1>", lambda e, k=j: on_click(k))
        self.focus_widgets.append({'frame': frame, 'label': lbl, 'name_label': name_lbl, 'type': 'center', 'index': j, 'selected': False})

    def _focus_show_players(self, indices, on_click=None, allow_self=False):
        self._focus_clear()
        for i in indices:
            self._focus_add_player_card(i, on_click=on_click)

    def _focus_show_centers(self, indices, on_click=None):
        self._focus_clear()
        for j in indices:
            self._focus_add_center_card(j, on_click=on_click)

    def _focus_show_single_role(self, role, title=None):
        self._focus_clear()
        # 展示单张放大
        frame = tk.Frame(self.focus_frame, bd=4, relief=tk.RIDGE, bg="#222")
        frame.pack(pady=10)
        if title:
            ttk.Label(frame, text=title).pack(side=tk.TOP, pady=(6, 4))
        lbl = ttk.Label(frame)
        img = self._load_role_photo(role, (200, 300), f"focus_single_{role}")
        if img:
            lbl.config(image=img)
        lbl.pack()
        # 中文角色名
        ttk.Label(frame, text=self._get_role_display_name(role)).pack(pady=(6, 2))
        self.focus_widgets.append({'frame': frame, 'label': lbl})

    # === 各角色聚焦交互的具体处理 ===
    def _focus_reveal_center_and_single(self, j):
        # 展示所点中央牌的正面，随后仅保留该牌
        role = self.center_roles[j]
        self._focus_show_single_role(role, title=f"中央{j+1}")

    def _werewolf_single_peek(self, j):
        """独狼点击一张中央进行查看，并允许继续。"""
        try:
            self._focus_reveal_center_and_single(j)
        except Exception:
            pass
        try:
            self.night_action_state['wolf_peeked'] = True
        except Exception:
            pass
        try:
            self._refresh_continue_buttons()
        except Exception:
            pass

    # 化身幽灵：选择并展示目标玩家角色
    def _dg_select_target(self, target_idx):
        try:
            role = self.player_roles[target_idx]
        except Exception:
            role = None
        if role:
            self._focus_show_single_role(role, title=f"玩家{target_idx+1}")
        self.night_action_state['dg_target'] = target_idx
        self.night_action_state['dg_copied_role'] = role
        # 启用确认按钮
        btn = self.night_action_state.get('dg_confirm_btn')
        if btn:
            try:
                btn.state(["!disabled"])  # 启用
            except Exception:
                pass

    def _dg_confirm_copy(self):
        # 确认复制后，若复制角色有夜晚行动，立即执行对应行动模块
        try:
            btn = self.night_action_state.get('dg_confirm_btn')
            if btn:
                btn.state(["disabled"])  # 防止重复点击
        except Exception:
            pass
        copied = self.night_action_state.get('dg_copied_role')
        dg_indices = self.night_action_state.get('dg_player_indices') or []
        if not copied or not dg_indices:
            # 未选择目标则直接进入下一步
            self._complete_role_and_advance()
            return
        # 可选：将复制信息写入引擎会话，供后续参考
        try:
            s = self.dealer.get_session() or {}
            s['doppelganger'] = { 'players': dg_indices, 'copied_role': copied }
            self.dealer.session = s
        except Exception:
            pass
        # 先播放化身幽灵闭眼，再进入复制角色的行动
        self._finish_role_and_then(lambda: self._run_dg_copied_role_action(copied, dg_indices))

    def _run_dg_copied_role_action(self, copied_role, dg_indices):
        """化身幽灵在复制后，立即执行所复制角色的夜晚行动（复用对应模块）。"""
        try:
            role = WerewolfDealer.normalize_role(copied_role)
        except Exception:
            role = str(copied_role) if copied_role else None
        if not role:
            self._complete_role_and_advance()
            return
        # 进入聚焦模式，渲染与该角色一致的 UI
        self._enter_focus_mode()
        # 文本提示
        try:
            cn = self._get_role_display_name(role)
        except Exception:
            cn = role
        idx = dg_indices[0] if dg_indices else None

        if role == 'seer':
            try:
                self.night_active_sound_role = role
                self._play_role_wake(role)
            except Exception:
                pass
            self.night_text.config(text=f"化身幽灵（{cn}）：请选择‘查看两张中央’或‘查看一名玩家’，完成操作后将出现‘继续’按钮。")
            btn_center = ttk.Button(self.night_buttons_frame, text="查看两张中央", command=self._seer_mode_center)
            btn_center.pack(side=tk.LEFT)
            btn_player = ttk.Button(self.night_buttons_frame, text="查看一名玩家", command=self._seer_mode_player)
            btn_player.pack(side=tk.LEFT)
            self.night_action_state['seer_btns'] = [btn_center, btn_player]
            return
        if role == 'robber' and idx is not None:
            try:
                self.night_active_sound_role = role
                self._play_role_wake(role)
            except Exception:
                pass
            self.night_action_state['robber'] = idx
            self.night_text.config(text=f"化身幽灵（强盗）：玩家{idx+1}，请选择一名其他玩家交换。单击目标后，仅展示其牌面，然后点击继续。")
            other_indices = [i for i in range(len(self.player_roles)) if i != idx]
            self._focus_show_players(other_indices, on_click=lambda i: self._robber_choose_target_and_show(i))
            self._create_continue_button()
            return
        if role == 'troublemaker' and idx is not None:
            try:
                self.night_active_sound_role = role
                self._play_role_wake(role)
            except Exception:
                pass
            self.night_action_state['tm'] = idx
            self.night_action_state['sel'] = []
            self.night_text.config(text=f"化身幽灵（捣蛋鬼）：玩家{idx+1}，请选择两名玩家交换。再次点击已选卡可取消选择。点击‘确认交换’生效。")
            self._focus_show_players(list(range(len(self.player_roles))), on_click=lambda i: self._tm_toggle_select(i), allow_self=True)
            btn = ttk.Button(self.night_buttons_frame, text="确认交换", command=self._tm_confirm_swap)
            btn.state(["disabled"])  # 至少两张才启用
            self.night_action_state['tm_confirm_btn'] = btn
            btn.pack(side=tk.LEFT)
            return
        if role == 'drunk' and idx is not None:
            try:
                self.night_active_sound_role = role
                self._play_role_wake(role)
            except Exception:
                pass
            self.night_action_state['drunk'] = idx
            self.night_action_state['center_sel'] = None
            self.night_text.config(text=f"化身幽灵（酒鬼）：玩家{idx+1}，请选择一张中央牌进行交换（不展示新牌）。选择后点击‘确认交换’。")
            self._focus_show_centers([0,1,2], on_click=lambda j: self._drunk_select_center(j))
            btn = ttk.Button(self.night_buttons_frame, text="确认交换", command=self._drunk_confirm_swap)
            btn.state(["disabled"])  # 未选择中心牌前禁用
            self.night_action_state['drunk_confirm_btn'] = btn
            btn.pack(side=tk.LEFT)
            return
        if role == 'insomniac' and idx is not None:
            try:
                self.night_active_sound_role = role
                self._play_role_wake(role)
            except Exception:
                pass
            self.night_text.config(text=f"化身幽灵（失眠者）：玩家{idx+1}，查看你当前的牌，然后点击继续。")
            self._focus_show_single_role(self.player_roles[idx], title=f"玩家{idx+1}")
            self._create_continue_button()
            return
        if role == 'werewolf':
            # 按需求：化身幽灵复制为狼人时不执行狼人操作，直接进入下一步
            self._complete_role_and_advance()
            return
        if role == 'minion':
            # 按需求：化身幽灵复制为爪牙时不执行爪牙操作，直接进入下一步
            self._complete_role_and_advance()
            return
        if role == 'mason':
            # 按需求：化身幽灵复制为守夜人时不执行守夜人操作，直接进入下一步
            self._complete_role_and_advance()
            return
        # 其它无夜晚行动或未覆盖的角色：直接进入下一步
        self._complete_role_and_advance()

    def _robber_choose_target_and_show(self, target_idx):
        r_idx = self.night_action_state.get('robber')
        if r_idx is None or target_idx == r_idx:
            return
        # 先记录目标当下牌面用于展示
        try:
            role_before = self.player_roles[target_idx]
        except Exception:
            role_before = None
        # 执行交换
        try:
            self.dealer.swap_between_players(r_idx, target_idx)
        except Exception:
            pass
        self._sync_from_session()
        # 仅展示目标牌（按需求展示其角色）
        if role_before:
            self._focus_show_single_role(role_before, title=f"玩家{target_idx+1}")
        else:
            self._focus_clear()
        # 标记强盗动作已完成，允许继续
        try:
            self.night_action_state['robber_swapped'] = True
            self._refresh_continue_buttons()
        except Exception:
            pass

    def _tm_toggle_select(self, idx):
        sel = self.night_action_state.get('sel', [])
        # 查找对应focus部件
        widget = None
        for w in self.focus_widgets:
            if w.get('type') == 'player' and w.get('index') == idx:
                widget = w
                break
        if not widget:
            return
        if idx in sel:
            sel.remove(idx)
            try:
                widget['frame'].config(bg="#222")
            except Exception:
                pass
        else:
            sel.append(idx)
            try:
                widget['frame'].config(bg="#2e7d32")  # 选中高亮
            except Exception:
                pass
        # 最多保留两个
        if len(sel) > 2:
            # 移除最早的一个选中并还原其颜色
            drop = sel.pop(0)
            for w in self.focus_widgets:
                if w.get('type') == 'player' and w.get('index') == drop:
                    try:
                        w['frame'].config(bg="#222")
                    except Exception:
                        pass
                    break
        self.night_action_state['sel'] = sel
        # 更新确认按钮可用性
        btn = self.night_action_state.get('tm_confirm_btn')
        if btn:
            if len(sel) == 2:
                try:
                    btn.state(["!disabled"])  # 启用
                except Exception:
                    pass
            else:
                try:
                    btn.state(["disabled"])  # 禁用
                except Exception:
                    pass

    def _tm_confirm_swap(self):
        sel = self.night_action_state.get('sel', [])
        if len(sel) != 2:
            return
        a, b = sel[0], sel[1]
        try:
            self.dealer.swap_between_players(a, b)
        except Exception:
            pass
        self._sync_from_session()
        # 交换完成后立即结束该角色回合
        try:
            btn = self.night_action_state.get('tm_confirm_btn')
            if btn:
                btn.state(["disabled"])  # 防止重复点击
        except Exception:
            pass
        self._complete_role_and_advance()

    def _drunk_select_center(self, j):
        # 高亮所选中心牌
        self.night_action_state['center_sel'] = j
        for w in self.focus_widgets:
            if w.get('type') == 'center':
                try:
                    w['frame'].config(bg="#222")
                except Exception:
                    pass
        for w in self.focus_widgets:
            if w.get('type') == 'center' and w.get('index') == j:
                try:
                    w['frame'].config(bg="#2e7d32")
                except Exception:
                    pass
                break
        btn = self.night_action_state.get('drunk_confirm_btn')
        if btn:
            try:
                btn.state(["!disabled"])  # 启用
            except Exception:
                pass

    def _drunk_confirm_swap(self):
        d_idx = self.night_action_state.get('drunk')
        j = self.night_action_state.get('center_sel')
        if d_idx is None or j is None:
            return
        try:
            self.dealer.swap_with_center(d_idx, j)
        except Exception:
            pass
        self._sync_from_session()
        # 交换完成后立即结束该角色回合
        try:
            btn = self.night_action_state.get('drunk_confirm_btn')
            if btn:
                btn.state(["disabled"])  # 防止重复点击
        except Exception:
            pass
        self._complete_role_and_advance()

    # 预言家子模式
    def _seer_mode_center(self):
        # 隐藏行动按钮
        for b in self.night_action_state.get('seer_btns', []) or []:
            try:
                b.destroy()
            except Exception:
                pass
        # 移除可能残留的继续按钮
        btnc = self.night_action_state.get('seer_continue_btn')
        if btnc:
            try:
                btnc.destroy()
            except Exception:
                pass
            self.night_action_state['seer_continue_btn'] = None

        self.night_action_state['seer_center_remaining'] = 2
        self._focus_show_centers([0,1,2], on_click=self._seer_reveal_center)

    def _seer_reveal_center(self, j):
        remain = self.night_action_state.get('seer_center_remaining', 0)
        if remain <= 0:
            return
        # 将该中心牌翻为正面
        for w in self.focus_widgets:
            if w.get('type') == 'center' and w.get('index') == j:
                role = self.center_roles[j]
                front = self._load_role_photo(role, (160, 240), f"focus_center_{j}")
                if front:
                    w['label'].config(image=front)
                # 同步显示中文角色名
                name_lbl = w.get('name_label')
                if name_lbl is not None:
                    try:
                        name_lbl.config(text=self._get_role_display_name(role))
                        if not name_lbl.winfo_ismapped():
                            name_lbl.pack(pady=(4, 2))
                    except Exception:
                        pass
                break
        remain -= 1
        self.night_action_state['seer_center_remaining'] = remain
        # 当完成两张中央的查看后，才出现“继续”按钮
        if remain <= 0 and not self.night_action_state.get('seer_continue_btn'):
            btnc = self._create_continue_button()
            self.night_action_state['seer_continue_btn'] = btnc

    def _seer_mode_player(self):
        # 隐藏行动按钮
        for b in self.night_action_state.get('seer_btns', []) or []:
            try:
                b.destroy()
            except Exception:
                pass
        # 移除可能残留的继续按钮
        btnc = self.night_action_state.get('seer_continue_btn')
        if btnc:
            try:
                btnc.destroy()
            except Exception:
                pass
            self.night_action_state['seer_continue_btn'] = None

        self.night_action_state['seer_player_done'] = False
        self._focus_show_players(list(range(len(self.player_roles))), on_click=self._seer_reveal_player)

    def _seer_reveal_player(self, i):
        # 仅允许查看一次
        if self.night_action_state.get('seer_player_done'):
            return
        role = self.player_roles[i]
        self._focus_show_single_role(role, title=f"玩家{i+1}")
        self.night_action_state['seer_player_done'] = True
        # 完成查看后，出现“继续”按钮
        if not self.night_action_state.get('seer_continue_btn'):
            btnc = self._create_continue_button()
            self.night_action_state['seer_continue_btn'] = btnc

    # --- 夜晚点击处理 ---
    def _night_handle_player_click(self, idx):
        mode = getattr(self, 'night_click_mode', None)
        if mode == 'seer_player':
            # 临时翻开该玩家牌
            self._reveal_player_front(idx)
            # 看完允许继续点其它吗？按规则只看一名玩家，这里看一次即可
            self.night_click_mode = None
        elif mode == 'robber_target':
            r_idx = self.night_action_state.get('robber')
            if r_idx is None or idx == r_idx:
                return
            try:
                self.dealer.swap_between_players(r_idx, idx)
            except Exception:
                return
            self._refresh_board_images()
            # 可提示强盗新牌
            self._reveal_player_front(r_idx)
            self.night_click_mode = None
        elif mode == 'troublemaker':
            sel = self.night_action_state.get('sel', [])
            if idx not in sel:
                sel.append(idx)
            if len(sel) >= 2:
                a, b = sel[0], sel[1]
                try:
                    self.dealer.swap_between_players(a, b)
                except Exception:
                    pass
                self._refresh_board_images()
                self.night_click_mode = None
            self.night_action_state['sel'] = sel

    def _night_handle_center_click(self, idx):
        mode = getattr(self, 'night_click_mode', None)
        if mode == 'werewolf_center':
            # 独狼看一张中央
            self._reveal_center_front(idx)
            self.night_action_state['peeked'] = True
            self.night_click_mode = None
        elif mode == 'seer_center':
            remain = self.night_action_state.get('seer_center_remaining', 0)
            if remain <= 0:
                return
            self._reveal_center_front(idx)
            remain -= 1
            self.night_action_state['seer_center_remaining'] = remain
            if remain <= 0:
                self.night_click_mode = None
        elif mode == 'drunk_center':
            d_idx = self.night_action_state.get('drunk')
            if d_idx is None:
                return
            try:
                self.dealer.swap_with_center(d_idx, idx)
            except Exception:
                return
            self._sync_from_session()
            self._refresh_board_images()
            self.night_click_mode = None

    # 辅助：直接把某玩家牌面显示为正面
    def _reveal_player_front(self, idx):
        if not (0 <= idx < len(self.board_player_widgets)):
            return
        widget = self.board_player_widgets[idx]
        if not widget.get('front'):
            widget['front'] = self._load_role_photo(self.player_roles[idx], (140, 210), f"board_player_{idx}")
        if widget['front']:
            widget['label'].config(image=widget['front'])
            widget['revealed'] = True

    def _reveal_center_front(self, idx):
        if not (0 <= idx < len(self.center_widgets)):
            return
        widget = self.center_widgets[idx]
        if not widget.get('front'):
            widget['front'] = self._load_role_photo(self.center_roles[idx], (160, 240), f"center_{idx}")
        if widget['front']:
            widget['label'].config(image=widget['front'])
            widget['revealed'] = True

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
