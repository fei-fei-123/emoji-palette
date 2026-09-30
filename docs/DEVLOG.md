# Emoji Palette 开发记录

> 配套文档:[DESIGN.md](../DESIGN.md)(需求与设计唯一来源)。本文件跟踪里程碑进度与开发过程,**开发时随时更新**,便于跨会话接续。

## 约定

- 每完成一个可验证的工作单元,在「开发日志」新增一条(最新在最上),写明:做了什么、验证结果、遗留问题;
- 里程碑状态仅在该里程碑**验收标准全部达成**后才改为 ✅;
- 遇到 DESIGN.md 未覆盖的架构级决策:先改 DESIGN.md,再在此记录决策原因。

## 里程碑总览(DESIGN.md §10)

| 里程碑 | 内容 | 验收标准 | 状态 |
|---|---|---|---|
| M0 | build_data.py + 索引 | `data/index.json` ≥3700 条;💩 条目含 zh/en/py/abbr 四类词;单测过 | ⬜ 未开始 |
| M1 | 热键 + 面板 + 搜索 + 上屏 | `Alt+E` 呼出 <50ms;打 `shi` 首位见 💩;Enter 上屏进记事本;Esc 即走 | ⬜ 未开始 |
| M2 | 分类浏览 + 频率学习 + 信息栏 | 8 分类可切换;常用栏随使用更新 | ⬜ 未开始 |
| M3 | 右键别名 + 文本扩展 + IME 检测 | `::shit ␣`→💩(英文态);中文 IME 开启时扩展自动失效不干扰 | ⬜ 未开始 |
| M4 | 托盘 + 设置窗 + 自启动 + 打包 | PyInstaller 单 exe 可用;开机自启可开关;热键可改 | ⬜ 未开始 |

**当前:** 初始化完成,即将启动 M0(数据管道)。

## 开发日志

### 2026-09-30 · 依赖环境攻坚(conda DLL 劫持 → uv 纯净环境)

**过程与结论(重要,勿走回头路):**

1. 默认 PyPI 源直连极慢 → 必须走镜像;**清华镜像对 PySide6 同步异常**(报 `from versions: none`),官方 PyPI 与阿里云正常 → 统一阿里云,已固化到项目根 [uv.toml](../uv.toml);
2. 本机网络对**大文件长连接会静默断连**:pip 装 PySide6(约 350MB 轮子)两次卡死(缓存字节数 25s+ 完全不动,pip 读超时救不回);小包秒装 → 结论:大轮子用 **uv**(并行分块+续传),pip 只适合小包;
3. **conda Python 是 PySide6 崩溃元凶**:最初 venv 基于 miniconda3 的 Python 3.14.6,`from PySide6 import QtCore` 报 WinError 127(入口点缺失)。排查:shiboken6 正常、VC 运行库版本均新(14.44~14.50)、清理 PATH 无效、预加载自带运行库无效、PE 导入表逐项检查通过 → 定性为 conda Python 启动时把 `miniconda3/Library/bin` 注册为 DLL 搜索目录(优先级高于 System32),系统内多份 `icuuc.dll`(System32 旧版 ICU vs conda ICU 78)抢绑定导致;
4. **最终方案:`uv venv` 托管的纯净 CPython 3.12.14** 重建 `.venv`,所有依赖装完后验证全过。

**验证结果:**
- PySide6 6.11.2 导入正常,Qt 6.11.2;
- `Segoe UI Emoji` 字体被 Qt 识别(坑 #5 前置验证 ✅);
- pypinyin:`便便` → `bianbian` / `bb`(与 DESIGN.md §4.2 示例一致);
- keyboard / pytest 可用。

**环境使用须知(接手必读):**
- 解释器:`.venv\Scripts\python.exe`(uv 托管 CPython 3.12.14,**勿用 miniconda 的 Python 建 venv**);
- 装依赖:项目根目录下 `uv pip install -r requirements.txt`(uv.toml 已固定阿里云镜像);uv 本体在旧环境丢失时 `pip install uv` 重取;
- GitHub 直连可用(uv 下载 CPython 验证过),后续 CLDR/emojilib 数据管道下载无虞。

### 2026-09-30 · 项目初始化

**已完成:**
- 项目骨架:按 DESIGN.md §9 建齐 `src/emoji_palette/` 全部 11 个模块桩文件(含对应设计章节引用)、`build_data.py`、`tests/` 3 个测试桩;
- `requirements.txt`(运行期 PySide6/keyboard;构建期 pypinyin;打包 pyinstaller;测试 pytest);
- `.gitignore`(排除 `data/raw/`、`data/index.json`、`.venv/`、打包产物);
- `docs/DEVLOG.md`(本文件)、`uv.toml`(镜像配置);
- git 仓库初始化(main 分支)。

**遗留 / 待办:**
- ⬜ 首次 commit(等用户确认);
- ⬜ 启动 M0:数据管道(build_data.py)。
