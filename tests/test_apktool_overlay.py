import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from integration.framework_policy import install, APKTOOL

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / 'integration/artisan/apktool.sh'


class ApktoolOverlayTests(unittest.TestCase):
    def test_workspace_accepts_upstream_then_installs_overlay_not_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            shutil.copytree(ROOT / 'reference/build', workspace, dirs_exist_ok=True)
            original = (workspace / APKTOOL).read_bytes()
            self.assertNotEqual(original, OVERLAY.read_bytes())
            install(workspace)
            self.assertEqual((workspace / APKTOOL).read_bytes(), OVERLAY.read_bytes())
            self.assertEqual((ROOT / 'reference/build' / APKTOOL).read_bytes(), original)
            subprocess.run(['bash', '-n', str(workspace / APKTOOL)], check=True)

    def test_unknown_upstream_still_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            shutil.copytree(ROOT / 'reference/build', workspace, dirs_exist_ok=True)
            (workspace / APKTOOL).write_text('unexpected source')
            with self.assertRaises(ValueError):
                install(workspace)

    def test_decode_executes_correct_per_dex_mapping_and_single_pass(self):
        text = OVERLAY.read_text()
        decode = text[text.index('DECODE()\n'):text.index('DEX_TO_API()\n')]
        for name, expected in [('other.jar', {'smali': '35', 'smali_classes2': '36'}),
                               ('services.jar', {'smali': '36', 'smali_classes2': '36'})]:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / name
                source.touch()
                output = root / 'decoded'
                harness = r'''
LOG() { :; }; LOGE() { echo "$*" >&2; }; READ_BYTES_AT() { echo 04034b50; }
EVAL() { eval "$1"; }
apktool() { mkdir -p "$OUTPUT_PATH"; touch "$OUTPUT_PATH/classes.dex" "$OUTPUT_PATH/classes2.dex"; }
DEX_TO_API() { if [[ "$1" == */classes.dex ]]; then echo 35; else echo 36; fi; }
baksmali() {
 local output="" api=""
 while [ "$#" -gt 0 ]; do
  case "$1" in -o) output="$2"; shift 2 ;; -a) api="$2"; shift 2 ;; *) shift ;; esac
 done
 mkdir -p "$output"
 echo "$api" >> "$output/invocations"
}
'''
                script = root / 'test.sh'
                script.write_text(harness + decode + '\nINPUT_FILE="$1"; OUTPUT_PATH="$2"; FORCE=false; THREAD_COUNT=1; DECODE\n')
                result = subprocess.run(['bash', str(script), str(source), str(output)], text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                rows = (output / 'dex_api_versions.tsv').read_text().splitlines()
                self.assertEqual(len(rows), 2)
                self.assertEqual(dict(line.split('\t') for line in rows), expected)
                for folder, api in expected.items():
                    self.assertEqual((output / folder / 'invocations').read_text().splitlines(), [api])
                # Execute the real assembly loop against the metadata just emitted.
                build = text[text.index('BUILD()\n'):text.index('    # Copy original META-INF')] + '}\n'
                mock = r'''
smali() {
 local output="" api=""
 while [ "$#" -gt 0 ]; do
  case "$1" in -o) output="$2"; shift 2 ;; -a) api="$2"; shift 2 ;; *) shift ;; esac
 done
 printf '%s' "$api" > "$output"
}
'''
                script.write_text(harness + mock + build + '\nINPUT_FILE="$1"; OUTPUT_PATH="$2"; THREAD_COUNT=1; BUILD\n')
                assembled = subprocess.run(['bash', str(script), str(source), str(output)], text=True, capture_output=True)
                self.assertEqual(assembled.returncode, 0, assembled.stderr)
                self.assertEqual((output / 'classes.dex').read_text(), expected['smali'])
                self.assertEqual((output / 'classes2.dex').read_text(), expected['smali_classes2'])

