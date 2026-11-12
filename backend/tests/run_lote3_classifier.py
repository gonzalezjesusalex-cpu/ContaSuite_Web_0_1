"""Pure synthetic classifier tests; no app/database/configuration/provider imports."""
import importlib.util
from pathlib import Path
from io import BytesIO
import unittest
spec=importlib.util.spec_from_file_location('isolated_classifier',Path(__file__).parents[1]/'app/storage/classifier.py')
classifier=importlib.util.module_from_spec(spec)
spec.loader.exec_module(classifier)
COMPANIES=[{'id':'a','rfc':'AAA010101AA1'},{'id':'b','rfc':'BBB010101BB1'}]
XML=b'<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Fecha="2026-11-11T12:00:00"><cfdi:Emisor Rfc="AAA010101AA1"/><cfdi:Receptor Rfc="BBB010101BB1"/></cfdi:Comprobante>'
class ClassificationTests(unittest.TestCase):
    def classify(self,content=XML,companies=COMPANIES):
        return classifier.classify(BytesIO(content),'synthetic.xml',companies)
    def test_two_registered_roles(self):
        r=self.classify();self.assertFalse(r['automatic'])
        self.assertEqual(r['links'],[{'company_id':'a','role':'issuer'},{'company_id':'b','role':'receiver'}])
        self.assertFalse(r['evidence']['authority_validated'])
    def test_one_registered(self):
        r=self.classify(companies=COMPANIES[:1]);self.assertTrue(r['automatic']);self.assertEqual(len(r['links']),1)
    def test_ambiguous_identity(self):
        r=self.classify(companies=COMPANIES+[{'id':'duplicate','rfc':' aaa010101aa1 '}])
        self.assertFalse(r['automatic']);self.assertEqual(r['evidence']['reason'],'ambiguous_identity')
    def test_malformed_no_automatic(self):
        self.assertFalse(self.classify(b'<broken')['automatic'])
    def test_private_key_never_touched(self):
        class Forbidden:
            def seek(self,*args):raise AssertionError('Private content touched')
        self.assertEqual(classifier.classify(Forbidden(),'private.key',COMPANIES)['links'],[])
    def test_exact_rfc_normalization(self):
        self.assertTrue(self.classify(XML.replace(b'AAA010101AA1',b' aaa010101aa1 '),COMPANIES[:1])['automatic'])
    def test_repeated_role_requires_review(self):
        content=XML.replace(b'<cfdi:Receptor',b'<cfdi:Emisor Rfc="AAA010101AA1"/><cfdi:Receptor')
        self.assertFalse(self.classify(content)['automatic'])
if __name__=='__main__':unittest.main(verbosity=2)
