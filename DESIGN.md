# Emoji Palette — Windows 表情快速上屏工具 · 设计稿

> 本文档是唯一的需求与设计来源,面向接手开发的 AI 或工程师。
> 目标:读完本文档即可直接开发,无需再做架构决策。
> 所有技术选型已定稿,除非遇到实现级障碍,不要更换。

---

## 0. 项目背景与目标

开发者对 Windows 10/11 自带的 emoji 面板(`Win + .`)长期不满:

| 痛点 | 现状 |
|---|---|
| 搜索 | Win10 无搜索框;Win11 搜索只认英文关键词,中文/拼音无效 |
| 排序 | 仅按使用频率,无相关度 |
| 键盘流 | 依赖鼠标点选,方向键在网格里逐格移动,低效 |
| 上屏 | 可接受(Unicode 字符直接输入) |

搜狗/微信输入法 PC 版的 emoji 候选**会上屏为图片**而非 Unicode 字符,在终端、代码编辑器、纯文本输入框中不可用,已被否决。

**本项目目标:做一个「呼之即来、呼之即去、键盘流优先、中英拼音混搜、纯 Unicode 上屏」的全局 emoji 工具。**

核心理念:
1. **上屏的永远是 Unicode 字符**(U+1F4A9 这种),绝不使用剪贴板图片、富文本或私有贴图格式;
2. **全程键盘操作**:热键呼出 → 打字搜索 → 回车上屏 → 面板消失,4 步 2 秒内完成;
3. **搜索是第一公民**:中文、英文、拼音全拼、拼音缩写四路命中,支持用户自定义别名;
4. 本地单机运行,无网络依赖、无账号、无遥测。

---

## 1. 需求规格(定稿)

### R1 面板生命周期:呼之即来,呼之即去
- FR1.1 全局热键(默认 `Alt+E`,可改)随时呼出搜索面板,任何应用前台均可;
- FR1.2 面板在**光标所在位置**附近弹出(多显示器跟随光标屏幕;贴近屏幕边缘时自动向内收拢);
- FR1.3 面板**常驻内存、预创建、仅 show/hide 切换**,严禁每次销毁重建(保证 <50ms 响应);
- FR1.4 关闭途径(任一即可,全部立即、无动画):
  - `Esc`;
  - 鼠标点击面板外任意位置(失焦);
  - 完成一次上屏后自动关闭(**M5 起可配置**:`panel.close_after_submit=false` 或 `Shift+Enter` 时保持面板连续上屏,见 §5);
- FR1.5 上屏动作 = 关闭面板(或按 FR1.4 配置保持)→ 还原呼出前的焦点窗口 → 向该窗口注入 Unicode 字符(见 R6;keep-open 焦点时序见 §5)。

### R2 emoji 数据:全量 + 分类
- FR2.1 覆盖 Unicode 最新正式版 emoji 全量(≥ 3700 个,含 fully-qualified 项);
- FR2.2 按 Unicode 官方 8 大组(group)分类,支持子组(subgroup)二级分类浏览;
- FR2.3 面板提供分类导航:左侧竖排分类栏(8 组)+ 顶部「最近常用」虚拟分类;
- FR2.4 长列表虚拟滚动(只渲染可见区域),保证流畅。

### R3 搜索:中英拼音四路命中
- FR3.1 输入任意一种均应命中同一 emoji,例:
  - 中文:`屎`、`便便`、`翔`(翔为自定义别名,见 FR3.5)
  - 英文:`shit`、`poop`
  - 拼音全拼:`shi`、`bianbian`
  - 拼音缩写:`bb`
  - 上述全部 → 💩(U+1F4A9)
- FR3.2 排序规则(优先级从高到低):
  1. 匹配档位:精确全等 > 关键词前缀 > 关键词子串;
  2. 同档位:按本地使用频率降频(每次上屏 +1,持久化);
  3. 同分:按 Unicode 码点排序(稳定输出);
- FR3.3 搜索结果即时刷新(逐键),毫秒级响应;
- FR3.4 支持皮肤色修饰符 emoji(ZWJ 序列)原样检索与上屏;
- FR3.5 **自定义别名**:右键任意 emoji → 菜单「添加搜索别名」→ 输入框(可多个,逗号分隔)→ 保存至用户数据文件,立即生效于搜索与文本扩展;右键菜单同时提供「查看/编辑现有别名」「移除」。

### R4 文本扩展:快捷上屏(M5 起为输入法候选条形态)
- FR4.1 全局监听键盘,输入触发前缀(默认 `::`)立即显示**候选条**(叠加于目标应用光标附近,不抢焦点);继续输入字母即前缀过滤候选,组合文本照常打进目标应用(真实可见);
  - 示例:任意输入框打 `::shit` + 空格 → 候选条随打字缩小到 💩 → 自动回删整个 `::shit` → 上屏 💩;
  - 空格 / Enter / 数字 1-9 / 鼠标点选 均可提交;`←→` 在条内移动选择;Esc/↑↓/点击条外 关条(已打文本保留原样);无命中条不关(灰暗提示);
- FR4.2 候选源 = 用户自定义别名 + 内置关键词(英文/缩写/**拼音**,前缀匹配,内置可配置关闭);提交即回删替换;未命中原样放行(不打扰正常打字);
- FR4.3 **IME 冲突处理(硬性要求)**:焦点窗口的中文输入法处于中文/全角子模式时,自动暂停文本扩展(此时按键归 IME 所有);IME 关闭/英文键盘/中文输入法的英文半角子模式恢复正常。检测手段见 §6.5;
- FR4.4 支持进程黑名单(如游戏客户端),黑名单进程前台时完全旁路;
- FR4.5 总开关(托盘/设置),可临时关闭。

### R5 常驻与设置
- FR5.1 系统托盘常驻:图标 + 菜单(显示面板 / 暂停全局热键 / 暂停文本扩展 / 设置… / 开机自启☑ / 退出);
- FR5.2 设置窗(简易 GUI):
  - 全局热键修改(热键录制控件);
  - 文本扩展:开关、触发前缀、进程黑名单;
  - 别名管理:表格列出 emoji ↔ 别名,增删改;
  - 外观:主题(深/浅)、网格图标尺寸、面板宽度;
  - 开机自启开关;
- FR5.3 开机自启:写/删 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 注册表值(数据 = 程序完整路径);
- FR5.4 所有配置、用户数据即时落盘(变更即写,不缓存丢失)。

### R6 Unicode 上屏(核心机制,约束)
- FR6.1 使用 Win32 `SendInput` + `KEYEVENTF_UNICODE` 注入字符,**不得使用剪贴板**(不破坏用户剪贴板内容)、不得使用 `pyautogui`(不可靠);
- FR6.2 非 BMP 字符(码点 > U+FFFF,绝大多数 emoji)按 **UTF-16 代理对**拆成两个 code unit 逐个注入;
- FR6.3 注入前必须把焦点还原到呼出前的目标窗口(`SetForegroundWindow`),并确认还原成功(轮询校验,见 §6.4);
- FR6.4 对拒绝接收输入的窗口(提权窗口/UAC)失败时静默降级:复制到剪贴板 + 托盘气泡提示一次(不反复打扰)。

### 范围外(明确不做,防止过度发挥)
- ❌ GIF/贴纸/颜文字(只做 Unicode emoji);
- ❌ 云同步、账号、联网功能(数据管道下载除外,仅构建期);
- ❌ macOS/Linux 支持(Windows 10/11 only);
- ❌ 多语言 UI(界面中文即可);
- ❌ IME 集成(不注册输入法,不碰 TSF 注册体系)。

---

## 2. 技术栈(定稿)

| 层 | 选型 | 备注 |
|---|---|---|
| 语言 | Python 3.11+ | |
| GUI | PySide6(Qt6,LGPL) | 面板 + 设置 + 托盘统一 |
| 全局热键/键盘钩子 | `keyboard` 库(v0.13+) | 内置 WH_KEYBOARD_LL 封装,支持 suppress |
| Win32 调用 | `ctypes`(标准库) | SendInput / 窗口焦点 / 注册表 / IME;不用 pywin32 减少依赖 |
| 拼音 | `pypinyin` | 仅构建期使用 |
| 数据 | JSON(索引)+ JSON(配置/别名/频率) | 数据量小(<5MB),不需要 SQLite |
| 打包 | PyInstaller `--onefile --noconsole` | 产物单 exe |

依赖全集:`PySide6, keyboard, pypinyin`(运行期仅前两个)。

不采用备选的理由(已评估,勿重开):
- AHK v2:拼音索引与打分排序实现痛苦,天花板低;
- C#/WPF:非作者技术栈,维护成本高;
- Electron/Tauri:重量级,且底层键盘钩子仍需 native 桥接,多此一举。

---

## 3. 系统架构

单进程单实例(QApplication + 后台线程),模块划分:

```
┌────────────────────────────────────────────────┐
│                  QApplication                   │
│  ┌──────────┐   ┌───────────┐   ┌───────────┐  │
│  │ Panel    │   │ Settings  │   │ TrayIcon  │  │
│  │ (面板UI) │   │ (设置窗)  │   │ (托盘)    │  │
│  └────┬─────┘   └─────┬─────┘   └─────┬─────┘  │
│       │               │               │        │
│  ┌────▼───────────────▼───────────────▼─────┐  │
│  │            Config(配置读写/自启动)        │  │
│  └──────────────────────────────────────────┘  │
├────────────────────────────────────────────────┤
│              后台线程(kkeyboard hook)          │
│  ┌──────────┐  ┌──────────┐  ┌─────────────┐  │
│  │ Hotkey   │  │ Expander │  │ HookWatchdog│  │
│  │ (热键)   │  │ (::扩展)  │  │ (钩子保活)   │  │
│  └────┬─────┘  └────┬─────┘  └─────────────┘  │
│       │             │                          │
│  ┌────▼─────────────▼─────────────────────┐    │
│  │ Sender(SendInput/焦点还原) + IME 检测   │    │
│  └────────────────────────────────────────┘    │
├────────────────────────────────────────────────┤
│  Search(索引加载/四路查询/打分) ← data/index.json │
│  UserData(别名/频率)                            │
└────────────────────────────────────────────────┘
```

关键数据流:
1. **搜索流**:热键回调 → Qt 信号 → Panel show(焦点在面板自身,导航模式)→ 用户输入(自动进搜索框)→ Search.query(text) → 结果列表 → Enter → Sender.type_to_last_window(emoji) → Panel hide(或 keep-open 保持);
2. **扩展流**:keyboard hook 回调 → Expander 状态机(O(1) 转移)→ compose 信号(queued)→ 主线程 Search.prefix_candidates 刷候选条 → 用户提交 → 回删+注入(Backspace×n + Unicode 单次 SendInput);
3. **构建流**(离线,`build_data.py`):下载 CLDR + emoji-test → 解析 → pypinyin 计算拼音 → 产出 `data/index.json`。

线程约定:
- keyboard 回调运行在钩子线程,**只做 O(1) 状态机与查表**,任何 Qt/UI 操作通过信号投递到主线程(Qt 信号跨线程默认 queued);
- 面板 UI 全部在主线程。

---

## 4. 数据层设计

### 4.1 数据源(构建期下载,运行期零网络)

| 数据 | 来源 | 用途 |
|---|---|---|
| 全量 emoji + 分类 | `https://www.unicode.org/Public/emoji/16.0/emoji-test.txt`(若 17.0 存在则用 `17.0`,404 回退) | 码点、char、group/subgroup |
| 英文关键词 | unicode-org/cldr-json 仓库 `cldr-json/cldr-annotations-full/main/en/annotations.json` | `default` 数组=关键词,`tts`=标准名 |
| 中文关键词 | 同上,`.../zh/annotations.json` | 中文关键词与中文名 |
| 英文俚语补充(可选) | github.com/muan/emojilib(`emoji-en-US.json`,MIT) | CLDR 偏正式,补 `shit/crap` 类俚语 |
| 拼音 | pypinyin 本地计算 | 全拼 + 缩写,无需下载 |

CLDR annotations 结构(以 en 为例):
```json
{ "annotations": { "annotations": {
  "1F4A9": { "default": ["funny", "joke", "poo", "stool", "..."],
             "tts": ["pile of poo"] }
} } }
```
解析注意:`default` 含 `(u1F4A9)` 形式的冗余项需过滤;zh 文件同样结构。

emoji-test.txt 解析注意:
- 只收 `fully-qualified` 行;`unqualified`/`minimally-qualified` 跳过;
- `# group: Xxx` / `# subgroup: xxx` 行维护当前分类上下文;
- 行格式:`1F4A9  ; fully-qualified # 💩 E1.0 pile of poo`,`;` 前为空格分隔的十六进制码点(多个码点=组合序列,空格分开);
- 中英文组名映射内置一张常量表(如 `Smileys and Emotion → 笑脸与情感`)。

### 4.2 索引产物 `data/index.json`

```json
{
  "version": "16.0",
  "built_at": "2026-09-30T16:00:00+08:00",
  "emojis": [
    {
      "cp": "1F4A9",
      "char": "💩",
      "name": "pile of poo",
      "name_zh": "大便",
      "group": "Smileys and Emotion",
      "group_zh": "笑脸与情感",
      "subgroup": "face-negative",
      "kw_en":  ["poop", "poo", "stool", "shit"],
      "kw_zh":  ["大便", "便便"],
      "kw_py":  ["bianbian", "da", "bian", "shi"],
      "kw_abbr": ["bb", "db", "s"]
    }
  ]
}
```
(示例值仅示意格式,实际以数据源解析结果为准。)

构建规则:
- `kw_py`:对每个 `kw_zh` 词逐字取拼音后拼接,整词拼音连写(如 `便便` → `bianbian`);多音字取 pypinyin 默认常用音,不枚举全排列;
- `kw_abbr`:`kw_py` 每项的首字母(单字词只产出单字母缩写,如 `屎` → `s`);
- 全部关键词统一 `strip + lower`(中文不受影响);
- 单字拼音歧义(如 `shi` 同音多字)天然由「同音字共同命中」解决,不需要消歧——搜索场景宁多勿漏。

### 4.3 用户数据(`%APPDATA%\EmojiPalette\`)

```
%APPDATA%\EmojiPalette\
├── config.json        # 见 §8
├── aliases.json       # [{"char": "💩", "aliases": ["翔", "bb", "bianbian"]}, ...]
└── frequency.json     # {"💩": 42, "😀": 7}   每次上屏 +1,退出+每 50 次落盘
```

运行期查询 = 内置索引(启动全量载入内存)+ 别名动态合并(别名文件变更即重载)。

---

## 5. 面板 UI 设计

布局(深色主题为默认,参考 Spotlight/Win+. 的紧凑感):

```
┌────────────────────────────────────────┐
│ 🔍 [ 搜索框(打字自动进入)            ] ✕ │  ← 高 44px
├────────┬───────────────────────────────┤
│ 常用   │  😀 😁 😂 🤣 😃 😄 😅 😆 😇 😈 │
│ 笑脸   │  🙂 🙃 😉 😊 😋 🤑 🤗 🤔 🤐 😪 │  ← 网格列数按视口动态计算
│ 人物   │  ...(虚拟滚动)                 │     图标 32~40px 可调
│ 动物   │                               │
│ 食物   │  [当前项大图预览 + 名称/码点]   │  ← 底部信息栏 高 32px
│ 活动   │                               │
│ 旅行   │                               │
│ 物品   │                               │
│ 符号   │                               │
│ 旗帜   │                               │
└────────┴───────────────────────────────┘
```

视觉(M5 重做):
- **整窗不透明背景**(否则 Windows layered 窗 alpha=0 区域滚轮/点击穿透到后方应用,坑 #13):根背景 `paintEvent` 自绘半透明圆角 + 1px 描边,alpha 235(深)/242(浅)——「些许透明」的高级感;**严禁 `setWindowOpacity`**(会淡化 emoji);子控件 QSS 背景 rgba 分层;emoji 由 delegate 前景绘制天然不透明;
- 深/浅双主题:根背景、边框、搜索框/分类栏/信息栏、delegate 选中块与回退文字色全套参数化。

交互规则(M5 两模式焦点模型):
- **呼出后焦点默认在面板自身(导航模式)**:
  - `←→` 横移 ±1,`↑↓` 纵移 ±列数,`PgUp/PgDn` ±3 行,`Home/End` 首/末项;
  - `Enter` 上屏,`Esc` 关闭;`+`(含 `=`)下一分类,`-`(含 `_`)上一分类;
  - 可打印字符 / 退格自动转入搜索框(输入模式);
- **输入模式(焦点在搜索框)**:`←→` 控制文本光标(QLineEdit 默认);`↑↓` 离框回面板导航模式并纵移一行;`Tab` 框↔面板互换;
- 搜索框有文字 = 搜索模式(分类栏淡化),`1-9` 直选前 9 项(高频加速);清空 → 回分类浏览;
- **切换分类(`+`/`-` 或鼠标点选)总是先清空搜索文本再切换**(消「分类切了结果还是搜索结果」的困惑);
- 上屏后行为可配置:`panel.close_after_submit`(默认 true,提交即关);`Shift+Enter` 且 `panel.shift_enter_keeps_open`(默认 true)时保持面板,提交后焦点「还原目标→注入→抢回」、选中项下移一行,便于连续上屏;
- **热键末键残留过滤**:热键呼出时触发键(如 ctrl+alt+**e** 的 E)常仍被按住,OS 自动重复会落进刚拿焦点的面板;呼出即武装过滤——吞掉同键值 KeyPress 直到观察到 KeyRelease(1s 超时兜底);
- 右键 emoji → 菜单:添加别名 / 编辑别名 / 移除 / 复制字符;
- 底部信息栏显示:当前高亮项的大图 + 中文名 + 英文名 + 码点 + 已配置别名;
- emoji 渲染字体:**`QFont("Segoe UI Emoji")`**(Windows 自带彩色 emoji 字体;Qt6 支持彩色字体渲染;若发现渲染为黑白,检查 QFontDatabase 中字体是否存在,勿用默认字体);
- 窗口标志:`Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool`(Tool = 不占任务栏)。

---

## 6. 关键模块实现细节

### 6.1 全局热键(Hotkey)
- `keyboard.add_hotkey(hotkey_str, on_hotkey, suppress=False)`,`hotkey_str` 形如 `"alt+e"`(keyboard 库语法,设置窗录制后写入 config);
- `on_hotkey` 在钩子线程执行,内容仅:`GetForegroundWindow()` 记录 → Qt 信号投递主线程 → 面板 show;
- 修改热键 = 先 `remove_hotkey` 再 `add_hotkey`(keyboard 库不支持原地改)。

### 6.2 面板显示定位
```python
pt = QCursor.pos()                      # 光标屏幕
scr = QGuiApplication.screenAt(pt)      # 所在显示器
geo = scr.availableGeometry()
w, h = panel.size().width(), panel.size().height()
x = min(max(pt.x() - w // 2,  geo.left() + 8), geo.right()  - w - 8)
y = min(max(pt.y() + 16,      geo.top()  + 8), geo.bottom() - h - 8)
panel.move(x, y); panel.show(); panel.raise_(); panel.activateWindow()
```

### 6.3 搜索与打分(Search)
启动时:`emojis = json.load(index)` + 别名合并 → 预展开为扁平匹配列表:
```python
# 每个 (emoji_idx, term, term_type, weight)
# term_type ∈ {en, zh, py, abbr, alias};  weight: alias=1.2, 其余=1.0
```
查询 `query(s)`:
```python
q = s.strip().lower()
# 档位:3=某 term == q;2=term.startswith(q);1=q in term
# 得分 = tier * 20000 + min(freq, 9999) * weight   ← 基数须 > 9999*1.2≈12000,
#                                              否则高频前缀可反超低频精确命中(实测修正)
# 取 top 50,同分按码点升序;同一 emoji 多词命中先取最高分去重
```
纯内存遍历(~3700 emoji × ~30 词 ≈ 11 万项,Python 线性扫 <10ms,可接受;若实测慢,再按首字母建桶,勿提前优化)。

### 6.4 Unicode 上屏 + 焦点还原(Sender)
```python
import ctypes
user32 = ctypes.windll.user32

INPUT_KEYBOARD, KEYEVENTF_UNICODE, KEYEVENTF_KEYUP = 1, 0x0004, 0x0002

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class INPUT(ctypes.Structure):
    class _I(ctypes.Union):
        class _S(ctypes.Structure):
            _fields_ = [("ki", KEYBDINPUT)]
        _fields_ = [("ki", KEYBDINPUT)]
    _anonymous_ = ("i",)
    _fields_ = [("type", ctypes.c_ulong), ("i", _I)]

def type_text(hwnd: int, text: str) -> bool:
    if not restore_focus(hwnd):          # 见下
        return False
    for unit in text.encode("utf-16-le") 拆成 2 字节组:
        wScan = int.from_bytes(unit, "little")
        down = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, wScan, KEYEVENTF_UNICODE, 0, None))
        up   = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, wScan, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, None))
        user32.SendInput(2, ctypes.byref(down) 之类数组, ctypes.sizeof(INPUT))
    return True
```
(以上为骨架示意,落地时按 ctypes 结构体对齐规范写全,注意 x64 下 INPUT 结构含 padding。
**实测硬约束:union 必须含 MOUSEINPUT/KEYBDINPUT/HARDWAREINPUT 全部三成员**,
只写 KEYBDINPUT 时 sizeof=32≠40,SendInput 会按错误步长读数组。)

焦点还原 `restore_focus(hwnd)`:
```python
# 预算式轮询(默认 300ms,记事本冷切换实测会超 50ms):
#   while 未到 deadline:
#       user32.SetForegroundWindow(hwnd)
#       4 次 × 5ms 校验 GetForegroundWindow() == hwnd → 成功返回 True
#       首轮失败 → keybd_event 敲一下 Alt(VK_MENU)解前台锁后继续
#   超预算 → 返回 False(上层走 FR6.4 降级)
```
时序约定:**先 hide 面板,再还原焦点,再注入**(面板可见时会抢走注入目标)。

### 6.5 IME 状态检测(IME)
```python
hwnd = user32.GetForegroundWindow()
hime = imm32.ImmGetDefaultIMEWnd(hwnd)
# 两级判定(ime.ime_transcribing,FR4.3 门禁):
open = user32.SendMessageW(hime, WM_IME_CONTROL(0x283), IMC_GETOPENSTATUS(5), 0)
# open == 0 → 纯英文键盘 → 放行
mode = user32.SendMessageW(hime, WM_IME_CONTROL(0x283), IMC_GETCONVERSIONMODE(1), 0)
# mode & (IME_CMODE_NATIVE(0x1) | IME_CMODE_FULLSHAPE(0x8)) → 中文/全角 → 拦截
# mode == 0 → 英文半角子模式 → 放行(MS 拼音实测:中文子模式 1025,英文 0)
```
- Expander 在每次进入 `::` 录制态前检查一次 + 录制期间每 500ms 复查,发现 IME 转写中 → 丢弃缓冲、状态复位;
- 进程黑名单:`tid` 反查进程名,黑名单内直接旁路;
- 探针结论(2026-10-01 真机数据):`ImmGetConversionStatus` 直连(AttachThreadInput)在现代 TSF 应用上 `ImmGetContext` 恒 NULL,死路;`WM_IME_CONTROL IMC_GETCONVERSIONMODE` 是唯一可用的子模式探针(**必须用文档值 0x0001**,论坛讹传 0x0101 不响应)。已知极端情况:不响应该消息的 IME 在中文态 mode 亦为 0,会被误判为英文态(扩展介入),接受并记录;英文全角(仅 FULLSHAPE 位)因产出非 ASCII、回删镜像会错位,一并拦截。

### 6.6 文本扩展:`::` 候选条(M5 重设计,Expander 状态机 + CandidateBar)

**形态**(输入法式叠加条,独立于主面板):
- 触发前缀(默认 `::`)输完**立即显示**横条:每格上为 emoji(不透明)、下为「序号 匹配词」小字,选中格高亮;高 ~64px、格宽 ~56px、最多 9 格,深/浅主题;
- 空缓冲显示默认候选 = 频率 top(9)+ 固定常用条补足,词条「常用」;
- **组合文本照常打进目标应用**(真实文本可见,条只是叠加提示);提交时空格/Enter 被吞 + 回删 `前缀+缓冲` 再注入(单次 SendInput 原子完成,复用 §6.4);
- 字母前缀过滤:**全部词型参与**(en/zh/py/abbr/alias——kw_py 在内,`::shi` → 💩 即此路径;M4 旧「精确全等静默替换表」漏拼音是 BUG① 真因之一);无命中条**不关**(灰暗「无匹配」提示,继续打字可恢复);
- 定位:`GetGUIThreadInfo` 取前台 caret,置于光标下方 ~20px;无 caret(终端等)回退鼠标位置;屏幕边缘收拢、底部放不下翻到上方;每次 update 重定位(跟随打字);
- **点击外部关闭**:非激活窗口收不到跨进程点击事件,条可见期间以 20ms QTimer 轮询 `GetAsyncKeyState(VK_LBUTTON)` 上升沿——光标不在条矩形内 → 收条(已打文本保留原样);在条内 → 忽略轮询,Qt `mousePressEvent` 正常收到,做点选提交。

**状态机**(IDLE/ARMED 不变;REC 态抑制矩阵,「有候选」= 主线程每次条刷新后回写的 `has_candidates` 标志,GIL 原子读):
```
IDLE --(':')--> ARMED --(':')--> REC(发 show)+ 字母逐键发 update
```

| 按键(REC 态) | 有候选 | suppress | 动作 / compose 事件 |
|---|---|---|---|
| 字母 a-z | — | 放行 | 入缓冲,发 `update` |
| 数字 1-9 | 有 | **吞** | 发 `digit n`(n=格序;`back`=前缀+缓冲) |
| 数字(含 0) | 无 | 放行 | 入缓冲(`100` 类词),发 `update` |
| 空格 / Enter | 有 | **吞** | 发 `commit`(`back`=前缀+缓冲),复位 |
| 空格 / Enter | 无 | 放行 | 复位,发 `close`(未命中原样放行) |
| Esc | — | **吞** | 复位,发 `close` |
| ↑ / ↓ | — | **吞** | 复位,发 `close`(用户指定) |
| ← / → | 有 | **吞** | 发 `left` / `right`(条内移动选择,不达目标应用) |
| ← / → | 无 | 放行 | 复位,发 `close`(光标移动会破坏回删镜像假设) |
| Backspace | — | 放行 | 应用侧自删 + 状态机镜像 pop → `update`;缓冲已空 → 复位 + `close` |
| 修饰键(shift/ctrl/alt/windows 及左右变体、alt gr) | — | 放行 | **不打断状态**:前缀 `:` 需按住 Shift 输入,两个前缀键之间的 shift 事件(松开重按/按住触发的系统自动重复)不得复位武装态(M5 真机 BUG① 真因,E2E 程序化驱动测不出) |
| 其他非单字符字母数字(功能键/Tab/Caps Lock/numpad) | — | 放行 | 复位,发 `close` |
| 缓冲 ≥24 字符 | — | 放行 | 复位,发 `close` |
| gate 复查失败(500ms 节流) | — | 放行 | 复位,发 `close` |

- `Expander(gate, prefix)` 无 matcher 参数——**字符解析/查候选全部移到主线程**(钩子线程只做 O(1) 状态转移);`ExpandBridge.compose = Signal(dict)` 事件载荷 `{"event", "buf", "n", "back"}`;
- 提交动作统一在主线程(app `_commit_candidate`):收条 → `get_foreground_window` → `type_text(hwnd, char, backspaces=back)` → 失败剪贴板降级 + 托盘气泡(FR6.4,修 M3 起扩展路径无降级的不对称)→ 成功频率 +1;
- 候选源 `search.prefix_candidates(buf, limit=9, use_builtin)`:前缀匹配全词型;同 emoji 取最优词(别名 1.2 权重优先、词短优先);排序 = 精确全等 > 词短 > 频率加权,码点 tie-break;
- suppress 实现:`keyboard.hook(callback, suppress=True)`;回调返回值遵循 `_winkeyboard.prepare_intercept` 约定:**True=放行 / False=拦截**(与直觉相反,M3 实测踩坑)。异常路径一律 `(False, None)` 默认放行,任何 bug 不得卡死键盘;
- 注入不在钩子回调内执行(SendInput 在低级钩子内重入有超时风险),compose 事件经 queued 信号排队至主线程。

### 6.7 钩子保活(Watchdog)
- Windows 对低级钩子回调有超时限制(注册表 `LowLevelHooksTimeout`,未配置时系统默认约 300ms),Python GC/卡顿超时会被系统静默摘除钩子;
- 对策(实现偏差,原案「发测试键校验」弃用——全局注入在本机不可靠且会向用户前台应用打进按键):每 30s 校验 `keyboard` 库监听线程存活,失活 → 置 `listening=False` 强制重启监听 + 业务层重挂全部钩子,托盘气泡提示(失活事件本身 ≤1 次/小时节流);
- 同时把 GC 冻结:`gc.freeze()` 于启动完成后,减少全代回收停顿。

### 6.8 自启动
```python
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
# 开:winreg.SetValueEx(HKEY_CURRENT_USER, RUN_KEY, "EmojiPalette", 0, REG_SZ, 命令串)
# 关:winreg.DeleteValue(...)
```
- 命令串:打包态 = exe 完整路径;开发态 = `python -X utf8 -c "import sys; sys.path.insert(0, r'<src>'); from emoji_palette.app import main; main()"`(Run 键无法设置环境变量,须内联 PYTHONPATH 与 UTF-8 模式);
- json `autostart` 为意图源:应用启动时若与注册表不一致,以 json 为准写入(否则设置窗读注册表会与 json 永久脱节);设置窗/托盘切换时两处同步更新。

---

## 7. 已知坑清单(接手前通读,均已在设计中给出对策)

| # | 坑 | 对策(见) |
|---|---|---|
| 1 | 中文 IME 开启时 `::` 扩展拿不到原始按键 | §6.5 IME 检测 + 暂停 |
| 2 | `SetForegroundWindow` 受 Windows 前台锁限制偶发失败 | §6.4 Alt 技巧 + 轮询校验 + 降级 |
| 3 | SendInput 无法输入到提权(UAC)窗口 | FR6.4 剪贴板降级 + 提示;设置中提供「以管理员运行」指引 |
| 4 | Python 钩子回调超时被系统摘钩 | §6.7 watchdog + gc.freeze |
| 5 | Qt 默认字体渲染 emoji 为黑白/豆腐块 | §5 显式 `QFont("Segoe UI Emoji")` |
| 6 | 非 BMP emoji 是代理对,单个 SendInput 不够 | §6.4 UTF-16 拆分 |
| 7 | suppress 钩子异常会卡死整个键盘输入 | §6.6 全路径 try/except 默认放行 |
| 8 | 全屏游戏/远程桌面注入异常 | 进程黑名单 + 失焦即停面板 |
| 9 | 面板抢焦点后注入目标错乱 | 先 hide → 再还原 → 再注入 的固定时序 |
| 10 | 多显示器下面板跑到屏幕外 | §6.2 按 `screenAt` 定位 + 边缘收拢 |
| 11 | keyboard 库热键与 suppress 钩子并存时的重入 | 统一走同一个 hook 句柄管理(watchdog 重挂两者一起) |
| 12 | Win10 与 Win11 的 Segoe UI Emoji 版本差异(新 emoji 显示为豆腐) | 数据层标注 `version` 字段,设置提供「隐藏本机不支持的版本」开关(读取系统字体支持度,选做) |
| 13 | **自定义 QWidget 子类不自动绘制 QSS 背景**:顶层 `WA_TranslucentBackground` 窗在本环境(PySide6 6.11.2/Win10)任何 QSS 背景写法都不绘制 → 整窗 alpha=0,Windows layered 窗对 alpha=0 像素做命中测试穿透,滚轮/点击落给后方应用;子控件 QSS `background: transparent` 同样会把该区域 alpha 抹零 | 根背景一律 `paintEvent` + `QPainter` 自绘(面板与候选条同法);网格关 `setAutoFillBackground`(让根背景透出);另附带发现:`QKeySequence(...)[0]` 返回 `QKeyCombination` 须 `.toCombined()` 取整键值 |

---

## 8. 配置文件 `config.json`(完整示例)

```json
{
  "hotkey": "alt+e",
  "panel": {
    "width": 600,
    "height": 440,
    "icon_size": 36,
    "theme": "dark",
    "position": "cursor",
    "show_recent": true,
    "recent_count": 24,
    "close_after_submit": true,
    "shift_enter_keeps_open": true
  },
  "expansion": {
    "enabled": true,
    "prefix": "::",
    "builtin_keywords": true,
    "process_blacklist": ["game.exe", "mstsc.exe"]
  },
  "autostart": true,
  "advanced": {
    "hook_watchdog": true,
    "fallback_to_clipboard": true,
    "hide_unsupported": true
  }
}
```
首启无文件 → 写入默认值;任何字段缺失 → 代码内默认值兜底(不抛错)。

历史死配置(读取忽略,保留仅为说明):`panel.columns`(M2 起网格列数按视口宽度动态计算)、`expansion.trigger_key`(M5 起提交键固定为 空格+Enter 双通道)。

---

## 9. 项目目录结构(交付物形态)

```
emoji-palette/
├── DESIGN.md                # 本文档
├── requirements.txt         # PySide6, keyboard, pypinyin, pyinstaller(打包用)
├── build_data.py            # 数据管道:下载→解析→拼音→data/index.json(支持 --offline 用缓存)
├── data/
│   ├── raw/                 # 下载缓存(gitignore)
│   └── index.json           # 构建产物(gitignore,首启检测缺失自动引导运行 build_data.py)
├── src/emoji_palette/
│   ├── __main__.py          # 入口:python -m emoji_palette
│   ├── app.py               # QApplication 装配、单实例锁(命名互斥体,见 DEVLOG M1)、托盘
│   ├── panel.py             # 搜索面板(§5)
│   ├── settings_ui.py       # 设置窗 + 别名管理表格
│   ├── hotkey.py            # 热键注册/改绑 + Watchdog
│   ├── expander.py          # 文本扩展状态机(§6.6)
│   ├── candidate.py         # :: 候选条叠加窗口(§6.6)
│   ├── ime.py               # IME 状态 + 进程黑名单(§6.5)
│   ├── sender.py            # SendInput/焦点还原/剪贴板降级(§6.4)
│   ├── search.py            # 索引加载/查询打分(§6.3)
│   ├── config.py            # 配置/别名/频率读写
│   └── groups.py            # Unicode 组名中英映射常量
├── tests/
│   ├── test_search.py       # 打分与四路命中(屎/翔/shit/shi/bb → 💩 必须全过)
│   ├── test_expander.py     # 状态机转换(表驱动)
│   └── test_build_data.py   # 索引完整性(数量、字段、无重复)
└── build.spec               # PyInstaller 配置
```

---

## 10. 开发里程碑

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| M0 | build_data.py + 索引 | `data/index.json` ≥3700 条;💩 条目含 zh/en/py/abbr 四类词;单测过 |
| M1 | 热键 + 面板 + 搜索 + 回车上屏 | `Alt+E` 呼出 <50ms;打 `shi` 首位见 💩;Enter 上屏进记事本;Esc 即走 |
| M2 | 分类浏览 + 频率学习 + 信息栏 | 8 分类可切换;常用栏随使用更新 |
| M3 | 右键别名 + 文本扩展 + IME 检测 | `::shit ␣`→💩(英文态);中文输入法开启时扩展自动失效不干扰打字 |
| M4 | 托盘 + 设置窗 + 自启动 + 打包 | PyInstaller 单 exe 可用;开机自启可开关;热键可改 |
| M5 | 面板重构 + 交互重做 + `::` 候选条 + 双 BUG 修复 | 网格空白区滚轮不穿透;导航模式/+/-/keep-open;`::shi ␣`→💩;热键末键不进搜索框 | ◐ 代码+离屏验证完成(2026-10-01),真机复验清单见 §11 |

M1 即最小可用产品(已优于 Win+.),M4 为完整交付。

---

## 11. 手动验收清单(最终交付前逐项过)

1. 记事本中:呼出 → `shit` / `屎` / `shi` / `bb` 四种输入,💩 均在首位或前三位;
2. 终端(Windows Terminal)、VS Code、浏览器地址栏、微信输入框:上屏均为 Unicode 字符(粘贴到 hex viewer 验证为 `F0 9F 92 A9`);
3. 上屏前后,用户剪贴板内容不变;
4. Esc、点外部、上屏完成,面板按 `close_after_submit` 配置立即消失或保持;Shift+Enter 上屏后面板不关、选中项下移一行、可继续连续上屏;
5. 中文输入法开启:打 `::shit`+空格 原样输出不误伤;关闭 IME 后同样操作变 💩;
6. 打游戏黑名单进程前台:热键/扩展完全无感;
7. 任务管理器确认常驻内存 <150MB,空闲 CPU≈0;
8. 重启机器:自启动生效,托盘可见;
9. 连续打字 10 分钟:无丢键、无卡顿(钩子稳定);
10. 修改热键/别名/主题:即时生效,重启后保留。

M5 增补(候选条 + 新交互,真机逐项过):
11. **按住热键稍久**再松开呼出面板:搜索框内无热键末键残留字符(如 ctrl+alt+e 的 `e`);
12. 网格空白区域滚轮:面板自身滚动,不再穿透到后方应用;
13. 面板呼出后直接按 `←→↑↓` 即导航(焦点默认在面板,不在搜索框);`+/-` 切分类且搜索文本被清空;
14. 候选条全链路:记事本打 `::` 条出现(默认常用)→ `shi` 筛出 💩 居首 → 空格上屏(回删 5 注入 1)→ `::s` + 数字 2 直选 → `←→` 移动选择 → Esc 关条且已打文本保留 → 无命中时条保持「无匹配」态 → 点击条外收条。

---

## 12. 约束与风格

- 代码:Python 3.11+,类型注解全量,ruff 通过;
- 注释与 UI 文案:中文;标识符:英文;
- 所有用户数据写入 `%APPDATA%\EmojiPalette\`,严禁散落;
- 异常处理原则:任何输入路径的异常都不得中断全局钩子(键盘安全 > 功能完整);
- 许可:私有项目,作者自用。

---

*设计稿版本:v1.1(2026-10-01):M5 面板视觉重构 + 两模式焦点模型 + `::` 候选条重设计(§5/§6.6/§8 重写,FR1.4/FR1.5/FR4.1/FR4.2 修订,坑 #13 新增)。实现过程中如遇本文档未覆盖且影响架构的决策,先更新本文档再写代码。*
