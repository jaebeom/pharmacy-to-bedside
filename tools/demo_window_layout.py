#!/usr/bin/env python3
"""시연 창 배치: Isaac 창을 화면 왼쪽 반, 웹(firefox) 창을 오른쪽 반으로 옮기고 올린다(재범 9/18 반반 화면).

설치 없이 python3 표준 라이브러리 ctypes 로 libX11 을 부른다(master02 에 wmctrl·xdotool 이 없다. 실습9 에서 마클2 가
같은 방법으로 firefox 를 옮겼다). **우리 두 창만** 옮기고 올린다. 다른 창은 최소화하거나 건드리지 않는다.

    python3 tools/demo_window_layout.py [--screen W H] [--isaac 식] [--web 식] [--wait-s S] [--list]

- 창은 _NET_CLIENT_LIST(창 관리자가 관리하는 최상위 창)에서 찾는다. 없으면 루트의 자식 창을 본다.
  제목(_NET_WM_NAME, 없으면 WM_NAME)과 WM_CLASS 를 합친 글자에 정규식(대소문자 무시)이 맞는 첫 창이다.
- 배치 영역은 _NET_WORKAREA(위 막대를 뺀 영역)가 있으면 그것, 없으면 --screen 또는 화면 크기다.
- 최대화된 창은 창 관리자가 옮기기를 무시하므로 먼저 _NET_WM_STATE 에서 최대화를 뺀다(EWMH 요청).
- 옮기는 것은 클라이언트 창이다. 창 관리자가 위 막대·그림자를 맞추느라 몇 픽셀 밀 수 있다
  (마클2 9/18 master02: 요청 y 0 → 실제 +9).
  밀림은 고치지 않고, 배치 뒤 실제 좌표를 다시 읽어 한 줄로 찍는다.
- 배치 뒤(또는 --check-only 면 배치 없이) 실제 좌표가 맡은 반쪽에 들어왔는지 본다(verdict).
  조용히 실패하지 않게 하려는 것이다.
  9/20 master01 첫 실행에서 창 둘 다 안 옮겨졌는데(요청 993,32 → 실제 116,69) 0 으로 끝났다(#339 뒤 관측).
- 창이 아직 없으면 `--wait-s`(배치 기본 30 s, `--check-only` 기본 0) 동안 2 s 마다 다시 찾는다. `up` 직후에는
  웹 창이 아직 없을 수 있다(마클1 9/25 회차73: 바로 돌려 3 으로 끝났고, 뒤 boot_check window 가 걸렸다).
- 끝나는 값: 0 다 됨, 3 X 를 못 열었거나(libX11·DISPLAY) 창을 하나라도 못 찾음,
  4 옮겼는데 자리가 아니다.
  3·4 면 Super+←/→ 안내를 찍는다. 시연 절차는 그때 손 배치(또는 Wnck)로 간다.
"""

import argparse
import ctypes
import ctypes.util
import re
import sys
import time

# master02 실측(마클2 9/18 실습9, GNOME 46 X11/mutter):
#   Isaac  제목 'Isaac Sim Python 5.1.0', WM_CLASS ("IsaacSim" "Isaac Sim Python 5.1.0")
#   firefox 제목 'ROKEY P3 관제 — Mozilla Firefox', WM_CLASS ("Navigator" "firefox_firefox")
#           대화상자도 같은 res_class 를 쓰므로(("Firefox" "firefox_firefox")) Navigator 로 고른다.
# 'IsaacSim' 만으로 고르면 호스트 이름에 그 글자가 든 PC(master01 `IsaacSim14`)의 터미널 창 'rokey@IsaacSim14' 가
# 먼저 잡힌다(마클1 9/24, 터미널이 왼쪽 반으로 가서 --check-only 가 거짓 통과).
# 창 제목·클래스의 'Isaac Sim Python' 으로 고른다.
ISAAC_DEFAULT = r'isaac sim python'
# firefox 는 WM_CLASS 'Navigator'(대화상자 'Firefox' 와 가른다). master02 는 Chrome --app 이라 클래스가
# '127.0.0.1 Google-chrome', 제목이 'P3 관제 · 개발자' 다(마클2 9/24). 둘 다 관제 페이지 제목에 'P3 관제' 가 든다.
WEB_DEFAULT = r'navigator|p3 관제'
HINT = '손으로: Isaac 창을 누르고 Super+←, 웹 창을 누르고 Super+→'
#: 창 관리자가 프레임·CSD 여백·크기 단위를 맞추느라 미는 정도는 통과시키고(관측: y +9·+37, 크기 ±33 안팎),
#: "요청이 통째로 무시됨"(관측: x 가 877 px 어긋남)은 걸리게 잡은 값이다. 실습 관측이 쌓이면 줄인다.
POSITION_TOLERANCE = 80
SIZE_TOLERANCE = 120
#: 옮기기 전에 빼야 하는 창 상태. 최대화·타일·전체화면이면 창 관리자가 옮기기를 무시하거나 되돌린다.
BLOCKING_STATES = ('_NET_WM_STATE_MAXIMIZED_VERT', '_NET_WM_STATE_MAXIMIZED_HORZ', '_NET_WM_STATE_FULLSCREEN',
                   '_NET_WM_STATE_TILED_LEFT', '_NET_WM_STATE_TILED_RIGHT',
                   '_NET_WM_STATE_TILED_TOP', '_NET_WM_STATE_TILED_BOTTOM')
SOURCE_PAGER = 2            # EWMH 보낸 쪽 표시. 창 관리자는 도구(pager)의 요청을 응용의 요청보다 너그럽게 받는다
#: 좌표를 클라이언트 창 기준으로 읽으라는 중력. 프레임(장식)을 좌표에 더하지 않는다.
#: master01 은 _NET_FRAME_EXTENTS 가 0,0,37,0 이라 기본 중력이면 y 가 37 px 내려갔다(9/20 요청 32 → 실제 69).
#: Wnck 방식이 요청=실제였던 것도 STATIC 으로 보냈기 때문이다(맥마클1 확인).
GRAVITY_STATIC = 10
STATE_WAIT_S = 1.0
FIND_RETRY_S = 2.0
PLACE_WAIT_S = 30.0
SETTLE_WAIT_S = 2.0


def halves(area):
    """(x, y, w, h) 영역 → (왼쪽 반, 오른쪽 반). 홀수 폭은 오른쪽이 1 픽셀 넓다."""
    x, y, w, h = area
    left = w // 2
    return (x, y, left, h), (x + left, y, w - left, h)


def move_flags(gravity=GRAVITY_STATIC, source=SOURCE_PAGER):
    """_NET_MOVERESIZE_WINDOW 의 data.l[0]: gravity | x·y·w·h 를 준다는 비트 | 보낸 쪽 표시."""
    return gravity | (1 << 8) | (1 << 9) | (1 << 10) | (1 << 11) | (source << 12)


def states_to_clear(names):
    """지금 창 상태 이름들 중 옮기기를 막는 것만(순서 유지)."""
    return [name for name in names if name in BLOCKING_STATES]


def verdict(requested, actual, position_tolerance=POSITION_TOLERANCE, size_tolerance=SIZE_TOLERANCE):
    """배치가 됐는지: (됐나, 이유). requested 는 그 창이 맡은 반쪽 (x, y, w, h) 다.

    창 중심이 맡은 반쪽 안에 있어야 하고, 위치·크기 차이가 허용 범위 안이어야 한다.
    중심 판정이 가장 굵은 신호다(요청이 무시되면 창이 반대쪽에 그대로 남는다).
    """
    if actual is None:
        return False, '실제 좌표를 읽지 못함'
    left, top, width, height = requested
    dx, dy = actual[0] - left, actual[1] - top
    dw, dh = actual[2] - width, actual[3] - height
    center = actual[0] + actual[2] // 2
    why = []
    if not left <= center < left + width:
        why.append(f'중심 x={center} 가 맡은 반쪽({left}..{left + width}) 밖')
    if abs(dx) > position_tolerance or abs(dy) > position_tolerance:
        why.append(f'위치 차이 {dx:+},{dy:+}(허용 ±{position_tolerance})')
    if abs(dw) > size_tolerance or abs(dh) > size_tolerance:
        why.append(f'크기 차이 {dw:+},{dh:+}(허용 ±{size_tolerance})')
    return not why, ', '.join(why)


def wait_for_windows(list_windows, patterns, wait_s, sleep=time.sleep, clock=time.monotonic):
    """(창 목록, 못 찾은 이름들). 하나라도 없으면 `wait_s` 동안 `FIND_RETRY_S` 마다 목록을 다시 읽는다."""
    deadline = clock() + wait_s
    while True:
        windows = list_windows()
        missing = [label for label, pattern in patterns if pick(windows, pattern) is None]
        if not missing or clock() >= deadline:
            return windows, missing
        sleep(FIND_RETRY_S)


def pick(windows, pattern):
    """windows: [(창 id, 제목, 클래스)]. 제목·클래스에 맞는 첫 창 id, 없으면 None."""
    rx = re.compile(pattern, re.IGNORECASE)
    for wid, title, klass in windows:
        if rx.search(f'{title} {klass}'):
            return wid
    return None


class X11:
    """필요한 만큼만 부르는 libX11 얇은 감싸개."""

    def __init__(self):
        name = ctypes.util.find_library('X11')
        if not name:
            raise OSError('libX11 을 찾지 못했다')
        x = ctypes.cdll.LoadLibrary(name)
        self.x = x
        x.XOpenDisplay.restype = ctypes.c_void_p
        x.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x.XDefaultRootWindow.restype = ctypes.c_ulong
        x.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        x.XInternAtom.restype = ctypes.c_ulong
        x.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        x.XGetWindowProperty.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_long, ctypes.c_long,
                                         ctypes.c_int, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
                                         ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_ulong),
                                         ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_void_p)]
        x.XFree.argtypes = [ctypes.c_void_p]
        x.XQueryTree.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
                                 ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_void_p),
                                 ctypes.POINTER(ctypes.c_uint)]
        x.XMoveResizeWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_uint, ctypes.c_uint]
        x.XRaiseWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        x.XFlush.argtypes = [ctypes.c_void_p]
        x.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x.XCloseDisplay.argtypes = [ctypes.c_void_p]
        x.XDefaultScreen.argtypes = [ctypes.c_void_p]
        x.XDisplayWidth.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x.XDisplayHeight.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x.XSendEvent.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_long, ctypes.c_void_p]
        x.XGetAtomName.restype = ctypes.c_char_p
        x.XGetAtomName.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        x.XGetGeometry.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
                                   ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                                   ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint),
                                   ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
        x.XTranslateCoordinates.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_int,
                                            ctypes.c_int, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                                            ctypes.POINTER(ctypes.c_ulong)]
        self.d = x.XOpenDisplay(None)
        if not self.d:
            raise OSError('X 디스플레이를 열지 못했다(DISPLAY·XAUTHORITY 확인)')
        self.root = x.XDefaultRootWindow(self.d)

    def atom(self, name):
        return self.x.XInternAtom(self.d, name.encode(), 0)

    def prop(self, wid, name, kind=0):
        """(형식 비트, 원소 수, 원시 바이트). 없으면 None. kind 0 = AnyPropertyType."""
        actual, fmt = ctypes.c_ulong(), ctypes.c_int()
        n, after, data = ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_void_p()
        status = self.x.XGetWindowProperty(self.d, wid, self.atom(name), 0, 1 << 20, 0, kind, ctypes.byref(actual),
                                           ctypes.byref(fmt), ctypes.byref(n), ctypes.byref(after), ctypes.byref(data))
        if status != 0 or not data.value:
            return None
        try:
            size = {8: 1, 16: ctypes.sizeof(ctypes.c_short), 32: ctypes.sizeof(ctypes.c_long)}.get(fmt.value, 1)
            return fmt.value, n.value, ctypes.string_at(data.value, n.value * size)
        finally:
            self.x.XFree(data)

    def longs(self, wid, name):
        got = self.prop(wid, name)
        if not got or got[0] != 32:
            return []
        return list((ctypes.c_long * got[1]).from_buffer_copy(got[2]))

    def text(self, wid, name):
        got = self.prop(wid, name)
        return got[2].decode('utf-8', 'replace').replace('\0', ' ').strip() if got and got[0] == 8 else ''

    def windows(self):
        ids = [w & 0xFFFFFFFF for w in self.longs(self.root, '_NET_CLIENT_LIST')]
        if not ids:                                     # 창 관리자가 목록을 안 내면 루트의 자식
            root, parent, children, n = ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_void_p(), ctypes.c_uint()
            if self.x.XQueryTree(self.d, self.root, ctypes.byref(root), ctypes.byref(parent), ctypes.byref(children),
                                 ctypes.byref(n)) and children.value:
                ids = list((ctypes.c_ulong * n.value).from_address(children.value))
                self.x.XFree(children)
        return [(wid, self.text(wid, '_NET_WM_NAME') or self.text(wid, 'WM_NAME'), self.text(wid, 'WM_CLASS'))
                for wid in ids]

    def workarea(self, screen):
        area = self.longs(self.root, '_NET_WORKAREA')
        if len(area) >= 4:
            return tuple(area[:4])
        if screen:
            return (0, 0, *screen)
        s = self.x.XDefaultScreen(self.d)
        return (0, 0, self.x.XDisplayWidth(self.d, s), self.x.XDisplayHeight(self.d, s))

    def state_names(self, wid):
        """_NET_WM_STATE 의 원자 이름들."""
        names = []
        for value in self.longs(wid, '_NET_WM_STATE'):
            raw = self.x.XGetAtomName(self.d, ctypes.c_ulong(value))
            if raw:
                names.append(raw.decode('ascii', 'replace'))
        return names

    def client_message(self, wid, kind, data):
        """루트로 보내는 EWMH 요청(SubstructureRedirect|SubstructureNotify)."""
        class ClientMessage(ctypes.Structure):
            _fields_ = [('type', ctypes.c_int), ('serial', ctypes.c_ulong), ('send_event', ctypes.c_int),
                        ('display', ctypes.c_void_p), ('window', ctypes.c_ulong), ('message_type', ctypes.c_ulong),
                        ('format', ctypes.c_int), ('l', ctypes.c_long * 5)]

        class Event(ctypes.Union):
            _fields_ = [('xclient', ClientMessage), ('pad', ctypes.c_long * 24)]

        event = Event()
        event.xclient.type = 33                         # ClientMessage
        event.xclient.window = wid
        event.xclient.message_type = self.atom(kind)
        event.xclient.format = 32
        for index, value in enumerate(data[:5]):
            event.xclient.l[index] = value
        mask = (1 << 19) | (1 << 20)                    # SubstructureNotify | SubstructureRedirect
        self.x.XSendEvent(self.d, self.root, 0, mask, ctypes.byref(event))
        self.x.XFlush(self.d)

    def clear_states(self, wid):
        """옮기기를 막는 상태(최대화·타일·전체화면)를 빼 달라고 하고, 빠질 때까지 기다린다. 남은 것을 돌려준다."""
        blocking = states_to_clear(self.state_names(wid))
        for name in blocking:                           # 0 = remove, 한 번에 둘까지라 하나씩 보낸다
            self.client_message(wid, '_NET_WM_STATE', [0, self.atom(name), 0, SOURCE_PAGER, 0])
        deadline = time.monotonic() + STATE_WAIT_S
        while blocking and time.monotonic() < deadline:
            time.sleep(0.05)
            blocking = states_to_clear(self.state_names(wid))
        return blocking

    def settle(self, wid, limit=SETTLE_WAIT_S):
        """창 관리자가 자리를 잡을 때까지: geometry 가 연속 두 번 같으면 그 값."""
        deadline = time.monotonic() + limit
        last = None
        while time.monotonic() < deadline:
            now = self.geometry(wid)
            if now is not None and now == last:
                return now
            last = now
            time.sleep(0.1)
        return last

    def geometry(self, wid):
        """창의 실제 (x, y, w, h). 화면 기준 좌표로 옮겨 읽는다. 창 관리자가 요청과 다르게 놓을 수 있다."""
        root, gx, gy = ctypes.c_ulong(), ctypes.c_int(), ctypes.c_int()
        w, h, border, depth = ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint()
        if not self.x.XGetGeometry(self.d, wid, ctypes.byref(root), ctypes.byref(gx), ctypes.byref(gy),
                                   ctypes.byref(w), ctypes.byref(h), ctypes.byref(border), ctypes.byref(depth)):
            return None
        ax, ay, child = ctypes.c_int(), ctypes.c_int(), ctypes.c_ulong()
        if not self.x.XTranslateCoordinates(self.d, wid, self.root, 0, 0, ctypes.byref(ax), ctypes.byref(ay),
                                            ctypes.byref(child)):
            return None
        return ax.value, ay.value, w.value, h.value

    def place(self, wid, rect):
        """창 관리자에게 옮겨 달라고 요청한다. (남은 막는 상태, 자리 잡은 뒤 geometry).

        관리 중인 창에 XMoveResizeWindow 를 직접 부르면 mutter 는 무시하거나 되돌린다(9/20 master01).
        그래서 EWMH _NET_MOVERESIZE_WINDOW 로 요청하고, 그래도 안 되면 옛 방식으로 한 번 더 해 본다.
        """
        x, y, w, h = rect
        left = self.clear_states(wid)      # 이번 실패의 원인은 아니었다(둘 다 최대화 아님). 방어로 둔다
        self.client_message(wid, '_NET_MOVERESIZE_WINDOW', [move_flags(), x, y, w, h])
        self.client_message(wid, '_NET_ACTIVE_WINDOW', [SOURCE_PAGER, 0, 0, 0, 0])
        self.x.XRaiseWindow(self.d, wid)
        self.x.XFlush(self.d)
        got = self.settle(wid)
        if not verdict(rect, got)[0]:                   # 요청을 안 받는 창 관리자용 폴백
            self.x.XMoveResizeWindow(self.d, wid, x, y, w, h)
            self.x.XRaiseWindow(self.d, wid)
            self.x.XFlush(self.d)
            got = self.settle(wid)
        return left, got

    def close(self):
        self.x.XCloseDisplay(self.d)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--screen', type=int, nargs=2, metavar=('W', 'H'), help='_NET_WORKAREA 가 없을 때 쓸 화면 크기')
    parser.add_argument('--isaac', default=ISAAC_DEFAULT, help=f'Isaac 창 제목·클래스 식(기본 {ISAAC_DEFAULT})')
    parser.add_argument('--web', default=WEB_DEFAULT, help=f'웹 창 제목·클래스 식(기본 {WEB_DEFAULT})')
    parser.add_argument('--list', action='store_true', help='창 목록만 찍고 옮기지 않는다')
    parser.add_argument('--check-only', action='store_true',
                        help='옮기지 않고 지금 자리가 맞는지만 본다(리허설, 손·Wnck 배치 뒤 확인)')
    parser.add_argument('--wait-s', type=float, default=None,
                        help=f'창이 없으면 다시 찾는 최대 s(배치 기본 {PLACE_WAIT_S:g}, --check-only·--list 기본 0)')
    args = parser.parse_args(argv)
    try:
        x11 = X11()
    except OSError as error:
        print(f'[demo_window_layout] 창을 옮기지 못한다: {error}. {HINT}')
        return 3
    try:
        if args.list:
            windows = x11.windows()
            for wid, title, klass in windows:
                print(f'0x{wid:08x} class={klass!r} title={title!r}')
            return 0
        wait_s = args.wait_s if args.wait_s is not None else (0.0 if args.check_only else PLACE_WAIT_S)
        windows, _ = wait_for_windows(x11.windows, (('isaac', args.isaac), ('web', args.web)), wait_s)
        area = x11.workarea(args.screen)
        left, right = halves(area)
        missing, wrong = [], []
        for label, pattern, rect in (('isaac', args.isaac, left), ('web', args.web, right)):
            wid = pick(windows, pattern)
            if wid is None:
                missing.append(label)
                continue
            stuck = []
            if args.check_only:
                got = x11.geometry(wid)
            else:
                stuck, got = x11.place(wid, rect)
                if stuck:
                    print(f'[demo_window_layout] {label}: 창 상태 {stuck} 가 안 빠졌다'
                          '(최대화·타일이면 옮기기가 막힌다)')
            # 창 관리자가 위 막대·그림자를 맞추느라 몇 픽셀 밀 수 있다. 고치려 들지 않고 실제 값을 적는다.
            shown = f'{got[0]},{got[1]} {got[2]}x{got[3]}' if got else '읽지 못함'
            ok, why = verdict(rect, got)
            head = '지금' if args.check_only else '요청'
            print(f'[demo_window_layout] {label} 0x{wid:08x} {head} {rect[0]},{rect[1]} {rect[2]}x{rect[3]} '
                  f'→ 실제 {shown}(작업 영역 {area})')
            if not ok:
                wrong.append(label)
                print(f'[demo_window_layout] 배치 실패: {label} 요청 {rect[0]},{rect[1]} {rect[2]}x{rect[3]} '
                      f'→ 실제 {shown}({why})')
        if missing:
            print(f'[demo_window_layout] 창을 못 찾음: {missing}(창 {len(windows)}개, {wait_s:g} s 기다림, '
                  f'--list 로 본다). {HINT}')
            return 3
        if wrong:
            print(f'[demo_window_layout] 자리가 아니다: {wrong}. {HINT}')
            return 4
        return 0
    finally:
        x11.close()


if __name__ == '__main__':
    sys.exit(main())
