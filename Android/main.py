import os
import sys
import random
from collections import Counter
from typing import List


try:
    from plyer import tts as plyer_tts
except ImportError:  # plyer may be unavailable on some desktops
    plyer_tts = None
# Prefer SDL2 audio provider to avoid missing GStreamer plugins on Windows
os.environ.setdefault('KIVY_AUDIO', 'sdl2')

from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.factory import Factory
from kivy.properties import StringProperty
from kivy.core.text import LabelBase
from kivy.graphics import Color, Rectangle

# Ensure core path
ROOT = os.path.dirname(os.path.abspath(__file__))
# Prefer bundled core at Android/wolf, fallback to project root's wolf
_wolf_candidates = [
    os.path.abspath(os.path.join(ROOT, 'wolf')),
    os.path.abspath(os.path.join(ROOT, '..', 'wolf')),
]
WOLF_DIR = None
for _wd in _wolf_candidates:
    if os.path.isdir(_wd):
        if _wd not in sys.path:
            sys.path.insert(0, _wd)
        WOLF_DIR = _wd
        break

from core.werewolf_dealer import WerewolfDealer  # noqa: E402

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
}

ASSET_ROLE_DIRS = []
if WOLF_DIR:
    ASSET_ROLE_DIRS.append(os.path.join(WOLF_DIR, 'resources', 'roles'))
# 开发态回退到项目根的 images/roles；打包时我们会把图片复制到 Android/wolf/resources/roles
ASSET_ROLE_DIRS.append(os.path.join(ROOT, '..', 'images', 'roles'))

CARD_BACK = None
CENTER_BACK = None
SOUNDS_DIR = None


def find_image(role: str):
    role = WerewolfDealer.normalize_role(role)
    for d in ASSET_ROLE_DIRS:
        for ext in ('.png', '.jpg', '.jpeg'):
            p = os.path.join(d, f"{role}{ext}")
            if os.path.exists(p):
                return p
    return None


def find_placeholder():
    """Locate a generic card-back/background image.

    Prefer project-level images/background.jpg, then fall back to common names
    in role/resource folders.
    """
    cand = ['background.jpg', 'background.png', 'back.png', 'card_back.png', 'unknown.png']
    search_dirs = []
    # 1) Top-level images/ (project root)
    search_dirs.append(os.path.join(ROOT, '..', 'images'))
    # 2) Android assets folder (if any)
    search_dirs.append(os.path.join(ROOT, 'assets'))
    # 3) Known role/resource folders
    search_dirs.extend(ASSET_ROLE_DIRS)
    # 4) Parent folders of role/resource dirs, in case background is placed next to roles/
    for d in ASSET_ROLE_DIRS:
        parent = os.path.dirname(d)
        if parent and parent not in search_dirs:
            search_dirs.append(parent)
    # scan
    for base in search_dirs:
        if not base or not os.path.isdir(base):
            continue
        for fn in cand:
            p = os.path.join(base, fn)
            if os.path.exists(p):
                return p
    return None


class RootManager(ScreenManager):
    pass


class OneNightApp(App):
    title = '一夜终极狼人 - Android'
    current_card_image = StringProperty('')

    def build(self):
        Builder.load_file(os.path.join(ROOT, 'one_night.kv'))
        self.manager = self.root = RootManager()
        # 初始化中文字体（覆盖默认 Roboto，使全局中文可见）
        self._init_cn_font()
        self.dealer = WerewolfDealer()
        self.available_roles = self.load_available_roles()
        self.current_role_pool = []
        self.player_roles = []
        self.center_roles = []
        self.player_count = 4
        self.view_index = 0
        self.viewed = []
        # Night state
        self.night_mode = False
        self.night_steps = []
        self.night_step_idx = 0
        self.night_remaining = 0
        self._night_ev = None
        self._bgm = None
        self.night_finished = False
        self.result_decided = False
        self._action_context = None
        self._playing_sounds = []
        self._tts_engine = plyer_tts
        self._tts_available = self._tts_engine is not None
        self._last_spoken_text = None
        self._advancing_role = False

        # Add screens defined in KV
        try:
            self.manager.add_widget(Factory.RoleSelectScreen())
            self.manager.add_widget(Factory.ViewingScreen())
            self.manager.add_widget(Factory.BoardScreen())
        except Exception:
            pass
        self.init_role_select_screen()
        return self.manager

    def _init_cn_font(self):
        # 依次尝试项目内 fonts/、上级 fonts/、Windows/Android 常见中文字体
        candidates = []
        # 项目内
        for base in ['NotoSansSC-Regular', 'NotoSansCJK-Regular', 'DroidSansFallback', 'msyh', 'simhei', 'simsun']:
            for ext in ('.ttf', '.otf', '.ttc'):
                candidates.append(os.path.join(ROOT, 'fonts', base + ext))
                candidates.append(os.path.join(ROOT, '..', 'fonts', base + ext))
        # Windows 常见路径
        win_fonts = os.environ.get('WINDIR', '')
        if win_fonts:
            for fn in ['msyh.ttc', 'simhei.ttf', 'simsun.ttc']:
                candidates.append(os.path.join(win_fonts, 'Fonts', fn))
        # Android 常见路径
        candidates += [
            '/system/fonts/NotoSansSC-Regular.otf',
            '/system/fonts/NotoSansCJK-Regular.ttc',
            '/system/fonts/DroidSansFallback.ttf',
        ]
        font_path = next((p for p in candidates if os.path.exists(p)), None)
        if font_path:
            try:
                # 覆盖全局默认字体名 'Roboto'
                LabelBase.register(name='Roboto', fn_regular=font_path)
            except Exception:
                pass

    def load_available_roles(self):
        role_set = set()
        for d in ASSET_ROLE_DIRS:
            if not os.path.isdir(d):
                continue
            for fn in os.listdir(d):
                name, ext = os.path.splitext(fn)
                if ext.lower() not in ('.png', '.jpg', '.jpeg'):
                    continue
                internal = WerewolfDealer.normalize_role(name)
                role_set.add(internal)
        # remove werewolf (controlled by count)
        role_set.discard('werewolf')
        return sorted(role_set)

    def _log_action(self, text):
        # 玩家不可见行动记录，保留函数以兼容既有调用
        return

    def init_role_select_screen(self):
        sc = self.manager.get_screen('role_select')
        roles_grid: GridLayout = sc.ids.roles_grid
        roles_grid.clear_widgets()
        self.selected_set = set()
        self.role_tiles = {}
        ph = find_placeholder()
        for r in self.available_roles:
            # 容器：图片 + 文字
            box = BoxLayout(orientation='vertical', size_hint_y=None, height='260dp', padding='4dp', spacing='4dp')
            # 图片按钮
            img_path = find_image(r) or ph or ''
            img_btn = Button(size_hint_y=None, height='210dp', background_normal=img_path, background_down=img_path)
            img_btn.role_internal = r
            # 角色中文名
            name_lbl = Label(text=ROLE_DISPLAY_NAMES.get(r, r), size_hint_y=None, height='24dp')
            box.add_widget(img_btn)
            box.add_widget(name_lbl)
            # 选中高亮：使用 canvas.before 绘制底色
            with box.canvas.before:
                color_instr = Color(0.98, 0.98, 0.98, 1)
                rect = Rectangle(pos=box.pos, size=box.size)

            def _upd_rect(_inst, _val, rect=rect, box=box):
                rect.pos = box.pos
                rect.size = box.size

            box.bind(pos=_upd_rect, size=_upd_rect)

            def _on_toggle(_btn, role=r):
                self.toggle_role(_btn, role)
            img_btn.bind(on_release=_on_toggle)

            roles_grid.add_widget(box)
            self.role_tiles[r] = {
                'box': box,
                'btn': img_btn,
                'lbl': name_lbl,
                'color_instr': color_instr,
                'rect': rect,
            }
        self.update_summary()

    def toggle_role(self, btn: Button, role_internal: str = None):
        r = role_internal or getattr(btn, 'role_internal', None)
        if not r:
            return
        if r in self.selected_set:
            self.selected_set.remove(r)
            self._set_tile_selected(r, False)
        else:
            self.selected_set.add(r)
            self._set_tile_selected(r, True)
        self.update_summary()

    def _set_tile_selected(self, role: str, selected: bool):
        tile = getattr(self, 'role_tiles', {}).get(role)
        if not tile:
            return
        color_instr = tile.get('color_instr')
        if not color_instr:
            return
        if selected:
            color_instr.rgba = (0.87, 0.95, 0.89, 1)
        else:
            color_instr.rgba = (0.98, 0.98, 0.98, 1)

    def compute_selection(self, player_count: int, werewolf_count: int):
        roles = ['werewolf'] * max(0, int(werewolf_count))
        for r in sorted(self.selected_set):
            if r == 'mason':
                roles += ['mason', 'mason']
            else:
                roles.append(r)
        return roles

    def update_summary(self):
        sc = self.manager.get_screen('role_select')
        player_count = int(sc.ids.player_count.text or 0)
        werewolf_count = int(sc.ids.werewolf_count.text or 0)
        roles = self.compute_selection(player_count, werewolf_count)
        cnt = Counter(roles)
        parts = [f"{ROLE_DISPLAY_NAMES.get(k,k)}×{v}" for k, v in cnt.items()]
        sc.ids.summary_lbl.text = f"已选 {len(roles)} 张（需 {player_count+3}）：" + (', '.join(parts) if parts else '无')

    # Start from selection
    def start_game_from_selection(self, player_count_text: str, werewolf_count_text: str):
        try:
            player_count = int(player_count_text)
            werewolf_count = int(werewolf_count_text)
        except Exception:
            self.popup('错误', '人数或狼人数量不合法')
            return
        roles = self.compute_selection(player_count, werewolf_count)
        if len(roles) != player_count + 3 or player_count < 4:
            self.popup('错误', '牌数应为 玩家数+3，且玩家数在4~12')
            return
        try:
            res = self.dealer.start_game_with_selection(roles)
        except Exception as e:
            self.popup('开始失败', str(e))
            return
        self.current_role_pool = roles[:]
        self._after_dealt(res['player_cards'], res['center_cards'])

    # Re-deal same pool or random deal
    def redeal_or_random(self, player_count_text: str):
        if self.current_role_pool:
            try:
                res = self.dealer.start_game_with_selection(self.current_role_pool[:])
            except Exception as e:
                self.popup('发牌失败', str(e))
                return
            self._after_dealt(res['player_cards'], res['center_cards'])
            return
        # 随机选角：对齐桌面版逻辑
        try:
            player_count = int(player_count_text)
        except Exception:
            self.popup('错误', '请输入有效人数')
            return
        sc = self.manager.get_screen('role_select')
        try:
            wolf_cnt = int(sc.ids.werewolf_count.text or 0)
        except Exception:
            wolf_cnt = 0

        total_needed = player_count + 3
        if player_count < 1:
            self.popup('错误', '玩家人数必须至少为 1。')
            return
        if wolf_cnt < 0:
            wolf_cnt = 0
        if wolf_cnt > total_needed:
            wolf_cnt = total_needed

        remaining = total_needed - wolf_cnt
        candidates = [r for r in self.available_roles if r != 'werewolf']
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
            self.popup('随机失败', '可选角色不足以组成完整牌堆，请调整狼人数量或玩家人数。')
            return

        # 更新 UI 选中状态
        self.selected_set.clear()
        for role, tile in self.role_tiles.items():
            self._set_tile_selected(role, False)
        for role in picked:
            self.selected_set.add(role)
            self._set_tile_selected(role, True)

        sc.ids.werewolf_count.text = str(wolf_cnt)
        self.update_summary()

    def _after_dealt(self, player_roles, center_roles):
        self.player_roles = list(player_roles)
        self.center_roles = list(center_roles)
        self.player_count = len(self.player_roles)
        self.view_index = 0
        self.viewed = [False] * self.player_count
        self.manager.current = 'viewing'
        self.refresh_viewer()

    def refresh_viewer(self):
        sc = self.manager.get_screen('viewing')
        sc.ids.viewer_title.text = f"玩家{self.view_index+1}"
        self._update_viewer_image(self.get_back())
        sc.ids.viewer_name.text = ''

    def _update_viewer_image(self, path):
        self.current_card_image = path or ''
        try:
            sc = self.manager.get_screen('viewing')
            sc.ids.card_btn.source = self.current_card_image
        except Exception:
            pass

    def on_view_click(self):
        idx = self.view_index
        if idx >= self.player_count:
            return
        sc = self.manager.get_screen('viewing')
        if not self.viewed[idx]:
            role = self.player_roles[idx]
            img = find_image(role)
            self._update_viewer_image(img or self.get_back())
            try:
                norm = WerewolfDealer.normalize_role(role)
            except Exception:
                norm = role
            sc.ids.viewer_name.text = ROLE_DISPLAY_NAMES.get(norm, role)
            try:
                self.dealer.view_card(idx)
            except Exception:
                pass
            self.viewed[idx] = True
            return
        self.view_index += 1
        if self.view_index < self.player_count:
            self.refresh_viewer()
        else:
            self.build_board()

    def build_board(self):
        self.manager.current = 'board'
        board = self.manager.get_screen('board')
        pg: GridLayout = board.ids.players_grid
        cg: GridLayout = board.ids.center_grid
        pg.clear_widgets()
        cg.clear_widgets()
        # reset night panel
        self.night_mode = False
        self._night_set_status('夜晚未开始')
        self._night_set_text('所有玩家已看牌。点击“开始夜晚”进入夜晚引导。')
        board.ids.night_countdown.text = ''
        self._set_continue_enabled(False)
        try:
            board.ids.night_start_btn.disabled = False
            board.ids.night_end.disabled = True
        except Exception:
            pass
        self.night_finished = False
        self.result_decided = False

        # players
        cols = 4
        for i, role in enumerate(self.player_roles):
            box = BoxLayout(orientation='vertical', size_hint_y=None, height='220dp', padding='4dp', spacing='4dp')
            box.add_widget(Label(text=f'玩家{i+1}', size_hint_y=None, height='24dp'))
            btn = Button(size_hint_y=None, height='180dp', background_normal='', background_down='', border=(0, 0, 0, 0))
            btn.card_back = self.get_back()
            btn.card_front = find_image(role) or self.get_back()
            btn.showing = False
            if btn.card_back:
                btn.background_normal = btn.card_back
                btn.background_down = btn.card_back
            btn.bind(on_release=lambda b, idx=i: self.toggle_player_card(b, idx))
            box.add_widget(btn)
            pg.add_widget(box)

        # centers
        for j, role in enumerate(self.center_roles):
            box = BoxLayout(orientation='vertical', size_hint_y=None, height='220dp', padding='4dp', spacing='4dp')
            box.add_widget(Label(text=f'中央{j+1}', size_hint_y=None, height='24dp'))
            btn = Button(size_hint_y=None, height='180dp', background_normal='', background_down='', border=(0, 0, 0, 0))
            btn.card_back = self.get_back(True)
            btn.card_front = find_image(role) or self.get_back(True)
            btn.showing = False
            if btn.card_back:
                btn.background_normal = btn.card_back
                btn.background_down = btn.card_back
            btn.bind(on_release=lambda b, idx=j: self.toggle_center_card(b, idx))
            box.add_widget(btn)
            cg.add_widget(box)

    # ---------- Night (Guided) ----------
    def start_guided_night(self):
        if self.night_mode:
            return
        self.night_mode = True
        self._advancing_role = False
        board = self.manager.get_screen('board')
        try:
            board.ids.night_start_btn.disabled = True
            board.ids.night_end.disabled = False
        except Exception:
            pass
        # 进入聚焦模式：隐藏玩家/中央卡池，仅呈现当前角色操作区域
        try:
            self._enter_focus_mode()
        except Exception:
            pass
        self._stop_voice_playback()
        self._night_start_bgm()
        self.night_steps = self.dealer.get_night_steps() or []
        self.night_step_idx = 0
        self._night_set_status('夜晚进行中')
        self._night_set_text('夜晚开始…')
        self._log_action('夜晚开始')
        self._action_context = None
        self._play_general_sound('night_start', on_complete=self.run_night_step)

    def night_continue(self):
        # Called by Continue button; advance to next step
        self._advance_role()

    def _advance_role(self):
        if not self.night_mode:
            return
        if getattr(self, '_advancing_role', False):
            return
        self._advancing_role = True
        self._set_continue_enabled(False)
        self._cancel_night_timer()
        self._stop_voice_playback()

        def _after():
            self._advancing_role = False
            self._next_night_step()

        self._finish_role_and_then(_after)

    def end_guided_night(self):
        if not self.night_mode:
            return
        self.night_mode = False
        self._stop_bgm()
        self._cancel_night_timer()
        self._stop_voice_playback()
        self._advancing_role = False
        # 退出聚焦模式并恢复牌桌
        try:
            self._leave_focus_mode()
        except Exception:
            pass
        self._night_set_status('夜晚已结束：可自由翻牌/交换')
        self._night_set_text('')
        self._log_action('夜晚结束')
        self.night_finished = True
        self.result_decided = False
        self._action_context = None
        try:
            board = self.manager.get_screen('board')
            board.ids.night_start_btn.disabled = False
            board.ids.night_end.disabled = True
        except Exception:
            pass

    def _next_night_step(self, *_):
        self.night_step_idx += 1
        self.run_night_step()

    def run_night_step(self, *_):
        self._advancing_role = False
        self._stop_voice_playback()
        board = self.manager.get_screen('board')
        actions = board.ids.night_actions
        actions.clear_widgets()
        self._set_continue_enabled(False)
        self._cancel_night_timer()

        if self.night_step_idx >= len(self.night_steps):
            self._night_set_text('夜晚结束。请点击“结束夜晚”进入讨论阶段。')
            self._action_context = None
            self._play_general_sound('night_over')
            self._set_continue_enabled(False)
            return

        # countdown
        self.night_remaining = 20
        self._night_tick()

        step = self.night_steps[self.night_step_idx]
        role = step.get('role')
        players = step.get('players', [])
        in_center = step.get('in_center', False)
        role_players_text = self._format_players(players)
        normalized_role = WerewolfDealer.normalize_role(role) if role else role
        display_name = ROLE_DISPLAY_NAMES.get(normalized_role, role or '')
        label = display_name
        if role_players_text:
            label = f"{display_name}（{role_players_text}）"
        self._action_context = {
            'role': normalized_role or role,
            'players': players,
            'label': label,
            'display': display_name,
        }
        if label:
            self._log_action(f"{label}开始行动")
        self._play_role_wake(role)

        # Dispatch per role
        if role == 'werewolf':
            if not players:
                self._night_set_text('狼人：若在场，请互相确认身份。')
                self._set_continue_enabled(True)
            elif len(players) == 1:
                if role_players_text:
                    text = f"狼人：{role_players_text} 为独狼，可查看任意一张中央牌。"
                else:
                    text = '狼人：独狼可查看一张中央牌。'
                self._night_set_text(text)
                def on_reveal(idx, seen_role):
                    name = ROLE_DISPLAY_NAMES.get(WerewolfDealer.normalize_role(seen_role), seen_role)
                    self._log_action(f"{label}查看中央{idx+1}：{name}")
                self._night_focus_centers(peek_count=1, on_done=lambda: self._set_continue_enabled(True), on_reveal=on_reveal)
            else:
                if role_players_text:
                    text = f"狼人：{role_players_text} 请互相确认身份。"
                else:
                    text = '狼人：互相确认身份。'
                self._night_set_text(text)
                if role_players_text:
                    self._log_action(f"{label}互相确认身份")
                else:
                    self._log_action('狼人互相确认身份')
                self._set_continue_enabled(True)
        elif role == 'minion':
            if not players:
                self._night_set_text('爪牙：若在场，请默记守护对象。')
                self._set_continue_enabled(True)
                return
            wolf_idxs = [i for i, r in enumerate(self.player_roles) if WerewolfDealer.normalize_role(r) == 'werewolf']
            wolf_text = self._format_players(wolf_idxs)
            if wolf_text:
                if role_players_text:
                    text = f"爪牙：{role_players_text}，狼人有 {wolf_text}。"
                else:
                    text = f"爪牙：狼人有 {wolf_text}。"
                self._log_action(f"{label}确认狼人：{wolf_text}")
            else:
                text = f"爪牙：{role_players_text}，本局没有狼人。" if role_players_text else '爪牙：本局没有狼人。'
                self._log_action(f"{label}确认本局没有狼人")
            self._night_set_text(text)
            # 音频顺序交由 _finish_role_and_then 统一处理（wake -> [thumb] -> close）
            self._set_continue_enabled(True)
        elif role == 'mason':
            if not players:
                self._night_set_text('守夜人：若在场，请互相确认身份。')
                self._set_continue_enabled(True)
                return
            if role_players_text:
                text = f"守夜人：{role_players_text} 请互相确认身份。"
            else:
                text = '守夜人：两位守夜人互认。'
            self._night_set_text(text)
            if role_players_text:
                self._log_action(f"{label}互认身份")
            self._set_continue_enabled(True)
        elif role == 'seer':
            if not players:
                self._night_set_text('预言家：若在场，可查看两张中央或一名玩家。')
                self._set_continue_enabled(True)
                return
            if role_players_text:
                text = f"预言家：{role_players_text}，请选择“查看两张中央”或“查看一名玩家”。"
            else:
                text = '预言家：请选择“查看两张中央”或“查看一名玩家”。'
            self._night_set_text(text)
            self._night_action_buttons([
                ('查看两张中央', lambda: self._seer_mode_center()),
                ('查看一名玩家', lambda: self._seer_mode_player()),
            ])
        elif role == 'robber':
            robber = players[0] if players else None
            if robber is not None:
                text = f"强盗：玩家{robber+1}，请选择一名其他玩家交换。"
            else:
                if not players:
                    self._night_set_text('强盗：若在场，请选择一名其他玩家交换。')
                    self._set_continue_enabled(True)
                    return
                text = '强盗：请选择一名其他玩家交换。'
            self._night_set_text(text)
            self._robber_mode(robber)
        elif role == 'troublemaker':
            tm = players[0] if players else None
            if tm is not None:
                text = f"捣蛋鬼：玩家{tm+1}，请选择两名其他玩家交换。"
            else:
                if not players:
                    self._night_set_text('捣蛋鬼：若在场，请选择两名玩家交换。')
                    self._set_continue_enabled(True)
                    return
                text = '捣蛋鬼：请选择两名其他玩家交换。'
            self._night_set_text(text)
            self._troublemaker_mode(tm)
        elif role == 'drunk':
            drunk = players[0] if players else None
            if drunk is not None:
                text = f"酒鬼：玩家{drunk+1}，请选择一张中央牌交换（不展示新牌）。"
            else:
                if not players:
                    self._night_set_text('酒鬼：若在场，请与中央任意一张牌交换。')
                    self._set_continue_enabled(True)
                    return
                text = '酒鬼：请选择一张中央牌交换（不展示新牌）。'
            self._night_set_text(text)
            self._drunk_mode(drunk)
        elif role == 'insomniac':
            i_idx = players[0] if players else None
            if i_idx is not None:
                text = f"失眠者：玩家{i_idx+1}，查看你当前的牌，然后点击继续。"
            else:
                if not players:
                    self._night_set_text('失眠者：若在场，请查看你当前的牌。')
                    self._set_continue_enabled(True)
                    return
                text = '失眠者：查看你当前的牌。'
            self._night_set_text(text)
            if i_idx is not None:
                self._night_focus_single_player(i_idx)
                seen_role = self.player_roles[i_idx]
                name = ROLE_DISPLAY_NAMES.get(WerewolfDealer.normalize_role(seen_role), seen_role)
                self._log_action(f"{label}查看当前身份：{name}")
            self._set_continue_enabled(True)
        elif role == 'doppelganger':
            # 化身幽灵：选择一名其他玩家查看并复制其角色，随后执行复制角色的夜晚行动
            if not players:
                self._night_set_text('化身幽灵：若在场，请选择一名玩家复制其角色。')
                self._set_continue_enabled(True)
                return
            if role_players_text:
                text = f"化身幽灵：{role_players_text}，请选择一名其他玩家复制其角色，然后点击“确认复制”。"
            else:
                text = '化身幽灵：请选择一名其他玩家，查看并复制其角色，然后点击“确认复制”。'
            self._night_set_text(text)
            self._play_sound('doppelganger_action.MP3')
            self._dg_mode(players)
        else:
            # Unknown or no-op role
            self._set_continue_enabled(True)

    # ---- Night UI helpers ----
    def _night_set_status(self, text):
        try:
            self.manager.get_screen('board').ids.night_status.text = text
        except Exception:
            pass

    def _speak_instruction(self, text):
        if not text:
            return
        if not getattr(self, '_tts_available', False):
            return
        engine = getattr(self, '_tts_engine', None)
        if not engine:
            return
        try:
            if hasattr(engine, 'stop'):
                engine.stop()
        except Exception:
            pass
        try:
            engine.speak(text)
            self._last_spoken_text = text
        except Exception:
            self._tts_available = False

    def _night_set_text(self, text, speak=True):
        try:
            self.manager.get_screen('board').ids.night_text.text = text
        except Exception:
            pass
        if speak and getattr(self, 'night_mode', False):
            self._speak_instruction(text)

    def _format_players(self, players):
        if not players:
            return ''
        return '、'.join(f"玩家{p+1}" for p in players)

    def _current_role_label(self, fallback_role=None, fallback_players=None):
        ctx = getattr(self, '_action_context', None)
        if ctx:
            label = ctx.get('label') or ctx.get('display')
            if label:
                return label
        if fallback_role:
            name = ROLE_DISPLAY_NAMES.get(WerewolfDealer.normalize_role(fallback_role), fallback_role)
            players_text = self._format_players(fallback_players or [])
            if players_text:
                return f"{name}（{players_text}）"
            return name
        return ''

    def _night_tick(self, *_):
        if not self.night_mode:
            return
        try:
            self.manager.get_screen('board').ids.night_countdown.text = str(self.night_remaining)
        except Exception:
            pass
        if self.night_remaining <= 0:
            return
        self.night_remaining -= 1
        if self.night_remaining <= 0:
            try:
                self.manager.get_screen('board').ids.night_countdown.text = '0'
            except Exception:
                pass
            Clock.schedule_once(lambda *_: self._advance_role(), 0)
        else:
            self._night_ev = Clock.schedule_once(self._night_tick, 1)

    def _cancel_night_timer(self):
        if self._night_ev is not None:
            try:
                self._night_ev.cancel()
            except Exception:
                pass
            self._night_ev = None

    def _night_action_buttons(self, items):
        actions = self.manager.get_screen('board').ids.night_actions
        actions.clear_widgets()
        for text, cb in items:
            btn = Button(text=text, size_hint_y=None, height='40dp')
            btn.bind(on_release=lambda b, f=cb: f())
            actions.add_widget(btn)

    def _set_continue_enabled(self, enabled):
        def _apply(*_):
            try:
                screen = self.manager.get_screen('board')
                screen.ids.night_continue.disabled = not enabled
            except Exception:
                pass
        Clock.schedule_once(_apply, 0)

    def _night_buttons_box(self):
        try:
            return self.manager.get_screen('board').ids.night_buttons
        except Exception:
            return None

    def _night_focus_centers(self, peek_count=1, on_done=None, on_reveal=None):
        actions = self.manager.get_screen('board').ids.night_actions
        actions.clear_widgets()
        remaining = {'n': peek_count}
        def on_click(j):
            if remaining['n'] <= 0:
                return
            role = self.center_roles[j]
            # reveal by replacing button background
            for child in actions.children:
                pass
            if on_reveal:
                try:
                    on_reveal(j, role)
                except Exception:
                    pass
            remaining['n'] -= 1
            if remaining['n'] <= 0 and on_done:
                try:
                    on_done()
                except TypeError:
                    on_done(None)
        # build three center buttons
        for j, role in enumerate(self.center_roles):
            btn = Button(size_hint_y=None, height='180dp', background_normal=self.get_back(True), background_down='')
            front = find_image(role) or self.get_back(True)
            def bind_click(b=btn, idx=j, front_path=front):
                def handler(_):
                    # 仅当仍有剩余次数时允许翻开
                    if remaining['n'] <= 0:
                        return
                    b.background_normal = front_path
                    on_click(idx)
                b.bind(on_release=handler)
            bind_click()
            actions.add_widget(btn)

    def _night_focus_players(self, indices, on_click):
        actions = self.manager.get_screen('board').ids.night_actions
        actions.clear_widgets()
        # 使用“卡背+编号”的独立操作卡片，避免展示全局牌桌
        for idx in indices:
            box = BoxLayout(orientation='vertical', size_hint_y=None, height='220dp', padding='4dp', spacing='4dp')
            box.add_widget(Label(text=f'玩家{idx+1}', size_hint_y=None, height='24dp'))
            btn = Button(size_hint_y=None, height='180dp', background_normal=self.get_back(), background_down=self.get_back(), border=(0,0,0,0))
            btn.bind(on_release=lambda b, i=idx: on_click(i))
            box.add_widget(btn)
            actions.add_widget(box)

    def _night_focus_single_player(self, idx):
        actions = self.manager.get_screen('board').ids.night_actions
        actions.clear_widgets()
        role = self.player_roles[idx]
        img = find_image(role) or self.get_back()
        btn = Button(size_hint_y=None, height='220dp', background_normal=img, background_down='')
        actions.add_widget(btn)
        name = ROLE_DISPLAY_NAMES.get(WerewolfDealer.normalize_role(role), role)
        actions.add_widget(Label(text=f'玩家{idx+1}：{name}', size_hint_y=None, height='28dp'))

    # ---- Doppelganger (化身幽灵) ----
    def _dg_mode(self, dg_indices):
        # 选择一名不在 dg_indices 列表中的玩家作为复制目标
        self._dg_state = {'players': dg_indices[:], 'target': None, 'copied_role': None, 'confirm_btn': None}
        others = [i for i in range(self.player_count) if i not in dg_indices]
        actions = self.manager.get_screen('board').ids.night_actions
        actions.clear_widgets()
        # 点击某玩家后，展示该玩家当前牌并记录复制角色
        def on_pick(i):
            role = self.player_roles[i]
            img = find_image(role) or self.get_back()
            actions.clear_widgets()
            btn = Button(size_hint_y=None, height='220dp', background_normal=img, background_down='')
            actions.add_widget(btn)
            name = ROLE_DISPLAY_NAMES.get(WerewolfDealer.normalize_role(role), role)
            actions.add_widget(Label(text=f'玩家{i+1}：{name}', size_hint_y=None, height='28dp'))
            self._dg_state['target'] = i
            self._dg_state['copied_role'] = role
            # 启用确认按钮
            if self._dg_state.get('confirm_btn') is None:
                box = self._night_buttons_box()
                if box is not None:
                    confirm = Button(text='确认复制', size_hint_y=None, height='40dp')
                    confirm.bind(on_release=lambda *_: self._dg_confirm_copy())
                    box.add_widget(confirm)
                    self._dg_state['confirm_btn'] = confirm
        self._night_focus_players(others, on_pick)

    def _dg_confirm_copy(self):
        role = self._dg_state.get('copied_role') if hasattr(self, '_dg_state') else None
        dg_indices = self._dg_state.get('players') if hasattr(self, '_dg_state') else []
        if not role or not dg_indices:
            # 未选择目标则直接进入下一步
            self._next_night_step()
            return
        target_idx = self._dg_state.get('target') if hasattr(self, '_dg_state') else None
        # 移除确认按钮，防止重复点击
        try:
            btn = self._dg_state.get('confirm_btn')
            if btn is not None:
                box = self._night_buttons_box()
                if box is not None:
                    box.remove_widget(btn)
                self._dg_state['confirm_btn'] = None
        except Exception:
            pass
        if target_idx is not None:
            copied_name = ROLE_DISPLAY_NAMES.get(WerewolfDealer.normalize_role(role), role)
            label = self._current_role_label('doppelganger', dg_indices) or '化身幽灵'
            self._log_action(f"{label}复制了 玩家{target_idx+1}（{copied_name}）")
        # 播放化身幽灵闭眼后进入复制角色的行动
        copied = role
        self._finish_role_and_then(lambda: self._dg_run_copied_role_action(copied, dg_indices))

    def _dg_run_copied_role_action(self, copied_role, dg_indices):
        try:
            role = WerewolfDealer.normalize_role(copied_role)
        except Exception:
            role = str(copied_role) if copied_role else None
        if not role:
            self._next_night_step()
            return
        cn_name = ROLE_DISPLAY_NAMES.get(role, role)
        players_text = self._format_players(dg_indices)
        action_label = f"化身幽灵（{cn_name}）"
        if players_text:
            action_label = f"{action_label}（{players_text}）"
        self._action_context = {'role': role, 'players': dg_indices, 'label': action_label, 'display': action_label}
        self._log_action(f"{action_label}开始行动")
    # 不播放复制角色的提示音，避免暴露化身幽灵的新身份
        # 选择首个化身幽灵玩家索引作为后续行动主体（与桌面版一致的简化）
        idx = dg_indices[0] if dg_indices else None
        if role == 'seer':
            self._night_set_text('化身幽灵（预言家）：选择“查看两张中央”或“查看一名玩家”')
            self._night_action_buttons([
                ('查看两张中央', lambda: self._seer_mode_center()),
                ('查看一名玩家', lambda: self._seer_mode_player()),
            ])
            return
        if role == 'robber' and idx is not None:
            self._night_set_text(f'化身幽灵（强盗）：玩家{idx+1}，请选择一名其他玩家交换')
            self._robber_mode(idx)
            return
        if role == 'troublemaker' and idx is not None:
            self._night_set_text(f'化身幽灵（捣蛋鬼）：玩家{idx+1}，请选择两名其他玩家交换')
            self._troublemaker_mode(idx)
            return
        if role == 'drunk' and idx is not None:
            self._night_set_text(f'化身幽灵（酒鬼）：玩家{idx+1}，请选择一张中央牌交换（不展示新牌）')
            self._drunk_mode(idx)
            return
        if role == 'insomniac' and idx is not None:
            self._night_set_text(f'化身幽灵（失眠者）：玩家{idx+1}，查看你当前的牌')
            self._night_focus_single_player(idx)
            seen_role = self.player_roles[idx]
            name = ROLE_DISPLAY_NAMES.get(WerewolfDealer.normalize_role(seen_role), seen_role)
            label = self._current_role_label('insomniac', dg_indices) or action_label
            self._log_action(f"{label}查看当前身份：{name}")
            self._set_continue_enabled(True)
            return
        # werewolf/minion/mason 或其它无行动：直接允许继续
        self._set_continue_enabled(True)

    # ---- Role modes ----
    def _seer_mode_center(self):
        picked = []
        def on_reveal(idx, role):
            picked.append((idx, role))
        def done(_=None):
            if picked:
                label = self._current_role_label('seer') or '预言家'
                parts = []
                for idx, role in picked:
                    name = ROLE_DISPLAY_NAMES.get(WerewolfDealer.normalize_role(role), role)
                    parts.append(f"中央{idx+1}（{name}）")
                self._log_action(f"{label}查看中央：{'，'.join(parts)}")
            self._set_continue_enabled(True)
        self._night_focus_centers(peek_count=2, on_done=done, on_reveal=on_reveal)

    def _seer_mode_player(self):
        def on_pick(i):
            role = self.player_roles[i]
            img = find_image(role)
            actions = self.manager.get_screen('board').ids.night_actions
            actions.clear_widgets()
            btn = Button(size_hint_y=None, height='220dp', background_normal=(img or self.get_back()), background_down='')
            actions.add_widget(btn)
            name = ROLE_DISPLAY_NAMES.get(WerewolfDealer.normalize_role(role), role)
            actions.add_widget(Label(text=f'玩家{i+1}：{name}', size_hint_y=None, height='28dp'))
            label = self._current_role_label('seer') or '预言家'
            self._log_action(f"{label}查看玩家{i+1}：{name}")
            self._set_continue_enabled(True)
        # 禁止查看自己：从当前执行预言家的玩家索引中过滤
        ctx = getattr(self, '_action_context', {}) or {}
        forbidden = set(ctx.get('players') or [])
        selectable = [idx for idx in range(self.player_count) if idx not in forbidden]
        self._night_focus_players(selectable, on_pick)

    # ---- Focus mode (hide board grids during role actions) ----
    def _enter_focus_mode(self):
        """Hide players/centers grids to present a clean action-focused UI area."""
        try:
            board = self.manager.get_screen('board')
            pg: GridLayout = board.ids.players_grid
            cg: GridLayout = board.ids.center_grid
            pg.clear_widgets()
            cg.clear_widgets()
        except Exception:
            pass
        self._in_focus_mode = True

    def _leave_focus_mode(self):
        """Restore the board by rebuilding players/centers grids."""
        try:
            self.build_board()
        except Exception:
            pass
        self._in_focus_mode = False

    def _robber_mode(self, robber_idx):
        if robber_idx is None:
            self._set_continue_enabled(True)
            return
        # 自定义独立操作界面（单击即定）：
        # 选择一名其他玩家后，立即执行交换，并仅展示被点玩家的原牌与编号；不再显示选择界面/确认按钮。
        actions = self.manager.get_screen('board').ids.night_actions
        actions.clear_widgets()
        others = [i for i in range(self.player_count) if i != robber_idx]

        def _pick_once(i):
            # 记录被点玩家当前牌用于展示
            role_before = self.player_roles[i]
            img = find_image(role_before) or self.get_back()
            name_before = ROLE_DISPLAY_NAMES.get(WerewolfDealer.normalize_role(role_before), role_before)
            # 执行交换
            try:
                self.dealer.swap_between_players(robber_idx, i)
            except Exception:
                pass
            self._sync_from_session_android()
            # 日志记录强盗的新牌
            new_role = self.player_roles[robber_idx]
            new_name = ROLE_DISPLAY_NAMES.get(WerewolfDealer.normalize_role(new_role), new_role)
            label = self._current_role_label('robber', [robber_idx]) or f'强盗（玩家{robber_idx+1}）'
            self._log_action(f"{label}与 玩家{i+1} 交换，现在获得 {new_name}")
            # 清空选择界面，仅展示被点玩家的原牌与编号
            actions.clear_widgets()
            btn = Button(size_hint_y=None, height='220dp', background_normal=img, background_down='')
            actions.add_widget(btn)
            actions.add_widget(Label(text=f'玩家{i+1}：{name_before}', size_hint_y=None, height='28dp'))
            # 允许继续
            self._set_continue_enabled(True)

        # 构建候选玩家卡片（单击即定）
        for idx in others:
            box = BoxLayout(orientation='vertical', size_hint_y=None, height='220dp', padding='4dp', spacing='4dp')
            box.add_widget(Label(text=f'玩家{idx+1}', size_hint_y=None, height='24dp'))
            btn = Button(size_hint_y=None, height='180dp', background_normal=self.get_back(), background_down=self.get_back(), border=(0,0,0,0))
            btn.bind(on_release=lambda b, i=idx: _pick_once(i))
            box.add_widget(btn)
            actions.add_widget(box)

    def _troublemaker_mode(self, tm_idx):
        if tm_idx is None:
            self._set_continue_enabled(True)
            return
        # 自定义独立操作界面：选择两名其他玩家，按“确认交换”生效
        actions = self.manager.get_screen('board').ids.night_actions
        actions.clear_widgets()
        others = [i for i in range(self.player_count) if i != tm_idx]
        # 状态：已选列表和每个tile的高亮
        self._tm_state = {
            'sel': [],
            'tiles': {},
            'confirm_btn': None,
            'tm': tm_idx,
        }

        def _update_confirm():
            btn = self._tm_state.get('confirm_btn')
            if not btn:
                return
            try:
                btn.disabled = not (len(self._tm_state['sel']) == 2)
            except Exception:
                pass

        def _set_tile_selected(i, selected):
            info = self._tm_state['tiles'].get(i)
            if not info:
                return
            color_instr = info.get('color')
            if not color_instr:
                return
            try:
                color_instr.rgba = (0.18, 0.49, 0.25, 1) if selected else (0.13, 0.13, 0.13, 1)
            except Exception:
                pass

        def _toggle(i):
            sel = self._tm_state['sel']
            if i in sel:
                sel.remove(i)
                _set_tile_selected(i, False)
            else:
                sel.append(i)
                # 最多保留两个，超出的移除最早的一个
                if len(sel) > 2:
                    drop = sel.pop(0)
                    _set_tile_selected(drop, False)
                _set_tile_selected(i, True)
            _update_confirm()

        # 构建候选玩家操作卡片
        for idx in others:
            box = BoxLayout(orientation='vertical', size_hint_y=None, height='220dp', padding='4dp', spacing='4dp')
            # 选中高亮底色
            with box.canvas.before:
                color_instr = Color(0.13, 0.13, 0.13, 1)
                rect = Rectangle(pos=box.pos, size=box.size)
            def _upd_rect(_inst, _val, rect=rect, box=box):
                rect.pos = box.pos
                rect.size = box.size
            box.bind(pos=_upd_rect, size=_upd_rect)
            # 标题 + 卡背按钮
            box.add_widget(Label(text=f'玩家{idx+1}', size_hint_y=None, height='24dp'))
            btn = Button(size_hint_y=None, height='180dp', background_normal=self.get_back(), background_down=self.get_back(), border=(0,0,0,0))
            btn.bind(on_release=lambda b, i=idx: _toggle(i))
            box.add_widget(btn)
            actions.add_widget(box)
            self._tm_state['tiles'][idx] = {'box': box, 'color': color_instr}

        # 底部确认按钮
        box_btns = self._night_buttons_box()
        if box_btns is not None:
            confirm = Button(text='确认交换', size_hint_y=None, height='40dp')
            confirm.disabled = True
            def _do_confirm(*_):
                sel = list(self._tm_state.get('sel') or [])
                if len(sel) != 2:
                    return
                a, b = sel[0], sel[1]
                try:
                    self.dealer.swap_between_players(a, b)
                except Exception:
                    pass
                self._sync_from_session_android()
                label = self._current_role_label('troublemaker', [tm_idx]) or f'捣蛋鬼（玩家{tm_idx+1}）'
                self._log_action(f"{label}交换了 玩家{a+1} 与 玩家{b+1}")
                try:
                    confirm.disabled = True
                except Exception:
                    pass
                self._set_continue_enabled(True)
            confirm.bind(on_release=_do_confirm)
            box_btns.add_widget(confirm)
            self._tm_state['confirm_btn'] = confirm
            _update_confirm()

    def _drunk_mode(self, drunk_idx):
        if drunk_idx is None:
            self._set_continue_enabled(True)
            return
        # 自定义独立操作界面：选择一张中央牌后按“确认交换”生效（不展示新牌）
        actions = self.manager.get_screen('board').ids.night_actions
        actions.clear_widgets()
        self._drunk_state = {'sel': None, 'tiles': {}, 'confirm_btn': None, 'drunk': drunk_idx}

        def _update_confirm():
            btn = self._drunk_state.get('confirm_btn')
            if not btn:
                return
            try:
                btn.disabled = (self._drunk_state.get('sel') is None)
            except Exception:
                pass

        def _set_center_selected(j, selected):
            info = self._drunk_state['tiles'].get(j)
            if not info:
                return
            color_instr = info.get('color')
            if not color_instr:
                return
            try:
                color_instr.rgba = (0.18, 0.49, 0.25, 1) if selected else (0.13, 0.13, 0.13, 1)
            except Exception:
                pass

        def _pick(j):
            # 单选：清除原选择，高亮新选择
            prev = self._drunk_state.get('sel')
            if prev is not None and prev != j:
                _set_center_selected(prev, False)
            self._drunk_state['sel'] = j
            _set_center_selected(j, True)
            _update_confirm()

        for j, role in enumerate(self.center_roles):
            box = BoxLayout(orientation='vertical', size_hint_y=None, height='220dp', padding='4dp', spacing='4dp')
            with box.canvas.before:
                color_instr = Color(0.13, 0.13, 0.13, 1)
                rect = Rectangle(pos=box.pos, size=box.size)
            def _upd_rect(_inst, _val, rect=rect, box=box):
                rect.pos = box.pos
                rect.size = box.size
            box.bind(pos=_upd_rect, size=_upd_rect)
            box.add_widget(Label(text=f'中央{j+1}', size_hint_y=None, height='24dp'))
            btn = Button(size_hint_y=None, height='180dp', background_normal=self.get_back(True), background_down=self.get_back(True), border=(0,0,0,0))
            btn.bind(on_release=lambda b, k=j: _pick(k))
            box.add_widget(btn)
            actions.add_widget(box)
            self._drunk_state['tiles'][j] = {'box': box, 'color': color_instr}

        # 底部确认按钮
        box_btns = self._night_buttons_box()
        if box_btns is not None:
            confirm = Button(text='确认交换', size_hint_y=None, height='40dp')
            confirm.disabled = True
            def _do_confirm(*_):
                j = self._drunk_state.get('sel')
                if j is None:
                    return
                try:
                    self.dealer.swap_with_center(drunk_idx, j)
                except Exception:
                    pass
                self._sync_from_session_android()
                label = self._current_role_label('drunk', [drunk_idx]) or f'酒鬼（玩家{drunk_idx+1}）'
                self._log_action(f"{label}与 中央{j+1} 交换")
                try:
                    confirm.disabled = True
                except Exception:
                    pass
                self._set_continue_enabled(True)
            confirm.bind(on_release=_do_confirm)
            box_btns.add_widget(confirm)
            self._drunk_state['confirm_btn'] = confirm
            _update_confirm()

    # ---- Session sync and refresh ----
    def _sync_from_session_android(self):
        s = self.dealer.get_session()
        if not s:
            return
        self.player_roles = s['player_cards']
        self.center_roles = s['center_cards']
        # 避免在夜晚引导中重建牌面导致 UI 被重置；仅在非夜晚时可考虑重建
        if not self.night_mode:
            try:
                self.build_board()
            except Exception:
                pass

    # ---- Audio ----
    def _ensure_sounds_dir(self):
        global SOUNDS_DIR
        if SOUNDS_DIR:
            return SOUNDS_DIR
        candidates = [
            os.path.join(ROOT, 'sounds'),
            os.path.join(ROOT, '..', 'sounds'),
        ]
        for d in candidates:
            if os.path.isdir(d):
                SOUNDS_DIR = d
                break
        return SOUNDS_DIR

    def _play_role_wake(self, role):
        mp = {
            'seer': ('seer_wake.mp3',),
            'robber': ('robber_wake.mp3',),
            'troublemaker': ('troublemaker_wake.mp3',),
            'drunk': ('drunk_wake.mp3',),
            'insomniac': ('insomniac_wake.mp3',),
            'mason': ('mason_wake.mp3',),
            'minion': ('minion_wake.mp3',),
            'werewolf': ('werewolf_wake.mp3',),
            'doppelganger': ('doppelganger_wake.mp3',),
        }
        r = WerewolfDealer.normalize_role(role)
        files = mp.get(r)
        if not files:
            return
        for fn in files:
            if self._play_sound(fn):
                break

    def _play_role_close(self, role, on_complete=None):
        mp = {
            'seer': ('seer_close.mp3',),
            'robber': ('robber_close.mp3',),
            'troublemaker': ('troublemaker_close.mp3',),
            'drunk': ('drunk_close.mp3',),
            'insomniac': ('insomniac_close.mp3',),
            'mason': ('mason_close.mp3',),
            'minion': ('minion_close.mp3',),
            'werewolf': ('werewolf_close.mp3',),
            'doppelganger': ('doppelganger_close.mp3',),
        }
        r = WerewolfDealer.normalize_role(role)
        files = mp.get(r)
        if not files:
            return False
        for fn in files:
            if self._play_sound(fn, on_complete=on_complete):
                return True
        return False

    def _finish_role_and_then(self, cb):
        role = None
        ctx = getattr(self, '_action_context', None)
        if ctx:
            role = ctx.get('role') or ctx.get('display')
        # 特殊处理：爪牙在结束时需先播放 thumb 再播放 close
        try:
            norm = WerewolfDealer.normalize_role(role) if role else None
        except Exception:
            norm = role
        if norm == 'minion':
            def _after_thumb():
                # 稍作停顿后播放 close，若未能播放则直接进入下一步
                def _play_close(*_):
                    played_close = self._play_role_close('minion', on_complete=lambda: cb() if callable(cb) else None)
                    if not played_close and callable(cb):
                        cb()
                try:
                    Clock.schedule_once(_play_close, 0.2)
                except Exception:
                    _play_close()
            # 先尝试播放 thumb，失败则直接播放 close
            if not self._play_sound('minion_thumb.mp3', on_complete=lambda: _after_thumb()):
                _after_thumb()
            return
        # 默认行为：仅播放 close
        played = self._play_role_close(role, on_complete=lambda: cb() if callable(cb) else None)
        if not played and callable(cb):
            cb()

    def _play_general_sound(self, name, on_complete=None):
        if not self._play_sound(f'{name}.mp3', on_complete=on_complete):
            if on_complete:
                on_complete()

    def _stop_voice_playback(self):
        # stop all currently playing guide sounds/tts to avoid overlap
        for snd in list(getattr(self, '_playing_sounds', []) or []):
            try:
                snd.stop()
            except Exception:
                pass
        self._playing_sounds = []
        if getattr(self, '_tts_available', False):
            engine = getattr(self, '_tts_engine', None)
            if engine and hasattr(engine, 'stop'):
                try:
                    engine.stop()
                except Exception:
                    pass

    def _play_sound(self, filename, on_complete=None):
        d = self._ensure_sounds_dir()
        if not d:
            return False
        path = os.path.join(d, filename)
        if not os.path.exists(path):
            # try uppercase extension variants
            base, ext = os.path.splitext(filename)
            alt = os.path.join(d, f'{base}.MP3')
            if not os.path.exists(alt):
                return False
            path = alt
        try:
            snd = SoundLoader.load(path)
            if snd:
                self._stop_voice_playback()
                fired = {'done': False}

                def _cleanup(*_):
                    if fired['done']:
                        return
                    fired['done'] = True
                    try:
                        snd.unbind(on_stop=_cleanup)
                    except Exception:
                        pass
                    try:
                        self._playing_sounds.remove(snd)
                    except (ValueError, AttributeError):
                        pass
                    if on_complete:
                        on_complete()

                try:
                    snd.bind(on_stop=_cleanup)
                except Exception:
                    pass
                try:
                    self._playing_sounds.append(snd)
                except Exception:
                    self._playing_sounds = [snd]
                snd.play()
                duration = getattr(snd, 'length', None)
                if duration is None or duration <= 0:
                    fallback_delay = 0.6
                else:
                    fallback_delay = duration + 0.05
                Clock.schedule_once(lambda *_: _cleanup(), fallback_delay)
                return True
        except Exception:
            return False
        return False

    def _night_start_bgm(self):
        d = self._ensure_sounds_dir()
        if not d:
            return
        # try Mysterious Light.*
        for base in ['Mysterious Light', 'mysterious light', 'Mysterious_Light', 'mysterious_light']:
            for ext in ['.mp3', '.MP3', '.ogg', '.wav']:
                p = os.path.join(d, base + ext)
                if os.path.exists(p):
                    try:
                        self._bgm = SoundLoader.load(p)
                        if self._bgm:
                            try:
                                self._bgm.loop = True
                            except Exception:
                                pass
                            self._bgm.play()
                            return
                    except Exception:
                        pass

    def _stop_bgm(self):
        try:
            if self._bgm:
                self._bgm.stop()
        except Exception:
            pass
        self._bgm = None

    def toggle_player_card(self, btn: Button, idx: int):
        # 若夜晚已结束且尚未判定结果：翻开即判定结果一次
        if self.night_finished and not self.result_decided:
            # 先翻开
            btn.background_normal = find_image(self.player_roles[idx]) or btn.card_front
            btn.background_down = btn.background_normal
            self._evaluate_result(idx)
            return
        btn.showing = not btn.showing
        if btn.showing:
            btn.background_normal = btn.card_front
            btn.background_down = btn.card_front
        else:
            btn.background_normal = btn.card_back
            btn.background_down = btn.card_back

    def toggle_center_card(self, btn: Button, idx: int):
        btn.showing = not btn.showing
        if btn.showing:
            btn.background_normal = btn.card_front
            btn.background_down = btn.card_front
        else:
            btn.background_normal = btn.card_back
            btn.background_down = btn.card_back

    def _evaluate_result(self, executed_idx: int):
        # 使用核心引擎的简化胜负判定
        try:
            result = self.dealer.evaluate_victory([executed_idx], is_tie=False)
        except Exception:
            # 兜底：按是否有狼人简单判定
            try:
                has_wolf = any(WerewolfDealer.normalize_role(r) == 'werewolf' for r in self.player_roles)
            except Exception:
                has_wolf = False
            msg = '本局结果：狼人阵营胜利' if has_wolf else '本局结果：好人阵营胜利'
            self.popup('结算', msg)
            self.result_decided = True
            return
        msg = []
        if result.get('good'):
            msg.append('好人阵营胜利')
        if result.get('wolf'):
            msg.append('狼人阵营胜利')
        if result.get('tanner'):
            msg.append('皮匠单独胜利')
        if not msg:
            msg = ['结果未判定']
        role = self.player_roles[executed_idx]
        name = ROLE_DISPLAY_NAMES.get(WerewolfDealer.normalize_role(role), role)
        self.popup('结算', f'你翻开的是 玩家{executed_idx+1}（{name}）。\n' + '，'.join(msg))
        self.result_decided = True

    def swap_two_players(self):
        content = BoxLayout(orientation='vertical', spacing=6, padding=6)
        b1 = TextInput(hint_text='玩家A编号(1-n)', input_filter='int', multiline=False)
        b2 = TextInput(hint_text='玩家B编号(1-n)', input_filter='int', multiline=False)
        row = BoxLayout(size_hint_y=None, height='40dp', spacing=6)
        ok = Button(text='确定')
        cancel = Button(text='取消')
        row.add_widget(ok)
        row.add_widget(cancel)
        content.add_widget(b1)
        content.add_widget(b2)
        content.add_widget(row)
        popup = Popup(title='交换两名玩家角色', content=content, size_hint=(.8, .5))
        def on_ok(_):
            try:
                a = int(b1.text) - 1
                b = int(b2.text) - 1
            except Exception:
                self.popup('错误', '请输入有效编号')
                return
            if a == b or a < 0 or b < 0 or a >= self.player_count or b >= self.player_count:
                self.popup('错误', '编号无效或重复')
                return
            try:
                self.dealer.swap_between_players(a, b)
            except Exception as e:
                self.popup('错误', str(e))
                return
            # update local
            self.player_roles[a], self.player_roles[b] = self.player_roles[b], self.player_roles[a]
            self._log_action(f"手动交换：玩家{a+1} 与 玩家{b+1}")
            self.build_board()
            popup.dismiss()
        ok.bind(on_release=on_ok)
        cancel.bind(on_release=lambda *_: popup.dismiss())
        popup.open()

    def redeal_same_pool(self):
        """Return to role selection instead of immediately dealing.

        - Prefill the selection screen with the last used role pool (if any):
          * player_count = len(pool) - 3
          * werewolf_count = count('werewolf')
          * selected roles = non-werewolf roles (mason treated as a single toggle)
        - Do NOT start dealing here; wait for the user to press the Start button.
        """
        # Go to selection screen
        try:
            sc = self.manager.get_screen('role_select')
        except Exception:
            # Fallback: just switch by name; screen should exist from KV
            self.manager.current = 'role_select'
            return

        pool = list(self.current_role_pool or [])
        # Clear previous UI selection state
        self.selected_set.clear()
        for role, _tile in getattr(self, 'role_tiles', {}).items():
            self._set_tile_selected(role, False)

        if pool:
            # Compute and fill counts
            wolf_cnt = sum(1 for r in pool if r == 'werewolf')
            player_cnt = max(1, len(pool) - 3)
            try:
                sc.ids.player_count.text = str(player_cnt)
            except Exception:
                pass
            try:
                sc.ids.werewolf_count.text = str(wolf_cnt)
            except Exception:
                pass

            # Prefill role tiles (exclude werewolves; mason is single toggle)
            picked = set()
            for r in pool:
                if r == 'werewolf':
                    continue
                if r == 'mason':
                    picked.add('mason')
                else:
                    picked.add(r)
            for r in picked:
                if r in getattr(self, 'role_tiles', {}):
                    self.selected_set.add(r)
                    self._set_tile_selected(r, True)
            # Refresh summary label
            try:
                self.update_summary()
            except Exception:
                pass
        else:
            # No known pool; keep existing inputs and just ensure summary is updated
            try:
                self.update_summary()
            except Exception:
                pass

        # Reset transient game state (no active game after returning to selection)
        self.player_roles = []
        self.center_roles = []
        self.player_count = 0
        self.view_index = 0
        self.viewed = []
        self.night_mode = False
        self.night_finished = False
        self.result_decided = False
        try:
            self._cancel_night_timer()
        except Exception:
            pass

        # Finally, show the selection screen
        self.manager.current = 'role_select'

    def get_back(self, center=False):
        global CARD_BACK, CENTER_BACK
        if center and CENTER_BACK:
            return CENTER_BACK
        if not center and CARD_BACK:
            return CARD_BACK
        ph = find_placeholder()
        if center:
            CENTER_BACK = ph or ''
            return CENTER_BACK
        CARD_BACK = ph or ''
        return CARD_BACK

    def popup(self, title, msg):
        Popup(title=title, content=Label(text=msg), size_hint=(.8, .4)).open()


if __name__ == '__main__':
    OneNightApp().run()
