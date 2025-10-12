import tkinter as tk
from tkinter import ttk, messagebox
from core.werewolf_dealer import WerewolfDealer
from PIL import Image, ImageTk
import os

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
        self.spin = ttk.Spinbox(top, from_=3, to=10, width=5)
        self.spin.set(4)
        self.spin.pack(side=tk.LEFT, padx=6)

        ttk.Label(top, text="模式:").pack(side=tk.LEFT, padx=(12,0))
        self.mode_cb = ttk.Combobox(top, values=["入门"], state="readonly", width=12)
        self.mode_cb.current(0)
        self.mode_cb.pack(side=tk.LEFT, padx=6)

        self.deal_btn = ttk.Button(top, text="发牌", command=self.deal)
        self.deal_btn.pack(side=tk.LEFT, padx=6)

        self.export_btn = ttk.Button(top, text="导出结果", command=self.export, state=tk.DISABLED)
        self.export_btn.pack(side=tk.LEFT, padx=6)

        self.cards_frame = ttk.Frame(frm)
        self.cards_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self._last_result = None

    def deal(self):
        try:
            count = int(self.spin.get())
        except Exception:
            messagebox.showerror("错误", "请输入有效人数")
            return
        modes = self.dealer.get_available_modes(count)
        if modes:
            self.mode_cb['values'] = modes
            self.mode_cb.current(0)
        try:
            player_roles, center = self.dealer.deal(count, mode=self.mode_cb.get())
        except Exception as e:
            messagebox.showerror("发牌失败", str(e))
            return

        for w in self.cards_frame.winfo_children():
            w.destroy()

        roles_dir = os.path.join("resources", "roles")
        for i, role in enumerate(player_roles):
            img_path = os.path.join(roles_dir, f"{role}.png")
            if os.path.exists(img_path):
                try:
                    img = Image.open(img_path).resize((100, 150), Image.LANCZOS)
                    tk_img = ImageTk.PhotoImage(img)
                    lbl = ttk.Label(self.cards_frame, image=tk_img, text=f"玩家{i+1}", compound="top", padding=6, relief=tk.RIDGE)
                    # 缓存引用
                    self._img_cache[f"p{i}"] = tk_img
                except Exception:
                    lbl = ttk.Label(self.cards_frame, text=f"玩家{i+1}: {role}", relief=tk.RIDGE, padding=6)
            else:
                # 缺图时退回到文本显示
                lbl = ttk.Label(self.cards_frame, text=f"玩家{i+1}: {role}", relief=tk.RIDGE, padding=6)
            lbl.grid(row=i//5, column=i%5, padx=6, pady=6, sticky='nsew')

        # 中央三张
        for j, role in enumerate(center):
            img_path = os.path.join(roles_dir, f"{role}.png")
            if os.path.exists(img_path):
                try:
                    img = Image.open(img_path).resize((120, 180), Image.LANCZOS)
                    tk_img = ImageTk.PhotoImage(img)
                    lbl = ttk.Label(self.cards_frame, image=tk_img, text=f"中央{j+1}", compound="top", padding=6, relief=tk.GROOVE)
                    self._img_cache[f"c{j}"] = tk_img
                except Exception:
                    lbl = ttk.Label(self.cards_frame, text=f"中央{j+1}: {role}", relief=tk.GROOVE, padding=6)
            else:
                lbl = ttk.Label(self.cards_frame, text=f"中央{j+1}: {role}", relief=tk.GROOVE, padding=6)
            lbl.grid(row=2, column=j, padx=6, pady=6)

        self._last_result = (player_roles, center)
        self.export_btn['state'] = tk.NORMAL

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
