from setuptools import setup, Extension
import os
import subprocess


def select_wireplumber_package():
    requested = os.environ.get("WYREPLUMBER_WP_API", "0.5")
    if requested not in {"0.4", "0.5"}:
        raise RuntimeError("WYREPLUMBER_WP_API must be 0.4 or 0.5")

    candidate = f"wireplumber-{requested}"
    if subprocess.run(
        ["pkg-config", "--exists", candidate],
        check=False,
    ).returncode == 0:
        return candidate
    raise RuntimeError(
        f"required WirePlumber pkg-config package not found: {candidate}"
    )


wireplumber_package = select_wireplumber_package()
cflags = subprocess.check_output(
    ["pkg-config", "--cflags", "libpipewire-0.3", wireplumber_package],
    text=True,
).split()
libs = subprocess.check_output(
    ["pkg-config", "--libs", "libpipewire-0.3", wireplumber_package],
    text=True,
).split()
wireplumber_api = wireplumber_package.removeprefix("wireplumber-")

setup(
    ext_modules=[
        Extension(
            "wyreplumber._core",
            sources=[
                "native/wyreplumber.c",
                "native/wp_connection/wp_connection.c",
                "native/wp_connection/get_nodes.c",
                "native/wp_connection/get_modules.c",
                "native/wp_connection/get_metadata.c",
                "native/wp_connection/capture_runtime.c",
                "native/wp_connection/runtime_events.c",
                "native/wp_connection/lifecycle.c",
                "native/wp_connection/mutation_dispatch.c",
                "native/wp_connection/load_module.c",
                "native/wp_connection/sync.c",
                "native/wp_pipewire_object/wp_pipewire_object.c",
                "native/wp_node/wp_node.c",
                "native/wp_port/wp_port.c",
                "native/wp_module/wp_module.c",
                "native/wp_metadata/wp_metadata.c",
                "native/wp_metadata/metadata_set.c",
                "native/wp_metadata/metadata_clear.c",
                "native/wp_metadata/metadata_find.c",
                "native/wp_metadata/metadata_iterate.c",
            ],
            include_dirs=[
                "native",
                "native/wp_connection",
                "native/wp_pipewire_object",
                "native/wp_node",
                "native/wp_module",
                "native/wp_metadata",
            ],
            define_macros=[
                ("WYREPLUMBER_WP_API_FAMILY", f'"{wireplumber_api}"'),
                ("WYREPLUMBER_WP_API_0_5", "1" if wireplumber_api == "0.5" else "0"),
            ],
            extra_compile_args=cflags,
            extra_link_args=libs
        )
    ]
)
