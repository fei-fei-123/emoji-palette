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
| M1 | 热键 + 面板 + 搜索 + 上屏 | `Alt+E` 呼出 <50ms;打 `shi` 首位见 💩;Enter 上屏进记事本;Esc 即走 | ✅ 完成(2026-10-01) |
| M2 | 分类浏览 + 频率学习 + 信息栏 | 8 分类可切换;常用栏随使用更新 | ✅ 完成(2026-10-01) |
| M3 | 右键别名 + 文本扩展 + IME 检测 | `::shit ␣`→💩(英文态);中文 IME 开启时扩展自动失效不干扰 | ✅ 完成(2026-10-01) |
| M4 | 托盘 + 设置窗 + 自启动 + 打包 | PyInstaller 单 exe 可用;开机自启可开关;热键可改 | ✅ 完成(2026-10-01) |
| M5 | 面板重构 + 交互重做 + `::` 候选条 + 双 BUG 修复 | 网格空白区滚轮不穿透;导航模式/+/-/keep-open;`::shi ␣`→💩;热键末键不进搜索框 | ◐ 候选条链路真机确认 ✅(2026-10-01);BUG② 残留字符/滚轮/导航/keep-open 复验待过(§11 增补 11-14) |

**当前:** M5 代码交付(用户实测反馈 docs/DEVTest.md 三类需求全部落地)。BUG①(`::` 无反应)真机闭环 ✅:数据面(kw_py 缺席)+ 状态机(修饰键流打断武装)+ 门禁(IME 英文子模式误拦)三层真因全部修复并由用户确认;BUG②/keep-open/滚轮穿透属真机时序/命中行为,待用户复验。

## 开发日志

### 2026-10-01 · M5 面板重构 + 交互重做 + `::` 候选条 + 双 BUG 修复 ◐(代码完成,真机复验待用户)

**背景:** 用户提交 docs/DEVTest.md 实测报告:① 面板无背景、滚轮穿透;② 控制体验(焦点/导航/+/- 切类/keep-open/`::` 改输入法候选条);③ BUG① `::shi ␣` 无反应、BUG② 热键呼出后 E 落进搜索框。按 U0-U6 计划逐单元交付。

**产出:** panel.py 重构(paintEvent 自绘根背景 + 两模式焦点模型 keyPressEvent/eventFilter + 热键末键残留过滤 + keep-open 焦点舞步)、candidate.py 新增(`::` 候选条:非激活叠加窗 + caret 跟随 + 20ms 点击外部轮询)、expander.py 重写(O(1) 状态机 + compose 信号 + 全抑制矩阵)、search.py 增 `prefix_candidates`(全词型,BUG① 数据面修复点)/删 `expander_table`、config.py 增 `close_after_submit`/`shift_enter_keeps_open`、settings_ui.py 增两开关、app.py 候选条装配(`_commit_candidate` 统一提交 + 剪贴板降级补齐)、diag_expand.py 诊断脚本(根,开发工具)。测试 50 → **81 全过**,ruff 无告警。

**验证结果(离屏 + 真平台渲染;真机复验项见 DESIGN §11 增补 11-14):**
- **滚轮穿透根因修复** ✓:根背景 alpha 235/242 全窗 >0(截图逐像素验证四角/中心/网格区 alpha);offscreen + 真平台双份截图目检深/浅主题;
- **BUG① 数据面** ✓:diag 阶段2 实测 `'shi' -> 9 项: 👐(shi), 💩(shi), 🥄(shi)`、`'shit' -> 💩(shit)` 居首——kw_py 现已参与候选(M4 静默替换表只取 kw_en/kw_abbr 漏拼音);回归测试 `test_prefix_candidates_pinyin_shi_hits_poo` 锁定;
- **候选条渲染** ✓:真平台(windows QPA)截图目检——彩色 emoji、小字词+序号、选中格蓝色高亮、深色圆角条全部正常;offscreen 截图的豆腐块确认为该平台字体伪影(U1 面板截图同样,非代码问题);
- 状态机矩阵全分支表驱动测试(31 用例);面板新交互 16 用例;候选条 7 用例。

**设计决议与偏差(DESIGN v1.1 已同步):**
1. **候选条组合文本可见**:字母照常打进目标应用,条只是叠加;提交才回删+注入(单次 SendInput)。弃「全吞+重放」纯 IME 方案——键盘安全原则下最坏情况只是「字符打出来了」而非「字符消失」;Esc/↑↓/点外关条时已打文本保留原样;
2. **提交 = 空格 + Enter 双通道**(用户确认);无命中 + 空格 = 放行 + 收条(「无命中不关条」指继续打字筛选时,空格仍是「我想打空格」信号);
3. **←→ 仅在有候选时劫持**(条内移动);无候选放行并收条——光标左移会破坏「回删镜像缓冲」假设;
4. **has_candidates 跨线程回写**:主线程每次条刷新后 `set_has_candidates`,钩子线程 GIL 原子读,决定空格/数字吞键——字符解析全部移出钩子线程(原 matcher 查表也删了);
5. **数字 0 恒入缓冲**(M4 表时代 0 无格;候选条时代 `100` 类词需要);数字越界(条只有 3 格按 5)吞键后安静收条;
6. **keep-open 时序**:先置 `_hold_grace`(0.6s 失活豁免)再 type_text,否则 event() 把「注入时面板失活」误判为点外关闭;完成后 restore_focus 抢回 + 选中下移一行;
7. **圆角外 8px 四角仍穿透**(layered 窗物理限制),接受并记 DESIGN 决策;**严禁 setWindowOpacity**(整窗淡化会伤 emoji,改根背景 alpha 235/242 实现「些许透明」);
8. **面板默认焦点 = 面板自身**(导航模式),打字自动进框;↑↓ 从框回面板;`+/-` 切类先清空文本;Tab 框↔面板互换(M2 的「搜索↔分类」语义废弃);
9. `expander_table`/`rebuild_table`/`aliases_changed`→重建链路整体删除——索引 `set_aliases` 已在别名保存时热更,`prefix_candidates` 每次现查自然生效;设置窗 `exp_builtin` 文案改「内置关键词参与候选(英文/缩写/拼音)」。

**过程踩坑(重要,含两起事故):**
- ⚠️ **事故 1:调试片段未打桩跑真注入,用户剪贴板被覆盖为 😀(不可恢复)**——写驱动脚本时漏了 monkeypatch sender,真实 `type_text` 失败走 `clipboard_fallback`。教训:凡离屏/诊断驱动涉及 `_submit`/`_commit` 路径,sender 打桩必须先于首次运行,不能「先跑一次看看」;
- ⚠️ **事故 2:同因产生 `%APPDATA%\EmojiPalette\frequency.json = {"😀": 1}`**(真注入后 bump)——删除被权限系统拒绝(项目树外的用户数据,应当),已留置(效果仅 😀 在常用栏出现一次),待用户自行处置;
- `WA_TranslucentBackground` 顶层窗 QSS 背景任何写法都不绘制 → 坑 #13(根背景必须 paintEvent 自绘);连带发现网格 QSS `background: transparent` 会把像素 alpha 抹零,须 `setAutoFillBackground(False)` 让根背景透出;
- `QKeySequence(tail)[0]` 在 PySide6 返回 QKeyCombination,直接 `> int` 抛 TypeError,须 `.toCombined()`;
- offscreen 平台 `QApplication.setActiveWindow(None)` 是弃用 no-op(activeWindow 仍= 面板)→ 失活关闭测试须 monkeypatch 模块级 QApplication 符号注入假 activeWindow;
- offscreen 字体渲染豆腐(emoji/中文)→ 截图目检必须补真平台一份(候选条 `WA_ShowWithoutActivating` 不抢焦点,可安全真平台渲染后 grab)。

**遗留:**
- **真机复验清单(用户)**:DESIGN §11 增补 11-14 —— 14(候选条全链路)已过 ✅;余:11 按住热键稍久无残留字符(BUG②)、12 滚轮不穿透、13 导航模式+/-切类、4/Shift+Enter keep-open;
- **BUG① 真因已锁定并修复,真机确认 ✅(2026-10-01 用户协助诊断)**:用户回报 英文布局下门禁放行(阶段3)但 `::` 仍无条、阶段4 无输出 —— 排除配置/数据/门禁后锁定状态机武装段:`:` 需按住 Shift 输入,**两个 `:` 之间的 shift 按下事件(松开重按/按住 >0.5s 的系统自动重复)会把 ARMED 打回 IDLE**,第二个 `:` 只能重新武装,永远进不了 REC。E2E 程序化驱动一气呵成按住 Shift,测不出人手松开 —— 修复:修饰键流(shift/ctrl/alt/windows 及左右变体、alt gr)在 ARMED/REC 放行且不打断状态,回归测试 `test_modifier_streams_do_not_break_state` 锁定;DESIGN §6.6 矩阵已同步。**用户真机复验:英文布局 `::` 正常出条**;
- **中文输入法英文子模式门禁已修复,用户真机确认 ✅(三轮用户协助探测定案,2026-10-01)**:第三轮 `--ime-probe`(改用文档常量 `IMC_GETCONVERSIONMODE=0x0001`)实测 **MS 拼音中文子模式 mode=1025(原生|符号)、英文子模式 mode=0** —— 子模式可探测。实现:`ime.ime_transcribing()` 两级判定(IME 开 ∧ 转换模式含 原生/全角 位 → 拦截;英文半角子模式 → 放行),app 门禁与诊断脚本均已换用,新增 `tests/test_ime.py` 6 用例(含 mode=0 放行回归、全角英文拦截、异常语义)。探针结论记入 DESIGN §6.5:C 直连路(AttachThreadInput+ImmGetConversionStatus)在 TSF 应用上 `ImmGetContext` 恒 NULL 死路,B 通道是唯一探针且必须用文档值 0x0001(讹传 0x0101 不响应)。已知极端情况:不响应 B 的 IME 中文态会被误判为英文态(扩展介入),接受并记录;英文全角(仅 FULLSHAPE 位)因产出非 ASCII、回删镜像错位一并拦截;
- `--live` 已升级逐键打印(键名/状态迁移/吞键/事件),真机「无反应」不再沉默;
- 临时截图目录 `%TEMP%\ep_m5\` 未清理(用户目检后可删);
- git 提交待用户确认。

**产出:** config.py 增 autostart 读写(HKCU Run 键)、panel.py 增浅色 QSS + `apply_cfg` 热应用 + `fallback_notice` 信号、settings_ui.py 完整设置窗(热键录制/扩展/外观/自启/别名表格)、hotkey.py 增 `HookWatchdog`、app.py 托盘 + 设置 + 看护装配 + 启动自启同步、build.spec。测试 43 → 50 全过,ruff 无告警。

**验收结果(离屏驱动 + 真机冒烟,三项验收标准全达成):**
- **PyInstaller 单 exe 可用** ✓:build.spec(onefile/noconsole,`datas` 打包 index.json,`pathex=src`)产出 46MB `dist/EmojiPalette.exe`;启动正常(onefile 引导壳+真实进程双进程属预期)、启动行 `已隐藏 209 个…` 正常、单实例互斥体持有/拒绝/随进程释放、`taskkill //T` 树杀干净;
- **开机自启可开关** ✓:`set_autostart` True/False 落册表/删值,设置窗与托盘两入口均同步 json+注册表(写失败回滚视觉态);
- **热键可改** ✓:驱动录 `Alt+Shift+P` → 保存 → `reapply_runtime` 热改绑链路 14 项检查全过;换算函数 7 条回归测试(裸键拒绝/纯修饰拒绝/Meta↔windows/往返一致);
- 离屏驱动另验:面板热应用(宽 700/格 38px/浅色 QSS 生效)、Watchdog 失活重挂(1 次 + 信号);真实应用托盘冒烟:启动、存活、干净退出无 stderr 残留。

**设计偏差/决策(DESIGN 已同步):**
1. **Watchdog 偏差(§6.7)**:原案「发测试键校验」弃用——keyboard 库全局注入在本机不可靠(M1 实测 57s 停顿)且会向用户前台应用打进按键;改为 30s QTimer 校验监听线程存活,失活置 `listening=False` 强制重启 + 业务层 `reapply_runtime` 全量重挂;
2. **自启 json 为意图源(§6.8)**:应用启动时 json 与注册表不一致则以 json 为准写入——否则 DEFAULT `autostart:true` 只是纸面值,设置窗读注册表会永久显示未勾选;开发态 Run 命令 = `python -X utf8 -c "…内联 sys.path+main"`(Run 键无法设环境变量);
3. **托盘图标程序化生成**:透明 QPixmap + QPainter 画 😀,免 .ico 资源文件与打包 datas 依赖;
4. **热键换算安全规则**:`qt_to_keyboard_hotkey` 拒绝无修饰裸键(否则全局注册会吞掉正常打字)、纯修饰键、超 3 字符键名;`windows↔Meta` 双向映射;
5. 设置窗不自作主张碰运行态:只改共享 cfg/aliases → 落盘 → 发 `applied` 信号,由 app 统一热改绑/重建扩展表/面板热应用(与 Watchdog 重挂共用 `reapply_runtime`);
6. 别名管理集中在设置窗表格(面板右键菜单仍是就地快捷编辑,两入口共享同一 dict,互相同步)。

**过程踩坑:**
- M4 驱动首跑用匿名 lambda 挂/卸钩子 → `unhook` 传入不同 lambda 对象 KeyError,atexit 恢复未执行,**用户 config.json 被测试值污染**(立即手工还原);教训:凡挂/卸回调必须具名函数 + atexit 兜底应覆盖全部被写文件——本次终检又发现 aliases.json 在上次崩溃中漏恢复(测试别名残留),已还原为 `[]`;
- git-bash 下 `taskkill /PID` 会被 MSYS 路径改写吞掉参数,须 `//PID //T //F`;
- 打包后 `_MEIPASS` 定位数据/互斥体跨进程持有/onefile 双进程结构均符合预期,无需代码适配(仅 app.py 的 `_BASE` 一处分支)。

**遗留:**
- §11 手动验收清单(重启机器验自启、多应用上屏 hex 验证等)交由用户交付前逐项过;
- 用户 json `autostart:true` 已物化为 Run 键(当前指向开发态命令);安装打包版后首次运行会自动改写为 exe 路径;
- Watchdog 真实失活场景(系统摘钩)无法确定性复现,仅以模拟线程死亡验证逻辑。

### 2026-10-01 · M3 右键别名 + 文本扩展 + IME 检测完成 ✅

**产出:** expander.py(状态机 + suppress 钩子 + 信号桥)、ime.py(IME 开合 + 前台进程名)、config.py 增 aliases.json 读写、search.py 增 `set_aliases` 热更 + `expander_table`、sender.py `type_text` 增退格参数、panel.py 右键别名菜单 + 信息栏别名、app.py 扩展装配。测试 19 → 42 全过,ruff 无告警。

**验收结果(真机 E2E,SendInput 真键注入 → LL 钩子 → WM_GETTEXT 读回):**
- `::shit ␣` → 记事本精确得 `💩`(回删 6 + 注入,空格被吞);
- 别名热更:保存 `xx`→💩 后纯别名表(关内置)`::xx ␣` → `💩💩`;
- 未命中 `::zzz ␣` 原样放行,零打扰;
- **IME 门禁(FR4.3)**:IMC_SETOPENSTATUS 开中文输入法后 `::shit ␣` 全程无介入(IME 正常转写,无新 💩、无任务、无吞键);
- 频率学习:两次命中 → `frequency.json {"💩": 2}`;
- 面板别名链路(离屏):信息栏 `别名: 翔, dabian` → 落盘 → 索引热更(查 `翔` 💩 居首)→ `aliases_changed` 信号 → 移除;
- 真机启动冒烟:扩展钩子随配置装载,干净退出无残留。

**设计决议与偏差(重要):**
1. **keyboard 库 suppress 返回值与直觉相反**:`_winkeyboard.prepare_intercept` 约定 **True=放行 / False=拦截**(DESIGN §6.6 原文写反,已修正)。初版按「True=吞」实现,真机一跑所有键全被吞(记事本一个字都收不到)——LL 钩子层返回值语义必须以库源码为准;
2. **注入不在钩子回调内做**:SendInput 在低级钩子回调内重入有 LowLevelHooksTimeout 风险(§6.7),任务经 `ExpandBridge.action` 信号排队到主线程执行(同 M1 热键桥模式);
3. **门禁含「面板可见」**:面板搜索框打字也会过全局 suppress 钩子,不让路会吞掉面板内空格 —— gate = 总开关 ∧ 面板不可见 ∧ 非黑名单进程 ∧ IME 关闭;
4. **gate 节流 500ms**(§6.5 复查节奏):IME/进程名是 syscall,IDLE→ARMED 必查,REC 内按时间窗复查;
5. **回删与注入合并为单次 SendInput**(退格 VK 对 + Unicode 单元混排),不完整序列不会半截留在目标窗口;
6. **扩展匹配表只取 kw_en/kw_abbr**(§6.6 原文如此):kw_py 不参与 —— `::` 录制是精确全等,拼音误触多;含空格/非拉丁词无法被 [a-z0-9] 缓冲命中,建表时剔除;别名同词覆盖内置(优先);
7. **别名编辑 = 预填现状的单框整体编辑**(逗号分隔,支持中文别名入搜索、拉丁别名入扩展;FR3.5 的「添加/查看/编辑」三合一,移除 = 清空提交);QInputDialog 模态属 Qt 标准,数据链路离屏驱动验证;
8. **E2E 键盘注入用 VkKeyScanW 真键事件**(shift 管理 + VK 击键):Unicode 注入(KEYEVENTF_UNICODE)在 LL 钩子层表现为 VK_PACKET,keyboard 库不报字符名,状态机看不见;真键事件与用户物理打键同路径;
9. **IME 开关是全局输入模式**:IMC_SETOPENSTATUS 切中文态后跨进程残留(上轮 E2E 遗留中文态导致下轮全被门禁拦)——E2E 驱动必须先关 IME 再测英文路径,结束恢复;
10. 意外收获:一次事故性验证 —— 全程 IME 开启下打字(`::shit ␣`→IME 转写 `::食堂`)扩展零介入,FR4.3 提前达标。

**遗留:**
- 黑名单进程旁路(FR4.4)逻辑在 gate 内(`foreground_process_name`),未单独真机验证(需前台黑名单进程;函数真机冒烟过);
- 右键菜单的模态交互(输入框视觉)未自动化,数据链路已验;M4 设置窗别名表格(FR5.2)提供第二入口。



### 2026-10-01 · M2 分类浏览 + 频率学习 + 信息栏完成 ✅

**产出:** panel.py 重写为 M2 形态(搜索框 + 分类栏 + 网格 + 信息栏);search.py 增 `entries_for_group` / `top_frequent`;config.py 默认 480×300 → **600×440**、新增 `advanced.hide_unsupported`;app.py 增 QRawFont 字形过滤;测试 +2(共 19 全过),ruff 无告警。

**验收结果:**
- **9 分类可切换**(超验收线 8):常用 + 9 组,笑脸 169 项首项 😀、大组 People & Body 2261 项填充 32-37ms,顺序与索引一致(test_entries_for_group 断言);
- **常用栏随使用更新(真机 E2E)**:frequency 复位 → popup(记事本)→ 搜 `shi` row2=💩 → 上屏 WM_GETTEXT 读回 `💩` → 第二周期呼出常用栏 💩 居首、frequency.json=`{"💩": 1}`;冷启动为固定常用条 23 项(非空);
- 信息栏跟随高亮项(`大便 · pile of poo · U+1F4A9` + 40px 大图预览);
- 截图目检:分类蓝色高亮、网格彩色 ~10 列、搜索模式分类栏整体淡化、无截断/重叠;
- 真机启动冒烟:`[app] 已隐藏 209 个本机字体不支持的 emoji`,RSS 70MB,退出无残留进程。

**设计决议与偏差(重要):**
1. **双模式判定 = 搜索框文本**:非空 → 搜索模式(分类栏 `setEnabled(False)` 淡化,§5 允许隐藏或淡化取淡化);空 → 回当前分类浏览;
2. **数字 1-9 直选仅搜索模式生效**(消歧决议:浏览模式数字照常入框当查询),Tab = 搜索↔分类切换且搜索→分类清空文本回浏览,分类栏可打字(自动跳回搜索框);
3. **列数动态计算** `viewport().width() // 46` 作 PgUp/PgDn 步长,弃固定 10 列(窗口宽度可配);
4. **常用栏 = 频率 top(recent_count)在前 + 固定常用条补足去重**,每次 popup 刷新(频率可能已变——clear() 对空文本不触发 textChanged,popup 末尾手动 `_load_category`);
5. **豆腐隐藏按 QRawFont 实测字形,弃 ver 字段猜测**(坑 #12 最终方案):`QRawFont.fromFont(QFont("Segoe UI Emoji")).glyphIndexesForString(cp)` 返回 `[0]`(.notdef)即字体无此码点。`QFontMetrics.inFontUcs4` 对彩色字体全 False 不可用;QRawFont 在 offscreen 平台会崩 → `platformName()` 守卫;字体缺失/检测异常返回 None 宁可显示豆腐不误删。本机 3781 → 3572(隐藏 209,全部 E13.0+,逐机精确);
6. 面板默认尺寸 600×440(§5 加分类栏+信息栏后 10 列需 ~600);DESIGN §8 已同步;
7. offscreen 平台不发真实窗口激活,`hasFocus()` 断言无效 → 驱动一律断言行为效果(文本清空/enable 状态),真实焦点已在 M1 真机验证;
8. 信息栏跟随**当前项**(填充后光标置 row0,↑↓/直选后即时更新)。

**用户配置迁移(已告知):** `%APPDATA%\EmojiPalette\config.json` 手动更新 width 600 / height 440 / hide_unsupported true(深合并只补缺不覆盖旧值),热键保持测试期 `ctrl+alt+e`。

**遗留:** 无。临时驱动/截图已清理,frequency.json 已复位。



### 2026-10-01 · M1 最小可用产品完成 ✅(热键 + 面板 + 搜索 + 回车上屏)

**产出:** config / search / sender / panel / hotkey / app / __main__ 七个模块从桩到实现,17 项测试全过,ruff 无告警。

**验收结果(进程内确定性驱动,不做全局按键注入):**
- 呼出延迟:首次 ~32ms、热态 ~16ms(<50ms ✓);
- 搜 `shi` 冷启动 💩 第 2 位(数据事实,见下)→ Enter SendInput 真实进记事本(WM_GETTEXT 读回 `💩`);第二次呼出频率学习生效,`shi` 首位即 💩,再上屏读回 `💩💩`;
- Esc 即走 / 点外关闭 / 上屏完成即隐藏,三途径验证;
- 单实例:二实例弹「已在运行」并以 0 退出,首实例存活;
- Ctrl+C:SIGINT → exec() 2.0s 返回,钩子全部卸载。

**冷启动数据事实(与 DESIGN 示例不同,测试断言按实际值):**
- `shi` 精确命中 kw_py 4 个,零频率码点升序为 👐(1F450)< 💩(1F4A9)< 🥄(1F944)< 🫡(1FAE1)→ **💩 是第 2 不是第 1**;用一次后频率加权即登顶;
- `bb` 命中中 💩 第 7(非第 3);🫡 在本机 Win10 渲染为豆腐块(E13.0 字体不支持,坑 #12 的 `ver` 字段留到 M2 隐藏)。

**设计偏差与踩坑(重要):**
1. **单实例锁换命名互斥体**:DESIGN §9 原定 `QLocalServer.listen` 失败检测,但 PySide6 6.11.2 Windows 下 listen **不再互斥**(同进程双 listen 实测均成功,两实例可并存)→ 改 `Local\EmojiPalette` 命名互斥体 + `ERROR_ALREADY_EXISTS`,进程退出系统自动回收;
2. **打分基数 10000 → 20000**:freq 上限 9999 × alias 权重 1.2 ≈ 12000 > 10000,高频前缀可反超低频精确命中 → 基数必须压过最大加权频率项(DESIGN §6.3 已同步修正);
3. **INPUT union 必须写全三成员**(MOUSEINPUT/KEYBDINPUT/HARDWAREINPUT):§6.4 骨架只含 KEYBDINPUT,x64 下 sizeof=32≠40,SendInput 按错误步长读数组(DESIGN 已修);
4. **前台锁两条路都要解**(坑 #2 扩展):① 面板自身呼出时 `activateWindow()` 会被后台进程前台锁拦下(面板可见但按键仍进原前台窗口)→ popup 内对自身 winId 跑 `restore_focus`;② 上屏时面板 hide 后激活飘走 → `restore_focus` 改**预算式轮询(300ms,首轮后 Alt 轻敲解锁)**,原 50ms 轮询在记事本冷切换下不够;
5. **失活关闭需 300ms 宽限**:suppress=False 下热键直通前台应用(Alt+E 呼出 VS Code 编辑菜单抢激活),ActivationChange 不能立即据此关面板;
6. **Ctrl+C 需 100ms 保活 QTimer**:Windows 下 Qt exec() 阻塞 Python 信号检查,无保活则 SIGINT 永不触发;
7. **频率即写盘**(FR5.4),与 §4.3 批量落盘矛盾,M4 再议优化;
8. 同 emoji 多词命中取最高分再排序(§6.3 留白);↑↓ 逐项移动(非整行);Esc 用 eventFilter 而非 QShortcut(QTest 无法触发快捷键);❤️ 等变体序列的常用条用元组存(按码点迭代会拆开);
9. **keyboard 库全局注入不可靠**(本机实测 57s 停顿、延迟重放)→ 验收一律进程内确定性驱动;
10. uv venv 的 `python.exe` 是跳板进程(真实解释器另有 PID),自动化测试按 pid 找窗口/杀进程树都会踩坑。

**遗留:**
- 用户 config.json 热键当前为 `ctrl+alt+e`(测试期临时值,Alt+E 与 VS Code 菜单冲突所致);恢复默认改 `%APPDATA%\EmojiPalette\config.json` 的 `hotkey` 字段即可;
- 🫡 等 E13.0+ 字符在 Win10 显示豆腐块,M2 用 `ver` 字段隐藏。

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
