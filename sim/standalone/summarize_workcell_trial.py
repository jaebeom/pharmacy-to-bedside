#!/usr/bin/env python3
"""Summarize recorded ROS telemetry without turning action claims into success."""
import argparse
import json
from pathlib import Path
import re


def summarize(events, results, stage_log):
    peaks = [0., 0., 0.]
    samples, clocks, previous_clock, reversals = 0, 0, None, 0
    selected = []
    for line in events:
        event = json.loads(line)
        topic, message = event['topic'], event['message']
        if topic == '/m0609/rail/joint_states' and len(message['velocity']) == 3:
            samples += 1
            peaks = [max(a, abs(b)) for a, b in zip(peaks, message['velocity'], strict=True)]
        if topic == '/clock':
            stamp = message['clock']['sec']+message['clock']['nanosec']/1e9
            clocks += 1
            reversals += int(previous_clock is not None and stamp < previous_clock)
            previous_clock = stamp
        if topic == 'feedback':
            match = re.search(r'\bplan cell=(\S+)', message['feedback']['phase'])
            if match:
                selected.append(match.group(1))
    attached = set(re.findall(r'refill_ros grasp attached[^\n]* cell=(\S+)', stage_log))
    released = set(re.findall(r'refill_ros released cell=(\S+)[^\n]* target=round\b', stage_log))
    verified = []
    for index, result in enumerate(results):
        cell = selected[index] if index < len(selected) else None
        release = result.get('last_release') or {}
        ok = bool(result['result']['success'] and result.get('home_observed')
                  and cell in attached and cell in released
                  and release.get('cell') == cell and release.get('target') == 'round')
        verified.append({'attempt': result['attempt'], 'cell': cell, 'verified': ok,
                         'action_success': result['result']['success'],
                         'attached': cell in attached, 'released_round': cell in released,
                         'home_observed': result.get('home_observed', False)})
    return {'mode': 'INTEGRATION_ONLY_DISTANCE_ATTACH', 'attempts': verified,
            'completed_three': (len(verified) == len(selected) == 3 and len(set(selected)) == 3
                                and all(r['verified'] for r in verified)),
            'attached_cells': sorted(attached), 'released_round_cells': sorted(released),
            'rail_peak_speed_m_s': peaks, 'rail_samples': samples,
            'clock_samples': clocks, 'clock_reversals': reversals}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--events', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--stage-log', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.events.open() as stream:
        report = summarize(stream, json.loads(args.results.read_text()), args.stage_log.read_text())
    with args.output.open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
