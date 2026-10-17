import unittest
from scripts.m3_r3_g5a import signature
class G5aPathSignatureTests(unittest.TestCase):
    def test_only_random_directory_and_checkout_root_are_normalized(self):
        def failure(root,folder,filename):
            return dict(kind='ERROR',traceback="FileNotFoundError: [Errno 2] No such file or directory: '"+root+'/'+folder+'/'+filename+"'")
        a=failure('C:/checkout_a','tmp00ge2g4o','source.json')
        b=failure('D:/checkout_b','tmpptzwyq7q','source.json')
        roots=['C:/checkout_a','D:/checkout_b']
        self.assertEqual(signature(a,roots),signature(b,roots))
        c=failure('D:/checkout_b','tmpptzwyq7q','labels.json')
        self.assertNotEqual(signature(a,roots),signature(c,roots))
        changed={**a,'traceback':a['traceback'].replace('[Errno 2]','[Errno 3]')}
        self.assertNotEqual(signature(a,roots),signature(changed,roots))
