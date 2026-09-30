# Emoji Palette 开发记录

> 配套文档:[DESIGN.md](../DESIGN.md)(需求与设计唯一来源)。本文件跟踪里程碑进度与开发过程,**开发时随时更新**,便于跨会话接续。

## 约定

- 每完成一个可验证的工作单元,在「开发日志」新增一条(最新在最上),写明:做了什么、验证结果、遗留问题;
- 里程碑状态仅在该里程碑**验收标准全部达成**后才改为 ✅;
- 遇到 DESIGN.md 未覆盖的架构级决策:先改 DESIGN.md,再在此记录决策原因。

## 里程碑总览(DESIGN.md §10)

| 里程碑 | 内容 | 验收标准 | 状态 |
|---|---|---|---|
| M0 | build_data.py + 索引 | `data/index.json` ≥3700 条;💩 条目含 zh/en/py/abbr 四类词;单测过 | ✅ 完成(2026-09-30) |
| M1 | 热键 + 面板 + 搜索 + 上屏 | `Alt+E` 呼出 <50ms;打 `shi` 首位见 💩;Enter 上屏进记事本;Esc 即走 | ⬜ 未开始 |
| M2 | 分类浏览 + 频率学习 + 信息栏 | 8 分类可切换;常用栏随使用更新 | ⬜ 未开始 |
| M3 | 右键别名 + 文本扩展 + IME 检测 | `::shit ␣`→💩(英文态);中文 IME 开启时扩展自动失效不干扰 | ⬜ 未开始 |
| M4 | 托盘 + 设置窗 + 自启动 + 打包 | PyInstaller 单 exe 可用;开机自启可开关;热键可改 | ⬜ 未开始 |

**当前:** M0 完成,下一步 M1(热键 + 面板 + 搜索 + 上屏,最小可用产品)。

## 开发日志

### 2026-09-30 · M0 数据管道完成 ✅

**产出:**
- `data/index.json`:**3781 条**(≥3700 ✓,emoji-test 16.0,1217 KB,跳过 Component 组、仅 fully-qualified);
- 💩 条目四类词齐全:`kw_zh=[大便,好臭,屎,粑粑…]`、`kw_en=[poo,poop,shit,crap…]`、`kw_py=[dabian,shi,baba…]`、`kw_abbr=[db,s,bb…]` —— FR3.1 要求的 屎/shit/shi/bb 四路命中数据面就绪;
- 测试 7 passed:拼音推导、码点归一化、数量、字段完整性(含 group_zh 全量映射)、码点去重、💩 四类词、关键词长度一致性。

**数据源踩坑(重要):**
1. cldr-json 仓库已改版:没有 `main/` 层,现路径为 `cldr-json/cldr-annotations-full/annotations/{lang}/annotations.json`(DESIGN.md §4.1 中的路径已过时);
2. CLDR 注解的键是 **emoji 字符本身**而非十六进制码点 → 逐字符 `ord()` 转码点再归一化,变体选择符/ZWJ 一并转出,与 emoji-test 码点序列天然对齐;
3. emojilib 实际路径 `dist/emoji-en-US.json`,v3 格式为 字符→关键词数组(加载器已兼容新旧格式);raw.githubusercontent 偶发瞬断,curl --retry 可作缓存预热兜底;
4. emoji 17.0 的 emoji-test.txt 尚未发布(404),按设计回退 16.0 生效。

**设计偏差备忘:**
- FR3.1 示例中的 `bianbian` 未覆盖(CLRD zh 对 💩 给的是 粑粑→`baba` 而非 便便)→ M3 用户别名机制兜底,不改数据管道;
- 新增 `ver` 字段(E 版本号,取自行注释)——为坑 #12「隐藏本机不支持的版本」预留。

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
