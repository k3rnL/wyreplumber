from setuptools import setup, Extension
import subprocess

# Detect PipeWire
cflags = subprocess.check_output(["pkg-config", "--cflags", "libpipewire-0.3", "wireplumber-0.4"], text=True).split()
libs = subprocess.check_output(["pkg-config", "--libs", "libpipewire-0.3", "wireplumber-0.4"], text=True).split()

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
            extra_compile_args=cflags,
            extra_link_args=libs
        )
    ]
)
