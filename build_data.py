"""数据管道:下载 CLDR/emoji-test → 解析 → pypinyin 拼音 → data/index.json。

用法:
    python build_data.py            # 在线下载并构建
    python build_data.py --offline  # 仅用 data/raw/ 缓存构建

产出规格见 DESIGN.md §4.2。运行期零网络。
"""
