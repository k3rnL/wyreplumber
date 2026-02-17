import pytest
import tempfile
import os

from pathlib import Path
from testcontainers.core.wait_strategies import FileExistsWaitStrategy
from testcontainers.core.container import DockerContainer
from testcontainers.core.image import DockerImage


@pytest.fixture(scope="session")
def pipewire_container():
    """
    Fixture that starts a Docker container with PipeWire running.
    The container exposes its PipeWire socket to the host.
    """
    # Create temporary directories for PipeWire runtime and config on the host
    runtime_dir = tempfile.mkdtemp(prefix="pipewire-runtime-")
    config_dir = str(Path('tests/pipewire_container/config').absolute())

    # Build the image
    image = DockerImage(path=str(Path("tests/pipewire_container").absolute()), tag="pypewire-test")
    image.build()

    # Build the container from the Dockerfile
    container = DockerContainer(image=image.tag)

    # Set environment variables
    container.with_env("PIPEWIRE_DEBUG", "3")
    container.with_env("XDG_RUNTIME_DIR", "/pipewire-runtime")

    # Mount the runtime directory to expose PipeWire socket to host
    container.with_volume_mapping(runtime_dir, "/pipewire-runtime", mode="rw")

    # Start the container
    container.start()
    container.waiting_for(FileExistsWaitStrategy("/pipewire-runtime/pipewire-0"))

    # Copy PipeWire configs from the container to make them available on the host
    # And set permissions to allow any user to access them
    container.exec("chmod 777 -R /pipewire-runtime")

    yield {"container": container, "runtime_dir": runtime_dir, "config_dir": config_dir}

    # Cleanup: stop the container and remove temp directories
    container.stop()
    import shutil
    shutil.rmtree(runtime_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def pipewire_socket(pipewire_container):
    """
    Fixture that provides the path to the PipeWire socket and sets up environment.
    Tests can run directly on the host using this socket.
    """
    runtime_dir = pipewire_container["runtime_dir"]
    config_dir = pipewire_container["config_dir"]

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
