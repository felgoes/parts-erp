from datetime import UTC, datetime
from types import SimpleNamespace

from app.api.routes.integrations_mercadolivre_full import _delta, _serialize_shipment


def test_two_partial_receptions_keep_received_totals_separate_from_later_sale():
    shipment = SimpleNamespace(
        id='local-1', inbound_id='INB-88', display_id='INB-88', status='processing',
        delivery_mode='vehicle', distribution_center='CD Cajamar',
        scheduled_at=None, expected_processing_at=None, physically_received_at=None,
        panel_url=None, notes=None, updated_at=datetime(2026, 11, 12, tzinfo=UTC),
        events=[],
        items=[SimpleNamespace(
            id='item-1', item_id='MLB1', variation_id='v1', inventory_id='INV1',
            sku='SKU-1', product_name='Sensor', declared_quantity=6,
            physical_count=None, discrepancy_note=None,
        )],
    )
    operations = [
        SimpleNamespace(inbound_id='INB-88', inventory_id='INV1',
            operation_type='INBOUND_RECEPTION', date_created=datetime(2026,11,10,tzinfo=UTC),
            detail={'available_quantity': 3, 'not_available_quantity': 0}),
        SimpleNamespace(inbound_id='INB-88', inventory_id='INV1',
            operation_type='INBOUND_RECEPTION', date_created=datetime(2026,11,11,tzinfo=UTC),
            detail={'available_quantity': 1, 'not_available_quantity': 1}),
        SimpleNamespace(inbound_id=None, inventory_id='INV1',
            operation_type='SALE', date_created=datetime(2026,11,12,tzinfo=UTC),
            detail={'available_quantity': -1}),
    ]

    result = _serialize_shipment(shipment, operations)

    assert result['api_reception'] is True
    assert result['items'][0]['confirmed_quantity'] == 5
    assert result['items'][0]['available_received'] == 4
    assert result['items'][0]['unavailable_received'] == 1
    assert result['status'] == 'processing'


def test_delta_distinguishes_unavailable_from_available():
    detail = {'available_quantity': {'delta': 2}, 'not_available_quantity': {'delta': 1}}
    assert _delta(detail, 'available') == 2
    assert _delta(detail, 'not_available') == 1


def test_api_discovered_shipment_keeps_declared_quantity_unknown_after_completion():
    completed = SimpleNamespace(
        id='evt-1', stage='completed', source='manual',
        operational_at=datetime(2026, 11, 12, tzinfo=UTC),
        recorded_at=datetime(2026, 11, 12, tzinfo=UTC), recorded_by_id='user-1',
        corrects_event_id=None, note=None,
    )
    shipment = SimpleNamespace(
        id='local-2', inbound_id='INB-99', display_id='INB-99', status='completed',
        delivery_mode=None, distribution_center=None, scheduled_at=None,
        expected_processing_at=None, physically_received_at=None, panel_url=None,
        notes=None, updated_at=datetime(2026, 11, 12, tzinfo=UTC), events=[completed],
        items=[SimpleNamespace(
            id='item-2', item_id='MLB2', variation_id=None, inventory_id='INV2',
            sku='SKU-2', product_name='Válvula', declared_quantity=None,
            physical_count=None, discrepancy_note=None,
        )],
    )
    operations = [SimpleNamespace(
        inbound_id='INB-99', inventory_id='INV2', operation_type='inbound_reception',
        date_created=None, detail={'available_quantity': 2},
    )]

    result = _serialize_shipment(shipment, operations)

    assert result['items'][0]['confirmed_quantity'] == 2
    assert result['items'][0]['declared_quantity'] is None
    assert result['items'][0]['completion_difference'] is None
    assert result['manual_stage_recorded'] is True
