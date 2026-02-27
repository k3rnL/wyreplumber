import pytest
import tempfile
import os
import shutil

from pathlib import Path
from testcontainers.core.wait_strategies import FileExistsWaitStrategy
from testcontainers.core.container import DockerContainer
from testcontainers.core.image import DockerImage


@pytest.fixture(scope="session")
def pipewire_image():
    """
    Build the PipeWire Docker image once per session.
    This is cached so we don't rebuild for every test.
    """
    image = DockerImage(
        path=str(Path("tests/pipewire_container").absolute()),
        tag="pypewire-test"
    )
    image.build()
    yield image.tag


@pytest.fixture(scope="function")
def pipewire_socket(pipewire_image):
    """
    Fixture that creates a fresh PipeWire container for each test.
    This ensures a clean state for every test.
    """
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
