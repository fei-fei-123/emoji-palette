"""pytest 共享配置:把项目根与 src 加入 sys.path,便于导入 build_data 与运行期包。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
