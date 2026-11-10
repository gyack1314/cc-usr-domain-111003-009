import unittest
from workbench.domain import *

class DomainBoundaryTests(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(leaf_key('fold2'),['fold',2])
        with self.assertRaises(ValueError):leaf_key('4')
        self.assertEqual(coverage(['1r','1v'],['1r','2r']),{'missing':['1v'],'duplicate':[],'extra':['2r']})
        self.assertFalse(licensed({'uses':['内部'],'until':'2027-01-01'},'公开','2026-01-01'))
