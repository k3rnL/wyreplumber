import ast
import inspect
from pathlib import Path

import wyreplumber
from wyreplumber import runtime


CONSUMER_API = {
    "MutationOutcome",
    "MutationStatus",
    "RuntimeContinuityError",
    "RuntimeEvent",
    "RuntimeEventKind",
    "RuntimeObjectKind",
    "RuntimeSnapshot",
    "capture_runtime_snapshot",
    "clear_default_node",
    "clear_runtime_metadata",
    "clear_stream_target",
    "create_managed_link",
    "drain_runtime_events",
    "next_runtime_event",
    "remove_managed_link",
    "require_event_continuity",
    "require_orchestration_contract",
    "select_device_profile",
    "select_device_route",
    "set_default_node",
    "set_node_audio_properties",
    "set_node_mute",
    "set_node_volume",
    "set_runtime_metadata",
    "set_runtime_parameter",
    "set_stream_target",
}

TYPED_FUNCTIONS = CONSUMER_API - {
    "MutationOutcome",
    "MutationStatus",
    "RuntimeContinuityError",
    "RuntimeEvent",
    "RuntimeEventKind",
    "RuntimeObjectKind",
    "RuntimeSnapshot",
}

NATIVE_RUNTIME_METHODS = {
    "capture_runtime_payload",
    "dispatch_runtime_mutation_payload",
    "drain_runtime_event_payloads",
    "next_runtime_event_payload",
    "reconnect",
    "stop",
}


def test_runtime_consumer_api_is_explicit_and_typed():
    assert CONSUMER_API <= set(runtime.__all__)
    assert len(runtime.__all__) == len(set(runtime.__all__))
    for name in CONSUMER_API:
        assert getattr(runtime, name) is not None
    for name in TYPED_FUNCTIONS:
        signature = inspect.signature(getattr(runtime, name))
        assert signature.return_annotation is not inspect.Signature.empty
        assert all(
            parameter.annotation is not inspect.Parameter.empty
            for parameter in signature.parameters.values()
        )


def test_installed_package_carries_pep561_marker_and_native_stub():
    package = Path(wyreplumber.__file__).parent
    assert package.joinpath("py.typed").is_file()
    stub = package.joinpath("_core.pyi")
    assert stub.is_file()

    module = ast.parse(stub.read_text())
    connection = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == "WPConnection"
    )
    methods = {
        node.name
        for node in connection.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert NATIVE_RUNTIME_METHODS <= methods


def test_consumer_example_compiles_without_starting_a_runtime():
    example = Path(__file__).parents[1] / "examples" / "runtime_orchestration.py"
    compile(example.read_text(), str(example), "exec")
