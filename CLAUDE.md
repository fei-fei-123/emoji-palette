# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概要

Windows 表情快速上屏工具:全局热键呼出面板 + `::` 文本扩展,四路搜索(中文/英文/拼音全拼/拼音缩写),纯 Unicode SendInput 注入上屏。技术栈:PySide6 + keyboard 库 + 纯 ctypes Win32。仅支持 Windows(大量 user32/imm32/winreg 调用)。

注释、文档字符串、UI 文案、commit message 均用中文,保持一致。

## 常用命令

```bash
# 环境:必须用项目 .venv(uv 托管 CPython,阿里云镜像见 uv.toml)
# 勿用 conda Python —— 会劫持 icuuc.dll 弄崩 PySide6
uv sync                            # 或 pip install -r requirements.txt

python build_data.py               # 构建数据索引(首次必须,需联网)
python build_data.py --offline     # 仅用 data/raw 缓存构建
python build_data.py --refresh     # 忽略缓存强制重新下载

PYTHONPATH=src python -m emoji_palette   # 运行(包未安装,需 src 在路径上)

python -m pytest tests             # 全部测试
python -m pytest tests/test_expander.py -k test_name   # 单个测试

python -m ruff check src tests build_data.py   # lint

python -m PyInstaller build.spec --noconfirm   # 打包单文件 exe(模块名大小写敏感:PyInstaller)
```

注意:

- `data/index.json` 不入库(gitignore),缺失时应用拒绝启动并提示先跑 build_data.py
- 打包产物 datas 把 index.json 打进 `_MEIPASS/data/`,app.py 以 `_MEIPASS` 定位
- 用户数据(配置/别名/频率)在 `%APPDATA%\EmojiPalette\`,不在仓库内

## 架构

### 两条交互流(app.py 装配全部组件)

1. **面板流**:全局热键(keyboard 库)→ `HotkeyBridge.activated`(queued 信号,携带前台 hwnd)→ `EmojiPanel.popup()` → 搜索选中 → Enter 上屏
2. **扩展流**:任意输入框打 `::前缀` → `ExpanderHook`(keyboard suppress 钩子,钩子线程)→ `Expander` 状态机(IDLE→ARMED→REC,纯逻辑)→ `ExpandBridge.compose` 事件(queued 到主线程)→ `CandidateBar` 渲染 + `SearchIndex.prefix_candidates` 匹配 → 空格/数字提交 → 回删前缀+缓冲后注入

### 线程模型与键盘安全(硬约束,改动前必读)

- **钩子线程只做 O(1) 工作**:状态转移与信号 emit,字符解析/匹配/渲染全在 Qt 主线程
- **钩子回调严禁抛出**:一律 try/except 放行(键盘安全 > 功能完整),见 expander.py / hotkey.py 各回调
- **钩子回调内不得 SendInput**(低级钩子重入有超时/死锁风险),注入必须经信号排队到主线程
- **吞键依据由主线程回写**:`Expander.set_has_candidates()`(GIL 原子读写),主线程每次刷新候选后回写
- `_winkeyboard` 返回值约定与直觉相反:True = 放行,False = 拦截(见 `ExpanderHook._on_event`)
- 退出清理顺序:`expand_hook.stop()` 必须最先 —— suppress 钩子任何残留都会卡死键盘
- `HookWatchdog` 每 30s 校验监听线程存活,失活重挂全部钩子

### 数据管道(build_data.py,构建期专用)

下载 emoji-test / CLDR annotations(en+zh)/ emojilib → 解析合并 → pypinyin 预计算拼音与缩写 → `data/index.json`。运行期零网络。pypinyin 仅构建期依赖。

### 搜索(search.py)

- 预展开扁平匹配表 `(term, emoji_idx, weight)`,别名段热更新时重建重挂
- 四路词型:kw_en / kw_zh / kw_py(拼音连写)/ kw_abbr(首字母缩写),另加用户别名(weight 1.2)
- 三级排序:档位(精确>前缀>子串)> 使用频率(封顶 9999)> 码点升序 tie-break。`_TIER_BASE=20000` 保证档位绝对主导
- 频率表是模块级共享 dict(config.py `_frequencies`),SearchIndex 持同一引用,bump 后查询即时可见

### 上屏(sender.py,纯 ctypes 零 Qt)

- `type_text`:UTF-16 逐 code unit(含代理对)合并为单次 SendInput(原子性),可选前置 N 次退格(扩展回删用)
- 修饰键夹逼(硬约束,`_build_keystrokes`):注入瞬间物理按住的 Shift/Ctrl/Alt(左右区分)批头合成松开——按住的 Shift 会让 VK_PACKET 字符被键盘态转写丢弃;**批尾按原键重压恢复**(带物理扫描码 `_SCAN_BY_VK`):不重压则 OS 修饰键状态被清空,keep-open 连击第二击失去 ShiftModifier、断成 dismiss;重压不带物理扫描码会毒化 keyboard 库热键匹配(面板无法再唤出的根因)
- `restore_focus` 等前台切换**且目标线程焦点窗口落位**(`GetGUIThreadInfo`):面板前台期间目标 WM_KILLFOCUS 后线程焦点为 NULL,目标处理 WM_SETFOCUS 是异步的,抢跑注入 = VK_PACKET 路由到空焦点静默丢弃(keep-open 连击丢字的根因)
- keep-open 提交后延迟 `_REGRAB_DELAY_MS` 抢回前台:SendInput 字符按出队时刻的前台窗口路由,立即抢回会与路由竞态导致字符丢失(panel.py `_submit`)
- 时序约定:先 hide 面板 → `restore_focus`(失败敲 Alt 解前台锁)→ 注入
- 失败降级 `clipboard_fallback`(如提权窗口),托盘气泡提示(每小时至多一次)

### IME 让位(ime.py)

经 `WM_IME_CONTROL` 探针检测 IME 转写模式(中文原生/全角),转写中扩展不吞键。`ImmGetConversionStatus` 在 TSF 应用拿不到上下文,不可用。钩子路径永不抛错。

### 配置(config.py)

`load_config` 深合并默认值并逐键类型校验(损坏文件回退默认)。全部写盘走临时文件 + `os.replace` 原子写。自启动 = HKCU Run 注册表,开发态用 `pythonw -c` 引导(Run 键无环境变量,`python -m` 找不到包;必须 pythonw,python.exe 会在开机后挂一整场控制台黑窗;`refresh_autostart` 在启动时自愈过期命令行模板)。

### 测试(tests/)

conftest.py 把仓库根与 src 加入 sys.path。`Expander` 状态机是纯函数式的(`on_key → (suppress, event)`),为表驱动单测的靶,逻辑改动优先保此纯度。测试不依赖 Qt 事件循环与真实键盘钩子。
