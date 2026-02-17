#!/usr/bin/env python3
"""
Development helper script to start a PipeWire container for local development.
This script provides an interactive environment with a running PipeWire instance.
"""

import argparse
import tempfile
import shutil
import sys
import os
import time
from pathlib import Path
from testcontainers.core.wait_strategies import FileExistsWaitStrategy
from testcontainers.core.container import DockerContainer
from testcontainers.core.image import DockerImage


def parse_args():
    parser = argparse.ArgumentParser(description="Start a PipeWire development container")
    parser.add_argument(
        "-r",
        "--runtime-dir",
        help="Host directory to use as the PipeWire runtime mount. "
             "If omitted, a temporary directory is created."
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print("🔧 Starting PipeWire development container...")

    # Decide runtime directory
    runtime_dir_created = False
    if args.runtime_dir:
        runtime_dir = os.path.abspath(args.runtime_dir)
        os.makedirs(runtime_dir, exist_ok=True)
    else:
        runtime_dir = tempfile.mkdtemp(prefix="pipewire-runtime-")
        runtime_dir_created = True

    config_dir = str(Path("tests/pipewire_container/config").absolute())

    print(f"📁 Runtime directory: {runtime_dir}")

    # Build the image
    print("🐳 Building Docker image...")
    image = DockerImage(
        path=str(Path("tests/pipewire_container").absolute()),
        tag="pypewire-dev",
    )
    image.build()

    # Build the container
    container = DockerContainer(image=image.tag)

    # Environment variables
    container.with_env("PIPEWIRE_DEBUG", "3")
    container.with_env("XDG_RUNTIME_DIR", "/pipewire-runtime")

    # Volume mount
    container.with_volume_mapping(runtime_dir, "/pipewire-runtime", mode="rw")

    try:
        print("🚀 Starting container...")
        container.start()
        container.waiting_for(
            FileExistsWaitStrategy("/pipewire-runtime/pipewire-0")
        )

        # Fix permissions
        container.exec("chmod 777 -R /pipewire-runtime")

        print("\n✅ PipeWire container is running!")
        print("\n📋 Environment variables to use:")
        print(f"   export XDG_RUNTIME_DIR={runtime_dir}")
        print(f"   export PIPEWIRE_CONFIG_DIR={config_dir}")

        print("\n🔌 PipeWire socket available at:")
        print(f"   {runtime_dir}/pipewire-0")

        print("\n💡 You can now run your Python code with these environment variables set.")
        print("   Press Ctrl+C to stop the container and clean up.\n")

        # Set env vars for this process
        os.environ["XDG_RUNTIME_DIR"] = runtime_dir
        os.environ["PIPEWIRE_CONFIG_DIR"] = config_dir

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\n🛑 Stopping container...")
    finally:
        container.stop()
        if runtime_dir_created:
            shutil.rmtree(runtime_dir, ignore_errors=True)
            print("🧹 Removed temporary runtime directory")
        print("✨ Cleanup complete!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)