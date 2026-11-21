# SPDX-License-Identifier: Apache-2.0
"""Synthetic Android vendor_boot v4 and Pixel-yogi-like regression tests."""
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace as Obj
from unittest.mock import patch
from twrpdtgen.vendor_ramdisk import plan_untyped_vendor_fragments, VendorFragmentConflict


def fragment(root, index, type=1, board=(0,)*16, name='default'):
    return Obj(root=root, index=index, ramdisk_type=type,
               board_id=board, name=name,
               type_name={0:'none',1:'platform',2:'recovery',3:'dlkm'}[type])


def device_tree_class():
    names=['git','sebaubuntu_libs','sebaubuntu_libs.libaik',
           'sebaubuntu_libs.libandroid','sebaubuntu_libs.libandroid.device_info',
           'sebaubuntu_libs.libandroid.fstab','sebaubuntu_libs.libandroid.props',
           'sebaubuntu_libs.liblogging','twrpdtgen.boot_image',
           'twrpdtgen.ramdisk_skeleton','twrpdtgen.templates']
    fake={name:types.ModuleType(name) for name in names}
    members={
      'git':{'Repo':object},
      'sebaubuntu_libs.libaik':{'AIKManager':object},
      'sebaubuntu_libs.libandroid.device_info':{'DeviceInfo':object},
      'sebaubuntu_libs.libandroid.fstab':{'Fstab':object},
      'sebaubuntu_libs.libandroid.props':{'BuildProp':object},
      'sebaubuntu_libs.liblogging':{'LOGD':lambda x:None},
      'twrpdtgen.boot_image':{'ModernImageManager':object,'is_modern_boot_image':lambda _:True},
      'twrpdtgen.ramdisk_skeleton':{'materialize_recovery_skeleton':lambda *a,**kw:{},
                                    'write_ramdisk_manifest':lambda *a,**kw:None},
      'twrpdtgen.templates':{'render_template':lambda *a,**kw:''},
    }
    for key,attrs in members.items():
        fake[key].__dict__.update(attrs)
    spec=importlib.util.spec_from_file_location(
        '_test_vendor_boot_yogi',Path(__file__).resolve().parents[1] /
        'twrpdtgen'/'device_tree.py')
    module=importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules,fake):
        spec.loader.exec_module(module)
    return module.DeviceTree


class VendorFragmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
    def root(self, label, files={}):
        result=self.base/label
        result.mkdir()
        for name,contents in files.items():
            file=result/name
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_text(contents)
        return result
    def test_common_platform_and_dlkm(self):
        a=fragment(self.root('a',{'etc/fstab.yogi':'fstab'}),0)
        b=fragment(self.root('b',{'lib/modules/mod.ko':'binary'}),1,3,name='dlkm')
        sources,audit=plan_untyped_vendor_fragments([a,b])
        self.assertEqual(sources,[a,b])
        self.assertFalse(audit['warnings'])
    def test_specific_fragment_not_automatically_selected(self):
        a=fragment(self.root('board_a',{'etc/fstab.yogi':'bad'}),0,board=(1,))
        sources,audit=plan_untyped_vendor_fragments([a],allow_generic_fallback=True)
        self.assertFalse(sources)
        self.assertEqual(len(audit['skipped_board_specific_fragments']),1)
    def test_conflicting_common_fragment_falls_back(self):
        a=fragment(self.root('a',{'etc/fstab.yogi':'one'}),0)
        b=fragment(self.root('b',{'etc/fstab.yogi':'two'}),1)
        sources,audit=plan_untyped_vendor_fragments([a,b],allow_generic_fallback=True)
        self.assertFalse(sources)
        self.assertEqual(audit['conflicting_paths'][0]['path'],'etc/fstab.yogi')
        with self.assertRaises(VendorFragmentConflict):
            plan_untyped_vendor_fragments([a,b])
    def test_one_common_and_one_variant(self):
        a=fragment(self.root('common',{}),0)
        b=fragment(self.root('variant',{}),1,board=(7,))
        sources,audit=plan_untyped_vendor_fragments([a,b])
        self.assertEqual(sources,[a])
        self.assertEqual(len(audit['skipped_board_specific_fragments']),1)
    def test_device_tree_selects_shared_sources_only(self):
        Tree=device_tree_class()
        init=self.root('generic')
        platform=self.root('platform',{'etc/fstab.yogi':'right'})
        dlkm=self.root('modules',{'lib/modules/a.ko':'x'})
        special=self.root('wrong',{'etc/fstab.yogi':'wrong'})
        a=fragment(platform,0);b=fragment(dlkm,1,3);c=fragment(special,2,board=(1,))
        vendor=Obj(kind='vendor_boot',source=Path('vendor_boot.img'),
                   vendor_ramdisk_fragments=[a,b,c],ramdisk_roots=[platform,dlkm,special])
        generic=Obj(kind='init_boot',source=Path('init_boot.img'),ramdisk_roots=[init])
        tree=object.__new__(Tree)
        tree.modern_manager=object();tree.recovery_layout='vendor_boot'
        tree.recovery_fragment=None;tree.image_info=Obj(source_images=[vendor,generic])
        roots,source=tree._select_recovery_ramdisk()
        self.assertEqual(roots,[init,platform,dlkm])
        self.assertNotIn(special,roots)
        self.assertEqual(source['kind'],'vendor_boot_composed_shared_fragments')
    def test_init_boot_fallback_when_all_fragments_specific(self):
        Tree=device_tree_class()
        init=self.root('generic')
        a=fragment(self.root('board_a'),0,board=(1,))
        b=fragment(self.root('board_b'),1,board=(2,))
        vendor=Obj(kind='vendor_boot',source=Path('vendor_boot.img'),
                   vendor_ramdisk_fragments=[a,b],ramdisk_roots=[a.root,b.root])
        generic=Obj(kind='init_boot',source=Path('init_boot.img'),ramdisk_roots=[init])
        tree=object.__new__(Tree)
        tree.modern_manager=object();tree.recovery_layout='vendor_boot'
        tree.recovery_fragment=None;tree.image_info=Obj(source_images=[vendor,generic])
        roots,source=tree._select_recovery_ramdisk()
        self.assertEqual(roots,[init])
        self.assertEqual(source['kind'],'init_boot_generic_with_unresolved_vendor_fragments')
    def test_verified_explicit_fragment_override(self):
        Tree=device_tree_class()
        a=fragment(self.root('board_a'),0,board=(1,),name='board-a')
        b=fragment(self.root('board_b'),1,board=(2,),name='board-b')
        vendor=Obj(kind='vendor_boot',source=Path('vendor_boot.img'),
                   vendor_ramdisk_fragments=[a,b],ramdisk_roots=[a.root,b.root])
        tree=object.__new__(Tree);tree.modern_manager=object()
        tree.recovery_layout='vendor_boot';tree.recovery_fragment='board-b'
        tree.image_info=Obj(source_images=[vendor])
        roots,source=tree._select_recovery_ramdisk()
        self.assertEqual(roots,[b.root])
        self.assertEqual(source['fragment_name'],'board-b')
    def test_partition_fstab_not_taken_from_wrong_board(self):
        Tree=device_tree_class()
        from twrpdtgen.next_support import NextOptions
        init=self.root('generic',{'prop.default':'ro.build.version.sdk=36'})
        a=self.root('board_a',{'etc/fstab.yogi':'wrong A','prop.default':'ro.product.device=wrong'})
        b=self.root('board_b',{'etc/fstab.yogi':'wrong B'})
        vendor=self.root('vendor_partition',{
            'etc/fstab.yogi':'/dev/block/mapper/vendor /vendor ext4 ro wait,logical\n',
            'build.prop':'ro.build.version.sdk=36\nro.product.device=yogi\n'})
        for image in ('init_boot.img','vendor_boot.img'):
            (self.base/image).write_bytes(b'fixture')
        fragments=[fragment(a,0,board=(1,)),fragment(b,1,board=(2,))]
        parsed=Obj(source_images=[
            Obj(kind='init_boot',source=self.base/'init_boot.img',ramdisk_roots=[init]),
            Obj(kind='vendor_boot',source=self.base/'vendor_boot.img',
                ramdisk_roots=[a,b],vendor_ramdisk_fragments=fragments)],
            ramdisk_roots=[init,a,b],recovery_ramdisk_roots=[],
            recovery_layout_hint='vendor_boot',kernel=None)
        loaded=[]
        class Props:
            def import_props(self,path):loaded.append(Path(path))
        class Device:
            def __init__(self,props):
                self.manufacturer='google';self.codename='yogi'
                self.device_is_ab=True;self.vendor_build_security_patch='2026-09-01'
        class Fstab:
            def __init__(self,path):self.path=path
            def get_logical_partitions(self):return []
            def get_ab_partitions_models(self):return []
        class Manager:
            def __init__(self,*a,**kw):pass
            def unpack(self):return parsed
        with patch.dict(Tree.__init__.__globals__,{
             'BuildProp':Props,'DeviceInfo':Device,'Fstab':Fstab,
             'ModernImageManager':Manager,'is_modern_boot_image':lambda _:True,
             'LOGD':lambda *a:None}):
            instance=Tree(self.base/'vendor_boot.img', options=NextOptions(),
                          init_boot=self.base/'init_boot.img',
                          partition_roots={'vendor':vendor})
        self.assertEqual(instance.stock_fstab_path,vendor/'etc/fstab.yogi')
        self.assertNotIn(a/'prop.default',loaded)


if __name__=='__main__':
    unittest.main()
