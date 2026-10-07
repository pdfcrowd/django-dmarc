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
from unittest import skipUnless
import pytz
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DataError, IntegrityError, connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from dmarc.exceptions import InvalidDMARCReport
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
                        InvalidDMARCReport,
                        f'Missing required DMARC element: {tag}'
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
                    InvalidDMARCReport,
                    'Expected a DMARC feedback root element'
                ):
                    call_command('importdmarcreport', xml=StringIO(xml))
                self.assert_no_rows()


class ImportDMARCValidationTestCase(TestCase):
    def report_tree(self):
        root = ET.Element('feedback')
        metadata = ET.SubElement(root, 'report_metadata')
        for tag, value in (
            ('org_name', 'Example Reporter'),
            ('email', 'dmarc@example.com'),
            ('report_id', 'example.com:1773626403'),
        ):
            ET.SubElement(metadata, tag).text = value
        date_range = ET.SubElement(metadata, 'date_range')
        ET.SubElement(date_range, 'begin').text = '1773540003'
        ET.SubElement(date_range, 'end').text = '1773626403'
        policy = ET.SubElement(root, 'policy_published')
        for tag, value in (
            ('domain', 'example.com'), ('adkim', 'r'), ('aspf', 's'),
            ('p', 'reject'), ('sp', 'quarantine'), ('pct', '100'),
        ):
            ET.SubElement(policy, tag).text = value
        for ip in ('192.0.2.1', '192.0.2.2'):
            record = ET.SubElement(root, 'record')
            row = ET.SubElement(record, 'row')
            ET.SubElement(row, 'source_ip').text = ip
            ET.SubElement(row, 'count').text = '1'
            evaluated = ET.SubElement(row, 'policy_evaluated')
            for tag, value in (
                ('disposition', 'none'), ('dkim', 'pass'), ('spf', 'pass'),
            ):
                ET.SubElement(evaluated, tag).text = value
            identifiers = ET.SubElement(record, 'identifiers')
            ET.SubElement(identifiers, 'header_from').text = 'example.com'
            results = ET.SubElement(record, 'auth_results')
            spf = ET.SubElement(results, 'spf')
            ET.SubElement(spf, 'domain').text = 'example.com'
            ET.SubElement(spf, 'result').text = 'pass'
        return root

    def import_report(self, root):
        xml = ET.tostring(root, encoding='unicode')
        call_command('importdmarcreport', xml=StringIO(xml))
        return xml

    def assert_no_rows(self):
        for model in (Reporter, Report, Record, Result):
            self.assertEqual(model.objects.count(), 0, model.__name__)

    def assert_rejected_before_writes(self, root, message):
        with CaptureQueriesContext(connection) as queries:
            with self.assertRaisesMessage(InvalidDMARCReport, message):
                self.import_report(root)
        writes = [query['sql'] for query in queries if
                  query['sql'].lstrip().upper().startswith(
                      ('INSERT', 'UPDATE', 'DELETE'))]
        self.assertEqual(writes, [])
        self.assert_no_rows()

    def test_invalid_policy_values_rejected_before_writes(self):
        for field in ('adkim', 'aspf', 'p', 'sp'):
            for value in ('unknown', 'invalid', ''):
                with self.subTest(field=field, value=value):
                    root = self.report_tree()
                    root.find(f'policy_published/{field}').text = value
                    parsed_value = value or None
                    self.assert_rejected_before_writes(
                        root, f'policy_published.{field}={parsed_value!r}',
                    )

    def test_reports_all_invalid_policy_fields_with_report_id(self):
        root = self.report_tree()
        for field in ('adkim', 'aspf', 'p', 'sp'):
            root.find(f'policy_published/{field}').text = 'unknown'
        with self.assertRaises(InvalidDMARCReport) as raised:
            self.import_report(root)
        message = str(raised.exception)
        self.assertIn('example.com:1773626403', message)
        for field in ('adkim', 'aspf', 'p', 'sp'):
            self.assertIn(f"policy_published.{field}='unknown'", message)
        self.assertIn("expected 'r', 's'", message)
        self.assertIn("expected 'none', 'quarantine', 'reject'", message)
        self.assert_no_rows()

    def test_required_policy_is_not_defaulted(self):
        root = self.report_tree()
        policy = root.find('policy_published')
        policy.remove(policy.find('p'))
        self.assert_rejected_before_writes(root, 'policy_published.p=None')

    def test_optional_policy_defaults_and_original_xml_are_preserved(self):
        root = self.report_tree()
        policy = root.find('policy_published')
        for field in ('adkim', 'aspf', 'sp'):
            policy.remove(policy.find(field))
        xml = self.import_report(root)
        report = Report.objects.get()
        self.assertEqual(report.policy_adkim, 'r')
        self.assertEqual(report.policy_aspf, 'r')
        self.assertEqual(report.policy_sp, 'none')
        self.assertEqual(report.policy_p, 'reject')
        self.assertEqual(report.report_xml, xml)
        self.assertEqual(Record.objects.count(), 2)
        self.assertEqual(Result.objects.count(), 2)

    def test_valid_policy_values_and_duplicates(self):
        for index, policy_value in enumerate(('none', 'quarantine', 'reject')):
            with self.subTest(policy=policy_value):
                root = self.report_tree()
                root.find('report_metadata/report_id').text = f'report-{index}'
                root.find('policy_published/p').text = policy_value
                root.find('policy_published/sp').text = policy_value
                root.find('policy_published/adkim').text = ('r', 's')[index % 2]
                root.find('policy_published/aspf').text = ('s', 'r')[index % 2]
                self.import_report(root)
                self.import_report(root)
                self.assertEqual(Reporter.objects.count(), 1)
                self.assertEqual(Report.objects.count(), index + 1)
                self.assertEqual(Record.objects.count(), 2 * (index + 1))
                self.assertEqual(Result.objects.count(), 2 * (index + 1))

    def test_database_errors_roll_back_every_import_stage(self):
        for path in (
            'report_metadata/email',
            'policy_published/domain',
            'record[2]/identifiers/header_from',
            'record[2]/auth_results/spf/result',
        ):
            with self.subTest(path=path):
                root = self.report_tree()
                root.find(path).text = None
                with self.assertRaises(IntegrityError):
                    self.import_report(root)
                self.assert_no_rows()
        # A corrected retry must import fully rather than look like a duplicate.
        self.import_report(self.report_tree())
        self.assertEqual(Report.objects.count(), 1)
        self.assertEqual(Record.objects.count(), 2)
        self.assertEqual(Result.objects.count(), 2)

    def test_failed_import_preserves_preexisting_data(self):
        self.import_report(self.report_tree())
        root = self.report_tree()
        root.find('report_metadata/report_id').text = 'failed-report'
        root.find('record[2]/auth_results/spf/result').text = None
        with self.assertRaises(IntegrityError):
            self.import_report(root)
        self.assertEqual(Reporter.objects.count(), 1)
        self.assertEqual(Report.objects.get().report_id,
                         'example.com:1773626403')
        self.assertEqual(Record.objects.count(), 2)
        self.assertEqual(Result.objects.count(), 2)

    @skipUnless(connection.vendor == 'postgresql',
                'PostgreSQL enforces varchar length limits')
    def test_postgresql_length_errors_are_not_masked(self):
        for path, value in (
            ('report_metadata/org_name', 'x' * 101),
            ('policy_published/domain', 'x' * 101),
            ('record[2]/identifiers/header_from', 'x' * 101),
            ('record[2]/auth_results/spf/result', 'x' * 10),
        ):
            with self.subTest(path=path):
                root = self.report_tree()
                root.find(path).text = value
                with self.assertRaises(DataError):
                    self.import_report(root)
                self.assert_no_rows()

    def test_malformed_xml_raises_instead_of_reporting_success(self):
        with self.assertRaisesMessage(InvalidDMARCReport, 'DMARC XML failed'):
            call_command('importdmarcreport', xml=StringIO('<feedback>'))
        self.assert_no_rows()
