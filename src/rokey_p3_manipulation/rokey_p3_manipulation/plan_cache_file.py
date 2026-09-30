"""칸별 계획 캐시를 파일로 두고 다시 쓴다. ROS 를 import 하지 않는다.

41725ff 회차에서 up 1분 52초 중 **73.6 s 가 계획 캐시**였다(최적화 9/23). 장면·계획 입력·계획 코드가
같으면 같은 답이 나오므로, 다 푼 뒤 한 번 저장해 두고 다음 기동에서 읽는다.

키(sha256 하나)의 재료는 답을 바꾸는 것 전부다:

- `scene_signature(scene)` — 장애물·수납·레일. 워크셀·씬 sha 는 inventory 를 거쳐 여기에 이미 들어 있다.
- `rail_select` — 같은 장면이라도 고르는 후보가 다르다.
- 칸마다 `cell_key(cell)` — 종류·중심·크기.
- 계획 입력 — seeds·params·tcp·link_boxes·home·home_rail·module_limits·관절 한계.
- 계획 **코드 파일**의 sha — `scene_v2`·`module_path`·`m0609_kinematics`·`pick_plan`.

`v2_seed`(칸 고르기 picker)는 넣지 않는다. 그 값은 어느 칸을 고를지만 정하고 칸의 계획은 바꾸지 않는다.

키가 다르면 그 파일을 **읽지 않을 뿐** 지우지 않는다. 못 푼 칸(steps None)은 저장하지 않는다 —
다음 기동에서 다시 푼다. 읽기·쓰기 실패는 회차를 멈추지 않는다(캐시가 없는 것과 같다).

파일은 pickle 이다. 저장소 밖, 사용자 홈 아래 우리 캐시 디렉터리에만 쓰고 읽으며, 키에 계획 코드의 sha 가
들어 있어 코드가 바뀐 파일은 애초에 읽지 않는다.
"""

import hashlib
import os
from pathlib import Path
import pickle
import tempfile

#: 기본 캐시 자리. 저장소 밖이다(회차 산출물이 아니라 기계마다 다시 만들 수 있는 값이다).
DEFAULT_DIR = '~/.cache/rokey_p3/plan_cache'
#: 키에 sha 를 넣는 계획 코드. 이 파일들이 답을 만든다.
CODE_MODULES = ('m0609_kinematics', 'module_path', 'pick_plan', 'scene_v2')
#: 파일 형식. 모양이 바뀌면 올린다(옛 파일은 읽히지 않는다).
FORMAT = 1


def code_digest(modules=CODE_MODULES):
    """계획 코드 파일들의 sha256. 코드가 바뀌면 키가 달라져 옛 파일을 읽지 않는다."""
    here = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for name in sorted(modules):
        path = here / f'{name}.py'
        digest.update(name.encode('utf-8'))
        digest.update(hashlib.sha256(path.read_bytes()).digest() if path.is_file() else b'missing')
    return digest.hexdigest()


def stable(value):
    """값을 순서가 정해진 순수 파이썬으로 편다. 같은 입력이면 같은 글자가 나와야 한다."""
    if value is None or isinstance(value, (str, bytes, bool, int)):
        return value
    if isinstance(value, float):
        return repr(round(value, 9))
    if hasattr(value, 'tolist'):                      # numpy 배열·스칼라
        return stable(value.tolist())
    if hasattr(value, '_asdict'):                     # namedtuple
        return [type(value).__name__, stable(dict(value._asdict()))]
    if isinstance(value, dict):
        return [[stable(key), stable(value[key])] for key in sorted(value, key=repr)]
    if isinstance(value, (set, frozenset)):
        return [stable(item) for item in sorted(value, key=repr)]
    if isinstance(value, (list, tuple)):
        return [stable(item) for item in value]
    return repr(value)


def plan_key(scene_signature, rail_select, cell_keys, inputs, code=None):
    """캐시 키(sha256 hex). `cell_keys` 는 {칸: cell_key}, `inputs` 는 계획 입력 mapping 이다."""
    material = stable({'signature': scene_signature, 'rail_select': rail_select,
                       'cells': dict(cell_keys), 'inputs': dict(inputs),
                       'code': code or code_digest(), 'format': FORMAT})
    return hashlib.sha256(repr(material).encode('utf-8')).hexdigest()


def path_for(directory, key):
    """키에 해당하는 파일 자리. `directory` 가 비면 None."""
    return None if not directory else Path(os.path.expanduser(str(directory))) / f'{key}.pkl'


def solved_only(plans):
    """푼 칸만 남긴다. `plans` 는 {칸: (cell_key, PlanEntry)} 다."""
    return {cell_id: value for cell_id, value in plans.items()
            if getattr(value[1], 'steps', None) is not None}


def load(directory, key):
    """{칸: (cell_key, PlanEntry)} 또는 None. 키가 다르거나 못 읽으면 None 이다(멈추지 않는다)."""
    path = path_for(directory, key)
    if path is None:
        return None
    try:
        with open(path, 'rb') as handle:
            payload = pickle.load(handle)
    except Exception:  # noqa: BLE001 - 캐시를 못 읽는 것은 캐시가 없는 것과 같다
        return None
    if not isinstance(payload, dict) or payload.get('format') != FORMAT or payload.get('key') != key:
        return None
    plans = payload.get('plans')
    return plans if isinstance(plans, dict) and plans else None


def save(directory, key, plans):
    """푼 칸을 파일 하나로 저장한다. 임시 파일에 쓰고 rename 한다. 쓴 자리 또는 None."""
    path = path_for(directory, key)
    keep = solved_only(plans or {})
    if path is None or not keep:
        return None
    handle, temporary = None, None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=str(path.parent), suffix='.tmp')
        with os.fdopen(handle, 'wb') as out:
            handle = None
            pickle.dump({'format': FORMAT, 'key': key, 'plans': keep}, out, protocol=4)
        os.replace(temporary, path)
        return path
    except Exception:  # noqa: BLE001 - 저장 실패는 회차를 멈추지 않는다
        if handle is not None:
            os.close(handle)
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
        return None
