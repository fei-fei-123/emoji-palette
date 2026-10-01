"""Unicode emoji 组名中英映射(key 与 emoji-test.txt 的 group 行一致)。"""

GROUP_ZH: dict[str, str] = {
    "Smileys & Emotion": "笑脸与情感",
    "People & Body": "人物与身体",
    "Animals & Nature": "动物与自然",
    "Food & Drink": "食物与饮料",
    "Travel & Places": "旅行与地点",
    "Activities": "活动",
    "Objects": "物品",
    "Symbols": "符号",
    "Flags": "旗帜",
}


def group_zh(name: str) -> str:
    """英文组名 → 中文名;未映射返回空串(兼容 `and` 写法)。"""
    if name in GROUP_ZH:
        return GROUP_ZH[name]
    return GROUP_ZH.get(name.replace(" and ", " & "), "")
