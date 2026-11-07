import contextlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from integration.package_inputs import capture, selected_layout, retire, load, check_image, write_layout_check
from integration.static_layout import normalize
from integration.build import identity
from test_build_stages import fixture, firmware


def s10(root):
    fixture(root);firmware(root)
    (root/'BEYOUD-WORKSPACE.json').write_text(json.dumps(dict(target='SM-G973F',codename='beyond1lte')))
    for p in ('out/config.sh','out/firmware-lock.json'):
        path=root/p;path.write_text(path.read_text().replace('SM-G975F','SM-G973F'))
    (root/'out/fw/SM-G975F_AUT').rename(root/'out/fw/SM-G973F_AUT')
    (root/'out/fw/SM-G973F_AUT/os_partitions_metadata.txt').write_text('system_size=5976883200\nvendor_size=1153433600\nproduct_size=650117120\n')


class PartitionProfileTests(unittest.TestCase):
    def setUp(self):self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    def test_confirmed_default_separates_stock_caps_and_declared_caps(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,BEYOUD_PARTITION_LAYOUT='extreme-default'):
            root=Path(tmp);s10(root);data=capture(root)
            self.assertEqual(data['stock_image_size_caps']['product'],650117120)
            self.assertEqual(data['image_size_caps'],dict(system=7340032000,vendor=1572864000,product=1572864000,odm=4194304,prism=629145600,optics=31457280))
            self.assertEqual(data['partition_layout']['id'],'extreme-default')

    def test_stock_remains_default_and_other_s10_model_cannot_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);s10(root)
            with patch.dict(os.environ,BEYOUD_PARTITION_LAYOUT='stock'):
                self.assertEqual(capture(root)['image_size_caps']['product'],650117120)
                strict=identity(root)
            with patch.dict(os.environ,BEYOUD_PARTITION_LAYOUT='extreme-default'):
                self.assertNotEqual(strict,identity(root))
                (root/'BEYOUD-WORKSPACE.json').write_text(json.dumps(dict(target='SM-G975F',codename='beyond2lte')))
                with self.assertRaises(ValueError):selected_layout(root)
            with patch.dict(os.environ,BEYOUD_PARTITION_LAYOUT='unknown'):
                with self.assertRaises(ValueError):selected_layout(root)

    def test_caps_survive_retirement_and_cache_cannot_cross_layouts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);s10(root)
            with patch.dict(os.environ,BEYOUD_PARTITION_LAYOUT='extreme-default'):
                retire(root);self.assertEqual(load(root)['image_size_caps']['product'],1572864000)
                cache=root/'out/beyoud-package-inputs.json';data=json.loads(cache.read_text())
                data['image_size_caps']['product']+=1;cache.write_text(json.dumps(data))
                with self.assertRaises(ValueError):load(root)
            with patch.dict(os.environ,BEYOUD_PARTITION_LAYOUT='stock'):
                with self.assertRaises(ValueError):load(root)

    def test_previous_product_size_is_accepted_but_profile_overflow_is_not(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,BEYOUD_PARTITION_LAYOUT='extreme-default'):
            root=Path(tmp);s10(root);image=root/'product.img'
            for size,valid in [(1540771963,True),(1572864000+4096,False)]:
                blocks=(size+4095)//4096
                image.write_bytes(struct.pack('<I4H4I',0xed26ff3a,1,0,28,12,4096,blocks,1,0))
                if valid:check_image(root,'product',image)
                else:
                    with self.assertRaises(ValueError):check_image(root,'product',image)

    def test_auxiliary_partitions_are_native_for_declared_layout_and_installer_checks_size(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,BEYOUD_PARTITION_LAYOUT='extreme-default'):
            root=Path(tmp);s10(root)
            work=root/'out/target/beyond1lte/work_dir'
            for p in ('system/system','configs','vendor','product','optics','prism','odm'):(work/p).mkdir(parents=True,exist_ok=True)
            (work/'configs/fs_config-system').write_text(' 0 0 755 capabilities=0x0\n')
            (work/'configs/file_context-system').write_text('/ u:object_r:rootfs:s0\n')
            (root/'out/beyoud-logs').mkdir()
            self.assertEqual(normalize(root,'beyond1lte')['embedded'],[])
            directory=root/'out/zip';directory.mkdir()
            script=directory/'partition-layout-check.sh';write_layout_check(root,script)
            text=script.read_text()
            self.assertIn('7340032000',text);self.assertIn('1572864000',text)
            self.assertIn('blockdev --getsize64',text)
            self.assertNotIn('sgdisk',text);self.assertNotIn('mkfs',text)
            subprocess.run(['sh','-n',str(script)],check=True)

    def test_generated_updater_checks_layout_before_first_image_write(self):
        from integration.build_policy import zip_policy
        root=Path(__file__).resolve().parents[1]
        transformed=zip_policy((root/'reference/build/scripts/internal/build_flashable_zip.sh').read_text())
        first=transformed.index('        PRINT_HEADER\n')
        last=transformed.index('        if [ "$TARGET_SUPER_PARTITION_SIZE"',first)
        snippet=transformed[first:last]
        result=subprocess.run(['bash','-c','PRINT_HEADER() { :; }; TARGET_BOOT_DEVICE_PATH=/dev/block/by-name;\n'+snippet],check=True,capture_output=True,text=True)
        self.assertIn('run_program("/sbin/sh", "/tmp/partition-layout-check.sh", "/dev/block/by-name") == 0',result.stdout)
        self.assertLess(transformed.index('Cannot extract partition layout check.'),transformed.index('block_image_update('))

    def test_content_sized_has_no_fixed_ceiling_and_records_real_image_requirements(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,BEYOUD_PARTITION_LAYOUT='content-sized'):
            root=Path(tmp);s10(root)
            self.assertTrue(all(v is None for v in capture(root)['image_size_caps'].values()))
            directory=root/'out/zip';directory.mkdir()
            image=directory/'system.img'
            # Synthetic sparse header: dimensions only, NOT an actual ROM image.
            logical=12*1024**3
            image.write_bytes(struct.pack('<I4H4I',0xed26ff3a,1,0,28,12,4096,logical//4096,1,0))
            check_image(root,'system',image)
            report=json.loads((directory/'REQUIRED-IMAGE-SIZES.json').read_text())
            self.assertEqual(report['image_size_bytes'],{'system':logical})
            script=directory/'partition-layout-check.sh';write_layout_check(root,script)
            text=script.read_text()
            self.assertIn(str(logical),text)
            self.assertNotIn('7340032000',text)
            subprocess.run(['sh','-n',str(script)],check=True)
            with self.assertRaises(ValueError):check_image(root,'super',image)
            image.write_bytes(b'')
            with self.assertRaises(ValueError):check_image(root,'system',image)

    def test_content_sized_preflight_does_not_reject_payload_over_extreme_system_size(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,BEYOUD_PARTITION_LAYOUT='content-sized'):
            root=Path(tmp);s10(root)
            work=root/'out/target/beyond1lte/work_dir'
            for p in ('system/system','configs','vendor','product','optics','prism','odm'):(work/p).mkdir(parents=True,exist_ok=True)
            (work/'configs/fs_config-system').write_text(' 0 0 755 capabilities=0x0\n')
            (work/'configs/file_context-system').write_text('/ u:object_r:rootfs:s0\n')
            (root/'out/beyoud-logs').mkdir()
            with (work/'system/system/large-test-payload').open('wb') as stream:stream.truncate(8481766531)
            report=normalize(root,'beyond1lte')
            self.assertGreaterEqual(report['payload_bytes']['system'],8481766531)
            self.assertEqual(report['embedded'],[])

    def test_content_sized_cache_and_missing_requirements_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);s10(root)
            with patch.dict(os.environ,BEYOUD_PARTITION_LAYOUT='content-sized'):
                retire(root);self.assertIsNone(load(root)['image_size_caps']['system'])
                directory=root/'out/zip';directory.mkdir()
                with self.assertRaises(FileNotFoundError):write_layout_check(root,directory/'partition-layout-check.sh')
            with patch.dict(os.environ,BEYOUD_PARTITION_LAYOUT='extreme-default'):
                with self.assertRaises(ValueError):load(root)

    def test_content_sized_collection_labels_custom_repartition_and_exports_requirements(self):
        from test_alpha import alpha,package
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);s10(root)
            archive=root/'out/ArtisanROM_0.1.0-alpha1_beyond1lte.zip'
            package(archive,model='SM-G973F')
            import zipfile
            requirements={'layout':'content-sized','model':'SM-G973F','image_size_bytes':{'system':12*1024**3}}
            with zipfile.ZipFile(archive,'a') as z:z.writestr('REQUIRED-IMAGE-SIZES.json',json.dumps(requirements))
            dest=root/'collected'
            inputs=dict(stock_image_size_caps={'system':5976883200},image_size_caps={'system':None},partition_layout={'id':'content-sized'})
            with patch.object(alpha,'load_package_inputs',return_value=inputs):alpha.collect(root,dest)
            self.assertEqual(json.loads((dest/'REQUIRED-IMAGE-SIZES.json').read_text()),requirements)
            self.assertTrue(list(dest.glob('*CUSTOM-REPARTITION-REQUIRED-UNTESTED.zip')))
            self.assertIn('CUSTOM REPARTITION REQUIRED',(dest/'WARNING.txt').read_text())
            self.assertNotIn('REQUIRES DEFAULT EXTREMEROM',(dest/'WARNING.txt').read_text())
