# Windows 可执行程序打包说明

本项目已在代码中适配了 PyInstaller 打包运行时资源路径（优先 `sys._MEIPASS`），因此按下述命令即可将图片与音频资源一并打包。

## 快速开始（PowerShell）

在项目根目录（含有 `wolf/`、`images/`、`sounds/` 的目录）执行：

```powershell
# 安装 PyInstaller（如未安装）
python -m pip install pyinstaller

# 调试构建（onedir，便于排查资源问题）
pyinstaller `
  --name wolf_app `
  --windowed `
  --clean `
  --hidden-import tkinter `
  --hidden-import PIL.Image `
  --hidden-import PIL.ImageTk `
  --hidden-import pygame `
  --add-data "wolf\resources\roles;resources\roles" `
  --add-data "images\roles;images\roles" `
  --add-data "sounds;sounds" `
  wolf\main.py
```

生成结果位于 `dist/wolf_app/`，可直接运行 `dist/wolf_app/wolf_app.exe`。

### 单文件打包（onefile）

```powershell
pyinstaller `
  --name wolf_app `
  --onefile `
  --windowed `
  --clean `
  --hidden-import tkinter `
  --hidden-import PIL.Image `
  --hidden-import PIL.ImageTk `
  --hidden-import pygame `
  --add-data "wolf\resources\roles;resources\roles" `
  --add-data "images\roles;images\roles" `
  --add-data "sounds;sounds" `
  wolf\main.py
```

单文件可执行位于 `dist/wolf_app.exe`。

> 说明：`--add-data "源;目标"` 在 Windows 使用分号 `;` 分隔；在 macOS/Linux 需改用冒号 `:`。

## 一键构建脚本

也可以使用仓库里的 PowerShell 脚本：

```powershell
# 调试 onedir
./scripts/build.ps1 -Clean

# 单文件 onefile
./scripts/build.ps1 -OneFile -Clean
```

## 常见问题

- 资源路径：本项目在运行时优先从 PyInstaller 解包目录（`sys._MEIPASS`）查找 `resources/roles`、`images/roles`、`sounds`，找不到再回退到源码相对路径。
- 声音播放后端：
  - 若安装了 `pygame`，优先使用 `pygame.mixer`（更顺滑）；否则回退到 `playsound`。未安装播放库时会跳过播放但不影响流程。
- onedir 与 onefile 的差异：
  - onedir：输出一个包含 exe 与依赖文件的目录，调试资源问题更直观；
  - onefile：单独一个 exe，首次启动会解压到临时目录，体积更小但启动略慢。
- 如打包后运行缺少字体/解码器等依赖，请先用 onedir 调试，按缺失信息补充 `--hidden-import` 或 `--add-data`。

### 报错：Failed to load Python DLL ... LoadLibrary: 找不到指定的模块

出现路径类似 `...\_internal\python312.dll` 的加载失败，通常由以下原因之一引起：

1. 从 build 目录运行了 exe（错误位置）

- 正确的运行位置在 `dist/`：
  - onedir：`dist\wolf_app\wolf_app.exe`
  - onefile：`dist\wolf_app.exe`
- 请不要双击 `build/` 目录下的文件（该目录是构建中间产物）。

1. 缺少 Microsoft Visual C++ 运行库（VC++ Redistributable）

- Python 3.12 依赖 VC++ 2015–2022 运行库。未安装时，加载 `python312.dll` 会因依赖缺失而失败。
- 解决：安装官方运行库（根据系统位数选择）：
  - x64（大多数 64 位系统）：[vc_redist.x64.exe](https://aka.ms/vs/17/release/vc_redist.x64.exe)
  - x86（32 位系统）：[vc_redist.x86.exe](https://aka.ms/vs/17/release/vc_redist.x86.exe)
- 安装后重启应用再试。

1. 路径包含非 ASCII 字符或特殊符号

- 个别环境/版本在包含中文/空格/特殊符号的路径下解压或加载 DLL 可能异常。
- 解决：将整个 `dist/` 目录拷贝到纯英文路径（例如 `C:\Apps\wolf_app\`），从该位置运行。

1. 架构不匹配或系统版本过旧

- 用 64 位 Python 打的包仅能在 64 位 Windows 上运行；32 位同理。
- Python 3.12 需要 Windows 10 及以上版本（不支持 Win7/8）。
- 如不确定架构，可在开发机执行：

```powershell
python -c "import struct,platform; print(struct.calcsize('P')*8, platform.platform())"
```

1. 杀毒/防护软件拦截

- 一些防护软件会拦截临时解压或阻止加载 DLL。
- 解决：将 `dist/` 目录（或单文件 exe）加入信任/白名单，或先用 onedir 版本验证可运行性。

若以上检查后仍有问题，可优先尝试：

- 先用 onedir 构建并从 `dist/wolf_app/` 运行，确认可用后再转 onefile；
- 在 PowerShell 中运行并观察输出信息：

```powershell
& "dist/wolf_app/wolf_app.exe"
```

并将完整报错与当前 Windows 版本、是否已安装 VC++ 运行库的信息一并反馈，便于进一步定位。
