"""No-model checks for this fixed Code-mode configuration revision."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
from pilot_alt_access import config_args
from pilot_alt_runtime import generation_argv, CLIENT, HOST


class RuntimeConfiguration(unittest.TestCase):
    def test_cad_enables_distinct_runtime_and_mode_once(self):
        args = generation_argv('gpt-5.6-sol', '/session', '/output', '/operator', '/kit')
        for feature in ('code_mode', 'code_mode_host'):
            self.assertEqual(args.count('features.' + feature + '=true'), 1)
            self.assertNotIn('features.' + feature + '=false', args)
        for name in ('shell_tool', 'unified_exec', 'multi_agent', 'browser_use'):
            self.assertIn('features.' + name + '=false', args)
        self.assertIn('permissions.robotgen-alt.network.enabled=false', args)
        grant = next(a for a in args if a.startswith('permissions.robotgen-alt.filesystem='))
        self.assertIn(json.dumps(CLIENT) + '="read"', grant)
        self.assertIn(json.dumps(HOST) + '="read"', grant)
        self.assertNotIn('"/home/camus"=', grant)

    def test_admission_configuration_remains_disabled(self):
        args = config_args()
        self.assertIn('features.code_mode=false', args)
        self.assertIn('features.code_mode_host=false', args)

    def test_inner_tool_guard_still_rejects_host_tools(self):
        for name in ('exec', 'functions.exec', 'exec_command', 'shell_command', 'apply_patch',
                     'read_file', 'spawn_agent', 'mcp__other__execute', 'mcp__cad__execute', 'mcp__cad__submit'):
            child = subprocess.run([sys.executable, '-I', '-B', str(TOOLS/'pilot_alt_guard.py'), '--cad'],
                                   input=json.dumps({'tool_name': name}), text=True, capture_output=True)
            self.assertEqual(child.returncode, 0)
            decision = json.loads(child.stdout)['hookSpecificOutput']['permissionDecision']
            self.assertEqual(decision, 'allow' if name in ('mcp__cad__execute','mcp__cad__submit') else 'deny')


if __name__ == '__main__':
    unittest.main()
