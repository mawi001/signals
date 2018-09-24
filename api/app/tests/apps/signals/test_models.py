"""
Tests for the model manager in signals.apps.signals.models
"""
from unittest import mock

from django.contrib.gis.geos import Point
from django.test import TransactionTestCase
from django.utils import timezone

from signals.apps.signals.models import (
    GEMELD,
    STADSDEEL_CENTRUM,
    CategoryAssignment,
    Location,
    Priority,
    Reporter,
    Signal,
    Status,
    SubCategory)
from tests.apps.signals import factories
from tests.apps.signals.factories import SubCategoryFactory


class TestSignalManager(TransactionTestCase):

    def setUp(self):
        sub_category = SubCategoryFactory.create(name='Veeg- / zwerfvuil')

        # Deserialized data
        self.signal_data = {
            'text': 'text message',
            'text_extra': 'test message extra',
            'incident_date_start': timezone.now(),
        }
        self.location_data = {
            'geometrie': Point(4.898466, 52.361585),
            'stadsdeel': STADSDEEL_CENTRUM,
            'buurt_code': 'aaa1',
        }
        self.reporter_data = {
            'email': 'test_reporter@example.com',
            'phone': '0123456789',
        }
        self.category_assignment_data = {
            'sub_category': sub_category,
        }
        self.status_data = {
            'state': GEMELD,
            'text': 'text message',
            'user': 'test@example.com',
        }
        self.priority_data = {
            'priority': Priority.PRIORITY_HIGH,
        }

    @mock.patch('signals.apps.signals.models.create_initial', autospec=True)
    def test_create_initial(self, patched_create_initial):
        # Create the full Signal
        signal = Signal.actions.create_initial(
            self.signal_data,
            self.location_data,
            self.status_data,
            self.category_assignment_data,
            self.reporter_data)

        # Check everything is present:
        self.assertEquals(Signal.objects.count(), 1)
        self.assertEquals(Location.objects.count(), 1)
        self.assertEquals(Status.objects.count(), 1)
        self.assertEquals(CategoryAssignment.objects.count(), 1)
        self.assertEquals(Reporter.objects.count(), 1)
        self.assertEquals(Priority.objects.count(), 1)

        # Check that we sent the correct Django signal
        patched_create_initial.send.assert_called_once_with(sender=Signal.actions.__class__,
                                                            signal_obj=signal)

    def test_create_initial_with_priority_data(self):
        signal = Signal.actions.create_initial(
            self.signal_data,
            self.location_data,
            self.status_data,
            self.category_assignment_data,
            self.reporter_data,
            self.priority_data)

        self.assertEqual(signal.priority.priority, Priority.PRIORITY_HIGH)

    @mock.patch('signals.apps.signals.models.update_location', autospec=True)
    def test_update_location(self, patched_update_location):
        signal = factories.SignalFactory.create()

        # Update the signal
        prev_location = signal.location
        location = Signal.actions.update_location(self.location_data, signal)

        # Check that the signal was updated in db
        self.assertEqual(signal.location, location)
        self.assertEqual(signal.locations.count(), 2)

        # Check that we sent the correct Django signal
        patched_update_location.send.assert_called_once_with(
            sender=Signal.actions.__class__,
            signal_obj=signal,
            location=location,
            prev_location=prev_location)

    @mock.patch('signals.apps.signals.models.update_status', autospec=True)
    def test_update_status(self, patched_update_status):
        signal = factories.SignalFactory.create()

        # Update the signal
        prev_status = signal.status
        status = Signal.actions.update_status(self.status_data, signal)

        # Check that the signal was updated in db
        self.assertEqual(signal.status, status)
        self.assertEqual(signal.statuses.count(), 2)

        # Check that we sent the correct Django signal
        patched_update_status.send.assert_called_once_with(
            sender=Signal.actions.__class__,
            signal_obj=signal,
            status=status,
            prev_status=prev_status)

    @mock.patch('signals.apps.signals.models.update_category_assignment', autospec=True)
    def test_update_category_assignment(self, patched_update_category_assignment):
        signal = factories.SignalFactory.create()

        # Update the signal
        prev_category_assignment = signal.category_assignment
        category_assignment = Signal.actions.update_category_assignment(
            self.category_assignment_data, signal)

        # Check that the signal was updated in db
        self.assertEqual(signal.category_assignment, category_assignment)
        self.assertEqual(signal.sub_categories.count(), 2)

        # Check that we sent the correct Django signal
        patched_update_category_assignment.send.assert_called_once_with(
            sender=Signal.actions.__class__,
            signal_obj=signal,
            category_assignment=category_assignment,
            prev_category_assignment=prev_category_assignment)

    @mock.patch('signals.apps.signals.models.update_reporter', autospec=True)
    def test_update_reporter(self, patched_update_reporter):
        signal = factories.SignalFactory.create()

        # Update the signal
        prev_reporter = signal.reporter
        reporter = Signal.actions.update_reporter(self.reporter_data, signal)

        # Check that the signal was updated in db
        self.assertEqual(signal.reporter, reporter)
        self.assertEqual(signal.reporters.count(), 2)

        patched_update_reporter.send.assert_called_once_with(
            sender=Signal.actions.__class__,
            signal_obj=signal,
            reporter=reporter,
            prev_reporter=prev_reporter)

    @mock.patch('signals.apps.signals.models.update_priority')
    def test_update_priority(self, patched_update_priority):
        signal = factories.SignalFactory.create()

        # Update the signal
        prev_priority = signal.priority
        priority = Signal.actions.update_priority(self.priority_data, signal)

        # Check that the signal was updated in db
        self.assertEqual(signal.priority, priority)
        self.assertEqual(signal.priorities.count(), 2)

        patched_update_priority.send.assert_called_once_with(
            sender=Signal.actions.__class__,
            signal_obj=signal,
            priority=priority,
            prev_priority=prev_priority)


class TestCategoryDeclarations(TransactionTestCase):

    def test_main_category_string(self):
        main_category = factories.MainCategoryFactory.create(name='First category')

        self.assertEqual(str(main_category), 'First category')

    def test_sub_category_string(self):
        sub_category = factories.SubCategoryFactory.create(main_category__name='First category',
                                                           name='Sub')

        self.assertEqual(str(sub_category), 'Sub (First category)')

    def test_department_string(self):
        department = factories.DepartmentFactory.create(code='ABC', name='Department A')

        self.assertEqual(str(department), 'ABC (Department A)')
