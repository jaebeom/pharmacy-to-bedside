"""테스트가 저장소 밖 임시 경로에서도 `app` 을 찾도록 한다.

이게 있어서 각 테스트 파일이 sys.path 를 건드리지 않아도 되고, 따라서 import 를
파일 맨 위에 둘 수 있다(E402 회피용 noqa 가 필요 없다).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
