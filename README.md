# Emoji Palette

Windows 表情快速上屏工具:呼之即来、呼之即去、键盘流优先、中英拼音混搜、纯 Unicode 上屏。

针对 `Win + .` 的三个老大难:

- 搜索不认中文和拼音(`屎` / `shi` / `bb` 都搜不到 💩)
- 只按使用频率排序,无相关度
- 依赖鼠标点选,键盘方向键逐格移动,低效

Emoji Palette 的答案:全局热键呼出 → 打字搜索(中文 / 英文 / 拼音全拼 / 拼音缩写四路命中)→ 回车上屏 → 面板即走。上屏的是**纯 Unicode 字符**(Win32 SendInput 注入,不经剪贴板),终端、代码编辑器、任何输入框通用——不会像搜狗/微信输入法那样变成图片。

## 特性一览

- 🔍 四路搜索:`屎` / `shit` / `shi` / `bb` → 💩;三级排序(匹配档位 > 使用频率 > 码点),越用越准
- ⌨️ 全键盘流:方向键导航、数字键直选、`Shift+Enter` 连续上屏
- 🚀 `::` 文本扩展:任意输入框打 `::shit` + 空格 → 💩,候选条跟随光标、不抢焦点
- 🏷️ 自定义别名:右键 emoji 添加(`翔` → 💩),搜索与扩展共用,即时生效
- 📦 Unicode 全量(3700+)+ 8 大分类 + 常用栏(频率学习)
- 🀄 IME 感知:中文输入法转写模式时扩展自动让位,不干扰打字
- 🎛️ 托盘 + 设置窗:热键 / 扩展 / 别名 / 外观 / 开机自启
- 🛡️ 键盘安全:钩子异常一律放行,失活自动重挂,退出必卸钩子

完整说明见 [docs/FEATURES.md](docs/FEATURES.md)。

## 安装

### 方式一:Release(推荐)

从 [Releases](../../releases) 下载 `EmojiPalette.exe`,双击运行,托盘出现 😀 图标即就绪。默认热键 `Alt+E`。

### 方式二:从源码

要求 Python 3.11+,Windows 10/11。

```bash
pip install -r requirements.txt   # 或: uv sync
python build_data.py              # 构建数据索引(首次必须,需联网)
python -m emoji_palette           # 运行
```

打包单文件 exe:

```bash
pyinstaller build.spec
```

## 使用

| 操作 | 方式 |
|---|---|
| 呼出 / 收起面板 | `Alt+E`(默认,可改) |
| 搜索 | 打字即搜:中文 / 英文 / 拼音 / 缩写 |
| 上屏 | `Enter`(选中的)/ 数字 `1-9`(前 9 项)/ 点击 |
| 连续上屏 | `Shift+Enter`(面板不关,自动下移) |
| 关闭 | `Esc` / 点击面板外 / 上屏后自动 |
| 文本扩展 | `::shit` + 空格 → 💩(前缀可改) |
| 扩展候选条 | `←→` 移动,数字直选,`↑↓` 或 `Esc` 关条 |
| 添加别名 | 面板中右键 emoji |
| 设置 | 托盘右键 → 设置… |

用户数据(配置 / 别名 / 频率)位于 `%APPDATA%\EmojiPalette\`。

## 数据来源

- [Unicode emoji-test](https://www.unicode.org/Public/emoji/) — 全量码点与分类
- [Unicode CLDR annotations](https://github.com/unicode-org/cldr-json)(en / zh)— 中英关键词
- [emojilib](https://github.com/muan/emojilib) — 英文俚语补充
- [pypinyin](https://github.com/mozillazg/python-pinyin) — 拼音预计算(仅构建期)

数据在构建期下载合并为本地索引,运行期零网络。

## 开发

```bash
python -m pytest tests    # 89 项测试
python -m ruff check src tests build_data.py
```

目录结构:

```
build_data.py        # 数据管道(下载 → 解析 → 拼音 → data/index.json)
build.spec           # PyInstaller 配置
src/emoji_palette/
  app.py             # 应用装配 / 托盘 / 单实例
  panel.py           # 搜索面板 UI
  candidate.py       # :: 扩展候选条
  expander.py        # :: 录制状态机
  search.py          # 索引与查询打分
  sender.py          # SendInput 注入 / 焦点还原 / 剪贴板降级
  ime.py             # IME 状态检测 / 进程黑名单
  hotkey.py          # 全局热键 / 钩子看护
  config.py          # 配置 / 别名 / 频率 / 自启动
  settings_ui.py     # 设置窗
  groups.py          # 分组中英映射
tests/               # 测试
docs/FEATURES.md     # 特性清单
```

## License

[MIT](LICENSE)
