# APK 放置目录

此目录用于存放构建出的 Android 安装包（APK）。你可以通过以下两种方式获取：

1) 通过 GitHub Actions 自动构建（推荐）
- 打开仓库的 Actions 页面，运行 “Build Android APK” 工作流；
- 构建完成后，下载名为 onenightwerewolf-debug-apk 的工件（artifact）；
- 将下载的 APK 放到本目录（可选），或直接拷贝到手机安装。

2) 本地（WSL/Ubuntu）使用 Buildozer 构建
- 按 `Android/README.md` 中的步骤安装 buildozer 及依赖；
- 在 `Android/` 目录执行 `buildozer android debug`；
- 构建产物默认出现在 `Android/bin/` 下（.apk 文件），拷贝到手机安装。

安装方法
- 将 APK 复制到手机，允许来自此来源安装应用；
- 直接点击 APK 安装，即可运行。
