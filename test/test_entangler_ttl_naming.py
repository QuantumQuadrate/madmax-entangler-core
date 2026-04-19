from entangler.gateware.io_mapping import allocate_entangler_dio
from entangler.gateware.io_mapping import build_standalone_ttl_exports


def test_single_dio_exports_follow_physical_ttl_numbers():
    exports = build_standalone_ttl_exports(
        ports=[3],
        num_inputs=4,
        num_outputs=4,
        edge_counters_enabled=True,
    )

    assert [export.device_name for export in exports] == [
        "ttl4",
        "ttl5",
        "ttl6",
        "ttl7",
        "ttl0",
        "ttl0_counter",
        "ttl1",
        "ttl1_counter",
        "ttl2",
        "ttl2_counter",
        "ttl3",
        "ttl3_counter",
    ]
    assert [export.rtio_channel for export in exports] == list(range(12))
    assert [export.physical_channel.pad_label for export in exports[:4]] == [
        "dio3[4]",
        "dio3[5]",
        "dio3[6]",
        "dio3[7]",
    ]


def test_multiple_ports_number_ttls_by_port_order():
    allocation = allocate_entangler_dio(
        ports=[5, 2],
        num_inputs=5,
        num_outputs=6,
    )

    assert [channel.exported_name for channel in allocation.inputs] == [
        "ttl0",
        "ttl1",
        "ttl2",
        "ttl3",
        "ttl8",
    ]
    assert [channel.exported_name for channel in allocation.outputs] == [
        "ttl4",
        "ttl5",
        "ttl6",
        "ttl7",
        "ttl12",
        "ttl13",
    ]
