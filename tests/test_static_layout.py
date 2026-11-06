import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from integration.static_layout import normalize
from test_build_stages import fixture, firmware


def layout(root, extras=('optics','prism','odm')):
    fixture(root);firmware(root)
    (root/'out/beyoud-logs').mkdir()
    work=root/'out/target/beyond2lte/work_dir'
    (work/'system/system').mkdir(parents=True)
    (work/'configs').mkdir()
    (work/'vendor/etc').mkdir(parents=True)
    (work/'vendor/etc/fstab.exynos9820').write_text('/dev/block/by-name/vendor /vendor ext4 ro wait\n'+''.join(f'/dev/block/by-name/{p} /{p} ext4 ro nofail,first_stage_mount\n' for p in extras))
    for kind in ('fs_config','file_context'):
        (work/'configs'/f'{kind}-system').write_text('system 0 0 755\n' if kind=='fs_config' else '/system u:object_r:system_file:s0\n')
    for name in extras:
        (work/name/'etc').mkdir(parents=True);(work/name/'etc/config.xml').write_text(name)
        (work/'system'/name).mkdir()
        (work/'configs'/f'fs_config-{name}').write_text(f'{name} 0 0 755\n{name}/etc/config.xml 1000 1000 644\n')
        (work/'configs'/f'file_context-{name}').write_text(f'/{name}(/.*)? u:object_r:vendor_file:s0\n')
    return work


class StaticLayoutTests(unittest.TestCase):
    def setUp(self):self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    def test_preserves_auxiliary_payload_labels_and_target_vendor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);work=layout(root)
            result=normalize(root,'beyond2lte')
            self.assertEqual({p['partition'] for p in result['embedded']},{'optics','prism','odm'})
            for name in ('optics','prism','odm'):
                self.assertFalse((work/name).exists())
                self.assertEqual((work/'system/system'/name/'etc/config.xml').read_text(),name)
                self.assertEqual((work/'system'/name).readlink(),Path('/system/'+name))
                self.assertIn(f'system/{name}/etc/config.xml 1000 1000 644',(work/'configs/fs_config-system').read_text())
                self.assertIn(f'/system/{name}(/.*)? u:object_r:vendor_file:s0',(work/'configs/file_context-system').read_text())
            self.assertEqual((work/'vendor/etc/fstab.exynos9820').read_text(),'/dev/block/by-name/vendor /vendor ext4 ro wait\n')
            self.assertEqual(normalize(root,'beyond2lte')['embedded'],[])

    def test_collision_rejects_before_moving_any_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);work=layout(root)
            (work/'system/system/prism/etc').mkdir(parents=True)
            (work/'system/system/prism/etc/config.xml').write_text('conflicting content')
            with self.assertRaises(ValueError):normalize(root,'beyond2lte')
            self.assertTrue((work/'optics/etc/config.xml').exists())
            self.assertTrue((work/'odm/etc/config.xml').exists())

    def test_unknown_partition_missing_metadata_and_size_are_not_ignored(self):
        for mode in ('unknown','metadata','size'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);work=layout(root,('optics',))
                if mode=='unknown':(work/'vendor_dlkm').mkdir()
                elif mode=='metadata':(work/'configs/fs_config-optics').unlink()
                else:
                    p=root/'out/fw/SM-G975F_AUT/os_partitions_metadata.txt'
                    p.write_text('system_size=1\nvendor_size=1000000\n')
                with self.assertRaises(ValueError):normalize(root,'beyond2lte')

    def test_existing_stock_auxiliary_partition_is_not_relocated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);work=layout(root,('optics',))
            p=root/'out/fw/SM-G975F_AUT/os_partitions_metadata.txt'
            p.write_text(p.read_text()+'optics_size=1000000\n')
            self.assertEqual(normalize(root,'beyond2lte')['embedded'],[])
            self.assertTrue((work/'optics/etc/config.xml').is_file())

    def test_standard_root_aliases_are_replaced_without_following_them(self):
        for name in ('odm','prism','optics'):
            for alias in (f'/vendor/{name}',f'/system/{name}',f'vendor/{name}'):
                with self.subTest(name=name,alias=alias),tempfile.TemporaryDirectory() as tmp:
                    root=Path(tmp);work=layout(root,(name,))
                    link=work/'system'/name;link.rmdir();link.symlink_to(alias)
                    before=normalize(root,'beyond2lte',check_only=True)
                    self.assertEqual(link.readlink(),Path(alias))
                    self.assertTrue((work/name/'etc/config.xml').exists())
                    report=normalize(root,'beyond2lte')
                    self.assertEqual(report['embedded'][0]['previous_root_link'],alias)
                    self.assertEqual(link.readlink(),Path('/system/'+name))
                    self.assertEqual((work/'system/system'/name/'etc/config.xml').read_text(),name)

    def test_nonempty_root_directory_is_merged_and_keeps_legacy_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);work=layout(root,('odm',))
            (work/'system/odm/legacy.conf').write_text('preserved')
            with (work/'configs/fs_config-system').open('a') as stream:stream.write('odm/legacy.conf 1000 1000 644\n')
            with (work/'configs/file_context-system').open('a') as stream:stream.write('/odm/legacy.conf u:object_r:vendor_file:s0\n')
            normalize(root,'beyond2lte')
            self.assertEqual((work/'system/system/odm/legacy.conf').read_text(),'preserved')
            self.assertIn('system/odm/legacy.conf 1000 1000 644',(work/'configs/fs_config-system').read_text())
            self.assertIn('/system/odm/legacy.conf u:object_r:vendor_file:s0',(work/'configs/file_context-system').read_text())

    def test_unknown_alias_and_conflicting_legacy_files_fail_before_any_move(self):
        for mode in ('link','file','metadata'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);work=layout(root)
                if mode=='link':
                    (work/'system/odm').rmdir();(work/'system/odm').symlink_to('/home/user/private')
                elif mode=='file':
                    (work/'system/odm/etc').mkdir();(work/'system/odm/etc/config.xml').write_text('different')
                else:
                    with (work/'configs/fs_config-system').open('a') as stream:stream.write('system/odm/etc/config.xml 123 456 600\n')
                with self.assertRaises(ValueError):normalize(root,'beyond2lte')
                self.assertTrue((work/'odm/etc/config.xml').exists())
                self.assertTrue((work/'optics/etc/config.xml').exists())

    def test_duplicate_files_count_once_in_projected_image_and_preserve_vendor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);work=layout(root,('odm',))
            (work/'system/odm/etc').mkdir()
            (work/'system/odm/etc/config.xml').write_text('odm')
            (work/'vendor/odm').mkdir()
            (work/'vendor/odm/stock.conf').write_text('stock must remain')
            with (work/'configs/fs_config-system').open('a') as stream:stream.write('odm/etc/config.xml 1000 1000 644\n')
            cap=root/'out/fw/SM-G975F_AUT/os_partitions_metadata.txt'
            cap.write_text('system_size=3\nvendor_size=1000000\n')
            report=normalize(root,'beyond2lte',check_only=True)
            self.assertEqual(report['payload_bytes']['system'],3)
            normalize(root,'beyond2lte')
            self.assertEqual((work/'system/system/odm/etc/config.xml').read_text(),'odm')
            self.assertEqual((work/'vendor/odm/stock.conf').read_text(),'stock must remain')
