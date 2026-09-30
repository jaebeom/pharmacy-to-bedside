"""인터페이스 파일이 계약 v1 10절의 v1.1 목록과 같은지 검사한다.

ROS 없이 돈다. 파일을 글자로 읽어 이름·타입·상수만 본다.
계약 문서를 고치는 PR 이 먼저 나가면 이 테스트도 같은 PR 에서 고친다.
"""
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / 'src/rokey_p3_interfaces'


def read_lines(relative):
    return PACKAGE.joinpath(relative).read_text(encoding='utf-8').splitlines()


def strip_comment(line):
    index = line.find('#')
    return (line if index < 0 else line[:index]).strip()


def fields(lines):
    """선언 순서대로 (타입, 이름). 상수와 주석은 뺀다."""
    out = []
    for line in lines:
        body = strip_comment(line)
        if not body or '=' in body:
            continue
        parts = body.split()
        if len(parts) >= 2:
            out.append((parts[0], parts[1]))
    return out


def constants(lines):
    """이름 → 값 문자열."""
    out = {}
    for line in lines:
        body = strip_comment(line)
        if '=' not in body:
            continue
        declaration, value = body.split('=', 1)
        parts = declaration.split()
        if len(parts) == 2:
            out[parts[1]] = value.strip()
    return out


def action_sections(relative):
    """액션 파일을 goal / result / feedback 세 덩어리로."""
    sections = [[]]
    for line in read_lines(relative):
        if line.strip() == '---':
            sections.append([])
        else:
            sections[-1].append(line)
    return sections


class InterfaceContractTests(unittest.TestCase):
    def test_event_has_the_four_v1_1_constants(self):
        names = constants(read_lines('msg/Event.msg'))
        for name in ('REQUEST_ACCEPTED', 'PICK_ATTEMPT', 'ARM_HOME', 'RESET_DONE'):
            self.assertEqual(f'"{name}"', names.get(name), f'{name} 상수가 없거나 값이 이름과 다르다')

    def test_event_constant_value_always_equals_its_name(self):
        for name, value in constants(read_lines('msg/Event.msg')).items():
            self.assertEqual(f'"{name}"', value)

    def test_belt_state_fields(self):
        self.assertEqual(
            [('std_msgs/Header', 'header'), ('bool', 'occupied'), ('bool', 'at_end'), ('string', 'order_id')],
            fields(read_lines('msg/BeltState.msg')))

    def test_cabinet_observation_fields(self):
        self.assertEqual(
            [('std_msgs/Header', 'header'), ('string', 'cabinet_id'),
             ('string', 'order_id'), ('bool', 'present')],
            fields(read_lines('msg/CabinetObservation.msg')))

    def test_scan_tag_sections(self):
        goal, result, feedback = action_sections('action/ScanTag.action')
        self.assertEqual([('uint8', 'kind'), ('string', 'zone_id')], fields(goal))
        self.assertEqual([('string', 'tag_id'), ('uint8', 'status')], fields(result))
        self.assertEqual([('string', 'phase')], fields(feedback))

    def test_order_status_claim_and_judgement_are_separate_constants(self):
        names = constants(read_lines('msg/OrderStatus.msg'))
        self.assertEqual('2', names.get('STATE_DELIVERED'))
        self.assertEqual('10', names.get('STATE_SUCCESS'))

    def test_pick_pouch_outcome_values_are_documented(self):
        text = PACKAGE.joinpath('action/PickPouch.action').read_text(encoding='utf-8')
        for outcome in ('ok', 'not_detected', 'qr_mismatch', 'grasp_failed',
                        'dropped', 'timeout', 'rejected_interlock'):
            self.assertIn(outcome, text)

    def test_every_interface_file_is_listed_in_cmakelists(self):
        text = PACKAGE.joinpath('CMakeLists.txt').read_text(encoding='utf-8')
        for folder, suffix in (('msg', '.msg'), ('srv', '.srv'), ('action', '.action')):
            for path in sorted(PACKAGE.joinpath(folder).glob(f'*{suffix}')):
                self.assertIn(f'"{folder}/{path.name}"', text, f'{path.name} 이 CMakeLists 목록에 없다')

    def test_interface_files_stay_ascii(self):
        # rosidl 이 .idl 을 ISO-8859-1 로 쓴다. 한글 주석은 빌드를 깨뜨린다.
        for folder in ('msg', 'srv', 'action'):
            for path in sorted(PACKAGE.joinpath(folder).iterdir()):
                path.read_bytes().decode('ascii')


if __name__ == '__main__':
    unittest.main()
