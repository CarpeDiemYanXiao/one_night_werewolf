import os
from collections import Counter
from typing import List, Dict

from PySide6 import QtCore, QtGui, QtWidgets

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
}


def roles_dir() -> str:
    # 优先 wolf/resources/roles，其次 repo images/roles
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'resources', 'roles'))
    if os.path.isdir(base):
        return base
    alt = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'images', 'roles'))
    return alt


def find_image_file(name: str) -> str | None:
    d = roles_dir()
    for ext in ('.png', '.jpg', '.jpeg'):
        p = os.path.join(d, f"{name}{ext}")
        if os.path.exists(p):
            return p
    return None


class RoleTile(QtWidgets.QFrame):
    toggled = QtCore.Signal(str, bool)  # internal, selected

    def __init__(self, internal: str, display: str, parent=None):
        super().__init__(parent)
        self.internal = internal
        self.display = display
        self.selected = False

        self.setFrameShape(QtWidgets.QFrame.Panel)
        self.setFrameShadow(QtWidgets.QFrame.Raised)
        self.setLineWidth(2)
        self.setStyleSheet("background:#F9FAFB;")

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        self.img_lbl = QtWidgets.QLabel(self)
        self.img_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self.text_lbl = QtWidgets.QLabel(display, self)
        self.text_lbl.setAlignment(QtCore.Qt.AlignCenter)

        lay.addWidget(self.img_lbl)
        lay.addWidget(self.text_lbl)

        # 角标
        self.badge = QtWidgets.QLabel("✓ 已选", self)
        self.badge.setStyleSheet("background:#22C55E;color:white;font-weight:bold;padding:2px 6px;border-radius:4px;")
        self.badge.hide()

        # 加载图片
        self._set_pixmap_for(internal)

    def resizeEvent(self, e: QtGui.QResizeEvent) -> None:
        super().resizeEvent(e)
        # 重新缩放图片以匹配更清晰尺寸
        self._set_pixmap_for(self.internal)

    def mousePressEvent(self, e: QtGui.QMouseEvent) -> None:
        super().mousePressEvent(e)
        self.toggle()

    def toggle(self):
        self.selected = not self.selected
        if self.selected:
            self.setStyleSheet("background:#DCFCE7;")
            self.setFrameShadow(QtWidgets.QFrame.Plain)
            self.setLineWidth(3)
            # 放置角标在右上角
            self.badge.show()
            self.badge.adjustSize()
            self.badge.move(self.width() - self.badge.width() - 6, 6)
        else:
            self.setStyleSheet("background:#F9FAFB;")
            self.setFrameShadow(QtWidgets.QFrame.Raised)
            self.setLineWidth(2)
            self.badge.hide()
        self.toggled.emit(self.internal, self.selected)

    def _set_pixmap_for(self, internal: str):
        path = find_image_file(internal) or find_image_file('background')
        if not path:
            self.img_lbl.clear()
            return
        pm = QtGui.QPixmap(path)
        # 目标尺寸更清晰
        target = QtCore.QSize(140, 210)
        pm = pm.scaled(target, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self.img_lbl.setPixmap(pm)


class WerewolfTile(QtWidgets.QFrame):
    valueChanged = QtCore.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QtWidgets.QFrame.Panel)
        self.setFrameShadow(QtWidgets.QFrame.Raised)
        self.setLineWidth(2)
        self.setStyleSheet("background:#F9FAFB;")

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        self.img_lbl = QtWidgets.QLabel(self)
        self.img_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self.text_lbl = QtWidgets.QLabel(f"{ROLE_DISPLAY_NAMES.get('werewolf','werewolf')}（数量）", self)
        self.text_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self.spin = QtWidgets.QSpinBox(self)
        self.spin.setRange(0, 5)
        self.spin.setValue(2)
        self.spin.valueChanged.connect(self.valueChanged)

        lay.addWidget(self.img_lbl)
        lay.addWidget(self.text_lbl)
        lay.addWidget(self.spin)

        # 点击图片也 +1（循环）
        self.img_lbl.mousePressEvent = self._inc

        self._set_pixmap()

    def _inc(self, _e):
        v = self.spin.value()
        v = v + 1 if v < self.spin.maximum() else self.spin.minimum()
        self.spin.setValue(v)

    def _set_pixmap(self):
        path = find_image_file('werewolf') or find_image_file('background')
        if not path:
            self.img_lbl.clear(); return
        pm = QtGui.QPixmap(path)
        target = QtCore.QSize(140, 210)
        pm = pm.scaled(target, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self.img_lbl.setPixmap(pm)

    def value(self) -> int:
        return self.spin.value()


class QtWerewolfApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("一夜终极狼人发牌器 - Qt")
        self.dealer = WerewolfDealer()

        # 背景图层
        self._bg_lbl = QtWidgets.QLabel(self)
        self._bg_lbl.setScaledContents(True)
        self._bg_pix: QtGui.QPixmap | None = None
        self._load_background()

        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)

        self.main_lay = QtWidgets.QVBoxLayout(central)
        self.main_lay.setContentsMargins(12, 12, 12, 12)
        self.main_lay.setSpacing(8)

        # 顶部栏
        top = QtWidgets.QHBoxLayout()
        self.main_lay.addLayout(top)

        top.addWidget(QtWidgets.QLabel("玩家人数:"))
        self.player_spin = QtWidgets.QSpinBox()
        self.player_spin.setRange(4, 12)
        self.player_spin.setValue(4)
        self.player_spin.valueChanged.connect(self._update_summary)
        top.addWidget(self.player_spin)

        self.start_btn = QtWidgets.QPushButton("开始局")
        self.start_btn.clicked.connect(self.start_game)
        top.addWidget(self.start_btn)

        self.deal_btn = QtWidgets.QPushButton("随机发牌")
        self.deal_btn.clicked.connect(self.deal_random)
        top.addWidget(self.deal_btn)

        self.export_btn = QtWidgets.QPushButton("导出结果")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self.export_result)
        top.addWidget(self.export_btn)

        top.addStretch(1)

        # 选择区域
        self.selection_group = QtWidgets.QGroupBox("选择角色（玩家人数 + 3）")
        self.main_lay.addWidget(self.selection_group)
        sel_lay = QtWidgets.QVBoxLayout(self.selection_group)

        # 角色网格（可滚动）
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        sel_lay.addWidget(self.scroll)

        self.grid_container = QtWidgets.QWidget()
        self.scroll.setWidget(self.grid_container)
        self.grid = QtWidgets.QGridLayout(self.grid_container)
        self.grid.setContentsMargins(8, 8, 8, 8)
        self.grid.setSpacing(8)

        # 加载可选角色与渲染
        self.available_roles = self._load_available_roles()
        self.role_tiles: Dict[str, RoleTile] = {}
        self._render_role_grid()

        # 底部统计
        self.summary_lbl = QtWidgets.QLabel("已选择 0 张")
        sel_lay.addWidget(self.summary_lbl)

        # 结果展示占位
        self.result_area = QtWidgets.QTextEdit()
        self.result_area.setReadOnly(True)
        self.result_area.setVisible(False)
        self.main_lay.addWidget(self.result_area)

        self._last_result: tuple[list[str], list[str]] | None = None
        self._update_summary()

    # 背景
    def resizeEvent(self, e: QtGui.QResizeEvent) -> None:
        super().resizeEvent(e)
        self._place_background()

    def _load_background(self):
        for name in ("background.jpg", "background.png"):
            p = os.path.join(roles_dir(), name)
            if os.path.exists(p):
                self._bg_pix = QtGui.QPixmap(p)
                break
        self._place_background()

    def _place_background(self):
        if not self._bg_pix:
            self._bg_lbl.hide(); return
        self._bg_lbl.show()
        self._bg_lbl.lower()
        self._bg_lbl.setGeometry(self.rect())
        # cover 效果
        w, h = self.width(), self.height()
        ow, oh = self._bg_pix.width(), self._bg_pix.height()
        if ow == 0 or oh == 0:
            return
        scale = max(w / ow, h / oh)
        nw, nh = int(ow * scale), int(oh * scale)
        scaled = self._bg_pix.scaled(nw, nh, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        # 居中裁剪
        x = max(0, (scaled.width() - w) // 2)
        y = max(0, (scaled.height() - h) // 2)
        cropped = scaled.copy(x, y, min(w, scaled.width()), min(h, scaled.height()))
        self._bg_lbl.setPixmap(cropped)

    # 角色加载与网格
    def _load_available_roles(self):
        role_dict = {}
        excluded = {"werewolf", "background", "bodyguard"}
        for internal, display in ROLE_DISPLAY_NAMES.items():
            if internal in excluded:
                continue
            role_dict.setdefault(internal, display)
        # 扫描图片目录，补充可能的图片
        d = roles_dir()
        if os.path.isdir(d):
            for fn in os.listdir(d):
                name, ext = os.path.splitext(fn)
                if ext.lower() not in ('.png', '.jpg', '.jpeg'):
                    continue
                internal = WerewolfDealer.normalize_role(name)
                if internal in excluded:
                    continue
                role_dict.setdefault(internal, ROLE_DISPLAY_NAMES.get(internal, name))
        sorted_roles = sorted(role_dict.items(), key=lambda kv: kv[1])
        return [{"internal": k, "display": v} for k, v in sorted_roles]

    def _render_role_grid(self):
        # 清空
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.role_tiles.clear()

        # 狼人 tile
        self.werewolf_tile = WerewolfTile()
        self.werewolf_tile.valueChanged.connect(lambda _v: self._update_summary())
        r, c, cols = 0, 0, 5
        self.grid.addWidget(self.werewolf_tile, r, c)
        c += 1
        if c >= cols:
            r += 1; c = 0

        # 其它角色
        for role in self.available_roles:
            tile = RoleTile(role['internal'], role['display'])
            tile.toggled.connect(lambda internal, _sel, self=self: self._update_summary())
            tile.img_lbl.mousePressEvent = self._wrap_toggle(tile, tile.img_lbl.mousePressEvent)
            tile.text_lbl.mousePressEvent = self._wrap_toggle(tile, tile.text_lbl.mousePressEvent)
            self.grid.addWidget(tile, r, c)
            self.role_tiles[role['internal']] = tile
            c += 1
            if c >= cols:
                r += 1; c = 0

    def _wrap_toggle(self, tile: RoleTile, old_handler):
        def handler(event):
            tile.toggle()
            if old_handler:
                try:
                    old_handler(event)
                except Exception:
                    pass
        return handler

    # 选择逻辑
    def _compute_selection(self) -> List[str]:
        roles: List[str] = ['werewolf'] * self.werewolf_tile.value()
        for internal, tile in self.role_tiles.items():
            if tile.selected:
                if internal == 'mason':
                    roles.extend(['mason', 'mason'])
                else:
                    roles.append(internal)
        return roles

    def _expected_card_count(self) -> int:
        return int(self.player_spin.value()) + 3

    def _update_summary(self):
        roles = self._compute_selection()
        counts = Counter(roles)
        expected = self._expected_card_count()
        parts = [f"{ROLE_DISPLAY_NAMES.get(r, r)}×{n}" for r, n in counts.items()]
        detail = ", ".join(parts) if parts else "未选择牌"
        self.summary_lbl.setText(f"已选择 {len(roles)} 张（需 {expected} 张）：{detail}")

    # 按钮动作
    def deal_random(self):
        count = int(self.player_spin.value())
        modes = self.dealer.get_available_modes(count)
        mode = modes[0] if modes else '入门'
        try:
            player_roles, center = self.dealer.deal(count, mode=mode)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "发牌失败", str(e)); return
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
        self.export_btn.setEnabled(True)
        self._show_result_text(player_roles, center)

    def start_game(self):
        sel = self._compute_selection()
        expected = self._expected_card_count()
        if len(sel) != expected:
            QtWidgets.QMessageBox.warning(self, "错误", f"当前选择 {len(sel)} 张，应为 {expected} 张。"); return
        try:
            res = self.dealer.start_game_with_selection(sel)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "开始失败", str(e)); return
        self._last_result = (res['player_cards'], res['center_cards'])
        self.export_btn.setEnabled(True)
        self._show_result_text(res['player_cards'], res['center_cards'])

    def _show_result_text(self, player_roles: List[str], center: List[str]):
        # 简单文本展示，后续可以迁移顺序查看/桌面展示到 Qt
        self.result_area.setVisible(True)
        lines = []
        for i, r in enumerate(player_roles, start=1):
            lines.append(f"玩家{i}: {r}")
        for j, r in enumerate(center, start=1):
            lines.append(f"中央{j}: {r}")
        self.result_area.setPlainText("\n".join(lines))

    def export_result(self):
        if not self._last_result:
            QtWidgets.QMessageBox.information(self, "导出", "当前没有可导出的局面"); return
        player_roles, center = self._last_result
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'core', 'output_deal.txt'))
        try:
            with open(path, 'w', encoding='utf-8') as f:
                for i, r in enumerate(player_roles, start=1):
                    f.write(f"玩家{i},{r}\n")
                f.write("中央,1," + center[0] + "\n")
                f.write("中央,2," + center[1] + "\n")
                f.write("中央,3," + center[2] + "\n")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "导出失败", str(e)); return
        QtWidgets.QMessageBox.information(self, "导出完成", f"已导出到 {path}")
