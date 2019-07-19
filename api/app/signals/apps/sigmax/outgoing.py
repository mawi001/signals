"""
Handle sending a signal to sigmax.
Retry logic ao are handled by Celery.
"""
import logging
import os
import uuid
from datetime import timedelta

import requests
from django.conf import settings
from django.template.loader import render_to_string
from lxml import etree

from signals.apps.sigmax.models import CityControlRoundtrip, Signal
from signals.apps.sigmax.pdf import _generate_pdf
from signals.apps.signals.models import (
    STADSDEEL_CENTRUM,
    STADSDEEL_NIEUWWEST,
    STADSDEEL_NOORD,
    STADSDEEL_OOST,
    STADSDEEL_WEST,
    STADSDEEL_WESTPOORT,
    STADSDEEL_ZUID,
    STADSDEEL_ZUIDOOST,
    Priority,
    Signal
)
from signals.apps.signals import workflow


logger = logging.getLogger(__name__)

# The double quotes are part of the SOAP spec
CREEER_ZAAK_SOAPACTION = \
    '"http://www.egem.nl/StUF/sector/zkn/0310/CreeerZaak_Lk01"'

VOEG_ZAAKDOCUMENT_TOE_SOAPACTION = \
    '"http://www.egem.nl/StUF/sector/zkn/0310/VoegZaakdocumentToe_Lk01"'

SIGNALS_API_BASE = os.getenv('SIGNALS_API_BASE',
                             'https://acc.api.data.amsterdam.nl')

SIGMAX_REQUIRED_ADDRESS_FIELDS = ['woonplaats', 'openbare_ruimte', 'huisnummer']
# See ticket SIG-743 for the origin of this mapping:
SIGMAX_STADSDEEL_MAPPING = {
    STADSDEEL_CENTRUM: 'SDC',
    STADSDEEL_NOORD: 'SDN',
    STADSDEEL_NIEUWWEST: 'SDNW',
    STADSDEEL_OOST: 'SDO',
    STADSDEEL_WEST: 'SDW',
    STADSDEEL_ZUID: 'SDZ',
    STADSDEEL_ZUIDOOST: 'SDZO',
    STADSDEEL_WESTPOORT: 'SDWP',  # not part of spec, but present in our data model
}

MAX_ROUND_TRIPS = 99


class SigmaxException(Exception):
    pass


def _generate_omschrijving(signal):
    """Generate brief descriptive text for list view in CityControl"""
    # We need sequence number to show in CityControl list view
    sequence_number = _generate_sequence_number(signal)

    # Note: we do not mention main or category here (too many characters)
    is_urgent = 'URGENT' if signal.priority.priority == Priority.PRIORITY_HIGH else 'Terugkerend'

    # Borough (stadsdeel) codes for Sigmax/CityControl are custom and do not
    # match the official ones as used by the municipality of Amsterdam; hence:
    stadsdeel = signal.location.stadsdeel
    stadsdeel_code_sigmax = SIGMAX_STADSDEEL_MAPPING.get(stadsdeel, 'SD--')

    return 'SIA-{}.{} {} {} {}'.format(
        signal.id,
        sequence_number,
        is_urgent,
        stadsdeel_code_sigmax,
        signal.location.short_address_text,
    )


def _generate_sequence_number(signal):
    """Generate a sequence number for external identifier in CityControl."""
    roundtrip_count = CityControlRoundtrip.objects.filter(_signal=signal).count()

    if not roundtrip_count < MAX_ROUND_TRIPS:  # check not sent too often
        raise SigmaxException(
            'Signal SIA-{} was sent to SigmaxCityControl too often.'.format(signal.sia_id))

    return '{0:02d}'.format(roundtrip_count + 1)  # start counting at one


def _address_matches_sigmax_expectation(address_dict):
    """Return whether an address has all information Sigmax/CityControl needs.

    Note: we do not validate the address against the Basisadministratie
    Adresses en Gebouwen (BAG). We do check that all required components are
    non-empty.
    """
    # TODO: consider checking the existence of an address / make it impossible
    # for non (BAG) validated addresses to reach Sigmax.
    # TODO: consider moving to a JSONSchema style check here (more concise)
    if not address_dict:  # protect against empty address fields
        return False

    for field in SIGMAX_REQUIRED_ADDRESS_FIELDS:
        if field not in address_dict:
            return False

    # We want a "huisnummer" to be (convertable to) an actual number
    try:
        int(address_dict['huisnummer'])
    except (ValueError, TypeError):
        return False

    # We want non-empty strings for "woonplaats" and "openbare_ruimte"
    if (not isinstance(address_dict['woonplaats'], str) or
            not isinstance(address_dict['openbare_ruimte'], str)):
        return False

    if (not address_dict['woonplaats'].strip() or
            not address_dict['openbare_ruimte'].strip()):
        return False

    return True


def _generate_creeerZaak_Lk01(signal, seq_no):
    """Generate XML for Sigmax creeerZaak_Lk01

    SIGMAX will be set up to receive Signals (meldingen) that have no address but do have
    coordinates (middle of park, somewhere on a body of water, etc.).
    """
    num_days_priority_mapping = {
        Priority.PRIORITY_HIGH: 1,
        Priority.PRIORITY_NORMAL: 3,
    }
    incident_date_end = (
        signal.created_at + timedelta(days=num_days_priority_mapping[signal.priority.priority]))

    return render_to_string('sigmax/creeerZaak_Lk01.xml', context={
        'address_matches_sigmax_expectation':
            _address_matches_sigmax_expectation(signal.location.address),
        'signal': signal,
        'sequence_number': seq_no,
        'incident_date_end': signal.incident_date_end or incident_date_end,
        'x': str(signal.location.geometrie.x),
        'y': str(signal.location.geometrie.y),
        'omschrijving': _generate_omschrijving(signal),
    })


def _generate_voegZaakdocumentToe_Lk01(signal, seq_no):
    """
    Generate XML for Sigmax voegZaakdocumentToe_Lk01 (for the PDF case)
    """
    # TODO: generalize, so that either PDF or JPG can be sent.
    encoded_pdf = _generate_pdf(signal)

    return render_to_string('sigmax/voegZaakdocumentToe_Lk01.xml', context={
        'signal': signal,
        'sequence_number': seq_no,
        'DOC_UUID': str(uuid.uuid4()),
        'DATA': encoded_pdf.decode('utf-8'),
        'DOC_TYPE': 'PDF',
        'FILE_NAME': f'{signal.sia_id}.pdf'
    })


def _stuf_response_ok(response):
    """
    Checks that a response is a Bv03 message.
    """
    namespaces = {
        'soap': 'http://schemas.xmlsoap.org/soap/envelope/',
        'stuf': 'http://www.egem.nl/StUF/StUF0301',
    }

    try:
        tree = etree.fromstring(response.text)  # raises if not XML
    except etree.XMLSyntaxError:
        return False

    found = tree.xpath('//stuf:stuurgegevens/stuf:berichtcode', namespaces=namespaces)

    if len(found) != 1 or found[0].text != 'Bv03':
        return False
    return True


def _send_stuf_message(stuf_msg: str, soap_action: str):
    """
    Send a STUF message to the server that is configured.
    """
    if not settings.SIGMAX_AUTH_TOKEN or not settings.SIGMAX_SERVER:
        raise SigmaxException('SIGMAX_AUTH_TOKEN or SIGMAX_SERVER not configured.')

    # Prepare our request to Sigmax
    encoded = stuf_msg.encode('utf-8')

    headers = {
        'SOAPAction': soap_action,
        'Content-Type': 'text/xml; charset=UTF-8',
        'Authorization': 'Basic ' + settings.SIGMAX_AUTH_TOKEN,
        'Content-Length': b'%d' % len(encoded)
    }

    # Send our message to Sigmax. Network problems, and HTTP status codes
    # are all raised as errors.
    try:
        response = requests.post(
            url=settings.SIGMAX_SERVER,
            headers=headers,
            data=encoded,
            verify=False
        )
        response.raise_for_status()
    except requests.RequestException as e:
        raise SigmaxException from e

    return response


def send_creeerZaak_Lk01(signal, seq_no):
    soap_action = CREEER_ZAAK_SOAPACTION
    msg = _generate_creeerZaak_Lk01(signal, seq_no)   # can raise
    response = _send_stuf_message(msg, soap_action)

    logger.info('Sent %s', soap_action)
    logger.info('Received:\n%s', response.text)
    return response


def send_voegZaakdocumentToe_Lk01(signal, seq_no):
    # TODO: refactor message generation to support PDF and JPG
    #       arguments like: (signal, encoded_message, doctype)
    soap_action = VOEG_ZAAKDOCUMENT_TOE_SOAPACTION
    msg = _generate_voegZaakdocumentToe_Lk01(signal, seq_no)
    response = _send_stuf_message(msg, soap_action)

    logger.info('Sent %s', soap_action)
    logger.info('Received:\n%s', response.text)
    return response


def handle_send_signal(signal):
    """
    Send a Signal to CityControl/Sigmax and if successful follow send PDF.
    """
    # Generate sequence number, check that signal was not sent too often (if so fail).
    try:
        sequence_number = _generate_sequence_number(signal)
    except SigmaxException:
        msg = 'Verzending van melding naar THOR is mislukt (te vaak verzonden).'
        data = {'state': workflow.VERZENDEN_MISLUKT, 'text': msg}

        Signal.actions.update_status(data, signal)
        raise

    send_signal(signal, sequence_number)
    send_signal_pdf(signal, sequence_number)


def send_signal(signal, seq_no):
    """
    Create a case (zaak) in Sigmax/CityControl.
    """
    try:
        response = send_creeerZaak_Lk01(signal, seq_no)
    except SigmaxException:
        success = False
    else:
        success = response.status_code == 200 and _stuf_response_ok(response)

    if success:
        # Increment roundtrip count, to update sequence number for next time.
        CityControlRoundtrip.objects.create(_signal=signal)

        # Update Signal status on success.
        msg = f'Verzending van melding naar THOR is gelukt onder nummer {signal.sia_id}.{seq_no}.'
        data = {'state': workflow.VERZONDEN, 'text': msg}

        Signal.actions.update_status(data, signal=signal)
    else:
        # Update Signal status on failure.
        msg = 'Verzending van melding naar THOR is mislukt.'
        data = {'state': workflow.VERZENDEN_MISLUKT, 'text': msg}

        Signal.actions.update_status(data, signal=signal)

    return success


def send_signal_pdf(signal, seq_no):
    """
    Attach extra info in PDF to a case (zaak) in Sigmax/CityControl.
    """
    # Data to create a Note with on failure.
    data = {'text': 'Let op, PDF waarschijnlijk niet verzonden.'}

    try:
        response = send_voegZaakdocumentToe_Lk01(signal, seq_no)
    except SigmaxException:
        success = False
    except:
        # Catch all non-specific errors, add Note that there was a failure
        # and allow error to propagate (so it may be logged in Sentry).
        Signal.actions.create_note(data, signal=signal)
        raise
    else:
        success = response.status_code == 200 and _stuf_response_ok(response)

    if not success:
        Signal.actions.create_note(data, signal=signal)

    return success
