import pytest
import tempfile
import os
import signal
import shutil
import subprocess
import time

from pathlib import Path


def _terminate_process(process):
    if process is None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=3)


@pytest.fixture(scope="session")
def pipewire_image():
    """
    Build the PipeWire Docker image once per session.
    This is cached so we don't rebuild for every test.
    """
    from testcontainers.core.image import DockerImage

    image = DockerImage(
        path=str(Path("tests/pipewire_container").absolute()),
        tag="pypewire-test"
    )
    image.build()
    yield image.tag


@pytest.fixture(scope="function")
def pipewire_socket(request):
    """
    Fixture that creates a fresh PipeWire container for each test.
    This ensures a clean state for every test.
    """
    if os.environ.get("WYREPLUMBER_SPAWN_PIPEWIRE") == "1":
        runtime_dir = tempfile.mkdtemp(prefix="wyreplumber-runtime-")
        config_dir = str(Path("tests/pipewire_container/config").absolute())
        process_env = os.environ.copy()
        process_env["XDG_RUNTIME_DIR"] = runtime_dir
        process_env["PIPEWIRE_CONFIG_DIR"] = config_dir
        process = subprocess.Popen(
            ["pipewire"],
            env=process_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        socket_path = Path(runtime_dir, "pipewire-0")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if socket_path.exists():
                break
            if process.poll() is not None:
                pytest.fail(
                    f"per-test PipeWire exited with status {process.returncode}"
                )
            time.sleep(0.05)
        else:
            pytest.fail("per-test PipeWire socket was not created within 5 seconds")

        original_runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        original_config_dir = os.environ.get("PIPEWIRE_CONFIG_DIR")
        os.environ["XDG_RUNTIME_DIR"] = runtime_dir
        os.environ["PIPEWIRE_CONFIG_DIR"] = config_dir
        try:
            yield runtime_dir
        finally:
            if original_runtime_dir is None:
                os.environ.pop("XDG_RUNTIME_DIR", None)
            else:
                os.environ["XDG_RUNTIME_DIR"] = original_runtime_dir
            if original_config_dir is None:
                os.environ.pop("PIPEWIRE_CONFIG_DIR", None)
            else:
                os.environ["PIPEWIRE_CONFIG_DIR"] = original_config_dir

            _terminate_process(process)
            shutil.rmtree(runtime_dir, ignore_errors=True)
        return

    if os.environ.get("WYREPLUMBER_IN_PROCESS_PIPEWIRE") == "1":
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        if not runtime_dir or not Path(runtime_dir, "pipewire-0").exists():
            pytest.fail("in-process PipeWire socket is not available")
        yield runtime_dir
        return

    from testcontainers.core.container import DockerContainer
    from testcontainers.core.wait_strategies import FileExistsWaitStrategy

    pipewire_image = request.getfixturevalue("pipewire_image")

    # Create temporary directory for PipeWire runtime
    runtime_dir = tempfile.mkdtemp(prefix="pipewire-runtime-")
    config_dir = str(Path('tests/pipewire_container/config').absolute())

    # Create a new container for this test
    container = DockerContainer(image=pipewire_image)

    # Set environment variables
    container.with_env("PIPEWIRE_DEBUG", "3")
    container.with_env("XDG_RUNTIME_DIR", "/pipewire-runtime")

    # Mount the runtime directory to expose PipeWire socket to host
    container.with_volume_mapping(runtime_dir, "/pipewire-runtime", mode="rw")

    # Start the container
    container.start()
    container.waiting_for(FileExistsWaitStrategy("/pipewire-runtime/pipewire-0"))

    # Set permissions to allow any user to access the socket
    container.exec("chmod 777 -R /pipewire-runtime")

    # Set environment variables for the duration of the test
    original_runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    original_config_dir = os.environ.get("PIPEWIRE_CONFIG_DIR")

    os.environ["XDG_RUNTIME_DIR"] = runtime_dir
    os.environ["PIPEWIRE_CONFIG_DIR"] = config_dir

    yield runtime_dir

    # Restore original environment
    if original_runtime_dir:
        os.environ["XDG_RUNTIME_DIR"] = original_runtime_dir
    else:
        os.environ.pop("XDG_RUNTIME_DIR", None)

    if original_config_dir:
        os.environ["PIPEWIRE_CONFIG_DIR"] = original_config_dir
    else:
        os.environ.pop("PIPEWIRE_CONFIG_DIR", None)

    # Cleanup: stop the container and remove temp directory
    try:
        container.stop()
    except Exception:
        pass  # Ignore errors during cleanup

    shutil.rmtree(runtime_dir, ignore_errors=True)
