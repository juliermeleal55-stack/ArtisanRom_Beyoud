import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from integration import patch_preflight as audit
from integration.preflight_policy import install

ROOT = Path(__file__).resolve().parents[1]


def setup(root):
    (root/'unica/patches/example').mkdir(parents=True)
    (root/'BEYOUD-WORKSPACE.json').write_text(json.dumps(dict(codename='beyond1lte')))
    decoded = root/'out/target/beyond1lte/apktool/test.jar'
    decoded.mkdir(parents=True)
    (decoded/'A.smali').write_text('old\n')
    return decoded


def change(root, name, old, new):
    path = root/'unica/patches/example'/name
    path.write_text(f'diff --git a/A.smali b/A.smali\n--- a/A.smali\n+++ b/A.smali\n@@ -1 +1 @@\n-{old}\n+{new}\n')
    return path


def completed_root(root):
    audit.record(root,dict(kind='module',module='unica/patches/example',status='passed'))
    audit.record(root,dict(kind='root',root='unica/patches',status='passed'))


class PatchPreflightTests(unittest.TestCase):
    def test_collects_multiple_mismatches_and_blocks_final_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);decoded=setup(root);audit.start(root)
            audit.apply(root,decoded,change(root,'1.patch','missing-one','new'))
            audit.apply(root,decoded,change(root,'2.patch','missing-two','new'))
            self.assertEqual((decoded/'A.smali').read_text(),'old\n')
            completed_root(root)
            with self.assertRaises(ValueError):audit.finish(root)
            report=json.loads((audit.logdir(root)/'patch-preflight.json').read_text())
            self.assertEqual(report['status'],'blocked')
            self.assertEqual(len(report['failures']),2)
            self.assertEqual(len(list((audit.logdir(root)/'patch-preflight-smali').rglob('*.smali'))),2)

    def test_successful_sequence_uses_prior_patch_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);decoded=setup(root);audit.start(root)
            audit.apply(root,decoded,change(root,'1.patch','old','middle'))
            audit.apply(root,decoded,change(root,'2.patch','middle','final'))
            completed_root(root)
            self.assertEqual(audit.finish(root)['status'],'passed')
            self.assertEqual((decoded/'A.smali').read_text(),'final\n')

    def test_empty_or_incomplete_root_traversal_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);decoded=setup(root);audit.start(root)
            with self.assertRaises(ValueError):audit.finish(root)
            audit.start(root)
            audit.apply(root,decoded,change(root,'1.patch','old','new'))
            audit.record(root,dict(kind='module',module='unica/patches/example',status='passed'))
            with self.assertRaises(ValueError):audit.finish(root)

    def test_native_or_customize_error_blocks_even_if_patches_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);decoded=setup(root);audit.start(root)
            audit.apply(root,decoded,change(root,'1.patch','old','new'))
            completed_root(root)
            audit.record(root,dict(kind='module',module='native',status='failed',detail='HEX_PATCH failed'))
            with self.assertRaises(ValueError):audit.finish(root)

    def test_cannot_start_collector_without_controller_or_escape_decoded_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);decoded=setup(root)
            path=change(root,'1.patch','old','new')
            with self.assertRaises(ValueError):audit.apply(root,decoded,path)
            self.assertEqual((decoded/'A.smali').read_text(),'old\n')
            audit.start(root)
            path.write_text(path.read_text().replace('b/A.smali','b/../../escape.smali'))
            with self.assertRaises(ValueError):audit.apply(root,decoded,path)

    def test_installer_production_path_retains_strict_git_apply_and_finish_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);shutil.copytree(ROOT/'reference/build',root,dirs_exist_ok=True)
            install(root)
            for script in root.rglob('*.sh'):subprocess.run(['bash','-n',str(script)],check=True)
            make=(root/'scripts/make_rom.sh').read_text()
            self.assertLess(make.index('patch_preflight.py" finish'),make.index('Building APKs/JARs'))
            utils=(root/'scripts/utils/module_utils.sh').read_text()
            self.assertIn('else\n    EVAL "LC_ALL=C git apply',utils)
            self.assertIn('--beyoud-audit-module', (root/'scripts/internal/apply_modules.sh').read_text())
            with self.assertRaises(ValueError):install(root)

    def test_runner_collects_later_modules_without_disabling_child_errexit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            shutil.copytree(ROOT/'reference/build',root,dirs_exist_ok=True)
            install(root)
            (root/'integration').mkdir()
            shutil.copyfile(ROOT/'integration/patch_preflight.py',root/'integration/patch_preflight.py')
            # Isolate the actual module runner from external Android tools.
            (root/'scripts/utils/module_utils.sh').write_text('LOG_STEP_IN() { :; }; LOG_STEP_OUT() { :; }; LOGE() { :; }; IS_VALID_PARTITION_NAME() { return 1; }\n')
            modules=root/'audit-modules'
            for name,script in [('a','echo before; false; echo SHOULD_NOT_RUN'),('b','false'),('c','echo LATER_MODULE_RAN')]:
                p=modules/name;p.mkdir(parents=True)
                (p/'module.prop').write_text('name=test\nauthor=test\n')
                (p/'customize.sh').write_text(script+'\n')
            audit.start(root)
            env=dict(os.environ,SRC_DIR=str(root),TARGET_SINGLE_SYSTEM_IMAGE='essi_64',BEYOUD_PATCH_PREFLIGHT='1')
            command=['bash',str(root/'scripts/internal/apply_modules.sh'),str(modules)]
            result=subprocess.run(command,env=env,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertNotIn('SHOULD_NOT_RUN',result.stdout)
            self.assertIn('LATER_MODULE_RAN',result.stdout)
            events=[json.loads(l) for l in (audit.logdir(root)/'patch-preflight.jsonl').read_text().splitlines()]
            self.assertEqual([e['status'] for e in events if e['kind']=='module'],['failed','failed','passed'])
            env.pop('BEYOUD_PATCH_PREFLIGHT')
            production=subprocess.run(command,env=env,text=True,capture_output=True)
            self.assertNotEqual(production.returncode,0)
            self.assertNotIn('LATER_MODULE_RAN',production.stdout)

    def test_controller_never_starts_real_pass_if_preflight_fails(self):
        from integration import build
        from test_build_stages import fixture
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fixture(root)
            error=subprocess.CalledProcessError(1,['make_rom.sh'])
            with patch.object(build,'environment',return_value={}), patch.object(build,'validate_prior'), patch.object(build,'run_command',side_effect=error) as run:
                with self.assertRaises(subprocess.CalledProcessError):build.execute(root,'patch')
                self.assertEqual(run.call_count,1)
                self.assertEqual(run.call_args.args[2]['BEYOUD_PATCH_PREFLIGHT'],'1')
                self.assertEqual(json.loads((root/'out/beyoud-stages/patch.json').read_text())['status'],'failed')

    def test_static_inventory_does_not_claim_donor_certification(self):
        report=json.loads((ROOT/'manifests/legacy-patch-review.json').read_text())
        self.assertEqual(len(report['patches']),66)
        self.assertEqual(len({e['path'] for e in report['patches']}),66)
        self.assertEqual(report['status'],'static-risk-inventory-not-donor-certification')
        self.assertEqual(sum(bool(e['adaptation']) for e in report['patches']),4)
