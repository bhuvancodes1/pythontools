from app.validation import normalize_mac, prepare_devices


def payload(devices):
    return {
        "store": {"identifier": "JS", "number": "5354"},
        "global_config": {"license_services": {"switch": "SWITCH-SVC", "iap": "AP-SVC"}},
        "devices": devices,
    }


def test_mac_normalization():
    assert normalize_mac("187A3B442340") == "18:7a:3b:44:23:40"


def test_switch_stack_and_ap_names():
    devices, errors = prepare_devices(payload([
        {"input_name": "M1-ST1-1", "device_type": "switch", "mac": "187A3B442340", "serial": "S1"},
        {"input_name": "M1-ST1-2", "device_type": "switch", "mac": "187A3B442341", "serial": "S2"},
        {"input_name": "AP1", "device_type": "iap", "mac": "FC7FF1C4116E", "serial": "A1"},
    ]))
    assert not errors
    assert devices[0].generated_name == "JS5354-M1-ST1"
    assert devices[0].deployment_type == "stack"
    assert devices[0].stack_size == 2
    assert devices[2].generated_name == "JS5354-AP01"


def test_missing_stack_member_one_fails():
    _, errors = prepare_devices(payload([
        {"input_name": "M1-ST1-2", "device_type": "switch", "mac": "187A3B442340", "serial": "S2"}
    ]))
    assert any("member 1" in error for error in errors)
