[app]
# 应用基本信息
title = One Night Werewolf
package.name = onenightwerewolf
package.domain = com.example
source.dir = .
source.include_exts = py,kv,png,jpg,jpeg,ttf,ttc,otf,txt,md,mp3,wav,ogg

# Kivy 依赖
requirements = python3,kivy

# 主入口
fullscreen = 0
orientation = portrait

# 图标（可选）
# icon.filename = %(source.dir)s/assets/icon.png

# 版本号
version = 0.1.0

# 包含额外源码/资源目录（将项目中的角色图复制进 APK）
# 注意：构建前会在 CI 中把 ../images/roles 同步到 Android/assets/roles

[buildozer]
log_level = 2
warn_on_root = 0

[app:android]
# 使用更高的 API 版本（按需调整）
android.api = 33
android.minapi = 21
android.archs = arm64-v8a, armeabi-v7a
# 禁用旧版 SDL2 调试
android.debug = True
android.accept_sdk_license = True
android.build_tools_version = 33.0.2
android.sdk_path = /usr/local/lib/android/sdk
android.ndk_path = /usr/local/lib/android/sdk/ndk/25.1.8937393

[p4a]
# 透传给 python-for-android 的选项（通常不需要改）

