# Android 版一夜终极狼人（Kivy）

本目录提供一个使用 Kivy 实现的 Android 端应用，直接复用项目 `wolf/core/werewolf_dealer.py` 的核心发牌与会话逻辑。

功能对齐（简化版）：

- 角色选择：
  - 多选角色（不含“狼人”），并可单独设置“狼人”数量；
  - 选择“守夜人（mason）”自动计为两张；
  - 校验总牌数 = 玩家人数 + 3。
- 发牌与查看：
  - 根据选择的角色池随机发牌；
  - 逐个玩家查看（点卡背显示角色，再点切到下一位）；
  - 查看完进入桌面。
- 桌面交互：
  - 玩家牌与中央 3 张：点一次翻面、再点回背面；
  - 捣蛋鬼回合：夜晚引导中点击两名玩家并按“确认交换”完成交换；
  - “重新选牌”按钮：返回“角色选择”界面，按上局同一牌池预填（玩家数、狼人数量与非狼人角色）；需再次点击“开始局”后才会发牌。

注意：这是一个基础实现，UI 布局与图片尺寸做了手机端友好调整；如果你有自定义美术资源，可替换 `assets/roles` 下图片。

## 运行方式（桌面调试）

Windows 桌面可直接安装 Kivy 运行（便于快速调试）：

```cmd
py -m pip install kivy
py Android\main.py
```

如需在桌面同时复用项目根目录下的图片资源，请保持目录结构不变（`images/roles/` 或 `wolf/resources/roles/`）。

## 打包 Android APK（推荐在 WSL/Ubuntu 或 Linux 环境）

Kivy 官方推荐使用 Buildozer（Linux 环境更简单）：

1. 安装 Buildozer 和依赖（参考 Kivy 文档）：
   <https://kivy.org/doc/stable/guide/packaging-android.html>
2. 在本目录初始化 buildozer：

   ```bash
   buildozer init
   ```

3. 编辑 `buildozer.spec`：
   - requirements 加入 `kivy`；
   - source.include_exts 加入 `py,png,jpg,jpeg,kv`；
   - (可选) 把 `Android/assets/roles` 目录打包进 APK。
4. 构建：

   ```bash
   buildozer -v android debug
   ```

5. 连接设备或模拟器后：

   ```bash
   buildozer android deploy run
   ```

如果你在 Windows 上没有 WSL，也可以考虑使用 Python-for-Android（p4a）或在 CI（GitHub Actions）中构建 APK。

## 使用 GitHub Actions 自动构建 APK（推荐）

仓库已内置工作流 `.github/workflows/android-apk.yml`：

1. 打开仓库的 Actions，手动触发 “Build Android APK”（或在有改动推送时自动触发）。
2. 工作流会：
   - 复制项目根目录的 `wolf/` 到 `Android/wolf/` 以便打包核心代码；
   - 同步 `images/roles/` 到 `Android/assets/roles/` 打包角色图片；
   - 运行 `buildozer -v android debug` 构建 APK；
   - 以工件（artifact）形式上传 APK（名称：`onenightwerewolf-debug-apk`）。
3. 在 Actions 页面下载 APK，拷贝到手机安装即可。你也可以把 APK 放到 `Android/apk/` 目录中便于查找。

## 资源放置

- 优先从 `Android/assets/roles/` 读取角色图片（建议 300x450 左右）；
- 其次尝试 `wolf/resources/roles/` 与 `images/roles/`；
- 找不到图片时显示占位卡背。

## 代码结构

- `Android/main.py`：Kivy 应用入口，三个屏幕：角色选择 -> 逐个查看 -> 桌面交互；
- `Android/one_night.kv`：Kivy 布局文件；
- `Android/assets/roles/`：角色图片（可选，如果不放则会回落到项目原有图片）。
- `Android/wolf/`：CI 构建时会复制项目根目录的 `wolf/` 到这里，便于打包到 APK 中；本地构建如不复制，请确保 `Android/main.py` 能访问到上级目录的 `wolf/`。

## 常见问题

- APK 打包失败：多数是 Android SDK/NDK 或 Java 环境问题，建议优先使用 WSL/Ubuntu；
- 图片不显示：确认路径与大小写、图片格式（png/jpg）正确；
- 性能：Kivy 在中低端设备上建议减少过大图片，使用中等分辨率资源。
