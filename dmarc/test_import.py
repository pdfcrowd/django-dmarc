#----------------------------------------------------------------------
# Copyright (c) 2015-2021, Persistent Objects Ltd https://p-o.co.uk/
#
# License: BSD
#----------------------------------------------------------------------

"""
DMARC tests for importing Aggregate Reports
http://dmarc.org/resources/specification/
"""
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from io import StringIO
import pytz
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from dmarc.models import Reporter, Report, Record, Result

class ImportDMARCReportTestCase(TestCase):
    """
    Standard core tests
    """

    def setUp(self):
        """Set up test environment"""
        pass

    def test_importdmarcreport_withoutargs(self):
        """Test importing withuot args"""
        msg = 'Check usage, please supply a single DMARC report file or email'
        out = StringIO()
        try:
            call_command('importdmarcreport', stdout=out)
        except CommandError as cmderror:
            msgerror = str(cmderror)
        self.assertIn(msg, msgerror)

    def test_importdmarcreport_filenotfound(self):
        """Test importing xml file not found"""
        msg = 'Unable to find DMARC file: filenotfound.xml'
        out = StringIO()
        msgerror = ''
        try:
            call_command(
                'importdmarcreport',
                xml='filenotfound.xml',
                stderr=out)
        except CommandError as cmderror:
            msgerror = str(cmderror)
        self.assertEqual(msgerror, msg)

    def test_importdmarcreport_file(self):
        """Test importing xml file"""
        out = StringIO()
        data = Reporter.objects.all()
        self.assertEqual(len(data), 0)
        dmarcreport = os.path.dirname(os.path.realpath(__file__))
        dmarcreport = os.path.join(dmarcreport, 'tests/dmarcreport.xml')
        call_command('importdmarcreport', xml=dmarcreport, stderr=out)
        self.assertIn('', out.getvalue())
        # Reporter object
        data = Reporter.objects.all()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0].org_name, 'Persistent Objects')
        self.assertEqual(data[0].email, 'ahicks@p-o.co.uk')
        # Report object
        data = Report.objects.all()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0].report_id, '5edbe461-ccda-1e41-abdb-00c0af3f9715@p-o.co.uk')
        if settings.USE_TZ:
            tz_utc = pytz.timezone(settings.TIME_ZONE)
            self.assertEqual(data[0].date_begin, datetime(2015, 2, 25, 12, 0, tzinfo=tz_utc))
            self.assertEqual(data[0].date_end, datetime(2015, 2, 26, 12, 0, tzinfo=tz_utc))
        else:
            self.assertEqual(data[0].date_begin, datetime(2015, 2, 25, 12, 0))
            self.assertEqual(data[0].date_end, datetime(2015, 2, 26, 12, 0))
        self.assertEqual(data[0].policy_domain, 'p-o.co.uk')
        self.assertEqual(data[0].policy_adkim, 'r')
        self.assertEqual(data[0].policy_aspf, 'r')
        self.assertEqual(data[0].policy_p, 'quarantine')
        self.assertEqual(data[0].policy_sp, 'none')
        self.assertEqual(data[0].policy_pct, 100)
        self.assertIn("<?xml version='1.0' encoding='utf-8'?>", data[0].report_xml)
        self.assertIn("<feedback>", data[0].report_xml)
        # Record
        data = Record.objects.all()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0].source_ip, '80.229.143.200')
        self.assertEqual(data[0].recordcount, 1)
        self.assertEqual(data[0].policyevaluated_disposition, 'none')
        self.assertEqual(data[0].policyevaluated_dkim, 'pass')
        self.assertEqual(data[0].policyevaluated_spf, 'pass')
        self.assertEqual(data[0].policyevaluated_reasontype, '')
        self.assertEqual(data[0].policyevaluated_reasoncomment, '')
        self.assertEqual(data[0].identifier_headerfrom, 'p-o.co.uk')

        # Result
        data = Result.objects.all()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0].record_type, 'spf')
        self.assertEqual(data[0].domain, 'p-o.co.uk')
        self.assertEqual(data[0].result, 'pass')
        self.assertEqual(data[1].record_type, 'dkim')
        self.assertEqual(data[1].domain, 'p-o.co.uk')
        self.assertEqual(data[1].result, 'pass')


class ImportDMARCNamespaceTestCase(TestCase):
    namespaces = (
        'urn:ietf:params:xml:ns:dmarc-2.0',
        'http://dmarc.org/dmarc-xml/0.1',
    )

    def report_tree(self):
        filename = os.path.join(os.path.dirname(__file__),
                                'tests/dmarcreport.xml')
        return ET.parse(filename).getroot()

    def report_xml(self, root, namespace=None, prefixed=False):
        if namespace:
            for node in root.iter():
                if not node.tag.startswith('{'):
                    node.tag = f'{{{namespace}}}{node.tag}'
        return ET.tostring(
            root, encoding='unicode',
            default_namespace=None if prefixed else namespace,
        )

    def assert_imported(self, xml):
        previous_count = Report.objects.count()
        call_command('importdmarcreport', xml=StringIO(xml))
        self.assertEqual(Report.objects.count(), previous_count + 1)
        report = Report.objects.latest('pk')
        self.assertEqual(report.report_xml, xml)
        self.assertEqual(report.reporter.org_name, 'Persistent Objects')
        self.assertEqual(report.reporter.email, 'ahicks@p-o.co.uk')
        self.assertEqual(report.date_begin.timestamp(), 1424865600)
        self.assertEqual(report.date_end.timestamp(), 1424952000)
        self.assertEqual(report.policy_domain, 'p-o.co.uk')
        self.assertEqual(report.policy_p, 'quarantine')
        self.assertEqual(report.policy_pct, 100)
        record = Record.objects.get(report=report)
        self.assertEqual(record.source_ip, '80.229.143.200')
        self.assertEqual(record.recordcount, 1)
        self.assertEqual(record.identifier_headerfrom, 'p-o.co.uk')
        self.assertEqual(record.policyevaluated_disposition, 'none')
        self.assertEqual(record.policyevaluated_dkim, 'pass')
        self.assertEqual(record.policyevaluated_spf, 'pass')
        self.assertCountEqual(
            record.results.values_list('record_type', 'domain', 'result'),
            [('spf', 'p-o.co.uk', 'pass'), ('dkim', 'p-o.co.uk', 'pass')],
        )
        return record

    def assert_no_rows(self):
        for model in (Reporter, Report, Record, Result):
            self.assertFalse(model.objects.exists(), model.__name__)

    def test_default_and_prefixed_namespaces(self):
        for namespace in self.namespaces:
            for prefixed in (False, True):
                with self.subTest(namespace=namespace, prefixed=prefixed):
                    root = self.report_tree()
                    root.find('report_metadata/report_id').text = (
                        f'{namespace}-{prefixed}'
                    )
                    evaluated = root.find('record/row/policy_evaluated')
                    reason = ET.SubElement(evaluated, 'reason')
                    ET.SubElement(reason, 'type').text = 'forwarded'
                    ET.SubElement(reason, 'comment').text = 'Forwarded mail'
                    xml = self.report_xml(root, namespace, prefixed)
                    record = self.assert_imported(xml)
                    self.assertEqual(record.policyevaluated_reasontype,
                                     'forwarded')
                    self.assertEqual(record.policyevaluated_reasoncomment,
                                     'Forwarded mail')

    def test_foreign_namespace_elements_are_not_imported(self):
        root = self.report_tree()
        for tag in ('report_metadata', 'policy_published', 'record'):
            root.insert(0, ET.Element(f'{{urn:example:extension}}{tag}'))
        domain = ET.Element('{urn:example:extension}domain')
        domain.text = 'extension.example'
        root.find('record/auth_results/dkim').insert(0, domain)
        self.assert_imported(self.report_xml(root, self.namespaces[0]))

    def test_missing_sections_rejected_before_writes(self):
        for namespace in (None, self.namespaces[0]):
            for tag in ('report_metadata', 'policy_published'):
                with self.subTest(namespace=namespace, section=tag):
                    root = self.report_tree()
                    root.remove(root.find(tag))
                    # An extension with the same local name is not metadata.
                    root.append(ET.Element(f'{{urn:example:extension}}{tag}'))
                    xml = self.report_xml(root, namespace)
                    with self.assertRaisesMessage(
                        CommandError, f'Missing required DMARC element: {tag}'
                    ):
                        call_command('importdmarcreport', xml=StringIO(xml))
                    self.assert_no_rows()

    def test_invalid_root_rejected_before_writes(self):
        for namespace, tag in ((None, 'document'),
                               ('urn:example:unsupported', 'feedback')):
            with self.subTest(namespace=namespace, root=tag):
                root = self.report_tree()
                root.tag = tag
                xml = self.report_xml(root, namespace)
                with self.assertRaisesMessage(
                    CommandError, 'Expected a DMARC feedback root element'
                ):
                    call_command('importdmarcreport', xml=StringIO(xml))
                self.assert_no_rows()
