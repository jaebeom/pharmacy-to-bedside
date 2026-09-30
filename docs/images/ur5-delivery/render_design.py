"""Render proposed UR5 design diagrams; SVG is the repository deliverable."""
import argparse
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

matplotlib.rcParams.update({'font.family': 'DejaVu Sans', 'svg.fonttype': 'none',
                            'svg.hashsalt': 'p3-ur5-design-v2'})
ROOT = Path(__file__).resolve().parent
INK, MUTED = '#172b45', '#50647a'
BLUE, GREEN, PURPLE = '#245ca8', '#128275', '#8055ac'
ORANGE, RED = '#b56b0b', '#bb4141'
NEW, OLD, OBS = '#fff1d6', '#edf2f7', '#e2f4ee'


def canvas(title, subtitle, height=820):
    fig = plt.figure(figsize=(12, height / 100), dpi=140, facecolor='#ffffff')
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set(xlim=(0, 1200), ylim=(height, 0))
    ax.axis('off')
    ax.text(40, 46, title, fontsize=22, weight='bold', color=INK)
    ax.text(40, 77, subtitle, fontsize=11, color=MUTED)
    ax.plot([40, 1160], [96, 96], color='#d9e2ec', lw=1)
    ax.text(40, height - 18, 'P3 / PR #232  |  PROPOSED DESIGN  |  NOT AN EXECUTION RECORD',
            fontsize=9, color=MUTED)
    return fig, ax


def box(ax, x, y, w, h, title, lines, fill=OLD, edge='#c8d3df', fs=11):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0,rounding_size=12',
                               facecolor=fill, edgecolor=edge, linewidth=1.2, zorder=2))
    ax.text(x + 16, y + 29, title, fontsize=13, weight='bold', color=INK, zorder=3)
    for i, line in enumerate(lines):
        ax.text(x + 16, y + 55 + i * 22, line, fontsize=fs, color=MUTED, zorder=3)


def arrow(ax, points, color=BLUE, dashed=False):
    xs, ys = zip(*points, strict=True)
    style = '--' if dashed else '-'
    if len(points) > 2:
        ax.plot(xs[:-1], ys[:-1], color=color, lw=1.8, ls=style, zorder=1)
    ax.add_patch(FancyArrowPatch(points[-2], points[-1], arrowstyle='-|>',
                                mutation_scale=13, color=color, lw=1.8,
                                linestyle=style, zorder=1, shrinkA=0, shrinkB=3))


def label(ax, x, y, text, color=MUTED, size=10, align='center'):
    ax.text(x, y, text, fontsize=size, color=color, ha=align, va='center',
            bbox={'facecolor': 'white', 'edgecolor': 'none', 'pad': 2}, zorder=4)


def architecture():
    fig, ax = canvas('01 / SYSTEM OWNERSHIP',
                     'One trip owner. Measured feedback. Independent evaluation.', 820)
    box(ax, 40, 135, 225, 100, 'WEB / EXISTING API',
        ['POST /api/requests', 'Display state and errors'])
    box(ax, 340, 135, 460, 130, 'ORCHESTRATOR / TRIP OWNER',
        ['Existing trip_fsm + proposed additions:',
         'custody ledger / slot reservations / auth', 'motion-mode supervisor: HOLD, ARM, DRIVE'], NEW)
    arrow(ax, [(265, 185), (340, 185)])
    label(ax, 302, 166, 'Deliver')
    box(ax, 40, 365, 240, 115, 'FLEET / NAV2',
        ['GoToZone + path validation', 'Owns navigation subgoals'])
    box(ax, 335, 365, 235, 115, 'ARM EXECUTOR',
        ['PickPouch + ScanTag', 'Collision / custody guards'])
    box(ax, 625, 365, 195, 115, 'PERCEPTION',
        ['QR / pose / placement', 'Measured, not commanded'], OBS, fs=9)
    arrow(ax, [(415, 265), (415, 305), (160, 305), (160, 365)])
    arrow(ax, [(520, 265), (520, 365)])
    label(ax, 258, 304, 'GoToZone')
    label(ax, 548, 321, 'Arm task')
    arrow(ax, [(85, 365), (85, 275), (315, 275), (315, 245), (340, 245)], GREEN)
    label(ax, 195, 275, 'Navigation result', GREEN, size=9)
    arrow(ax, [(570, 382), (600, 382), (600, 265)], GREEN)
    label(ax, 658, 295, 'Transfer receipt', GREEN, size=9)
    arrow(ax, [(625, 435), (570, 435)], GREEN)
    label(ax, 599, 405, 'Observe', GREEN, size=9)
    box(ax, 40, 600, 780, 130, 'ISAAC + DRIVERS / PHYSICAL STATE',
        ['Base + mobile UR5 + deck + belt + destination cabinet',
         'Local permit / epoch / watchdog enforcement  |  Actual attachment feedback',
         'Commands do not imply attachment, release, placement, or stopping'], NEW)
    arrow(ax, [(160, 480), (160, 600)])
    label(ax, 160, 540, 'Base command')
    arrow(ax, [(450, 480), (450, 600)])
    label(ax, 450, 540, 'Arm / gripper command')
    arrow(ax, [(265, 600), (265, 480)], GREEN)
    label(ax, 265, 578, 'Odometry', GREEN, size=9)
    arrow(ax, [(560, 600), (560, 480)], GREEN)
    label(ax, 560, 578, 'Joints / HELD', GREEN, size=9)
    arrow(ax, [(720, 600), (720, 480)], GREEN)
    label(ax, 720, 540, 'Sensor data', GREEN)
    arrow(ax, [(800, 205), (850, 205), (850, 560), (795, 560), (795, 600)], ORANGE)
    label(ax, 850, 315, 'Permit', ORANGE)
    box(ax, 900, 135, 260, 105, 'RUN RECORD / REPORT',
        ['Compare claim vs observation', 'Mismatch remains visible'], '#f2ebfa')
    arrow(ax, [(800, 165), (900, 165)], BLUE)
    label(ax, 850, 139, 'Claim', BLUE, size=9)
    box(ax, 900, 385, 260, 130, 'EVALUATOR / LOGGER',
        ['Cabinet ground truth', 'Independent SUCCESS', 'Never an operating input'], '#f2ebfa')
    arrow(ax, [(1030, 385), (1030, 240)], PURPLE, True)
    label(ax, 1030, 300, 'Evaluation', PURPLE)
    arrow(ax, [(820, 680), (1030, 680), (1030, 515)], PURPLE, True)
    label(ax, 1030, 596, 'Evaluation-only channel', PURPLE)
    label(ax, 431, 769, 'Blue: commands   |   Green: observations   |   Amber: added guards', size=11)
    return fig


def transfer():
    fig, ax = canvas('02 / TRANSFER AND CUSTODY',
                     'Same protocol for BELT -> DECK and DECK -> CABINET.', 835)
    box(ax, 40, 155, 330, 110, 'SOURCE CONFIRMED',
        ['Order + source slot match', 'Reserve target / bind task'], OBS)
    box(ax, 440, 155, 320, 110, 'GRIPPER CONFIRMED',
        ['Fresh actual HELD after command', 'Lift + monitored transfer'], OBS)
    box(ax, 830, 155, 330, 110, 'RELEASE SENT',
        ['Lower onto support, then OPEN', 'Do not commit yet'], NEW)
    arrow(ax, [(370, 210), (440, 210)])
    arrow(ax, [(760, 210), (830, 210)])
    box(ax, 830, 355, 330, 125, 'VERIFY TARGET',
        ['Released + correct slot / order', 'Stable support + source cleared', 'Use fresh operating observations'], OBS)
    arrow(ax, [(995, 265), (995, 355)])
    label(ax, 995, 310, 'Physical release is not receipt')
    box(ax, 440, 355, 320, 125, 'UNKNOWN -> HOLD',
        ['Missing / conflicting observation', 'No retry, home, or redispatch',
         'Retain slot reservations'], '#fceaea', RED)
    arrow(ax, [(830, 417), (760, 417)], RED)
    label(ax, 795, 391, 'Unclear', RED, size=9)
    arrow(ax, [(600, 265), (600, 355)], RED)
    label(ax, 600, 310, 'Feedback lost / fault', RED)
    box(ax, 440, 620, 320, 115, 'RECONCILE',
        ['Fresh source / target / grip check', 'Still unknown: remain paused'], NEW)
    arrow(ax, [(600, 480), (600, 620)], RED)
    label(ax, 600, 550, 'Observe, do not repeat the transfer')
    box(ax, 40, 620, 330, 115, 'SOURCE RECONFIRMED',
        ['Safe state + remaining retry budget', 'New attempt, new observation'], OBS)
    arrow(ax, [(440, 678), (370, 678)], GREEN)
    arrow(ax, [(205, 620), (205, 265)], GREEN)
    label(ax, 205, 450, 'Verified source only', GREEN)
    box(ax, 830, 620, 330, 115, 'COMMIT ONCE',
        ['Custody = TARGET; store receipt', 'Duplicate result: no new motion'], OBS)
    arrow(ax, [(995, 480), (995, 620)], GREEN)
    label(ax, 995, 550, 'Target verified', GREEN)
    arrow(ax, [(760, 678), (830, 678)], GREEN)
    label(ax, 795, 755, 'Recovered target receipt', GREEN, size=9)
    label(ax, 600, 785,
          'GRIPPER reconfirmed: controlled hold/recovery only; UNKNOWN never implies HOLD_RETURN.', size=11)
    return fig


def motion_modes():
    fig, ax = canvas('03 / MOTION AUTHORITY',
                     'HOLD revokes permission. It does not prove that motion has stopped.', 850)
    box(ax, 420, 145, 360, 120, 'HOLD / TRANSITION',
        ['Revoke previous generation', 'Drain goals + measure stopped', 'One owner: orchestrator'], NEW)
    box(ax, 60, 395, 370, 140, 'ARM PERMITTED',
        ['Base stopped and Nav2 drained', 'Current epoch + fresh permit', 'Monitor base + grip every tick'], OBS)
    box(ax, 770, 395, 370, 140, 'DRIVE PERMITTED',
        ['Arm settled at home; no arm goal', 'Gripper empty; deck slots secure',
         'Monitor arm + permit every tick'], OBS)
    arrow(ax, [(420, 190), (240, 190), (240, 395)], GREEN)
    label(ax, 240, 312, 'Base-stop gate', GREEN)
    arrow(ax, [(780, 190), (960, 190), (960, 395)], GREEN)
    label(ax, 960, 312, 'Stow + payload gate', GREEN)
    arrow(ax, [(430, 445), (500, 445), (500, 265)], BLUE)
    label(ax, 475, 348, 'End ARM', BLUE, size=9)
    arrow(ax, [(770, 445), (700, 445), (700, 265)], BLUE)
    label(ax, 726, 348, 'End DRIVE', BLUE, size=9)
    box(ax, 420, 665, 360, 110, 'FAULT / RESET FENCE',
        ['Local stop; retain grip; block tasks', 'Reconcile before any new permit'], '#fceaea', RED)
    arrow(ax, [(600, 265), (600, 665)], RED)
    label(ax, 600, 554, 'Cancel / stale / reset', RED)
    arrow(ax, [(245, 535), (245, 720), (420, 720)], RED)
    arrow(ax, [(955, 535), (955, 720), (780, 720)], RED)
    label(ax, 240, 609, 'Any broken guard', RED)
    label(ax, 960, 609, 'Any broken guard', RED)
    label(ax, 600, 811, 'No direct ARM <-> DRIVE switch. Reset timeout is never permission to start a task.', size=11)
    return fig


def implementation_gates():
    fig, ax = canvas('04 / IMPLEMENTATION GATES',
                     'Code completion is not physical acceptance. C requires actual observations from D.', 1010)
    box(ax, 390, 125, 420, 95, 'A / CONTRACT + READINESS',
        ['Destination, custody, auth, permit, version'], NEW)
    box(ax, 390, 275, 420, 95, 'B / MOBILE ASSET + DRIVER',
        ['Geometry + sensors + actuator stop/fence'], NEW)
    arrow(ax, [(600, 220), (600, 275)])
    box(ax, 40, 435, 330, 110, 'C / ARM TRANSFER',
        ['Collision + measured endpoints', 'First L1/L2 with explicit fixtures'])
    box(ax, 440, 435, 320, 110, 'D / REAL OBSERVATIONS',
        ['QR / depth or plane / placement', 'UNKNOWN remains unknown'])
    box(ax, 830, 435, 330, 110, 'E / MAP + NAVIGATION',
        ['Graph -> validated path -> follow', 'Footprint + docking + stop'])
    for x in (205, 600, 995):
        arrow(ax, [(600, 370), (600, 398), (x, 398), (x, 435)])
    box(ax, 190, 620, 540, 95, 'C + D / PHYSICAL TRANSFER GATE',
        ['Belt -> deck AND deck -> cabinet, with real observations'], OBS, fs=10)
    arrow(ax, [(205, 545), (205, 620)], GREEN)
    arrow(ax, [(600, 545), (600, 620)], GREEN)
    box(ax, 390, 790, 420, 80, 'F / ONE COMPLETE DELIVERY',
        ['One robot / one pouch / one bed'], NEW)
    arrow(ax, [(460, 715), (460, 790)], GREEN)
    arrow(ax, [(995, 545), (995, 830), (810, 830)], GREEN)
    label(ax, 995, 715, 'Navigation L3 gate', GREEN)
    box(ax, 390, 910, 420, 70, 'G / FROZEN ACCEPTANCE',
        ['Then expand slots / rooms / ward'], OBS, fs=10)
    arrow(ax, [(600, 870), (600, 910)], GREEN)
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview-dir', type=Path)
    args = parser.parse_args()
    if args.preview_dir:
        args.preview_dir.mkdir(parents=True, exist_ok=True)
    for name, draw in [('architecture', architecture), ('transfer', transfer),
                       ('motion-modes', motion_modes),
                       ('implementation-gates', implementation_gates)]:
        fig = draw()
        destination = ROOT / f'{name}.svg'
        fig.savefig(destination, metadata={'Date': None})
        # Matplotlib emits trailing spaces in path data; keep generated diffs clean.
        destination.write_text('\n'.join(line.rstrip() for line in
                                        destination.read_text().splitlines()) + '\n')
        if args.preview_dir:
            fig.savefig(args.preview_dir / f'{name}.png', dpi=140)
        plt.close(fig)
        print(f'Rendered {name}.svg')


if __name__ == '__main__':
    main()
