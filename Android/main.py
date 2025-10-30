import os
import sys
from collections import Counter
from typing import List

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
    cand = [
        'background.jpg', 'background.png', 'back.png', 'card_back.png', 'unknown.png'
    ]
    for d in ASSET_ROLE_DIRS:
        for fn in cand:
            p = os.path.join(d, fn)
            if os.path.exists(p):
                return p
    return None


class RootManager(ScreenManager):
    pass


class OneNightApp(App):
    title = '一夜终极狼人 - Android'
    current_card_image = ''

    def build(self):
        Builder.load_file(os.path.join(ROOT, 'one_night.kv'))
        self.manager = self.root = RootManager()
        self.dealer = WerewolfDealer()
        self.available_roles = self.load_available_roles()
        self.current_role_pool: List[str] = []
        self.player_roles: List[str] = []
        self.center_roles: List[str] = []
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

        self.init_role_select_screen()
        return self.manager

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

    def init_role_select_screen(self):
        sc = self.manager.get_screen('role_select')
        roles_grid: GridLayout = sc.ids.roles_grid
        roles_grid.clear_widgets()
        self.selected_set = set()
        for r in self.available_roles:
            btn = Button(text=ROLE_DISPLAY_NAMES.get(r, r), size_hint_y=None, height='36dp')
            btn.role_internal = r
            btn.background_normal = ''
            btn.background_color = (0.2, 0.2, 0.2, 1)
            btn.bind(on_release=lambda b: self.toggle_role(b))
            roles_grid.add_widget(btn)
        self.update_summary()

    def toggle_role(self, btn: Button):
        r = btn.role_internal
        if r in self.selected_set:
            self.selected_set.remove(r)
            btn.background_color = (0.2, 0.2, 0.2, 1)
        else:
            self.selected_set.add(r)
            btn.background_color = (0.1, 0.5, 0.2, 1)
        self.update_summary()

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
        # fallback: try rules-based deal
        try:
            player_count = int(player_count_text)
        except Exception:
            self.popup('错误', '请输入有效人数')
            return
        modes = self.dealer.get_available_modes(player_count)
        mode = modes[0] if modes else '入门'
        try:
            ps, cs = self.dealer.deal(player_count, mode)
        except Exception as e:
            self.popup('发牌失败', str(e))
            return
        self.current_role_pool = ps + cs
        self._after_dealt(ps, cs)

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
        self.current_card_image = self.get_back()
        sc.ids.viewer_name.text = ''

    def on_view_click(self):
        idx = self.view_index
        if idx >= self.player_count:
            return
        sc = self.manager.get_screen('viewing')
        if not self.viewed[idx]:
            role = self.player_roles[idx]
            img = find_image(role)
            self.current_card_image = img or self.get_back()
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
        self._night_set_status("")
        self._night_set_text("")
        board.ids.night_countdown.text = ''
        board.ids.night_continue.disabled = True
        self.night_finished = False
        self.result_decided = False

        # players
        cols = 4
        for i, role in enumerate(self.player_roles):
            box = BoxLayout(orientation='vertical', size_hint_y=None, height='220dp', padding='4dp', spacing='4dp')
            box.add_widget(Label(text=f'玩家{i+1}', size_hint_y=None, height='24dp'))
            btn = Button(size_hint_y=None, height='180dp', background_normal='', background_down='')
            btn.card_back = self.get_back()
            btn.card_front = find_image(role) or self.get_back()
            btn.showing = False
            btn.bind(on_release=lambda b, idx=i: self.toggle_player_card(b, idx))
            box.add_widget(btn)
            pg.add_widget(box)

        # centers
        for j, role in enumerate(self.center_roles):
            box = BoxLayout(orientation='vertical', size_hint_y=None, height='220dp', padding='4dp', spacing='4dp')
            box.add_widget(Label(text=f'中央{j+1}', size_hint_y=None, height='24dp'))
            btn = Button(size_hint_y=None, height='180dp', background_normal='', background_down='')
            btn.card_back = self.get_back(True)
            btn.card_front = find_image(role) or self.get_back(True)
            btn.showing = False
            btn.bind(on_release=lambda b, idx=j: self.toggle_center_card(b, idx))
            box.add_widget(btn)
            cg.add_widget(box)

    # ---------- Night (Guided) ----------
    def start_guided_night(self):
        if self.night_mode:
            return
        self.night_mode = True
        self._night_start_bgm()
        self.night_steps = self.dealer.get_night_steps() or []
        self.night_step_idx = 0
        self._night_set_status('夜晚进行中')
        self._night_set_text('夜晚开始…')
        self._play_general_sound('night_start', on_complete=self.run_night_step)

    def night_continue(self):
        # Called by Continue button; advance to next step
        self._finish_role_and_then(self._next_night_step)

    def end_guided_night(self):
        if not self.night_mode:
            return
        self.night_mode = False
        self._stop_bgm()
        self._cancel_night_timer()
        self._night_set_status('夜晚已结束：可自由翻牌/交换')
        self._night_set_text('')
        self.night_finished = True
        self.result_decided = False

    def _next_night_step(self, *_):
        self.night_step_idx += 1
        self.run_night_step()

    def run_night_step(self, *_):
        board = self.manager.get_screen('board')
        actions = board.ids.night_actions
        actions.clear_widgets()
        board.ids.night_continue.disabled = True
        # countdown
        self._cancel_night_timer()
        self.night_remaining = 15
        self._night_tick()

        if self.night_step_idx >= len(self.night_steps):
            self._night_set_text('夜晚结束。')
            self._play_general_sound('night_over', on_complete=lambda: board.ids.night_continue.__setattr__('disabled', False))
            return

        step = self.night_steps[self.night_step_idx]
        role = step.get('role')
        players = step.get('players', [])
        self._play_role_wake(role)

        # Dispatch per role
        if role == 'werewolf':
            if len(players) == 1:
                self._night_set_text('狼人：独狼可查看一张中央牌')
                self._night_focus_centers(peek_count=1, on_done=lambda: setattr(board.ids.night_continue, 'disabled', False))
            else:
                self._night_set_text('狼人：互相确认身份')
                board.ids.night_continue.disabled = False
        elif role == 'minion':
            self._night_set_text('爪牙：确认场上有哪些狼人')
            board.ids.night_continue.disabled = False
        elif role == 'mason':
            self._night_set_text('守夜人：两位守夜人互认')
            board.ids.night_continue.disabled = False
        elif role == 'seer':
            self._night_set_text('预言家：选择“查看两张中央”或“查看一名玩家”')
            self._night_action_buttons([
                ('查看两张中央', lambda: self._seer_mode_center()),
                ('查看一名玩家', lambda: self._seer_mode_player()),
            ])
        elif role == 'robber':
            self._night_set_text('强盗：选择一名其他玩家交换')
            robber = players[0] if players else None
            self._robber_mode(robber)
        elif role == 'troublemaker':
            self._night_set_text('捣蛋鬼：选择两名其他玩家交换')
            tm = players[0] if players else None
            self._troublemaker_mode(tm)
        elif role == 'drunk':
            self._night_set_text('酒鬼：选择一张中央牌交换（不展示新牌）')
            drunk = players[0] if players else None
            self._drunk_mode(drunk)
        elif role == 'insomniac':
            i_idx = players[0] if players else None
            self._night_set_text('失眠者：查看你当前的牌')
            if i_idx is not None:
                self._night_focus_single_player(i_idx)
            board.ids.night_continue.disabled = False
        elif role == 'doppelganger':
            # 化身幽灵：选择一名其他玩家查看并复制其角色，随后执行复制角色的夜晚行动
            self._night_set_text('化身幽灵：请选择一名其他玩家，查看并复制其角色，然后点击“确认复制”')
            self._dg_mode(players)
        else:
            # Unknown or no-op role
            board.ids.night_continue.disabled = False

    # ---- Night UI helpers ----
    def _night_set_status(self, text):
        try:
            self.manager.get_screen('board').ids.night_status.text = text
        except Exception:
            pass

    def _night_set_text(self, text):
        try:
            self.manager.get_screen('board').ids.night_text.text = text
        except Exception:
            pass

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

    def _night_buttons_box(self):
        try:
            return self.manager.get_screen('board').ids.night_buttons
        except Exception:
            return None

    def _night_focus_centers(self, peek_count=1, on_done=None):
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
            remaining['n'] -= 1
            if remaining['n'] <= 0 and on_done:
                on_done()
        # build three center buttons
        for j, role in enumerate(self.center_roles):
            btn = Button(size_hint_y=None, height='180dp', background_normal=self.get_back(True), background_down='')
            front = find_image(role) or self.get_back(True)
            def bind_click(b=btn, idx=j, front_path=front):
                def handler(_):
                    b.background_normal = front_path
                    on_click(idx)
                b.bind(on_release=handler)
            bind_click()
            actions.add_widget(btn)

    def _night_focus_players(self, indices, on_click):
        actions = self.manager.get_screen('board').ids.night_actions
        actions.clear_widgets()
        for idx in indices:
            role = self.player_roles[idx]
            btn = Button(text=f'玩家{idx+1}', size_hint_y=None, height='60dp')
            btn.bind(on_release=lambda b, i=idx: on_click(i))
            actions.add_widget(btn)

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
        # 唤醒复制的角色音效
        self._play_role_wake(role)
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
            self.manager.get_screen('board').ids.night_continue.disabled = False
            return
        # werewolf/minion/mason 或其它无行动：直接允许继续
        self.manager.get_screen('board').ids.night_continue.disabled = False

    # ---- Role modes ----
    def _seer_mode_center(self):
        picked = {'n': 0}
        def done():
            self.manager.get_screen('board').ids.night_continue.disabled = False
        self._night_focus_centers(peek_count=2, on_done=done)

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
            self.manager.get_screen('board').ids.night_continue.disabled = False
        self._night_focus_players(list(range(self.player_count)), on_pick)

    def _robber_mode(self, robber_idx):
        if robber_idx is None:
            self.manager.get_screen('board').ids.night_continue.disabled = False
            return
        others = [i for i in range(self.player_count) if i != robber_idx]
        def on_pick(tgt):
            # show target's pre-swap card
            role_before = self.player_roles[tgt]
            img = find_image(role_before)
            actions = self.manager.get_screen('board').ids.night_actions
            actions.clear_widgets()
            btn = Button(size_hint_y=None, height='220dp', background_normal=(img or self.get_back()), background_down='')
            actions.add_widget(btn)
            name = ROLE_DISPLAY_NAMES.get(WerewolfDealer.normalize_role(role_before), role_before)
            actions.add_widget(Label(text=f'玩家{tgt+1}：{name}', size_hint_y=None, height='28dp'))
            # perform swap
            try:
                self.dealer.swap_between_players(robber_idx, tgt)
            except Exception:
                pass
            self._sync_from_session_android()
            self.manager.get_screen('board').ids.night_continue.disabled = False
        self._night_focus_players(others, on_pick)

    def _troublemaker_mode(self, tm_idx):
        if tm_idx is None:
            self.manager.get_screen('board').ids.night_continue.disabled = False
            return
        sel = []
        def on_pick(i):
            nonlocal sel
            if i in sel:
                sel.remove(i)
            else:
                sel.append(i)
            if len(sel) == 2:
                try:
                    self.dealer.swap_between_players(sel[0], sel[1])
                except Exception:
                    pass
                self._sync_from_session_android()
                self.manager.get_screen('board').ids.night_continue.disabled = False
        self._night_focus_players([i for i in range(self.player_count) if i != tm_idx], on_pick)

    def _drunk_mode(self, drunk_idx):
        if drunk_idx is None:
            self.manager.get_screen('board').ids.night_continue.disabled = False
            return
        actions = self.manager.get_screen('board').ids.night_actions
        actions.clear_widgets()
        for j, role in enumerate(self.center_roles):
            btn = Button(size_hint_y=None, height='180dp', background_normal=self.get_back(True), background_down='')
            def bind_click(idx=j):
                def handler(_):
                    try:
                        self.dealer.swap_with_center(drunk_idx, idx)
                    except Exception:
                        pass
                    self._sync_from_session_android()
                    self.manager.get_screen('board').ids.night_continue.disabled = False
                return handler
            btn.bind(on_release=bind_click())
            actions.add_widget(btn)

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
        }
        r = WerewolfDealer.normalize_role(role)
        files = mp.get(r)
        if not files:
            return
        for fn in files:
            if self._play_sound(fn):
                break

    def _finish_role_and_then(self, cb):
        # play close sound and then callback
        if self._play_sound('role_close_placeholder.mp3'):
            Clock.schedule_once(lambda *_: cb(), 0.1)
        else:
            cb()

    def _play_general_sound(self, name, on_complete=None):
        played = self._play_sound(f'{name}.mp3')
        if on_complete:
            if played:
                Clock.schedule_once(lambda *_: on_complete(), 0.1)
            else:
                on_complete()

    def _play_sound(self, filename):
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
                snd.play()
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
            self._evaluate_result(idx)
            return
        btn.showing = not btn.showing
        btn.background_normal = ''
        btn.background_down = ''
        btn.canvas.ask_update()
        btn.canvas.before.clear()
        if btn.showing:
            btn.background_normal = btn.card_front
        else:
            btn.background_normal = btn.card_back

    def toggle_center_card(self, btn: Button, idx: int):
        btn.showing = not btn.showing
        if btn.showing:
            btn.background_normal = btn.card_front
        else:
            btn.background_normal = btn.card_back

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
            self.build_board()
            popup.dismiss()
        ok.bind(on_release=on_ok)
        cancel.bind(on_release=lambda *_: popup.dismiss())
        popup.open()

    def redeal_same_pool(self):
        if not self.current_role_pool:
            self.popup('提示', '当前没有已选择的牌池')
            return
        try:
            res = self.dealer.start_game_with_selection(self.current_role_pool[:])
        except Exception as e:
            self.popup('发牌失败', str(e))
            return
        self._after_dealt(res['player_cards'], res['center_cards'])

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
