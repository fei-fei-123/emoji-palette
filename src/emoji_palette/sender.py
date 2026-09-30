"""SendInput Unicode 注入 / 焦点还原 / 剪贴板降级(DESIGN.md §6.4)。

时序约定:先 hide 面板 → 再还原焦点 → 再注入。
非 BMP 字符按 UTF-16 代理对逐 code unit 注入,不使用剪贴板(降级除外)。
"""
