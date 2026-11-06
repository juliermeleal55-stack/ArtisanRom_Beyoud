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
        worker = text[text.index('WAIT_FOR_DEX_WORKERS()\n'):text.index('BUILD()\n')]
        decode = worker + text[text.index('DECODE()\n'):text.index('DEX_TO_API()\n')]
        for name, expected in [('other.jar', {'smali': '35', 'smali_classes2': '34'}),
                               ('services.jar', {'smali': '35', 'smali_classes2': '34'})]:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / name
                source.touch()
                output = root / 'decoded'
                harness = r'''
LOG() { :; }; LOGE() { echo "$*" >&2; }; READ_BYTES_AT() { echo 04034b50; }
EVAL() { eval "$1"; }
apktool() { mkdir -p "$OUTPUT_PATH"; touch "$OUTPUT_PATH/classes.dex" "$OUTPUT_PATH/classes2.dex"; }
DEX_TO_API() { if [[ "$1" == */classes.dex ]]; then echo 35; else echo 34; fi; }
baksmali() {
 local output="" api=""
 while [ "$#" -gt 0 ]; do
  case "$1" in -o) output="$2"; shift 2 ;; -a) api="$2"; shift 2 ;; *) shift ;; esac
 done
 mkdir "$OUTPUT_PATH/inflight" || return 1
 sleep 0.02
 mkdir -p "$output"
 echo "$api" >> "$output/invocations"
 rmdir "$OUTPUT_PATH/inflight"
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
                build = worker + text[text.index('BUILD()\n'):text.index('    # Copy original META-INF')] + '}\n'
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


    def test_failed_earlier_dex_worker_cannot_be_hidden_by_last_success(self):
        text = OVERLAY.read_text()
        worker = text[text.index('WAIT_FOR_DEX_WORKERS()\n'):text.index('BUILD()\n')]
        script = worker + '\nBEYOUD_DEX_PIDS=(); (exit 7) & BEYOUD_DEX_PIDS+=("$!"); (exit 0) & BEYOUD_DEX_PIDS+=("$!"); WAIT_FOR_DEX_WORKERS\n'
        self.assertNotEqual(subprocess.run(['bash','-c',script]).returncode,0)

    def test_services_api_override_cannot_reintroduce_unsupported_api_36(self):
        text=OVERLAY.read_text()
        self.assertNotIn('&& DEX_API_LEVEL=36',text)
        worker=text[text.index('WAIT_FOR_DEX_WORKERS()\n'):text.index('BUILD()\n')]
        build=worker+text[text.index('BUILD()\n'):text.index('    # Copy original META-INF')]+'}\n'
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp);(output/'smali').mkdir()
            (output/'dex_api_versions.tsv').write_text('smali\t36\n')
            harness='LOG() { :; }; LOGE() { echo "$*" >&2; }; smali() { echo SHOULD_NOT_ASSEMBLE; };\n'
            result=subprocess.run(['bash','-c',harness+build+'\nOUTPUT_PATH="$1"; INPUT_FILE=services.jar; THREAD_COUNT=1; BUILD','test',str(output)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('Invalid DEX API level',result.stderr)
            self.assertNotIn('SHOULD_NOT_ASSEMBLE',result.stdout)

    def test_dex_header_mapping_reads_full_magic_not_last_ascii_digit(self):
        text=OVERLAY.read_text()
        mapper=text[text.index('DEX_TO_API()\n'):text.index('PREPARE_SCRIPT()\n')]
        harness='LOGE() { echo "$*" >&2; }; READ_BYTES_AT() { od -An -v -tx1 -j "$2" -N "$3" "$1" | tr -d " \\n"; };\n'
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'classes.dex'
            for version,api in [('035','23'),('037','25'),('038','27'),('039','29'),('040','34'),('041','35')]:
                path.write_bytes(('dex\n'+version+'\0').encode())
                result=subprocess.run(['bash','-c',harness+mapper+'\nDEX_TO_API "$1"','test',str(path)],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout.strip(),api)
            path.write_bytes(b'dex\n999\0')
            result=subprocess.run(['bash','-c',harness+mapper+'\nDEX_TO_API "$1"','test',str(path)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
